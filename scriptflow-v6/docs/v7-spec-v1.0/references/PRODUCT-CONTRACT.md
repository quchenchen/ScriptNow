# V6 开发契约

1. 作品对象是界面与 API 的主语，Agent 不是。
2. AI 只能创建 Candidate Revision，不能直接覆盖 Adopted Revision。
3. 每次修改记录目标、范围、依据、保留项、约束和基线。
4. 基线变化后 Candidate 进入 Stale，重新比较前禁止采用。
5. 用户采用、拒绝和撤销是明确的领域动作，不是聊天消息。
6. 新代码不得导入仓库旧版应用模块。
7. 身份、项目、记忆和 Agent 权限遵循 [`IDENTITY-MEMORY-AGENT-BOUNDARIES.md`](./IDENTITY-MEMORY-AGENT-BOUNDARIES.md)；隔离测试通过前不开放真实用户数据。
8. 创建 Project 必须真实创建首个 AgentTask；没有持久化 Task 时，UI 不得显示“已排队”或“正在工作”。
9. 创作模型由平台统一路由；普通用户不能配置 Provider、模型或密钥，只能看到能力等级、额度、任务状态与交付质量。
