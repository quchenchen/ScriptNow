# ADR-0011：自适应 SkillPlan 与受控能力进化

- 状态：Accepted
- 日期：2026-07-21

## 背景

当前运行时仅按 `medium + role_key` 静态装配 Skills。该机制可重复、可审计，但无法根据创作收束后形成的题材、主题、结构、语气、视角与禁忌选择不同的创作方法，也无法把持续发生的用户纠偏转化为项目能力。

## 决策

1. 创意收束形成平台层只读投影 `CreativeProfile`。它引用领域事实，不取代 Script/Novel 各自的 StoryCore、蓝图或正文事实源。
2. 每次运行由确定性的 `SkillResolver` 生成 `SkillPlan`：先按领域、角色、阶段和权限硬过滤，再依据 CreativeProfile 标签、历史评估与预算评分。
3. Skill 分四层：核心 Skill、风格 SkillPack、项目 Overlay、单次运行策略。优先级依次为领域不变式、用户明确约束、项目 Overlay、风格包、通用建议。
4. `WorkflowOrchestrator` 决定阶段和执行角色；`SkillResolver` 只负责装配；创作 Agent 不得自行发布全局 Skill。
5. `SkillCurator` 只产出 `SkillProposal`。项目级自动晋升必须通过回放评估和可回滚门禁；全局晋升必须跨项目验证并由管理员批准。
6. 每次运行固化 Skill key、digest、层级、得分和选择理由。已有运行永不受后续 Skill 修改影响。

## 不变式

1. Script 与 Novel 的风格 Skill、正文 Skill、审读 Skill 不跨域复用；仅平台诊断与治理机制共享。
2. Agent 不能同时担任 Skill 使用者、唯一评价者和发布者。
3. 项目私有规则不得自动进入全局 Skill，也不得包含其他项目事实。
4. Skill 冲突必须在运行前解析；无法解析时阻止运行并要求用户或治理策略裁决。
5. 自动生成的 Skill 内容默认是候选，不直接覆盖已发布版本。
6. 所有晋升、回滚、绑定变化和自动提案写入审计与产品事件。

## 结果

系统能够让不同作品和不同角色使用不同的创作方法，同时保留确定性、解释性和回滚能力。代价是需要增加 CreativeProfile、SkillPlan、评估与晋升生命周期，不能把“自我进化”简化为 Agent 修改自己的 Prompt。
