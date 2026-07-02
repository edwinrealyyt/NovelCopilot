# PowerShell 一键部署脚本 (install.ps1)
# 适用于无 Docker 的 Windows 环境下快速部署 AI Novel Creation Copilot

# 确保脚本在其所在目录运行
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ($null -eq $scriptDir -or $scriptDir -eq "") {
    $scriptDir = Get-Location
}
Set-Location $scriptDir

# 设置控制台输出编码为 UTF8，避免中文乱码
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Clear-Host

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "      AI Novel Creation Copilot 一键部署向导 (Windows)     " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  * 适用环境：无 Docker / 纯 Windows 环境" -ForegroundColor Gray
Write-Host "  * 部署内容：项目源码下载 + Python环境配置 + 依赖安装 + 桌面启动" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host

# --- 步骤 1: 项目源码获取与校验 ---
$hasSource = (Test-Path "backend\requirements.txt") -and (Test-Path "frontend\index.html")
$targetDir = $scriptDir

if (-not $hasSource) {
    Write-Host "[*] 未在当前目录下检测到 NovelCopilot 源码，开始执行在线下载..." -ForegroundColor Cyan
    
    $tempZip = Join-Path $env:TEMP "NovelCopilot-master.zip"
    $extractTemp = Join-Path $env:TEMP "NovelCopilot-Extract"
    
    # 确保提取临时目录为空
    if (Test-Path $extractTemp) {
        Remove-Item $extractTemp -Recurse -Force
    }
    New-Item -ItemType Directory -Path $extractTemp | Out-Null
    
    # 备用下载通道 (主站 + 加速代理镜像)
    $zipUrls = @(
        "https://github.com/edwinrealyyt/NovelCopilot/archive/refs/heads/master.zip",
        "https://ghp.ci/https://github.com/edwinrealyyt/NovelCopilot/archive/refs/heads/master.zip"
    )
    
    $downloadSuccess = $false
    foreach ($url in $zipUrls) {
        Write-Host "[*] 正在尝试下载源码包: $url" -ForegroundColor Cyan
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $url -OutFile $tempZip -TimeoutSec 60 -ErrorAction Stop
            $downloadSuccess = $true
            Write-Host "[+] 下载成功！" -ForegroundColor Green
            break
        } catch {
            Write-Host "[!] 下载失败，尝试下一个通道..." -ForegroundColor Yellow
        }
    }
    
    if (-not $downloadSuccess) {
        Write-Host "[-] 下载源码包失败，请检查网络连接是否通畅。" -ForegroundColor Red
        Read-Host "按回车键退出..."
        exit
    }
    
    Write-Host "[*] 正在解压源码..." -ForegroundColor Cyan
    try {
        Expand-Archive -Path $tempZip -DestinationPath $extractTemp -Force
    } catch {
        Write-Host "[-] 解压源码失败。" -ForegroundColor Red
        Read-Host "按回车键退出..."
        exit
    }
    
    # 清理 zip 压缩包
    Remove-Item $tempZip -Force -ErrorAction SilentlyContinue
    
    # 从解压出的 NovelCopilot-master 移动文件至目标目录
    $extractedFolder = Join-Path $extractTemp "NovelCopilot-master"
    if (Test-Path $extractedFolder) {
        $targetDir = Join-Path $scriptDir "NovelCopilot"
        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir | Out-Null
        }
        
        Write-Host "[*] 正在部署文件到目标目录: $targetDir" -ForegroundColor Cyan
        Get-ChildItem -Path $extractedFolder | ForEach-Object {
            $dest = Join-Path $targetDir $_.Name
            if (Test-Path $dest) {
                Remove-Item $dest -Recurse -Force
            }
            Move-Item $_.FullName $targetDir -Force
        }
        
        # 清理临时提取目录
        Remove-Item $extractTemp -Recurse -Force
    } else {
        Write-Host "[-] 未找到解压后的项目目录 NovelCopilot-master。" -ForegroundColor Red
        Read-Host "按回车键退出..."
        exit
    }
    
    # 切换工作目录到目标安装目录
    Set-Location $targetDir
    $scriptDir = $targetDir
} else {
    Write-Host "[+] 检测到当前目录下已存在项目源码，跳过下载步骤。" -ForegroundColor Green
}

# --- 步骤 2: Python 环境变量或常用路径检查 ---
function Get-PythonPath {
    # 尝试从系统变量寻找 python
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd) {
        # 确认版本是否为 3.x
        $versionStr = & python --version 2>&1
        if ($versionStr -match "Python 3\.") {
            return "python"
        }
    }
    
    # 尝试扫描用户/系统常见安装路径
    $possiblePaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python39\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python38\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python37\python.exe",
        "C:\Python312\python.exe",
        "C:\Python311\python.exe",
        "C:\Python310\python.exe",
        "C:\Python39\python.exe",
        "C:\Python38\python.exe",
        "C:\Python37\python.exe"
    )
    
    foreach ($path in $possiblePaths) {
        if (Test-Path $path) {
            $versionStr = & $path --version 2>&1
            if ($versionStr -match "Python 3\.") {
                return $path
            }
        }
    }
    return $null
}

