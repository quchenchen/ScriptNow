# ADR-0001: 采用 "生长式" 作为核心产品隐喻，替代 "流水线"

- **Status**: Accepted
- **Date**: 2026-07-15
- **Deciders**: Q老师、阿泡（AI 助理）
- **Supersedes**: PRD-V3 §5.2 "核心业务流程（用户旅程）" 的 J1-J10 线性叙事

## Context

初版 PRD（V1-V4）把产品定位成 "7 阶段流水线" —— `ideation → structure → writing → review → polish → assets → prompts`。这份定位在文档里逻辑通顺，但落到实际实现和 UI 上产生了以下问题：

1. **UI 上**：Workspace.vue 的 7 个 tab 页面各自空白，前后阶段之间没有可视化的传递感。用户从 A tab 切到 B tab 后，找不到"前一阶段产出如何变成下一阶段起点"的入口。
2. **数据模型上**：产出物存在 `script_versions` 表里独立行，没有血缘关系。修改上游（比如 Structure 里的角色）不会通知下游（比如已经写好的 Episode）。
3. **Agent 上**：每个 stage 一个 sys_prompt，Agent 之间不通消息，靠 SQL 读上一阶段产物"续写"。
4. **用户心智上**：Q老师明确表达 "让好剧本生长出来，而不是东拼西凑" 是核心诉求。当前流水线设计正好落在 "拼凑" 那一端。

## Decision

采用 **"生长式创作系统"（Growing）** 作为核心产品隐喻：

- 产出物之间有**血缘图谱**（Growth Tree），不是独立文件
- **横向骨架**（Living Assets: Character / Foreshadow / Scene / Prop / VisualAsset）贯穿所有 stage，有独立生命周期
- **反馈进化循环**（Evolution Loop）三层嵌套：Ralph Loop / Reflection / Style Library

术语的具体定义见 [`CONTEXT.md`](../../CONTEXT.md)。

**旧文档处理**：PRD-V3、SPEC-V4、PLAN、PLAN-V2、FRAMEWORK-COMPARISON、AGENTSCOPE-ANALYSIS 归档到 `docs/archive/`，作为决策历史保留但不再是主线。新主线是：

- `CONTEXT.md`（领域语言）
- `docs/PRD-V5.md`（主线 PRD，Phase 1 产出）
- `docs/adr/*.md`（架构决策）

## Consequences

### 好的

- **UI 有了新方向**：核心视图从"7 tab 顺序推进"变成"Growth Tree 可视化 + Living Assets 面板"（具体形态在 Phase 1 PRD 里定）。
- **数据模型有了指导原则**：任何"stage 独立表 / 独立文件"设计需 ADR 举证，默认走血缘。
- **Agent 编排有了目标**：Agent 不再是"某个 stage 独占"，而是"围绕 Living Assets 协作"。
- **用户价值主张清晰**："AI Agent 团队让你的剧本长出来" 比 "AI 帮你走完 7 段流水" 强得多，也更贴 Q老师原本想要的定位。

### 坏的 / 代价

- **现有代码大部分要重构**。特别是：
  - `backend/app/core/pipelines.py` — stage 定义方式要重想（stage 变成 Growth Tree 上的节点类型，不是数组）
  - `backend/app/api/workspace.py` — 前端接口大改
  - `frontend/src/pages/Workspace.vue` — 从 tab UI 换成 Growth Tree UI
- **PRD-V3 里的一些承诺现在需要重新对齐** —— 尤其 "12-20 分钟一部 80 集短剧全流程" 这种线性时长承诺，可能不再适用（生长式 UI 用户会在树上来回走）。
- **对新 contributor 的学习曲线** — 需要先读 CONTEXT.md 才能理解代码，比传统 CRUD 项目门槛高。

### 中立

- 用户在 Growth Tree 上可以走"深度优先"（一路推到成片）或"广度优先"（每层多做几个候选再选）。UI 要支持两种，但产品哲学不偏向。

## Alternatives Considered

### (a) 保留流水线，只在 UI 层做美化

拒绝理由：Q老师的四层不满意（产品逻辑 / UI 交互 / 功能 / skills 逻辑）用美化解决不了。根本问题在 metaphor，不在 skin。

### (b) 完全废弃现有代码，从零重写

拒绝理由：现有代码里已经有很多"骨架已想到但没用起来"的信号（`characters` 表的 `first_appearance` / `career_stage` 等字段、`foreshadows` 表的完整状态字段）。这说明原设计者朝这个方向想过，但没坚持到 UI 层。重构比重写代价小。

### (c) 混合 —— 保留 7 stage 定义但改 UI 隐喻

拒绝理由：数据模型和 Agent 编排不改，UI 就无从长出 Growth Tree。半心半意的改造会同时保留新旧两种复杂度。

## Notes

- 这个隐喻决策影响后续所有 ADR 的框架。
- 后续可能出现"某个具体功能不适合 Growth Tree 表达"的情况（比如批量导出、批量评估）— 允许这类功能走独立入口，但**主创作流** 必须在 Growth Tree 上。
