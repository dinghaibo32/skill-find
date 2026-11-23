# skill-find

FastAPI（后端）+ Vue 3 + TypeScript + Vite（前端）的全栈项目骨架，已预留大模型（LLM）调用层。

## 目录结构

```
skill-find/
├── dev.py                  # 一键启动前后端的开发脚本
├── backend/                # Python 后端（FastAPI）
│   ├── .venv/              # 后端虚拟环境（不入库）
│   ├── pyproject.toml      # 依赖与打包配置（含 dev  extras）
│   ├── .env.example        # 环境变量模板（LLM 配置）
│   ├── app/
│   │   ├── main.py         # 应用入口：create_app 工厂、CORS、路由注册
│   │   ├── core/           # 核心配置（pydantic-settings）
│   │   ├── api/            # HTTP 接口层
│   │   │   ├── router.py   # 路由聚合（/ 与 /api 前缀）
│   │   │   └── routes/     # 按功能拆分的路由（health.py ...）
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   └── services/       # 业务服务层
│   │       └── llm/        # LLM 抽象层（Protocol + OpenAI 兼容实现）
│   └── tests/              # pytest 测试
└── frontend/               # 前端（Vue 3 + TypeScript + Vite）
    ├── vite.config.ts      # dev 代理：/health、/api → 后端 8000
    └── src/
        ├── api/            # 接口访问层（组件不直接 fetch）
        ├── types/          # 与后端 schema 对应的 TS 类型
        ├── components/     # 组件（HealthStatus.vue ...）
        ├── App.vue
        └── main.ts
```

分层原则：路由层（api）只做参数与响应，业务逻辑放 services，数据结构放 schemas；
前端组件只消费 api 层与 types，不直接发请求。

## 环境要求

- Python >= 3.12（后端虚拟环境 `backend/.venv` 使用 3.13）
- Node.js >= 20（含 npm）

## 安装

在项目根目录执行（Windows PowerShell）：

```powershell
# 1. 后端依赖（虚拟环境位于 backend/.venv，如无需先创建：python -m venv backend\.venv）
.\backend\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"

# 2. 前端依赖
npm install --prefix frontend

# 3. （可选，接大模型时）配置环境变量
Copy-Item backend\.env.example backend\.env
# 编辑 backend\.env，填入 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
```

Linux / macOS：

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install -e "./backend[dev]"
npm install --prefix frontend
cp backend/.env.example backend/.env
```

## 启动

一条命令同时启动前后端（根目录执行）：

```powershell
python dev.py
```

- 后端：http://127.0.0.1:8000 （接口文档 http://127.0.0.1:8000/docs）
- 前端：http://localhost:5173 （打开页面点击 "Check backend health" 即可调通 /health）
- `Ctrl+C` 同时停止两者

也可以分开启动：

```powershell
# 后端（在 backend 目录，使用 backend/.venv）
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# 前端（在 frontend 目录）
npm run dev
```

## 测试

```powershell
# 后端单元/接口测试
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -v

# 手动验证健康检查接口
curl http://127.0.0.1:8000/health
# 期望返回：{"status":"ok","service":"skill-find","version":"0.1.0"}

# 前端类型检查 + 生产构建
npm run build --prefix frontend
```

## 大模型调用（预留）

后续接入大模型时不需要改动路由层结构：

1. 在 `backend/.env` 配置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`（支持任意 OpenAI 兼容服务：OpenAI、DeepSeek、通义、Ollama 等）。
2. 在 service 中通过 `from app.services.llm import get_llm_client, ChatMessage` 获取客户端，调用 `await client.chat([...])`。
3. 如需更换供应商协议，实现 `LLMClient` Protocol 并在工厂 `get_llm_client()` 中替换即可。

## 工程规则（后续开发必须遵守）

### 语言规则

- **代码、注释、标识符、状态名、事件名、接口名必须用英文。**
  包括：变量/函数/类名、Git 分支名、API 路径与字段、前端状态（如 `idle` / `loading` / `success` / `error`）、事件名、日志文案、代码内注释与 docstring。
- **设计文档、README.md 和「提交（commit message）」一节可以用中文或英文。**

### 目录与分层规则

- 后端代码一律放 `backend/`，前端代码一律放 `frontend/`，不混放。
- 后端遵循 Python 项目规范：`pyproject.toml` 管理依赖；按 `api / schemas / services / core` 分层，新功能按路由 → schema → service 的顺序落位；测试放 `backend/tests/`。
- 前端遵循组件化思想：`api/` 统一封装请求，`types/` 定义接口类型，`components/` 放组件；组件不直接调用 `fetch`。
- 配置走环境变量 / `.env`（模板为 `.env.example`），密钥不入库、不硬编码。
- 新增后端业务接口挂到 `/api` 前缀下（`app/api/router.py` 的 `api_router`）；`/health` 保持根路径供探活。

### 启动命令

```powershell
python dev.py
```