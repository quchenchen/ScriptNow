# 08 · Foreshadow 看板（补全状态机）+ Prop 面板

- **Status**: proposed
- **Type**: feature
- **Blocked by**: 06
- **Blocks**: 11
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #13-#17, #21-#22

## What to build

### Foreshadow

现有 `foreshadows` 表字段设计得挺全（`plant_episode` / `target_episode` / `actual_episode` / `urgency` / `is_long_term` / `related_characters` / `remind_before` / `auto_remind`），但状态机代码路径不全。

- 状态机完整实装：`pending → planted → partially_resolved → resolved` 或 `→ abandoned`
- API：`/api/projects/{pid}/assets/foreshadow` CRUD + `PATCH /foreshadow/{id}/status`
- Agent tool `plant_foreshadow` / `resolve_foreshadow` / `partial_resolve_foreshadow` / `abandon_foreshadow`
- 目标集接近未回收 → 后端计算 `is_overdue` 属性，前端渲染 badge
- `ForeshadowBoard.vue`：Kanban 布局，列 = 状态；每张卡带埋点集 / 目标集 / 重要性 / 隐蔽度

### Prop

新增，因为 PRD-V5 里 P0 要求道具面板。

- 新建 `props` 表：`id`, `project_id`, `name`, `description`, `significance` (`background/plot_device/macguffin`), `first_appearance`, `last_appearance`, `usage_count`, `created_at`
- SQLAlchemy 模型 + Alembic 迁移
- API：`/api/projects/{pid}/assets/prop` CRUD
- `PropPanel.vue`：简单列表 + 分类筛选（significance）+ 出场集数

## Acceptance criteria

- [ ] Foreshadow 状态可从 UI 全 5 态之间流转
- [ ] 目标集减 remind_before 集内未回收 → 前端显示 ⚠badge
- [ ] Writing Agent 生成完一集，若 LLM 输出含"回收伏笔 X" → 通过 tool 调用推进状态
- [ ] Prop CRUD 端到端可用
- [ ] Workspace 右侧面板 tabs 增加"伏笔" / "道具"
- [ ] `backend/tests/test_foreshadow_state_machine.py` 覆盖所有状态转换 + 非法转换报错

## Notes

- 状态转换用 python `enum` + 迁移函数（避免 magic string）
- 隐蔽度（subtlety 1-5）字段已有，UI 用它，agent 也读它决定"埋得明显还是隐晦"
