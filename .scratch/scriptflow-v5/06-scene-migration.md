# 06 · Scene 独立表 + 数据迁移

- **Status**: done
- **Type**: refactor + feature
- **Blocked by**: 02, 04
- **Blocks**: 07, 08, 10, 11, 12
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #18, #19; ADR-0002

## What to build

`episodes.scenes` 字段当前存的是"整集正文 JSON 数组"，一个 scene 对象里塞了整集内容 —— 词汇债。改成正确的领域建模：Scene 是独立实体。

- 新建 `scenes` 表：`id`, `episode_id`, `scene_number`, `location`, `time`, `content`, `characters_involved` (JSON), `props_used` (JSON), `status`, `created_at`, `updated_at`
- 新建 SQLAlchemy 模型 `Scene`
- Alembic 迁移 0002：CREATE scenes、data-migrate 拆分旧 JSON、DROP episodes.scenes
- 新建 Scene CRUD API：`GET/POST/PUT/DELETE /api/workspace/{pid}/episodes/{ep_num}/scenes[/{sn}]`
- `save_episode` tool 拆场景写入
- `context_engine.build_context` / `memory_service.list_scenes` 走新 scenes 表
- 前端 `parseScenes()` 兼容 array，`viewEp` 走 GET 拿完整 scenes

## Acceptance criteria

- [x] Alembic migration up 成功：老数据能拆分成 scenes 行（5 fixture 覆盖）
- [x] Alembic migration down 成功：能回滚，episodes.scenes 复原
- [x] `pytest tests/test_scene_migration.py`：5/5（空项目、单场景无标记、多场景带标记、损坏 JSON、down 往返）
- [x] `pytest tests/test_scene_api.py`：6/6（GET single inline scenes、list、add、update、delete、owner isolation 404）
- [x] `episodes.scenes` 字段被移除后，backend 全部端点仍工作 (35/35 pytest 全绿)
- [x] Splitter 抽到 `app/services/scene_splitter.py` — 运行时用；alembic migration 保留独立副本作 immutable history
- [ ] 前端 Scene 单独编辑 UI（`ScenePanel.vue`）— 留给 Batch 3 组件库统一升级

## Notes

- **破坏性 schema 变更** —— dev db 是 0 字节所以无痛；生产升级前先 `.db` 备份
- Splitter 逻辑基于行分析（`【场景N】location·time`），比 regex 版更稳
- Frontend minimal change：`parseScenes` 兼容 array | JSON string 两种；`getEpisode` 现在 inline scenes 数组
