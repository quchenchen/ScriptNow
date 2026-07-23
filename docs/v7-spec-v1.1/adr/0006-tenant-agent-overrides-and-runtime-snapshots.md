# ADR-0006：项目级 Agent 覆盖与运行快照

- 状态：Accepted
- 日期：2026-07-20
- 关联：PRD §2.1、§3.11，Development Plan P8.2

## 背景

Creator 需要为当前项目微调 Agent 名称、Soul 和模型，但系统模板仍由平台管理员统一发布。若覆盖只保存在浏览器，或在运行时直接读取会变化的配置，就无法证明某次产出实际使用了哪套能力，也无法安全回放。

## 决策

1. 新增 `tenant_agent_configs`，以 `tenant_id + project_id + role_key` 唯一约束保存项目级覆盖；不在 Script 或 Novel 领域表内保存平台 Agent 配置。
2. 系统模板 Soul 始终保留，项目 `soul_override` 以附加约束合并，不允许替换系统安全与能力边界。
3. 模型覆盖必须通过 Creator 可见性公式校验；禁用、Provider 断连或等级不足的模型不得保存。
4. `AgentFactory` 在创建下一次运行快照时解析覆盖，并把 `tenant_agent_config_id`、最终名称、合并 Soul 和模型版本写入不可变 `runtime_config_snapshots`。运行开始后配置变化不影响该次运行。
5. “恢复默认”删除覆盖记录，而不是写入一份复制的默认值；后续运行重新继承最新已发布系统模板。
6. 所有读取和写入都由服务端会话解析 `tenant_id`，写操作要求 CSRF 并进入审计日志。

## 后果

- 系统模板发布与租户个性化可以独立演进，同时每次运行仍可追溯。
- Script 与 Novel 只共享平台 Agent 装配机制，不共享任何正文或写作领域模型。
- 后续 Admin 发布模板、回滚版本时，无需批量重写租户覆盖；只有下一次运行快照会采纳新默认值。
