# ADR-0014：受控 Dreaming 与经验进化

- 状态：Accepted
- 日期：2026-07-28

## 背景

ScriptNow 需要让每次人机对话、候选、决定、人工修订、作品结果和质量审读转化为后续创作
的可复用经验。仅追加会话摘要会造成重复、矛盾、过期和噪音；允许 Agent 在线修改 Prompt
或 Skill 又会破坏确定性、租户隔离、版权边界和可回滚性。

## 决策

1. 采用双速学习：在线 CreativeOperation 只形成 provenance 完整的
   `ExperienceEpisode`；离线 `DreamRun` 在只读工作区内跨 Episode 整合。
2. Dream 不修改输入存储，只产出版本化 `DreamResult`。结果分为 MemoryCandidate、
   PreferenceCandidate、SkillProposal 和 BenchmarkCandidate。
3. Session、Project、User、Tenant、Global 五级作用域必须显式声明。跨作用域前完成内容
   最小化、去标识、许可和近似复述检查。
4. 已采纳领域事实不由 Dream 覆盖；用户偏好必须可见、可修改、可删除；SkillProposal
   继续走 ADR-0011 的回放、shadow、canary、审批和回滚链。
5. AgentScope 负责实时 Agent 执行；Creative Session Protocol 提供 durable provenance；
   ScriptNow Dream Orchestrator 负责离线选择与治理。Dream 不是一次 reply 内的递归自改写。
6. 隐藏思维链不进入 ExperienceEpisode。可学习证据限于计划摘要、工具结果、领域产物、
   用户决定、人工修订差异、质量结果和稳定失败码。
7. 删除和撤回沿 provenance 传播。只由已删除内容支撑的派生候选必须失效。
8. 质量提升必须通过与未启用候选的基线比较证明，不能使用 Dream 自评作为唯一发布依据。

## 不变式

1. 未采纳候选、失败结果和 Agent 推测不得写成用户事实或项目事实。
2. 私有作品默认不贡献全局能力，也不得通过检索或 Skill 泄漏到其他项目。
3. Novel、Script、Translation 与 Recreation 只能共享平台治理机制，不能共享正文 Skill
   或领域产物契约。
4. 已开始运行固定使用原 SkillPlan digest；Dream 结果不修改在途运行。
5. Dream 失败不阻断在线创作，不覆盖原始 memory store，不产生伪成功。
6. 任何晋升都必须有来源证据、评测结果、批准主体、版本和回滚记录。

## 结果

系统可以从持续协作中获得可量化复利，同时保留事实边界、隐私、版权、解释性和可恢复性。
代价是需要新增 ExperienceEpisode、DreamRun、DreamResult、评测和删除传播机制，不能把
“系统进化”简化为自动追加记忆或在线自改 Prompt。
