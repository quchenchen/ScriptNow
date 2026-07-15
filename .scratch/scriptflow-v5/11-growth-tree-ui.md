# 11 · Growth Tree UI + Workspace 从 tab 转 Tree+Panel

- **Status**: proposed
- **Type**: feature
- **Blocked by**: 07, 08, 10
- **Blocks**: —
- **Est**: L
- **Parent PRD**: docs/PRD-V5.md §User Stories #1-#4; ADR-0001

## What to build

**这是 Growing 隐喻在 UI 上的落点。** Workspace.vue 从"7 tab 顺序"改成"左侧 Growth Tree + 右侧 Panel"。

**前端：**
- `frontend/src/composables/useGrowthTree.ts`：
  - `tree` reactive
  - `activeNodeId` reactive
  - `lineage(nodeId)` / `descendants(nodeId)`
  - `subscribe(project_id)` → SSE 实时收到新节点新边（tree 会长）
- `TreeView.vue`：
  - 竖向布局：Idea（顶）→ Structure（次层）→ Outline / Character / Foreshadow（骨架层，横向铺）→ Episodes（往下延展）→ Scenes / Assets（叶子）
  - 用 SVG 或 mermaid 渲染，节点可点击
  - 每个节点显示：类型 icon + label + 状态徽章（`dirty` / `frozen` / `human_review_needed`）
- `LineageBreadcrumb.vue`：当前选中节点的追溯路径面包屑
- `Workspace.vue` 大改：
  - 左侧：TreeView（永久可见）
  - 中间：选中节点的详情编辑（若是 Episode → ScenePanel + RalphLoopView；若是 Character → 详情表；若是 Foreshadow → 状态编辑；若是 Idea → 方案卡片）
  - 右侧：可切换的 Panel（Chat / 角色 / 伏笔 / 道具 / 视觉资产）
- 顶部保留 7 stage bar 作为**跳转 shortcut**（点击跳到该 stage 的第一个未完成节点），但不再是主创作动线
- 老的"进度条 + 7 tab"作为设置里可开的 "经典视图" 保留（escape hatch，见 PRD-V5 §Further Notes）

## Acceptance criteria

- [ ] 打开 Workspace → 立刻看到 TreeView（不是 tab）
- [ ] 点树节点 → 中间区域切换到该节点的编辑视图
- [ ] Cascade dirty 标能在 tree 上可见（哪些 Episode 现在跟新的上游脱节）
- [ ] Agent 生成新产出 → 树实时长出新节点（SSE）
- [ ] `frontend/src/tests/TreeView.spec.ts` 覆盖：渲染、点击、dirty 状态
- [ ] 经典 tab 视图可从设置里开启作为对比

## Notes

- 树规模上限：一部 80 集短剧大约 80+80+10+10+80 ≈ 260 节点。SVG 渲染 OK。
- 大规模时可 collapse 未选中的分支
- 树 layout 用简单的 tidy tree 算法（d3-hierarchy 可选，也可以手写）
- 这个 slice 最大，可能要拆成 3-4 个 commit：composable → TreeView → Workspace 集成 → Panel 联动
