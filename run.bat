@echo off
title AI Novel Creation Copilot - Startup Service

echo ========================================================
echo   AI Novel Creation Copilot (Startup Process)
echo ========================================================
echo.

:: Check Python environment
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found on your system. Please install Python 3.7+.
    pause
    exit /b
)

:: Try creating virtual environment
echo [STATUS] Setting up python virtual environment...
python -m venv venv >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Failed to create virtual environment. Falling back to global Python.
    set USE_VENV=0
) else (
    echo [STATUS] Virtual environment created successfully.
    set USE_VENV=1
)

:: Activate virtual environment if exists
if "%USE_VENV%"=="1" (
    if exist "venv\Scripts\activate.bat" (
        echo [STATUS] Activating virtual environment...
        call venv\Scripts\activate.bat
    )
)

:: Install requirements
echo [STATUS] Installing required dependencies...
if "%USE_VENV%"=="1" (
    :: In venv, install WITHOUT --user so packages are saved inside venv folder
    python -m pip install -r backend/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
) else (
    :: In global fallback, install WITH --user for permission safety
    python -m pip install -r backend/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --user
)

:: Verify uvicorn availability
python -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] uvicorn not found in current environment. Trying global fallback with --user installation...
    if exist "venv\Scripts\activate.bat" (
        :: Deactivate venv to fall back to global environment
        call deactivate >nul 2>&1
    )
    python -m pip install -r backend/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --user
)

echo.
echo ========================================================
echo   [SUCCESS] Service is starting up!
echo   - Open your browser and visit: http://localhost:8000
echo   - Press Ctrl + C in this window to stop the server.
echo ========================================================
echo.

:: Start FastAPI backend
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

pause
