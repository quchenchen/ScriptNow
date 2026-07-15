# 02 · Schema 单一 source of truth + 首次 Alembic

- **Status**: proposed
- **Type**: refactor
- **Blocked by**: 01
- **Blocks**: 04, 06, 09, 10
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #51

## What to build

当前 `backend/app/main.py` 用 aiosqlite 裸 SQL 建表，`backend/app/models.py` 有 SQLAlchemy 模型 —— 两套并存，字段不完全一致，SQLAlchemy 从未被调用。收敛成一套。

- 删掉 `main.py` 里的 `init_db()` 裸 SQL 代码块
- 把 `models.py` 拆到 `backend/app/models/` 包（每类实体一个文件：user, project, episode, character, foreshadow, script_version, chat_message, review, scene_asset）
- 引入 `alembic` + 生成初始 migration（`0001_initial.py`）
- lifespan 里改成 `alembic upgrade head`（自动跑 migration），保留 admin user seed
- `backend/app/db.py` 作为 DB 连接管理入口（AsyncSession factory），API 层用它
- 现有 API（auth / projects / workspace）改成从 db.py 拿 session，不再 `aiosqlite.connect()`

## Acceptance criteria

- [ ] `alembic upgrade head` 从空库生成完整 schema，与 V4 一致
- [ ] `main.py` 不再有裸 SQL DDL
- [ ] 所有 API 端点仍工作（现有前端 dashboard 打开 → 项目列表能拿到）
- [ ] `pytest backend/tests/test_db.py` 通过（migration up/down、admin seed）
- [ ] `models.py`（旧文件）删除，全部走 `models/` 包

## Notes

- 这个 slice 触发**破坏性变更**（现有 `backend/app/data/*.db` 可能要重建）—— 提示 Q老师备份或允许重置。
- Alembic 用 `async` template（sqlalchemy 2.x + aiosqlite）
- 迁移到独立 Scene 表放到 issue #06，不塞这里