# --- 步骤 3: 自动下载并安装 Python (如果未发现) ---
function Install-Python {
    Write-Host "[!] 未检测到可用的 Python 3。开始自动安装 Python 3..." -ForegroundColor Yellow
    
    # 优先使用 winget 安装
    $wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
    if ($wingetCmd) {
        Write-Host "[*] 发现系统支持 winget，正在下载安装 Python 3.10..." -ForegroundColor Cyan
        try {
            Start-Process winget -ArgumentList "install -e --id Python.Python.3.10 --silent --accept-package-agreements --accept-source-agreements" -NoNewWindow -Wait
            # 重新加载环境变量
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
            $pyPath = Get-PythonPath
            if ($pyPath) {
                Write-Host "[+] 通过 winget 安装 Python 成功！" -ForegroundColor Green
                return $pyPath
            }
        } catch {
            Write-Host "[!] winget 安装过程遇到问题，准备切换到备用下载方式..." -ForegroundColor Yellow
        }
    }
    
    # 备用方案：下载官方 Installer 进行静默安装
    $pythonUrl = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe"
    $installerPath = Join-Path $env:TEMP "python-3.10.11-installer.exe"
    
    Write-Host "[*] 正在从 python.org 官方下载 Python 3.10.11 安装包..." -ForegroundColor Cyan
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $pythonUrl -OutFile $installerPath -ErrorAction Stop
    } catch {
        Write-Host "[-] 下载 Python 安装包失败，请检查网络连接。" -ForegroundColor Red
        Write-Error $_
        return $null
    }
    
    Write-Host "[*] 下载完成，正在进行静默安装 (建议在弹出的 UAC 提示中选择“是”)..." -ForegroundColor Cyan
    $arguments = "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_doc=0"
    $process = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru
    
    # 清理安装包
    Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
    
    # 刷新环境变量
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    
    $pyPath = Get-PythonPath
    if ($pyPath) {
        Write-Host "[+] Python 安装并配置成功！" -ForegroundColor Green
        return $pyPath
    } else {
        Write-Host "[-] 自动安装失败。请手动访问 https://www.python.org/downloads/ 下载并安装 Python 3.7+ (并勾选 'Add Python to PATH')。" -ForegroundColor Red
        return $null
    }
}

# --- 执行安装与配置流程 ---

# 确认 Python
$pythonExec = Get-PythonPath
if ($null -eq $pythonExec) {
    $pythonExec = Install-Python
    if ($null -eq $pythonExec) {
        Write-Host "[-] 部署被终止，无法继续。请手动安装 Python 之后再试。" -ForegroundColor Red
        Read-Host "按回车键退出..."
        exit
    }
} else {
    Write-Host "[+] 检测到可用 Python 环境: $pythonExec" -ForegroundColor Green
}

# --- 步骤 4: 创建虚拟环境 (venv) ---
Write-Host "`n[*] 正在配置 Python 虚拟环境 (venv)..." -ForegroundColor Cyan
$venvDir = Join-Path $scriptDir "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (Test-Path $venvDir) {
    Write-Host "[+] 虚拟环境目录已存在，跳过新建阶段。" -ForegroundColor Green
} else {
    try {
        Write-Host "[*] 正在创建虚拟环境，请稍候..." -ForegroundColor Cyan
        & $pythonExec -m venv venv
        if (-not (Test-Path $venvPython)) {
             throw "未能在指定目录找到 venv/Scripts/python.exe，虚拟环境可能创建失败"
        }
        Write-Host "[+] 虚拟环境创建成功！位置: $venvDir" -ForegroundColor Green
    } catch {
        Write-Host "[-] 创建虚拟环境失败。将尝试直接使用系统/用户全局 Python 环境。" -ForegroundColor Yellow
        $venvPython = $pythonExec
    }
}

# --- 步骤 5: 安装依赖模块 ---
Write-Host "`n[*] 正在安装项目依赖库..." -ForegroundColor Cyan
$reqFile = Join-Path $scriptDir "backend\requirements.txt"
if (-not (Test-Path $reqFile)) {
    Write-Host "[-] 未找到 backend/requirements.txt 依赖文件，脚本执行目录错误。" -ForegroundColor Red
    Read-Host "按回车键退出..."
    exit
}

