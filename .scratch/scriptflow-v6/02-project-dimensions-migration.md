# 02 · Project 双维度字段与兼容迁移

- **Status**: ready-for-agent
- **Type**: refactor / migration
- **Blocked by**: 01
- **Blocks**: 03, 04
- **Est**: M
- **Parent PRD**: docs/PRD-V6.md §项目模型

## What to build

为 Project 增加 `creation_source`、`delivery_medium`、`seed_maturity`，迁移并兼容现有字段。已有 video_prompt 项目保持可读取，新建 API 不再接受 video_prompt。

## Acceptance criteria

- [ ] Alembic migration up/down 有 fixture 测试
- [ ] 字段映射符合 ADR-0004
- [ ] legacy video_prompt 可读但不能新建
- [ ] Project API 返回新字段并过渡兼容旧字段
- [ ] owner isolation 继续通过

## Notes

真实数据迁移前先备份数据库。本 slice 不删除旧列。
