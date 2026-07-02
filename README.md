# AI Novel Creation Copilot 🛸

AI Novel Creation Copilot 是一款专业的 AI 小说全生命周期创作辅助智能体系统。系统基于 **前后端分离 + 离线轻量持久化 + Agent 编排管线** 的三层架构，提供高保真的人机协作（Human-in-the-loop）小说撰写、设定管理、Token 计费估算及去 AI 套路化润色功能。

---

## 🏗️ 整体系统架构图

```
                       ┌─────────────────────────┐
                       │   前端展示层 (HTML/JS)  │
                       │   (Tiptap风格富文本/树形) │
                       └────────────┬────────────┘
                                    │
                                    ▼ (异步 REST API)
                       ┌─────────────────────────┐
                       │   后端业务层 (FastAPI)  │
                       │   (状态机控制与数据映射)  │
                       └────────────┬────────────┘
                                    │
                                    ▼ (编排引擎管线)
                 ┌──────────────────────────────────────┐
                 │    AI 编排与网关层 (AIService)        │
                 │   - Token 预估与 Cost 跟踪计费       │
                 │   - 冲突检测 / 防 OOC 人设规则       │
                 │   - drafting -> de-ai 多轮管道       │
                 └──────────┬─────────────────┬─────────┘
                            │                 │
                            ▼ (真实 API 接口)  ▼ (无密 Sandbox 模拟)
                     ┌─────────────┐   ┌─────────────┐
                     │ Gemini/DS   │   │  本地 Mock  │
                     │ 底座 API    │   │  生成引擎   │
                     └─────────────┘   └─────────────┘
```

---

## 🛠️ 技术实现路径与特性

1. **中断确认状态机 (Workflow B)**: 
   - 章节在初始生成时，状态标识为 `pending`。
   - 系统展示前置章节标题和大纲详细梗概，**暂停执行，等待作家确认与编辑**。
   - 点击“确认梗概”后，触发后端大模型生成正文，章节状态跃迁为 `completed`，并提供大纲回退 `revert` 机制。

2. **多模型适配与计费跟踪 (Workflow C)**:
   - 适配了 **Gemini 1.5 Pro**, **Gemini 3.5 Flash**, **Claude 3.5 Sonnet**, **DeepSeek-Coder** 路由。
   - 在请求模型前，自动进行 Context 的 Token 预估并按照多模型费率表显示本次操作的预估成本。

3. **双轮 Agent 降重与消除 AI 痕迹**:
   - **第一轮 (Drafting)**: 根据当前大纲与主角金手指背景设定，大模型生成小说首稿。
   - **第二轮 (De-AI Polish)**: 后端进行高频 AI 词汇过滤替换，并执行白描拟人类风格 Prompt 覆写，并在右侧高亮展示 Diff 修改前后的对比。

4. **防 OOC 设定一致性校验**:
   - 后端对章节正文实施自动人设与物理规则检验（如女主白雀是“冷面独行黑客”，当章节出现“大哭崩溃”等动作时，自动出具 OOC 风险警告并指导修改）。

---

## 📦 项目结构目录

```
NovelCopilot/
├── backend/
│   ├── main.py         # FastAPI 业务控制器与接口路由
│   ├── models.py       # Pydantic 实体与接口请求体定义
│   ├── database.py     # flat-file 极简持久化层驱动 (data.json)
│   ├── ai_service.py   # Token计数、计费表、多模型调度与De-AI润色核心
│   └── requirements.txt# 依赖模块声明
├── frontend/
│   └── index.html      # 磨砂暗黑极光玻璃风前端主界面
├── Dockerfile          # 容器构建文件
├── docker-compose.yml  # 容器一键编排描述
├── run.bat             # Windows 本地一键启动脚本
├── data.json           # 本地持久化数据库文件
└── README.md           # 项目架构自述说明书
```

---

## 🚀 启动与部署指南

### 1. 本地极速启动 (Windows 环境)
直接双击运行目录下的 [run.bat](file:///C:/Users/Administrator/NovelCopilot/run.bat)。
- 脚本会自动为您创建隔离虚拟环境 `venv`。
- 安装必要的轻量级第三方依赖，并启动 FastAPI 服务。
- 启动成功后，浏览器访问 `http://localhost:8000` 即可完全访问本系统。

### 2. 容器化一键部署 (CentOS / Arch Linux 生产环境)
使用 Docker Compose 进行一键构建并拉起多模型 API 编排服务：
```bash
# 1. 确保克隆/放置项目目录后，进入项目根目录
cd NovelCopilot

# 2. 一键构建并启动容器 (后台运行)
docker-compose up -d --build

# 3. 访问端口
# 系统将会在宿主机的 8000 端口提供服务，直接访问 http://<SERVER_IP>:8000
```
*(注：所有的修改和生成结果都会实时映射到宿主机的 `data.json` 中，确保即使容器删除重建，小说资产和创作进度依然完好无损。)*

### 3. 本地无后台 Sandbox 沙盒运行 (降级方案)
如果您当前处于完全离线环境，甚至未安装任何 Python 运行库：
- 可直接在浏览器中双击 [frontend/index.html](file:///C:/Users/Administrator/NovelCopilot/frontend/index.html)。
- 系统在检测到后端 API 不可达后，会自动降级为 **LocalStorage 本地浏览器存储 Sandbox 模式**。
- 您依旧可以在前台直接体验大纲管理、梗概编辑以及基于本地高保真模拟器的“模拟 AI 章节生成”。
