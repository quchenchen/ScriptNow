# 当前工作树集成清单

| | |
|---|---|
| 日期 | 2026-07-28 |
| 目的 | 把当前大批量改动拆成可审查、可验证、可回滚的集成单元 |
| 状态 | 已完成分批集成，待全量门禁 |

## 1. 当前工作主题

当前工作树不是单一 UI 修复，而是一次跨层升级，主要包含：

1. Creative Session / Operation / Stage / ArtifactRef / Checkpoint / Decision 内核与迁移；
2. AgentScope `reply_stream()`、Block 事件、Dock 会话和确认通道；
3. Novel、Script、Translation、Recreation 四领域生成入口接入；
4. 黄金流程审计、诊断、证据采集与回放测试；
5. Creator/Admin 前端运行状态、领域流程和测试；
6. v1.1 规格、ADR、升级路线与全系统业务流程图。

## 2. 本地资产边界

审计截图、临时检查输出、演示 PPTX 和调试 NDJSON 已移出开发树，保存到：

```text
/Users/quchenchen/Documents/agent-script-platform-archives/
  2026-07-28-worktree-local-assets/
```

这些资产不进入 Git。`.artifacts/`、`.codex-tmp/` 与 `*.inspect.ndjson` 已加入忽略规则。

## 3. 实际提交序列

| 顺序 | 提交 | 主题 | 主要范围 | 验证 |
|---:|---|---|---|---|
| 1 | `f377750` | 建立可恢复创作运行内核 | migration、platform、AgentScope/Dock、四领域入口与 public API 测试 | 空库迁移、后端全量测试、Ruff |
| 2 | `767e8da` | 建立四领域黄金审计基线 | golden fixtures、真实证据采集、审计脚本与回放测试 | 18 项黄金契约测试、Ruff |
| 3 | `b51ed6a` | 统一创作搭档运行状态交互 | Creator/Admin stores、components、shared messages 与样式 | 55 项前端测试、双 SPA 类型检查与构建 |
| 4 | 当前提交 | 更新 v1.1 规格与工作树治理 | docs 14—20、ADR 0013/0014、PRD 修订、忽略规则 | 链接扫描、diff check |

实际集成考虑了模块强耦合关系：AgentScope/Dock 和四领域入口依赖同一 Creative Operation
契约，因此合并为一个可迁移、可测试的后端原子提交，而不是机械拆成不可运行的中间状态。
所有提交均按主题精确暂存，没有使用全量 `git add .`。

## 4. 全量集成门

```bash
make test
make lint
make build
git diff --check
```

此外必须验证：

- 空库 Alembic 升级和现存开发库升级；
- Novel、Script、Translation、Recreation 各一条黄金路径；
- timeout、cancel、contract invalid、刷新重连和重复确认；
- 运行成功后产物可读、血缘完整、Checkpoint 完整；
- 前端不展示 Pydantic、Provider 或 AgentScope 原始异常；
- Script 与 Novel 不出现跨域 DTO、Writer、包装或导出语义。

## 5. 暂不随本轮主线提交

- 产品化 CLI 与外部 Agent 适配器；
- 未通过退出门的受控 Dreaming 自动发布；
- 用兜底文本掩盖结构化输出失败的“降级成功”；
- 为测试方便而写死的模型、章节数、字数、预算、市场或业务策略。
