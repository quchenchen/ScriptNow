# ADR-0002: Living Assets 作为独立的横向数据模型

- **Status**: Accepted
- **Date**: 2026-07-15
- **Deciders**: Q老师、阿泡（AI 助理）
- **Depends on**: [ADR-0001](./0001-adopt-growing-metaphor.md)

## Context

在旧的 7 阶段流水线设计里：

- **Character** 是 Structure 阶段的"输出"。Writing 阶段用 `query_characters` 工具只读拉取。
- **Foreshadow** 名义上跨阶段，但实际主要在 Writing 阶段被 `plant_foreshadow` 埋、由 `resolve_foreshadow` 收 —— 没有"追踪、提醒、更新"的完整生命周期。
- **Scene** 概念被 `episodes.scenes` 字段吞并了 —— 该字段实际存的是"整集正文的 JSON 数组"，一个 scene 对象里塞了整集内容。这是词汇债，不是设计。
- **Prop** 没有独立表。
- **VisualAsset** 完全没有。Q老师明确要求引入专业生图 LLM，这需要一个独立实体承载图像及其 prompt 迭代历史。

以上导致：
- 角色属性（性格、弧光）在 Structure 定义后基本"冻结"，Writing 阶段不能修改（技术上能，但没入口）
- 伏笔状态不完整 —— 表里字段设计得挺全，但代码只用到 `pending / planted / resolved` 三个态
- Scene 术语在数据库、代码、UI 之间语义不一致
- 图像资产要塞到剧本里没地方

## Decision

**Living Assets 是横向骨架层**，独立于任何单一 stage 存在。共 5 类：

### 五类 Living Asset

| Asset | 状态机 | 关键字段（新增或复活的） |
|---|---|---|
| **Character** | `active / suspended / deceased` | `first_appearance`、`last_appearance`、`career_stage`、`current_state`、`state_episode`、`arc_progress`（新） |
| **Foreshadow** | `pending → planted → partially_resolved → resolved` 或 `→ abandoned` | 完整用起来现有字段：`plant_episode`、`target_episode`、`actual_episode`、`urgency`、`is_long_term`、`related_characters` |
| **Scene** | `draft / final` | 独立表 `scenes`，字段：`episode_id`、`scene_number`、`location`、`time`、`content`、`characters_involved`、`assets_used` |
| **Prop** | `active / retired` | 独立表 `props`，字段：`project_id`、`name`、`first_appearance`、`last_appearance`、`significance`（`background / plot_device / macguffin`） |
| **VisualAsset** | `prompt_draft / generating / ready / iterating / accepted` | 独立表 `visual_assets`，字段：`project_id`、`asset_type`（character/scene/prop）、`asset_ref`（fk）、`prompt`、`prompt_version`、`image_url`、`generator`（哪个生图 LLM）、`feedback_history`（JSON） |

### 通用约束

每个 Living Asset 必须：

1. **跨 stage 存活** —— Ideation 里提及 → 到 Structure 里定型 → 在 Writing 里被使用 → 在 Review 里被检查 → 在 Assets 阶段被视觉化 → 全程同一份数据，同一 id
2. **有独立 UI 视图** —— 用户可以脱离剧本树直接查阅、编辑 Character 列表 / Foreshadow 状态板 / VisualAsset 图库
3. **可被多 Agent 读写** —— Writing Agent 可以给 Character 更新 `current_state`；Reflection 可以给 Foreshadow 标 `at_risk_not_resolved`
4. **参与 Cascade** —— 改一个 Character 的性格 → 所有涉及该 Character 的 Episode 收到 dirty 标记

### `episodes.scenes` 字段的历史错误处理

当前 `episodes.scenes` 字段存的是"整集正文 JSON 数组"，一个 scene 对象里塞了整集内容。这个字段将被：

1. 迁移到新独立 `scenes` 表（每个 scene 一行）
2. Episode 表新增 `word_count`、`raw_content`（可选，作为编辑源）字段
3. 数据迁移脚本处理旧数据 —— 现有 `episodes.scenes[0].content` → 作为该集单一 Scene 或按 `【场景N】` 正则拆分成多个 Scene

## Consequences

### 好的

- **Schema 表达力对齐领域语言**（CONTEXT.md 术语与数据库表一一对应）
- **Agent 编排简化** —— Agent 不再"隶属"某个 stage，而是"操作某类 Living Asset"。Writing Agent 变成 "读 Character/Foreshadow，写 Scene/Episode"。
- **UI 有了独立可 mount 的面板** —— 角色管理面板 / 伏笔状态板 / 视觉资产图库 都是独立视图，不必绑定 stage
- **Cascade 有了触点** —— Character.character_updated 事件 → 触发所有涉及 Episode 的 dirty 标
- **VisualAsset 打开了生图 LLM 集成的口子**

### 坏的 / 代价

- **数据迁移** —— 现有 `episodes.scenes` 需要一次性迁移。属于破坏性 schema 变更，需要 backup + 迁移脚本。
- **schema 复杂度上升** —— 从 8 张表变到 11 张（+ scenes + props + visual_assets）。但每张表职责单一，比现在的"scenes 字段一鱼多吃"清晰。
- **需要重新写 `query_characters` 等工具** —— 从"一次性只读拉"变成"随时可读可改"。
- **前端要相应新增管理面板** —— 是 Phase 3 工作量的一部分。

### 中立

- 现有代码里 `characters` 和 `foreshadows` 表**已经设计得基本符合 Living Asset 要求**（字段齐全）。主要是：
  - Foreshadow 状态机需要补齐用起来
  - Character 需要有 UI 让用户看到跨集轨迹和状态演化
  - Scene / Prop / VisualAsset 是新增的

## Alternatives Considered

### (a) 保留 stage-owned 数据模型，只加一层 view 视图

拒绝理由：view 视图不能改变"角色数据在 Structure stage 才可编辑"的实质限制。用户需要在 Writing 时改角色，view 视图救不了。

### (b) 把所有 Living Asset 合并成一张 `assets` 表用 type 字段区分

拒绝理由：多态表在 SQLite 上性能不是问题，但 Foreshadow 的状态机、VisualAsset 的 prompt 迭代历史都很不同 —— 强行合并会让每张表都有一堆"其他 type 用不到的字段"。分表更符合"深模块"设计原则（每个 Asset 类型有自己的行为）。

### (c) 完全 Event Sourcing，产出物都从事件流回放

拒绝理由：对当前项目规模过度工程。真需要 event 时（比如 VisualAsset 的 prompt 迭代），可以在单个 asset 内加 `history` 字段（JSON），不必全局 event sourcing。

## Notes

- 数据迁移会作为独立的 tracer bullet issue 独立干一遍，不塞进其他 slice。
- 前端管理面板的具体样式在 PRD-V5 里定。
