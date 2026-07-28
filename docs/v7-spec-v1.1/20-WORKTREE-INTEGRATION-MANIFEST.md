# 当前工作树集成清单

| | |
|---|---|
| 日期 | 2026-07-29 |
| 对应产品版本 | `0.2.0` 开发预览 |
| 目的 | 记录跨层升级的集成边界、验证证据和未通过项 |
| 状态 | 自动化门禁已通过；真实 Provider 黄金回放仍有未完成领域 |

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

## 3. 已完成的集成序列

| 顺序 | 提交 | 主题 | 主要范围 | 验证 |
|---:|---|---|---|---|
| 1 | `f377750` | 建立可恢复创作运行内核 | migration、platform、AgentScope/Dock、四领域入口与 public API 测试 | 空库迁移、后端全量测试、Ruff |
| 2 | `767e8da` | 建立四领域黄金审计基线 | golden fixtures、真实证据采集、审计脚本与回放测试 | 18 项黄金契约测试、Ruff |
| 3 | `b51ed6a` | 统一创作搭档运行状态交互 | Creator/Admin stores、components、shared messages 与样式 | 55 项前端测试、双 SPA 类型检查与构建 |
| 4 | 当前版本整理 | 更新 v1.1 规格与工作树治理 | docs 14—22、版本记录、归档索引、忽略规则 | 链接扫描、全量门禁、diff check |

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

2026-07-29 版本整理前的最近一次完整自动化门禁为：

- 后端 `315 passed`；
- 前端 `55 passed`；
- Ruff、Creator/Admin 类型检查与构建通过；
- `git diff --check` 通过。

版本整理后的最终复跑结果记录在 [`RELEASE-NOTES.md`](./RELEASE-NOTES.md)。

真实 Provider 回放不属于可被单元测试替代的门禁。当前 Novel、Script、Translation、
Recreation 均仍有至少一个未完成阶段，因此 `0.2.0` 明确保持“开发预览”，不得标记为
Release Candidate。

## 5. 暂不随本轮主线提交

- 产品化 CLI 与外部 Agent 适配器；
- 未通过退出门的受控 Dreaming 自动发布；
- 用兜底文本掩盖结构化输出失败的“降级成功”；
- 为测试方便而写死的模型、章节数、字数、预算、市场或业务策略。

## 6. 仓库边界

- 唯一可执行产品目录为 `scriptnow/`。
- 唯一现行规格目录为 `docs/v7-spec-v1.1/`。
- 历史研究和阶段审计统一位于 `docs/archive/`，不得被运行时代码导入。
- 用户素材、数据库快照和运行日志只允许进入本机 `.local/` 或其他 Git 忽略目录。
- 当前版本与验证结果以 [`RELEASE-NOTES.md`](./RELEASE-NOTES.md) 为准。
