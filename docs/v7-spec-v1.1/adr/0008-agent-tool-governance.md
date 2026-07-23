# ADR-0008：Agent 模板版本与 ToolGroup 挂载治理

- 状态：Accepted
- 日期：2026-07-20

## 决策

Agent 模板继续采用不可变版本记录；草稿发布时只改变发布指针语义，运行开始后把模板版本与能力清单写入 `runtime_config_snapshots`。ToolGroup 是平台层能力集合，挂载矩阵只引用角色和 ToolGroup，不引用 Script 或 Novel 领域实现。禁用 ToolGroup 或挂载只影响下一次运行。

## 不变式

1. 一个角色可以保留多个历史发布版本，运行只解析最新发布版本，历史运行永远读取既有快照。
2. ToolGroup 必须同时通过平台启用、挂载启用和租户 Tier 三重检查，才可进入运行快照。
3. 管理端发布、回滚、ToolGroup 配置和挂载修改全部写入统一平台审计。
4. Script 与 Novel 工具实现保持独立；ToolGroup 只保存稳定的工具 key。
