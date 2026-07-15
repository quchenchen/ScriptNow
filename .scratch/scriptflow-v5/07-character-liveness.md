# 07 · Character 活起来（管理面板 + 跨 stage 编辑 + Cascade）

- **Status**: done (backend complete; UI polish deferred to Batch 3)
- **Type**: feature
- **Blocked by**: 06
- **Blocks**: 09, 11
- **Est**: M-L
- **Parent PRD**: docs/PRD-V5.md §User Stories #7-#10

## What to build

Character 表已经有 first_appearance/last_appearance/career_stage/current_state/state_episode/arc 一堆字段，此前没 UI 用起来。这一批把 Living Asset 后端完整化。

**后端 (done):**
- Character CRUD 端点通过 `memory_api.py` 已就位（issue #04 就落地）
- **新增** `GET /api/memory/{pid}/characters/{cid}/dirty-episodes` — Cascade 预览（用 growth tree 的 mark_dirty）
- **新增 tool** `update_character_state(character_id, current_state, state_episode=0)` — writer 生成完一集后调，state_episode 缺省为最新集
- Growth tree 里 character 作为 `asset` node，`references` edge 挂到最早出场的 episode
- `is_terminal` / `is_overdue` 计算已在 foreshadow_state module

**前端 (deferred to Batch 3):**
- CharacterPanel.vue 详情抽屉、出场时间轴、Cascade badge — 都属于 UI 精修范畴，等 Batch 3 组件库选型后统一升级；现在骨架 asset panel 已能显示 character 列表

## Acceptance criteria

- [x] Writing Agent 生成完一集 → 通过 tool `update_character_state` 更新角色 current_state → 数据入库 (tool 直接测覆盖)
- [x] `dirty-episodes` 端点用 growth tree 计算受影响 Episode（tested with 1 character + 1 episode → 返回 episode node）
- [x] `pytest test_agent_tools.py` 覆盖 update_character_state（含 state_episode 缺省回退到 max episode）
- [x] `pytest test_living_asset_api.py::test_character_dirty_episodes_via_growth_tree`
- [ ] 前端 Character 详情抽屉 + 时间轴 + Cascade badge — Batch 3

## Notes

- Cascade **不改数据**，只计算下游 episode/scene 节点 — UI 决定要不要修
- Character 的 growth node 现在通过 `backfill_project` 建立；后续 `add_character` API 应该也自动 record — 留给 P1 slice
- 关系图谱（#10）+ 肖像图（#11）没在这版
