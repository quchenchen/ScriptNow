# 01 · 依赖锁定 + 开发脚手架

- **Status**: proposed
- **Type**: chore
- **Blocked by**: None
- **Blocks**: 02, 03
- **Est**: S
- **Parent PRD**: docs/PRD-V5.md §User Stories #50

## What to build

让任何人（包括 CI 上未来的 agent）能在 5 分钟内 clone 下来跑起来。

- 后端建 `backend/pyproject.toml`（Python 3.11+），依赖锁定：fastapi、uvicorn、aiosqlite、sqlalchemy、pyjwt、agentscope、pydantic、pytest、pytest-asyncio、ruff
- 前端 package.json 已存在，仅确认锁定 lockfile 提交进 git
- 根目录 `README.md`：一句话产品定位 + 快速开始 + 指向 AGENTS.md
- 根目录 `Makefile` 或 `scripts/dev.sh`：一条命令起后端 + 前端
- 后端 `backend/tests/` 目录 + `conftest.py` 骨架 + 一个通过的冒烟测试（`/api/health` 返 200）
- 前端 `frontend/src/` 下加一个 vitest 骨架 + 一个通过的冒烟测试

## Acceptance criteria

- [x] `cd backend && pip install -e ".[dev]"` 成功
- [x] `cd backend && pytest` 至少 1 个 test 通过（2 passed）
- [ ] `cd frontend && npm ci && npm run test` 至少 1 个 test 通过（前端骨架留到独立小 slice，不阻塞 backend 主线）
- [x] `make dev`（或 `scripts/dev.sh`）同时起后端 8000 + 前端 5173 （Makefile 提供）
- [x] README 里"5 分钟从零开始"章节可以照着一遍走通
- [x] `ruff check tests/` 无错

## Notes

- 不引入 poetry / uv，用 pip + pyproject 就行（Q老师环境已 python 3.11）
- 前端 lockfile 用 `package-lock.json`（已有），不切 pnpm
- 冒烟测试不追求覆盖率，只求"环境跑通"信号
