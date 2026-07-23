# 11 · 上下文指令器与创作章程

- **Status**: done
- **Type**: product / backend / frontend
- **Blocked by**: 10
- **Blocks**: Agent Activity, Story Core Editor
- **Est**: M
- **Parent PRD**: docs/PRD-V6.md

## What to build

拆除悬浮的万能导演控制台。指令必须绑定 Project、Manuscript Unit 或 Agent Task，并声明有效期；分别从正文、故事规划和审阅决策进入。

## Acceptance criteria

- [x] 指令显示目标对象、有效期和将读取的上下文
- [x] Scene/Chapter 指令从正文内部创建
- [x] 项目长期规则从故事规划创建
- [x] Agent Task 返工指令从审阅决策创建
- [x] Context Pack 保存目标元数据
- [x] 不再显示全局悬浮导演控制台
- [x] 前后端回归通过
