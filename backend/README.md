# ScriptFlow · Backend

FastAPI + AgentScope 2.0 + SQLite。

## 5 分钟启动

```bash
# 1. 建虚拟环境
python3.11 -m venv .venv
source .venv/bin/activate

# 2. 装依赖（含 dev）
pip install -e ".[dev]"

# 3. 配 secrets
cp .env.example .env
# 编辑 .env 至少填一个 LLM provider 的 API key

# 4. 建库 & 迁移
# (issue #02 之前) 数据库会在启动时自动建
# (issue #02 之后) alembic upgrade head

# 5. 起服务
export $(cat .env | xargs)     # 加载 env
uvicorn app.main:app --reload --port 8000
```

打开 http://localhost:8000/docs 看 API。

## 目录

```
backend/
├── app/
│   ├── api/          FastAPI routers
│   ├── core/         领域核心（LLM 网关、agent 编排、config、context 引擎）
│   ├── agents/       Agent 定义（issue #03 之后收敛到 team.py）
│   ├── skills/       Agent 领域 prompt 模板（.md）
│   ├── models*       ORM 模型（issue #02 之后收敛到 models/ 包）
│   └── main.py       FastAPI app
├── tests/            pytest 单元 + 集成测试
├── data/             SQLite 数据（gitignored）
├── pyproject.toml
├── .env.example
└── README.md
```

## 常用命令

| 目的 | 命令 |
|---|---|
| 装依赖（首次） | `pip install -e ".[dev]"` |
| 起开发服务 | `uvicorn app.main:app --reload --port 8000` |
| 跑测试 | `pytest` |
| 跑单个测试 | `pytest tests/test_smoke.py -v` |
| Lint | `ruff check .` |
| Lint 修 | `ruff check --fix .` |

## 相关

- 项目根目录 [`AGENTS.md`](../AGENTS.md)：整体 agent 协作约定
- [`CONTEXT.md`](../CONTEXT.md)：领域语言
- [`docs/PRD-V5.md`](../docs/PRD-V5.md)：产品需求
- [`docs/adr/`](../docs/adr/)：架构决策
- [`.scratch/scriptflow-v5/`](../.scratch/scriptflow-v5/)：当前 issue tracker
