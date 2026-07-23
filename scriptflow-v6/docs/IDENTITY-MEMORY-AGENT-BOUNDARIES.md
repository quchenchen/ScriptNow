# 身份、项目、记忆与 Agent 隔离契约

## 1. 隔离主键

所有持久化对象必须能沿以下链路追溯，不允许只有模糊的 `memory_key`：

```text
User → Project → Artifact → Revision / Task / Decision
```

每个查询和写入必须携带 `user_id + project_id`。即使对象 ID 全局唯一，也不能省略所有权条件。越权访问统一返回 404，防止枚举。

## 2. 四类记忆

| 记忆层 | 作用域 | 内容 | 写入规则 |
|---|---|---|---|
| Project Truth | project | 已采用 Story Core、Source Canon、Manuscript、Decision | 只能由明确领域动作写入；最高可信 |
| Project Working Memory | project + task | Task 摘要、Checkpoint、开放问题、临时假设 | Task 完成后归档；不能覆盖作品事实 |
| User Preference | user | 用户主动保存或稳定确认的创作/协作偏好 | 跨项目可读；项目规则优先 |
| Agent Runtime Memory | user + project + agent + session | 短期对话、工具结果和执行轨迹 | 有 TTL；不直接成为 Story Core |

禁止跨用户检索。跨项目记忆默认关闭，只有 User Preference 可以按明确规则跨项目读取。

## 3. 记忆检索优先级

```text
Frozen / Adopted Project Truth
→ 当前 Artifact 与相邻 Story Map
→ 当前 Task Working Memory
→ 用户已确认 Preference
→ 相关历史协作摘要
```

发生冲突时，高层覆盖低层；Agent 必须把冲突作为 Alert 或 Decision，而不是自行拼接出“折中事实”。检索结果记录来源、作用域、版本和纳入原因。

## 4. Agent 能力隔离

Agent 不是拥有全部数据库权限的聊天角色。每个 Agent Profile 声明：

- `responsibility`：负责什么。
- `allowed_skills`：可激活哪些 Skill 版本。
- `allowed_tools`：可调用哪些领域工具。
- `read_scopes`：可读取哪些 Context Pack 槽位。
- `write_scopes`：可创建哪些 Candidate Artifact。
- `autonomy_ceiling`：最高 A0–A4 等级。

审稿人可以创建 Review 与 Revision Candidate，但不能 Adopt；写作者可以创建 Manuscript Candidate，但不能修改 Frozen Story Core；任何 Agent 都不能跨项目读写。

## 5. Skill 隔离与升级

- Skill Registry 按版本保存，Task 锁定实际使用版本。
- 项目可以 pin Skill/Craft Profile 版本，平台升级不能静默改变在写作品。
- Reference Pack 按需读取，并进入 Context Pack 使用记录。
- 新版本先跑 Golden Project；未通过回归不得设为默认。
- 允许同一用户在新 Project 试用新版本，旧 Project 保持原版本。

## 6. 可删除与可迁移

- 用户删除项目时，项目事实、工作记忆、运行记忆和索引按项目级清理；User Preference 不被误删。
- 用户可以查看、修改和清除个人偏好。
- Memory 必须支持导出来源和删除审计，不能成为不可解释的黑箱向量库。
- Embedding 只是派生索引，原始结构化事实才是事实源；索引可重建。

## 7. 必须通过的测试

1. User A 无法读取或修改 User B 的 Project、Revision、Task、Decision 和 Memory。
2. 同一 User 的 Project A 不会检索 Project B 的 Working/Runtime Memory。
3. User Preference 可跨项目读取，但 Project Preference 能覆盖它。
4. Review Agent 无权 Adopt 自己的 Candidate。
5. Skill 升级不改变已 pin 的 Project。
6. Task 重试使用原 Context Pack 和 Skill 版本，除非用户明确重新规划。
7. 删除 Project 后无法通过向量索引召回其内容。

这些测试进入下一开发 slice，在通过前不得宣称“多用户记忆隔离完成”。
