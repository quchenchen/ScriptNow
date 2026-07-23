# P0-01 固化 V7 基线与工程边界

- Label: ready-for-agent
- Status: completed
- Source: `docs/v7-spec-v1.1/`

## 验收

- V7 新代码目录和 platform/script/novel 依赖方向明确。
- Script 与 Novel 领域模块不能互相 import。
- 根 README 与 AGENTS 只把 v1.1 标为当前基线。
- 新 ADR 使用未占用编号或独立的 V7 ADR 目录，不覆盖历史 ADR。

## 产出

- `scriptflow-v7/backend/src/scriptflow_v7/{platform,script,novel}`
- 后端 AST import 边界测试与 Script/Novel block 隔离测试
- `scriptflow-v7/frontend/apps/{creator,admin}` + `packages/shared`
- `docs/v7-spec-v1.1/adr/0001-modular-monolith-and-domain-isolation.md`
- 后端：4 tests passed，ruff passed
- 前端：Creator/Admin production build passed，npm audit 0 vulnerabilities
