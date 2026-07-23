# 05 · Dashboard 真实进度与状态

- **Status**: ready-for-agent
- **Type**: feature
- **Blocked by**: 04
- **Blocks**: —
- **Est**: S-M
- **Parent PRD**: docs/PRD-V6.md §P0 项目与工作台

## What to build

移除伪百分比。项目卡分别显示 Manuscript 数量进度、质量状态、风险数和 Agent 状态；缺数据时显示明确空态。

## Acceptance criteria

- [ ] Script 使用 Episode，Novel 使用 Chapter
- [ ] 未设置目标时只显示实际数量
- [ ] human_review_needed、dirty、解析失败风险可见
- [ ] Agent working/waiting/idle 有明确文案
- [ ] 删除操作对键盘和触屏可发现
- [ ] 组件测试覆盖 novel/script/empty/risk
