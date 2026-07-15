# 07 · Character 活起来（管理面板 + 跨 stage 编辑 + Cascade）

- **Status**: proposed
- **Type**: feature
- **Blocked by**: 06
- **Blocks**: 09, 11
- **Est**: M-L
- **Parent PRD**: docs/PRD-V5.md §User Stories #7-#10

## What to build

Character 表字段已经有一堆（`first_appearance`、`last_appearance`、`career_stage`、`current_state`、`state_episode`、`arc`），但没 UI 用起来，且只在 Structure 阶段可编辑。改成 Living Asset。

**后端：**
- 新建 `backend/app/repos/living_asset_repo.py` 的第一个 impl：`CharacterRepo`
- 新建 `/api/projects/{pid}/assets/character` 端点（GET list / GET/{id} / POST / PUT / DELETE）
- Cascade：`PUT /character/{id}` 后端事件 → 把所有涉及该 Character 的 Episode 标 dirty（`episodes.dirty_reason` 新增字段，或用独立 dirty markers 表）
- Writing Agent 的 tool `query_characters` 返回完整 Character 对象（含 current_state / arc）
- Writing Agent 新增 tool `update_character_state`（在生成完一集后可更新角色 current_state）

**前端：**
- `CharacterPanel.vue`：
  - 表格：姓名 / 定位（主/反/配）/ 年龄 / 出场轨迹（"EP1-EP12"）/ 当前状态 / 弧光进度
  - 点角色 → 详情抽屉：可编辑所有字段
  - 出场时间轴（水平条形，每集一格，标戏份轻重）
- Workspace 主视图右侧多一个 tab："角色"
- Cascade 提示：任何 Episode 卡片 / 树节点上，若 `dirty_reason` 存在 → 显示 "⚠可能要修（角色 A 已更新）"

## Acceptance criteria

- [ ] 从 Writing 阶段打开角色面板 → 编辑 Character.arc → 保存 → 所有涉及该 Character 的 Episode 出现 dirty 标记
- [ ] 出场时间轴数据正确（从 `scenes.characters_involved` 或 Episode 内容抽取）
- [ ] Writing Agent 生成完一集后调 `update_character_state` → 数据入库
- [ ] `backend/tests/test_character_repo.py` 覆盖 CRUD + Cascade
- [ ] 前端 `CharacterPanel.spec.ts` 覆盖：显示、编辑、Cascade 提示

## Notes

- 关系图谱（User Story #10）留到 P1 slice，不塞这里
- 肖像图（#11）关联到 VisualAsset，Phase 4 做
- Cascade 只标 dirty，**不自动改** —— 用户点开决定修不修
