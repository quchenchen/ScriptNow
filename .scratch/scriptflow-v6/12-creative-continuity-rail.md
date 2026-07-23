# 12 · 右侧创作协作与连续性栏

- **Status**: done
- **Type**: product / frontend
- **Blocked by**: 10, 11
- **Blocks**: Continuity Ledger, Agent Activity
- **Est**: M
- **Parent PRD**: docs/product/V6-UI-INTERACTION-SYSTEM.md

## What to build

恢复三栏创作工作台。右侧栏持续跟随当前 Project 与 Manuscript Unit，统一展示连续性、上下文指令、待决策事项和创作节点，并支持折叠与小屏抽屉降级。

## Acceptance criteria

- [x] 右栏显示当前作用对象和 Agent 状态
- [x] 连续性展示角色状态、开放线程和风险
- [x] 指令入口显示目标、有效期和 Context Pack 范围
- [x] 决策聚合 Story Core、Revision、Living Asset Candidate
- [x] 创作节点展示 Project → Story Core → Unit → Revision
- [x] 正文保持视觉中心，窄屏不产生横向溢出
- [x] 前端测试与构建通过
