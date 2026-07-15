# 06 · Scene 独立表 + 数据迁移

- **Status**: proposed
- **Type**: refactor + feature
- **Blocked by**: 02, 04
- **Blocks**: 07, 08, 10, 11, 12
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #18, #19; ADR-0002

## What to build

`episodes.scenes` 字段当前存的是"整集正文 JSON 数组"，一个 scene 对象里塞了整集内容 —— 词汇债。改成正确的领域建模：Scene 是独立实体。

- 新建 `scenes` 表：
  - `id`, `episode_id`, `scene_number`, `location`, `time`, `content`, `characters_involved` (JSON), `props_used` (JSON), `status` (`draft`/`final`), `created_at`, `updated_at`
- 新建 SQLAlchemy 模型 `Scene`
- Alembic 迁移：
  - 创建 `scenes` 表
  - 遍历旧 `episodes.scenes` JSON，按 `【场景N】地点·时间` 正则拆分（拆不出来的整段作为一个 Scene）
  - `episodes` 表新增 `word_count`（如没有），移除 `scenes` 列
- 新建 API：`GET/POST/PUT/DELETE /api/projects/{pid}/episodes/{ep_num}/scenes[/{sn}]`
- 前端 `Workspace.vue` 里的"分集详情" —— 用新 `<ScenePanel>` 组件替代 `<pre>{{ parseScenes(...) }}</pre>`
- 每个 Scene 卡片可折叠、可展开、可单独编辑（内联 textarea + 保存）

## Acceptance criteria

- [ ] Alembic migration up 成功：老数据能拆分成 scenes 行
- [ ] Alembic migration down 成功：能回滚（scenes 表 drop，字段复原）
- [ ] `pytest backend/tests/test_scene_migration.py` 覆盖：无 scenes 字段的空项目、单场景项目、多场景项目、格式错乱项目（4 个 fixture）
- [ ] 前端 Episode 详情打开：看到 Scene 卡片而非一坨 pre 文本
- [ ] Scene 单独编辑保存后，刷新页面仍在
- [ ] `episodes.scenes` 字段被移除后，backend 全部端点仍工作

## Notes

- **破坏性 schema 变更** —— 迁移前提示备份 `.db` 文件
- 老数据里能拆的按 `【场景N】` 拆；拆不出的整段作为该集单一 Scene（`scene_number=1`）
- `characters_involved` / `props_used` 字段先留空，issue #07/09 里填充
