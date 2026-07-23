# V7 动态创作规划契约

## 1. 产品原则

叙事结构是导航与诊断框架，不是不可变的内容模板。蓝图负责让创作在开始时“足够可写”，但不假设开始前能够穷尽全部角色、场景和情节。创作中出现的新需要必须能够生长，同时保持因果、连续性和用户决策可追溯。

系统区分三层事实：

1. **硬约束 Canon**：用户明确采纳的世界规则、人物身份、不可违背边界。任何 Agent 不得直接改写。
2. **弹性计划 Plan**：角色功能、地点、节拍、伏笔、场景目标。允许以候选形式增补、合并、移动或退场。
3. **局部发现 Local Discovery**：只在当前创作单元有效的群众角色、无名地点、动作细节。跨单元复用或影响因果时必须升级为蓝图锚点。

## 2. 结构 Skill 映射

创建向导的结构值必须进入 CreativeProfile，并装配对应领域 Architect 的结构执行规范。Script 与 Novel 使用独立参考，不共享节拍、场次或章节语义。

| value | 方法 | Script 主要产物 | Novel 主要产物 |
|---|---|---|---|
| `hero_journey` | 英雄之旅 | 可见行动门槛、试炼、归返 | 身份变化、价值归返 |
| `three_act` | 三幕结构 | 建立/对抗/解决与两个转折点 | 起势/深化/兑现与中点重构 |
| `five_act` | 五幕结构 | 引入/上升/高潮/下降/结局 | 五阶段压力与人物内在变化 |
| `save_the_cat` | 救猫咪 | 15 节拍及片长比例诊断 | 节拍功能按篇幅弹性映射 |
| `eight_sequence` | 八序列 | 八个有局部目标与高潮的序列 | 八段承诺—兑现链 |
| `harmon_circle` | 哈蒙圆环 | 舒适区到改变后的回归 | 欲望、适应、代价与新状态 |
| `freytag` | 弗雷塔格金字塔 | 戏剧高潮与下降动作 | 悲剧/舞台化因果弧线 |
| `custom` | 自定义 | 用户命名阶段、完成条件和比例 | 用户命名阶段、章级覆盖规则 |

结构 Skill 必须输出：阶段定义、必需节拍、可选节拍、完成条件、压缩规则、偏离诊断以及迁移映射。短篇可以压缩或合并节拍，但不能只删除其叙事功能。

## 3. 短篇的覆盖规划

短篇在进入写作前执行一次 `CoverageCheck`：

- 角色：每个有名字的角色必须有叙事功能、欲望、阻力关系、进入与退出位置。
- 场景/地点：每个地点必须承担冲突或信息功能；重复地点需说明状态变化。
- 情节：触发、承诺升级、中点变化、危机选择、高潮兑现、余波均有承载单元。
- 连续性：关键道具、人物知识、时间、空间移动和伤病均有来源。
- 经济性：可合并角色、重复场景、无状态变化的段落进入优化建议。

CoverageCheck 只产生 `ready / ready_with_risks / blocked` 和证据，不自动增加内容。

## 4. 创作中动态增补

Writer 或 Reviewer 发现内容缺口时创建 `CreativeChangeProposal`，不得直接写入蓝图：

```text
id · project_id · medium · base_blueprint_version · source_unit_id
operation(add|modify|merge|retire|move)
entity_type(character|location|event|foreshadow|world_rule|structure_beat)
rationale · trigger_evidence · proposed_payload
affected_units[] · affected_anchors[] · continuity_risks[]
structure_impact · scope(local|project) · status
author_role · skill_plan_fingerprint · created_at
```

处理链：

```text
Writer/Reviewer 发现需要
→ Architect 形成 1–3 个结构化方案
→ Impact Analyzer 计算影响范围
→ 用户采纳 / 要求修订 / 保持局部
→ 生成新蓝图版本
→ 受影响 StoryMap/正文标记 stale 或待复核
→ Writer 使用新 context pack 继续
```

## 5. 分级决策

- **局部自动**：无名群众、一次性地点陈设、不跨单元的动作细节，可由 Writer 使用并记录来源。
- **项目候选**：命名角色、复用地点、新世界规则、新主情节、新伏笔、结构节拍移动，必须由 Architect 提案并经用户采纳。
- **阻断确认**：改变已采纳结局、核心人物身份、主题命题、世界硬规则或叙事结构时，必须暂停受影响写作并显示完整影响。

## 6. 影响分析

每个候选必须展示：新增、修改、失效和保留的蓝图锚点；受影响的卷/章或集/场与已采纳正文；人物弧线、伏笔、知识边界和时间线冲突；结构节拍覆盖变化；最小修复、完整重排和不采纳的代价。

采纳永远创建新版本。旧版本与事件保留，可比较、可回滚；下游内容只标记 stale，不静默删除。

## 7. Agent 与 Skill 职责

| 主体 | 职责 |
|---|---|
| Director | 核心方向、主题或结局根本变化时重新收束 StoryCore |
| Architect | 管理蓝图、结构节拍和 CreativeChangeProposal |
| Writer | 发现并举证内容需要；只处理局部发现，不直接改全局事实 |
| Reviewer | 检查新增内容造成的连续性、结构、人物功能或冗余问题 |
| SkillResolver | 按 medium、structure、stage、proposal entity type 装配 SkillPlan |
| 用户 | 对项目级和阻断级变更拥有最终决定权 |

## 8. Creator 交互

蓝图和 StoryMap 顶部增加“计划健康度”；Writer 出现内容需要时在 Dock 显示“发现创作缺口”，可一键转为提案。提案抽屉包含变更前后、原因、影响对象、Agent/Skill 来源，以及采纳、反馈修订、保持局部三个动作。结构选择旁显示“已装配的结构 Skill”，并允许在蓝图阶段发起结构迁移。

## 9. 验收不变式

1. Agent 不能静默创建跨单元全局事实。
2. 每个全局新增项可追溯到证据、角色、SkillPlan 和用户决定。
3. 旧蓝图版本不可覆盖；受影响正文不会自动删除。
4. Script 与 Novel 的影响分析使用各自领域单位。
5. 同一项目同一聚合同时只有一个 active 变更候选。
6. 结构迁移后所有已采纳单元都有 mapped、stale 或 explicitly_retained 状态。
