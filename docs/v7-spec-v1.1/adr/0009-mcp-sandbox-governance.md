# ADR-0009：MCP 发现白名单与沙箱确认策略

- 状态：Accepted
- 日期：2026-07-20

## 决策

MCP Server 的完整连接配置使用与 Provider 凭据相同的认证加密，只向 Admin 返回去密后的公共摘要。发现结果先进入关闭的白名单，管理员逐项批准后才形成运行时可用工具。Server 断连时其工具自动不可用。MCP 与 Bash 默认需要用户确认，沙箱策略只有 `direct`、`sandbox`、`sandbox_confirm` 三档。

## 不变式

1. 未发现、未白名单、被禁用或 Server 非 connected 的 MCP 工具不得进入运行时。
2. MCP headers/env 不通过 API、日志或审计详情回显。
3. 连接测试失败必须记录可解释的状态与审计，但不得删除既有白名单。
4. 沙箱和确认策略修改只影响下一次运行快照。
