# 06 · 前端 Vitest 标准测试基线

- **Status**: ready-for-agent
- **Type**: chore / test
- **Blocked by**: 01
- **Blocks**: 04
- **Est**: S
- **Parent PRD**: docs/PRD-V6.md §Release Gate

## What to build

补齐标准 test scripts、jsdom、Vue Test Utils 和 API mock 设置，把已有测试纳入标准命令并增加 App 冒烟测试。

## Acceptance criteria

- [ ] `npm run test` 非交互执行
- [ ] 已有 useWorkflowGraph test 被执行
- [ ] App/Router 冒烟测试通过
- [ ] 测试不访问真实网络或开发服务器
- [ ] build 与 test 均通过
