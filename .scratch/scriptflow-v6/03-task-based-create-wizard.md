# 03 · 四类任务式创建入口

- **Status**: ready-for-agent
- **Type**: feature
- **Blocked by**: 02
- **Blocks**: 04
- **Est**: M
- **Parent PRD**: docs/PRD-V6.md §核心用户旅程

## What to build

创建向导第一步改成四个用户任务。第二步按任务询问种子成熟度或 Source Canon，第三步收集题材、受众和风格并确认摘要。

## Acceptance criteria

- [ ] 四入口写入正确的双维度字段
- [ ] 原创接受 theme/pitch/synopsis/outline
- [ ] 改编要求 Source Canon 与使用权确认
- [ ] 不显示 video_prompt 新建入口
- [ ] 字段错误就近显示并给出修复方式
- [ ] 支持 Esc、焦点管理和键盘完成流程
- [ ] 组件测试覆盖四条任务和提交 payload
