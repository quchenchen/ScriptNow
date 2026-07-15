# 08 · Foreshadow 看板（补全状态机）+ Prop 面板

- **Status**: done (backend complete; Kanban UI deferred to Batch 3)
- **Type**: feature
- **Blocked by**: 06
- **Blocks**: 11
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #13-#17, #21-#22

## What to build

### Foreshadow (done)

现有字段设计得挺全（plant/target/actual_episode / urgency / is_long_term / related_characters / remind_before / auto_remind），但状态机路径不全，加齐。

- **新增** `app/services/foreshadow_state.py` — enum + valid transitions 表 + `can_transition` / `transition` / `is_terminal` / `is_overdue`
- 5 态：pending → planted → partially_resolved → resolved | abandoned
- **新增 tools**：`partial_resolve_foreshadow` / `abandon_foreshadow`（`plant_foreshadow` / `resolve_foreshadow` 已有，改成走 state machine 校验）
- **新增 API** `PATCH /api/memory/{pid}/foreshadows/{fid}/status` — body `{"target": "resolved", "resolution_text": "..."}`；非法转换 400
- `is_overdue` 计算在 `GET /foreshadows` 时 annotate（target_episode - max_episode ≤ remind_before）

### Prop (done)

新增 Prop 表 + CRUD。

- 新建 `props` 表：id / project_id / name / description / significance (background/plot_device/macguffin) / first_appearance / last_appearance / usage_count / created_at
- SQLAlchemy 模型 `Prop` + Alembic migration 0004
- API `/api/memory/{pid}/props` — CRUD + significance 筛选
- **新增 tools**：`add_prop` / `mark_prop_used`（后者累加 usage_count + 更新 last_appearance）

### 前端 (deferred to Batch 3)

- ForeshadowBoard.vue Kanban 布局 — Batch 3 组件库升级时做
- PropPanel.vue + Workspace 右侧 tab 增加"道具" — Batch 3
- 现在 `propList` 已通过 loadAssets 从 `/memory` summary 拿到，注入到 useWorkspace 供后续 UI 用

## Acceptance criteria

- [x] Foreshadow 状态可从 API 全 5 态之间合法流转，非法转换返 400 (`test_living_asset_api::test_foreshadow_transition_planted_to_resolved`, `test_foreshadow_illegal_transition_rejected`)
- [x] 目标集减 remind_before 集内未回收 → GET foreshadows 返回 is_overdue=true (`test_foreshadow_list_annotates_is_overdue`)
- [x] Writing Agent 通过 tool 推进状态（parametric + partial → resolved 覆盖）
- [x] Prop CRUD 端到端可用（4 tests：round trip、significance filter、owner isolation、memory summary include）
- [x] `pytest test_foreshadow_state_machine.py` 覆盖所有状态转换 + 非法转换报错（16 params + 5 misc = 21 tests）
- [ ] Workspace 右侧 tabs 增加"伏笔" / "道具" — Batch 3

## Notes

- 状态转换用 python enum + `_ALLOWED` 邻接表 —— 避免 magic string，legality 一目了然
- `subtlety` 字段已有，UI 用它决定"埋得明显还是隐晦"（等 Batch 3 面板）
- Prop 的 first_appearance / last_appearance 自动维护（mark_prop_used）