# 使用阿里云国内镜像源加速
$mirrorUrl = "https://mirrors.aliyun.com/pypi/simple/"
Write-Host "[*] 正在升级 pip 并安装依赖..." -ForegroundColor Cyan

# 尝试使用镜像源安装
$pipSuccess = $false
try {
    # 升级 pip
    & $venvPython -m pip install --upgrade pip -i $mirrorUrl --timeout 15
    # 安装依赖
    & $venvPython -m pip install -r $reqFile -i $mirrorUrl --timeout 30
    $pipSuccess = $true
} catch {
    Write-Host "[!] 镜像源连接超时或失败，正在尝试使用 PyPI 官方默认源..." -ForegroundColor Yellow
}

if (-not $pipSuccess) {
    try {
        & $venvPython -m pip install --upgrade pip
        & $venvPython -m pip install -r $reqFile
        $pipSuccess = $true
    } catch {
        Write-Host "[-] 依赖安装失败，请检查您的网络连接或手动运行 pip install 命令。" -ForegroundColor Red
        Read-Host "按回车键退出..."
        exit
    }
}

Write-Host "[+] 项目依赖库安装成功！" -ForegroundColor Green

# --- 步骤 6: 校验启动服务可用性 ---
Write-Host "`n[*] 正在校验依赖项可用性..." -ForegroundColor Cyan
$checkUvicorn = & $venvPython -c "import fastapi, uvicorn, pydantic, requests; print('OK')" 2>&1
if ($checkUvicorn -eq "OK") {
    Write-Host "[+] 依赖包完整性校验成功！" -ForegroundColor Green
} else {
    Write-Host "[!] 校验失败，某些包可能未正确加载: $checkUvicorn" -ForegroundColor Yellow
}

# --- 步骤 7: 生成一键启动脚本 (run.ps1) ---
Write-Host "`n[*] 正在生成 Windows 启动脚本 run.ps1 ..." -ForegroundColor Cyan
$runScriptContent = @"
# PowerShell 启动脚本
`$scriptDir = Split-Path -Parent `$MyInvocation.MyCommand.Path
if (`$null -eq `$scriptDir -or `$scriptDir -eq "") {
    `$scriptDir = Get-Location
}
Set-Location `$scriptDir

`[Console]::OutputEncoding = `[System.Text.Encoding]::UTF8

Clear-Host
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "          AI Novel Creation Copilot 正在启动...           " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  * 运行模式：本地直接部署 (非容器化)" -ForegroundColor Gray
Write-Host "  * 本地服务地址：http://localhost:8000" -ForegroundColor Cyan
Write-Host "  * 提示：如果要停止服务，请直接关闭此窗口或按 Ctrl + C。" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Green
Write-Host

& "venv\Scripts\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"@

$runScriptPath = Join-Path $scriptDir "run.ps1"
try {
    [System.IO.File]::WriteAllText($runScriptPath, $runScriptContent, [System.Text.Encoding]::UTF8)
    Write-Host "[+] 启动脚本生成成功: $runScriptPath" -ForegroundColor Green
} catch {
    Write-Host "[-] 写入 run.ps1 脚本失败。" -ForegroundColor Red
}

# --- 步骤 8: 创建桌面快捷方式 (NovelCopilot.lnk) ---
Write-Host "`n[*] 正在创建桌面快捷方式..." -ForegroundColor Cyan
try {
    $WshShell = New-Object -ComObject WScript.Shell
    $shortcutPath = Join-Path [System.Environment]::GetFolderPath("Desktop") "NovelCopilot.lnk"
    $Shortcut = $WshShell.CreateShortcut($shortcutPath)
    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runScriptPath`""
    $Shortcut.WorkingDirectory = $scriptDir
    $Shortcut.IconLocation = "imageres.dll,203" # 书本/文档风格图标
    $Shortcut.Description = "启动 AI Novel Creation Copilot"
    $Shortcut.Save()
    Write-Host "[+] 桌面快捷方式创建成功！" -ForegroundColor Green
} catch {
    Write-Host "[!] 创建桌面快捷方式失败，不影响系统运行。您可以直接双击 $runScriptPath 启动项目。" -ForegroundColor Yellow
}

# 部署完成总结
Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "                 🎉 一键部署配置已全部完成！" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host " 1. 软件已成功安装在: $scriptDir"
Write-Host " 2. 您可以双击桌面的 [NovelCopilot] 快捷方式直接启动服务。"
Write-Host " 3. 或者在安装目录下执行以下 PowerShell 命令启动："
Write-Host "    .\run.ps1" -ForegroundColor Cyan
Write-Host " 4. 系统启动后，打开浏览器访问以下地址即可体验系统："
Write-Host "    http://localhost:8000" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host

Read-Host "部署结束，请按回车键退出本向导..."
