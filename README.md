# ScriptFlow

**让好剧本"长出来"的 AI Agent 团队协作平台。**

用户输入创意种子，Agent 团队接力灌溉，用户是总指挥兼审美裁判。产出的是一棵有血缘、有骨架、能进化的**剧本树**，不是一坨拼凑的文档。

## 状态

🚧 **V5 重构中**。V1-V4 的历史文档在 [`docs/archive/`](./docs/archive/)。当前主线：

- [`CONTEXT.md`](./CONTEXT.md) — 领域语言（**读代码前先读**）
- [`docs/PRD-V5.md`](./docs/PRD-V5.md) — 产品需求
- [`docs/adr/`](./docs/adr/) — 架构决策
- [`.scratch/scriptflow-v5/`](./.scratch/scriptflow-v5/) — 当前 issue tracker

## 5 分钟启动（开发环境）

```bash
# 后端
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # 编辑填 API keys
uvicorn app.main:app --reload --port 8000

# 前端（另一 terminal）
cd frontend
npm install
npm run dev

# 打开 http://localhost:5173
```

或者：

```bash
make dev    # 一条命令起前后端（前提：backend 已 pip install）
```

## 项目文档

### 一定要读

- [`AGENTS.md`](./AGENTS.md) — Agent 协作约定 + 代码约定
- [`CONTEXT.md`](./CONTEXT.md) — 领域词汇表 + 核心隐喻

### 按需读

- [`backend/README.md`](./backend/README.md) — 后端启动 & 目录
- [`docs/PRD-V5.md`](./docs/PRD-V5.md) — 完整产品需求（55 条 user story）
- [`docs/adr/`](./docs/adr/) — 架构决策
- [`docs/archive/`](./docs/archive/) — V1-V4 历史文档（参考用，不再是主线）

## 技术栈

- **Backend**: FastAPI + AgentScope 2.0 + SQLite (aiosqlite) + Alembic
- **Frontend**: Vue 3 + Vite + TypeScript
- **LLM**: DashScope（阿里云百炼）/ DeepSeek / OpenAI / Anthropic 可切换

## 常用命令

见 [`Makefile`](./Makefile) 或分别看 [`backend/README.md`](./backend/README.md) / [`frontend/`](./frontend/) 说明。

## 授权

Proprietary. All rights reserved.
