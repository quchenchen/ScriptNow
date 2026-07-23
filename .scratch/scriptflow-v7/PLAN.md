# ScriptFlow V7 执行计划索引

完整 WBS、测试体系和 RC 门槛：`docs/v7-spec-v1.1/03-DEVELOPMENT-PLAN.md`。

## 当前

- P0.1–P0.7：本地可执行契约与风险验证完成
- 外部环境门：Studio/agentscope-runtime 未安装，Docker daemon 未运行；启用生产沙箱前必须补验
- P1：进行中，下一切片为 DB/session/tenant API vertical slice

## 阶段入口

| 阶段 | Issue | 前置门 |
|---|---|---|
| P0 | `01`–`06`，P0.3 合并在 `02` | 无 |
| P1 | `07-platform-trusted-core.md` | P0 全部完成 |
| P2 | `08-creator-shell.md` | P1 API vertical slice |
| P3 | `09-script-loop.md` | P2 项目创建 |
| P4 | `10-novel-loop.md` | P2 项目创建 |
| P5 | `11-revision-and-versioning.md` | P3/P4 基本写作闭环 |
| P6 | `12-agent-dock-and-recovery.md` | P1 run protocol + P5 candidate |
| P7 | `13-export-snapshot-restore.md` | P3/P4/P5 |
| P8 | `14-commercial-and-admin.md` | P1 治理服务 + Creator 主链路 |
| P9/RC | `15-hardening-and-rc.md` | P2–P8 全部阶段出口通过 |

一次只推进当前最前置的未完成 issue。
