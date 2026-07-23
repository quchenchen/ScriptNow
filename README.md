# ScriptFlow

**AI Agent 团队驱动的剧本与小说创作平台。**

V7 作为全新产品开发：复用经过契约验证的旧技术资产，不继承旧产品领域模型。Script 与 Novel 使用独立的创作领域能力，共享平台基础设施。

## 状态

🚧 **V7 P0 启动中**。当前唯一规格基线：

- [`docs/v7-spec-v1.1/00-README.md`](./docs/v7-spec-v1.1/00-README.md) — 基线与已批准决策
- [`docs/v7-spec-v1.1/01-PRD-V7.md`](./docs/v7-spec-v1.1/01-PRD-V7.md) — 产品与技术规格
- [`docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md`](./docs/v7-spec-v1.1/02-LEGACY-DECONTAMINATION.md) — 复用、归档与删除规则
- [`docs/v7-spec-v1.1/03-DEVELOPMENT-PLAN.md`](./docs/v7-spec-v1.1/03-DEVELOPMENT-PLAN.md) — 直到完整测试 Release Candidate 的开发计划
- [`.scratch/scriptflow-v7/`](./.scratch/scriptflow-v7/) — V7 issue tracker

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
- [`docs/v7-spec-v1.1/`](./docs/v7-spec-v1.1/) — V7 唯一开发基线

### 按需读

- [`backend/README.md`](./backend/README.md) — 后端启动 & 目录
- [`scriptflow-v6/docs/v7-spec-v1.0/`](./scriptflow-v6/docs/v7-spec-v1.0/) — 冻结原型与上一规格版本
- [`CONTEXT.md`](./CONTEXT.md)、[`docs/PRD-V5.md`](./docs/PRD-V5.md)、[`docs/adr/`](./docs/adr/) — V5 历史材料，不是 V7 依据
- [`docs/archive/`](./docs/archive/) — 更早历史文档

## 技术栈

- **Backend**: FastAPI + AgentScope 2.0 + SQLite (aiosqlite) + Alembic
- **Frontend**: Vue 3 + Vite + TypeScript
- **LLM**: DashScope（阿里云百炼）/ DeepSeek / OpenAI / Anthropic 可切换

## 常用命令

见 [`Makefile`](./Makefile) 或分别看 [`backend/README.md`](./backend/README.md) / [`frontend/`](./frontend/) 说明。

## 授权

Proprietary. All rights reserved.
