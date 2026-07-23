# ADR-0005：领域独立导出与可逆快照

- 状态：Accepted
- 日期：2026-07-20

## 背景

P7 要求 Script 与 Novel 都能生成 DOCX、保存手动快照并回滚，同时 V7 明确禁止两个产品领域复用正文、格式或导出模块。导出任务还必须可幂等重试，回滚不得覆盖历史正文。

## 决策

1. Script 与 Novel 分别拥有导出器、导出 manifest 表、快照正文表和回滚服务；任一领域模块不得导入另一领域的正文契约。
2. 平台层 `project_snapshots` 只保存租户范围、媒介、版本、范围和内容 hash 等元数据。正文副本分别进入 `script_snapshot_contents` 与 `novel_snapshot_contents`。
3. 导出 manifest 固定范围、形态与领域格式，并以 `(project_id, idempotency_key)` 去重。失败保留 manifest，重试增加 attempts，成功 artifact 以 SHA-256 校验。
4. 回滚以当前内容 hash 为并发前置条件，为每个创作单元生成并采纳新的正文 revision；旧 revision 和旧 snapshot 均不可变。因此回滚结果可再次保存并回滚。
5. 备份包由数据库与 workspace 文件组成，manifest 对每个成员记录 hash；恢复前必须完整校验，禁止部分恢复。

## 结果

- 格式规则和正文类型不会跨域污染。
- 快照列表可共享平台投影，但内容和回滚规则保持领域独立。
- 导出重试与回滚冲突可以通过稳定契约自动测试。
