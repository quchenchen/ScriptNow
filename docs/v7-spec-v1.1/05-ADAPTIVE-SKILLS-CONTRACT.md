# V7 自适应 Skills 产品与领域契约

## 1. CreativeProfile

CreativeProfile 是创意收束后的平台投影，至少包含：

- `medium`：novel / script
- `genres`：题材标签
- `themes`：主题与伦理矛盾
- `styles`：语言、视觉和情绪风格
- `structures`：叙事结构
- `pov`：视角
- `audience`：目标受众
- `constraints`：用户明确禁用与必须保留规则
- `source_revision`：来源领域事实版本
- `confidence`：字段置信度，低置信度不得触发强覆盖

CreativeProfile 只从用户输入和已采纳事实生成。聊天推测、未采纳候选和 Agent 私有记忆不得直接进入。

## 2. Skill 元数据

每个 SKILL.md 除 `name/description` 外允许声明：

```yaml
roles: [writer]
stages: [writing, revision]
genres: [science-fiction]
themes: [human-ai-relationship]
styles: [restrained, cold]
structures: [save-the-cat]
selection_priority: 50
```

缺少匹配元数据的 Skill 只能通过核心角色绑定装配，不能被语义猜测自动选中。

## 3. SkillPlan

SkillPlan 是一次运行的不可变能力清单：

- `role_key / stage / medium`
- `creative_profile_fingerprint`
- `selections[]`：skill key、digest、layer、score、reasons
- `rejected_conflicts[]`
- `resolver_version`
- `token_budget`

运行配置快照必须内嵌 SkillPlan。管理后台和 Creator Dock 可以解释“为何选择”。

## 4. 调度职责

| 主体 | 职责 |
|---|---|
| WorkflowOrchestrator | 判断阶段、任务依赖、执行角色和完成条件 |
| SkillResolver | 根据硬规则和 CreativeProfile 生成 SkillPlan |
| Director | 收束 CreativeProfile 候选并请求用户采纳 |
| Architect | 将 CreativeProfile 转换为结构与连续性约束 |
| Writer | 消费 SkillPlan 写作，不发布 Skill |
| Reviewer | 评价作品并产生能力缺口证据 |
| SkillCurator | 汇总重复纠偏，产出 SkillProposal |
| 管理员/评估门禁 | 全局发布、灰度、回滚 |

## 5. 进化级别

- L0 运行策略：自动生成，运行结束失效。
- L1 项目 Overlay 提案：允许自动产生，用户可见、可删除。
- L2 项目 Skill 版本：通过新旧版本回放后可灰度启用。
- L3 全局 Skill：跨项目匿名化评估并人工批准。

## 6. 评价门禁

至少比较：采纳率、返工率、连续性缺陷、风格偏离、用户撤销率、token 成本和领域事实破坏数。任何候选只要修改已采纳事实、跨域引用或降低安全边界，直接淘汰。
