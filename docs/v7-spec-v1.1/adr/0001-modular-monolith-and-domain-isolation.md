# V7 ADR-0001：模块化单体与 Script/Novel 领域隔离

- Status: Accepted
- Date: 2026-07-18
- Scope: V7 only

## Context

V7 是全新产品，但当前团队和交付阶段不需要承担微服务的部署、网络一致性与运维成本。同时，Script 与 Novel 的正文、目录、Writer、审读、格式和导出契约不能继续混用。

## Decision

后端采用模块化单体，一个 FastAPI composition root 组装三个源码区域：

- `platform`：认证、租户、事件、计量、AgentScope 运行时、权限、文件与观测。
- `script`：剧本领域。
- `novel`：小说领域。

允许依赖：

```text
app → platform
app → script → platform
app → novel  → platform
```

禁止：

- `platform → script|novel`
- `script ↔ novel`
- V7 直接导入 `scriptflow_v6` 或根目录旧应用

前端采用 npm workspaces：Creator SPA 与 Admin SPA 独立构建；`packages/shared` 只能包含无领域语义的 UI、传输和基础类型。领域组件留在所属 SPA/领域包内。

依赖边界通过自动化测试执行，不只依赖代码评审约定。

## Consequences

- 当前仍保持单次部署和本地事务，开发与调试成本低。
- Script/Novel 可以独立演化，不因“复用”被迫共享错误抽象。
- 将来若某领域需要独立扩缩容，可从稳定模块边界拆服务。
- composition root 可以依赖所有领域，因此必须保持薄层，只负责装配和路由。
