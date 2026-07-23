# V7 ADR-0002：可信租户上下文与会话边界

- Status: Accepted
- Date: 2026-07-18
- Scope: V7 only

## Context

V7 的项目、AgentState、事件、计量、记忆、RAG 与工作区都属于租户数据。若 tenant_id 由请求体、URL 查询参数或前端 store 决定，任何遗漏过滤条件都会成为 IDOR 越权漏洞。

## Decision

### Trusted Tenant Context

- tenant/user 身份只由服务端认证中间件解析并注入。
- repository/service 方法必须显式接收 `TenantContext`；不得提供无 tenant 参数的租户数据查询。
- 请求体中的 tenant_id 一律拒绝或忽略，不作为授权依据。
- 外部对象 ID 使用 UUID；查询其他租户对象返回同样的 Not Found，避免存在性泄漏。
- 数据库层使用 `(tenant_id, id)` 复合查询、外键和唯一约束；后台跨租户查询使用独立 AdminContext API。

### Session

- Access JWT：短时、HttpOnly、Secure、SameSite=Lax，包含 issuer/audience/session/user/tenant/exp/jti。
- Refresh token：256-bit 随机不透明值，仅保存哈希；每次刷新旋转，检测旧 token 复用后撤销整个 session family。
- 所有非安全 HTTP 方法要求双提交 CSRF token；登录、刷新和敏感 Admin 操作同时限流。
- 注销、停用租户、密码变更和管理员强制退出均撤销 server-side session。
- Creator 与 Admin 使用不同 audience 与权限依赖；普通 Creator token 不能调用 Admin API。

### Credentials

- Provider Key 与 MCP headers/env 进入统一 secret store，不保存在普通 config JSON。
- 使用 AES-GCM 等 AEAD；每条密文保存 key version、nonce、ciphertext、tag 和关联对象上下文。
- 主密钥来自部署环境或密钥服务；API 只返回 configured/masked 状态，不返回可逆密文或明文。

### Upload and Workspace

- 扩展名不是类型证据；服务端执行 MIME/签名嗅探、文件数/大小/解压体积配额。
- DOCX/PDF/TXT 解析不执行宏、脚本或外部引用；解析失败进入隔离态。
- 所有文件路径由 `(tenant_id, project_id, generated filename)` 生成；用户文件名只作显示元数据。
- LocalWorkspace 仅用于开发；生产工具在 Docker/runtime 环境门通过前保持默认拒绝。

## Consequences

- repository API 略显冗长，但 tenant scope 无法被调用者“忘记”。
- Admin 跨租户能力必须走显式高权限路径并完整审计。
- 会话刷新需要持久化 session family，但可以可靠注销和检测重放。
