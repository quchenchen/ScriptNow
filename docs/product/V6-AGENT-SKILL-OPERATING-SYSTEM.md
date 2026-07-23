# ScriptFlow V6 Agent × Skill 创作操作系统

> 状态：V6 产品与技术执行契约。本文补足 PRD 中 Agent Task、Artifact、Revision、Decision 与 Delivery 的运行语义。

## 1. 设计结论

ScriptFlow 不把“多个 Agent 同时聊天”当作团队协作。团队协作由可追踪的任务、受约束的能力、可比较的产物和明确的人类决策组成。

```text
Goal → Agent Task → Skill Bundle → Candidate Artifact
     → Review Evidence → Revision / Decision → Adopted Artifact
```

底层可以复用同一 AgentScope 运行时；角色差异来自责任、上下文、允许工具和交付标准。V6 不以增加 Agent 数量作为目标。

## 2. 五个执行对象

### Agent Task

一次有边界的团队工作。必有目标、负责人、输入对象、允许工具、预期交付和完成条件。

状态机：

```text
queued → running → delivered
  │         ├─→ waiting_decision
  │         ├─→ blocked → running
  │         └─→ failed → queued
  └─→ cancelled
```

`delivered` 只表示 Agent 已交付候选，不表示作品已采用。

### Artifact

创作过程中可被引用、审阅和形成血缘的产物。V6 P0 类型为 Story Core、Story Beat、Manuscript Unit、Adaptation Map、Review Report。

Artifact 必须区分稳定身份与内容版本：`artifact_id` 标识作品对象，`revision_id` 标识一次内容状态。

### Revision

对 Artifact 的一次可比较修改。Revision 不直接覆盖当前采用内容。

状态机：

```text
draft → candidate → adopted
                 ├─→ rejected
                 └─→ superseded
```

每个 Revision 记录作者类型、父版本、变更理由、影响范围、引用来源和质量证据。AI 只能创建 `candidate`；用户编辑可保留为 `draft`，显式提交后成为 `candidate` 或直接采用自己的修改。

### Decision

只有无法由既定规则安全决定、且会改变创作方向或当前采用内容时才创建 Decision。

状态为 `open / resolved / dismissed / expired`。Decision 必须提供问题、选项、影响、推荐理由与可撤销性，禁止只有“确认/取消”。

### Delivery

Agent Task 的交付通知，连接 Task 与一个或多个候选 Artifact/Revision。Delivery 不是新的内容存储，也不等于完成状态。

## 3. 角色责任与权限

| 角色 | 主要责任 | 可以交付 | 不得执行 |
|---|---|---|---|
| 创意导演 | 命题、受众、方向差异化 | Idea Branch、Story Core 候选 | 自动采用创作方向 |
| 故事架构师 | 结构、因果、节奏、人物弧光 | Story Beat、结构 Revision | 静默改写正文 |
| 写作者 | Scene/Chapter 正文与局部修订 | Manuscript Revision | 修改 Frozen Story Core |
| 审稿人 | 基于证据发现问题并提出方案 | Review Report、修订候选 | 接受自己的建议 |
| 改编策划师 | 来源解析、取舍、媒介转换 | Adaptation Map、Source Reference | 删除或篡改 Source Canon |

角色之间通过 Artifact 和 Task 交接，不以聊天记录作为唯一上下文。

## 4. Skill Contract

每个可执行 Skill 使用同一契约：

```yaml
name: scene-draft
version: 1.0.0
purpose: 根据已采用 Story Beat 生成一个可拍摄 Scene 候选
applies_when:
  creation_source: [original, adaptation]
  delivery_medium: [script]
requires:
  - story_core_revision
  - story_beat_revision
inputs:
  scene_goal: string
  constraints: string[]
outputs:
  artifact_type: manuscript_scene
  state: candidate
allowed_tools:
  - query_characters
  - query_foreshadows
  - search_source
  - create_revision
invariants:
  - 不改变 Frozen Story Core
  - 改编项目的来源事实必须附 Source Reference
rubric:
  - 因果与场景目标
  - 人物声音一致性
  - 可拍摄性
  - 与上下场衔接
recovery:
  missing_context: 创建 blocked Task，并指出缺失对象
```

Skill 文档可以包含知识，但只有具备上述契约、样例和测试夹具的 Skill 才能进入生产 Skill Registry。

### Skill Bundle 组合顺序

为避免 Prompt 膨胀和规则冲突，按以下优先级合成：

1. 产品安全与用户 Frozen 约束
2. 项目 Story Core 与 Source Canon
3. 交付媒介规范（Script / Novel）
4. 当前任务 Skill
5. 类型、风格和项目偏好

高优先级规则不可被低优先级覆盖。每次 Task 记录实际加载的 Skill 版本。

## 5. 两条贯穿工作流

### A. 原创剧本：从创作种子到采用 Scene

1. 创意导演提交三个差异化 Story Core 候选。
2. 用户采用、编辑后采用或创建 Branch。
3. 故事架构师基于已采用 Story Core 交付 Story Beat 候选。
4. 写作者生成 Scene Candidate Revision。
5. 审稿人输出带正文证据的 Review Report。
6. 低风险格式修复可生成新候选；方向问题进入 Decision Inbox。
7. 用户逐项或整体采用，形成当前 Revision 与完整 lineage。

### B. 小说改编剧本：从来源到采用 Scene

1. 改编策划师把 Source Canon 解析为章节与稳定片段引用。
2. 用户选择忠实度原则，策划师交付“来源 → 决策 → 目标”的 Adaptation Map。
3. 对删除、合并、重排和原创新增给出理由；关键取舍进入 Decision。
4. 写作者只依据已采用映射生成 Scene Candidate。
5. 审稿同时检查人物偏移、关键事实、情节遗漏和媒介转换质量。
6. 用户采用后，Scene 保留 Source Reference；无来源内容明确标记为原创新增。

## 6. 质量基准与 Release Gate

建立四个固定 Golden Project：原创短剧、原创长篇小说、小说改编剧本、剧本改编小说。V6 Release Gate 先要求前两条主路径。

每次 Skill 或 Agent 变更至少验证：

- Schema：输入输出、状态迁移、权限与工具白名单。
- Continuity：人物、时间线、Story Beat、伏笔的已知冲突。
- Traceability：候选是否能追溯到 Task、父 Revision 和来源。
- Review Recall：审稿能否发现夹具中的预设问题并定位证据。
- Adoption Quality：修订是否解决问题，且没有破坏未选范围。
- Recovery：上下文缺失、模型失败、用户离开后能否恢复。

不得用单一总分代替这些门槛。LLM 评分只作为辅助证据，结构化不变量由确定性测试执行。

## 7. V6 实施边界

第一阶段不建设 Agent 自由讨论网络、自动无限返工、跨项目自动学习和复杂调度器。先用单一调度器、五种责任角色、十个生产级 Skill 与两条 tracer workflow 证明闭环。

## 8. Creative Continuity Protocol

结合外部项目机制审计，所有生产写作 Task 增加统一协议：

```text
Assemble Context Pack → Plan Revision Brief → Execute by Depth
→ Supervise → Deliver Candidate + Evidence + Impact
```

Context Pack、Batch/Checkpoint、Novelty Ledger、Living Asset Candidate 和 Skill 三层结构的完整定义见 [`V6-REFERENCE-PATTERN-SYNTHESIS.md`](./V6-REFERENCE-PATTERN-SYNTHESIS.md)。这些机制扩展本操作系统，但不得突破人机协作宪法规定的 A0–A4 自主边界。
