# Domain Docs — Single Context

本项目是 **single-context**：全项目共享同一份领域语言。

## 主要文件

- **[`CONTEXT.md`](../../CONTEXT.md)** — 领域词汇表 + 核心隐喻 + 反面示例。每次改代码前先扫一眼相关术语。
- **[`docs/adr/`](../adr/)** — 架构决策记录。按 `NNNN-slug.md` 编号，记录"为什么这么设计"。

## 使用规则

### 添加术语

- 遇到 CONTEXT.md 里没有的领域概念 → 先加进去再写代码
- 不要在代码里使用未定义术语，即使"当前显而易见"

### 与 CONTEXT.md 冲突

- 现有代码用了旧术语（如 `role` / `pipeline`）→ 逐步替换成 CONTEXT.md 里的正名（如 `character` / `growth_tree`）
- 替换动作可以在任何 refactor slice 顺便做，不需要独立 issue，但需要在 commit message 里提

### 添加 ADR

- 触发条件：架构级决策（数据模型、模块划分、Agent 编排方式、跨模块 API 契约）
- 编号：`docs/adr/NNNN-<slug>.md`，从 0001 递增
- 格式：Michael Nygard 风格 —— Status / Context / Decision / Consequences / Alternatives Considered
- 现有 ADR 想推翻 → 写新 ADR，`Supersedes: ADR-XXXX`，旧 ADR 改 Status 为 `Superseded by ADR-YYYY`

### 不做多 context

如果未来 backend 和 frontend 需要各自的领域词汇（不太可能，因为它们服务同一个产品），再考虑升级到 multi-context（`CONTEXT-MAP.md` + 每层各自 CONTEXT.md）。
