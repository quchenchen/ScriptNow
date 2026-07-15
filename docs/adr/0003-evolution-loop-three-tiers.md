# ADR-0003: Evolution Loop 三层结构 —— Ralph / Reflection / Style Library

- **Status**: Accepted
- **Date**: 2026-07-15
- **Deciders**: Q老师、阿泡（AI 助理）
- **Depends on**: [ADR-0001](./0001-adopt-growing-metaphor.md)、[ADR-0002](./0002-living-assets-horizontal-model.md)

## Context

Q老师明确表达："能够持续强化不同类型和风格的反馈并自我进化的能力。"

反馈+进化不是一个动作，是多个尺度的循环嵌套。当前代码状态：

- **Ralph Loop（单集内）** —— PRD-V3 承诺，代码里死了。`agents/review_agent.py` 依赖的常量 `MAX_RALPH_LOOP_RETRIES` / `REVIEW_PASS_THRESHOLD` / `REVIEW_REVISE_THRESHOLD` 在 config 里根本不存在，agent 也没被任何 caller 调用。
- **单作品跨集反哺** —— 完全没有。
- **跨作品自我进化 / 风格库** —— 完全没有。`chat_messages` 表存了历史但从不被 Agent 读回去做 few-shot。

Q老师希望这个能力从产品层就要**看得见** —— 用户能感觉到"AI 越用越懂我"，而不是每次都从零开始。

## Decision

**三层嵌套 Evolution Loop**，从内到外：

### Tier 1: Ralph Loop（单集内）

- **触发**：Writing Agent 完成一集 → 自动触发 Review Agent
- **步骤**：
  1. Review Agent 按六维（人物 / 情节 / 对白 / 节奏 / 钩子 / 类型契合度）打分，产出 `Review` 记录
  2. 若 `overall_score >= REVIEW_PASS_THRESHOLD`（默认 85）→ Episode 状态 `done`，退出
  3. 若 `overall_score < REVIEW_REVISE_THRESHOLD`（默认 60）→ 触发 "重新架构" 建议给用户，不自动改
  4. 中间态 → Writing Agent 拿到 Review 的 `issues` 列表 → 修 → 再回到 步骤 1
  5. 最多循环 `MAX_RALPH_LOOP_RETRIES`（默认 3）次；达到上限 → 挂 `human_review_needed` 标签
- **可见性**：UI 上必须能看到每次循环的过程：`第 5 集 · Ralph #1 · 72 分（人物不足）→ 修改中 → #2 · 84 分 → 通过 ✅`。这是"过程感"的最小可见单元。
- **配置**：阈值、最大次数、六维权重 —— 全部走 project 级配置，可用户调。

### Tier 2: Reflection（单作品跨集反哺）

- **触发条件**：
  - Ralph Loop 里的 Review 检出"角色 A 前后矛盾"、"伏笔 X 埋了没收"、"世界观自相矛盾"这类**跨集问题**
  - 或者 Reflection Agent 定期扫描（每写完 N 集触发一次）
- **动作**：Reflection Agent 找到问题的**上游根因**，生成"建议修改点" —— 可能指向 Structure（改人设）、Outline（改这几集顺序）、甚至 Idea（这个题材角色行为不合理）
- **不自动改**，永远提示用户决策：
  - 用户点"确认修" → 触发 Cascade（改上游 → 下游相关 Episode / Scene 标 dirty，等待用户逐个 review）
  - 用户点"忽略" → Reflection 记录用户偏好："这类问题用户不介意" → 影响未来 few-shot
- **实体**：新增 `reflections` 表，记录每次反哺的问题、建议、用户决策
- **UI**：Growth Tree 上，被反哺的上游节点会显示 "⚠ 3 集提出异议"，点开是 Reflection 列表

### Tier 3: Style Library（跨作品自我进化）

三级作用域，作用域越窄权重越高：

- **`project.style_profile`** —— 一部作品内的风格约束（类型、观众定位、语气偏好），Ideation 时用户设定 + Agent 生成过程中沉淀
- **`user.style_preferences`** —— 用户跨作品累积的偏好。事件源：
  - 用户在 Ideation 阶段的选择（选 A 弃 B）
  - 用户在 Editing 阶段的改动（人工改了什么）
  - 用户在 Reflection 阶段的决策（确认修/忽略）
  - 显式反馈（👍/👎）
  - **不**自动学 → 用户可查看、可编辑、可删除。是 profile 不是黑盒。
- **`genre.style_conventions`** —— 类型/题材通用惯例，全局共享。由平台维护（可能 admin 手动，也可能从多用户匿名统计），不属于任何单一用户
- **应用点**：所有 Agent 的 system prompt 生成时都合并这三级 style，作用域窄的覆盖宽的
- **实体**：`style_profiles` 表（scope: project/user/genre + rules JSON + version）
- **UI**：用户 profile 页面有"我的风格档案"，可查看/编辑/新建

## Consequences

### 好的

- **"过程感" 的最强触点** —— Ralph Loop 的可视化是 Q老师能立刻感觉到"AI 团队在为我干活"的第一个证据
- **PRD-V3 承诺的 Ralph Loop 真正兑现**
- **用户越用越爱** —— Style Library 让第二部作品的 Ideation 就明显比第一部更贴用户
- **可解释** —— 用户能查看/编辑 style profile，AI 不是黑盒，符合"用户是总指挥"的定位

### 坏的 / 代价

- **Review Agent 需要正确实现**（当前是死代码 —— 命名保留但从零重写）
- **Reflection 是新 Agent** —— 需要单独设计
- **Style Library 涉及新表 + 用户 UI + Agent 集成** —— 是 Phase 3 里比较大的工作量
- **Ralph Loop 的可视化要占用 UI 空间** —— 不能只是"loading 一下"完事，得让用户看到 loop 的每一次

### 中立

- 三层可以分批实现。**MVP 优先 Tier 1（Ralph Loop）**，Tier 2 和 Tier 3 分别是后续。
- Style Library 里 `user.style_preferences` 涉及隐私 —— 明确不同步到 `genre.style_conventions`（不做默默的众筹训练），保持透明。

## Alternatives Considered

### (a) 只做 Ralph Loop，不做另外两层

拒绝理由：Q老师明确说 "自我进化"，只做 Tier 1 只是"六维审核"，谈不上进化。至少 Tier 2 必须做。

### (b) Style Library 做成 embedding 向量库

拒绝理由：过度工程。当前用结构化 profile（JSON rules）就够，未来数据量大了再迁 embedding。**KISS 优先**。

### (c) Reflection 完全自动改，不问用户

拒绝理由：违反"用户是总指挥"的产品定位。Agent 团队自主推进 ≠ Agent 团队自主决策。Reflection 提议，用户拍板。

## Notes

- Ralph Loop 的六维默认权重和阈值需要一份初始默认值 —— 由 Phase 1 PRD-V5 给出，可后续调。
- Reflection Agent 的实现细节留到 Phase 3 单独 issue 讨论。
- Style Library 的三级作用域 merge 规则要有 unit test 覆盖 —— 是 skill layer 的关键 seam。
