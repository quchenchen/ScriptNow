# P0-03 平台安全与租户隔离

- Label: ready-for-agent
- Status: contract-complete-implementation-pending-p1

## 验收

- 服务端 tenant scope 覆盖数据库、工作区、RAG、记忆和 AgentState。
- 双租户负向测试无法读取或修改对方任何对象。
- 会话具备 HttpOnly、SameSite、CSRF、撤销、限流和安全密码哈希。
- Provider/MCP 凭据使用带认证加密和密钥版本，API 不回显。
- 管理操作统一写入不可变审计日志。

## 已完成

- V7 ADR-0002 冻结可信 TenantContext、会话、CSRF、凭据与上传边界。
- `TenantScopedStore` executable contract 与三类双租户负向测试。

## P1 实施项

- SQL repository 复合 tenant 查询与约束。
- Access/refresh/CSRF/session-family 实现。
- AEAD secret store、上传隔离与 admin audit log。
