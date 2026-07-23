# ScriptFlow V6 产品蓝图

- **Status**: Accepted as product design source of truth
- **Date**: 2026-07-16
- **Audience**: 产品、设计、研发、Agent prompt 设计
- **Depends on**: [`PRD-V6.md`](../PRD-V6.md)、ADR-0004、ADR-0005

## 产品不是生成器，而是创作控制台

ScriptFlow 的核心任务不是替用户一次性写完作品，而是让用户能指挥一个持续理解故事、维护结构、提交候选、解释影响并接受审美判断的 Agent Team。

产品价值由三层组成：

| 层级 | 用户获得的价值 | 产品证明 |
|---|---|---|
| 创作推进 | 从模糊想法走到下一份可用产出 | 候选、Story Beat、Scene/Chapter |
| 创作控制 | 用户能编辑、比较、接受、拒绝、回滚 | Revision、diff、Branch、决策 Inbox |
| 创作连续性 | 人物、世界、来源和风格不会每轮重置 | Story Core、Source Canon、Growth Tree |

一句话价值主张：

> 你掌握故事方向和审美，AI 创作团队负责让作品持续向前生长，而且每一步都可追溯、可编辑、可推翻。

## 服务对象与关键场景

V6 首要服务独立叙事创作者。他们通常同时承担策划、编剧、编辑和审稿工作，最大的困难不是缺少一段生成文字，而是创作跨度长、上下文容易丢失、全量重写成本高、改编决策难以解释。

V6 以两条深路径验证产品：原创剧本和小说改编剧本。原创小说与改编小说进入同一产品体系，但暂时只承诺基础 Story Core、Chapter Editor 和 Revision。

## 用户与 Agent 的权责边界

### 用户拥有最终决定权

- 采用哪个 Idea、Structure 或 Branch
- 是否改变人物、世界规则和重要 Story Beat
- 是否接受 AI 修改或 Cascade 建议
- 改编项目中哪些内容保留、合并、删除或原创
- 哪个 Revision 成为当前采用版本

### Agent 可以自主执行

- 在已确认目标内研究、检索和生成候选
- 维护结构化资产和引用
- 执行格式、一致性、风格和改编审查
- 计算影响范围并提出修订方案
- 在不覆盖已采用内容的前提下创建草稿或 Branch

### Agent 不得静默执行

- 覆盖用户正文
- 修改已冻结 Story Core
- 接受自己的审查建议
- 删除 Source Canon 或 Manuscript
- 把用户偏好同步为跨用户数据

## 产品核心对象

### Project

创作容器，记录 Creation Source、Delivery Medium、当前采用 Branch、目标与项目级风格。

### Story Core

故事的共享事实与结构。World、Character、Relationship、Timeline、Plot Thread、Foreshadow 和 Story Beat 在这里维护，不隶属于某个阶段。

### Manuscript

用户实际阅读、编辑和导出的正文。Script 使用 Episode/Scene；Novel 使用 Volume/Chapter。

### Source Canon

改编依据。它不仅是上传文件，还包括章节、片段、解析状态、引用和失效关系。

### Revision 与 Branch

Revision 是一次可比较的修改；Branch 是替代方向。任何 AI 重写先形成 Revision 或 Branch，不直接成为当前采用内容。

### Agent Task 与 Decision

Agent Task 表示团队正在做什么；Decision 表示需要用户拍板什么。聊天消息不是任务和决策的唯一存储形态。

## 三种工作模式

### 专注创作

默认模式。用户在作品目录中定位 Chapter/Episode/Scene，在编辑器中写作，通过选区、边注和可收起状态与 Agent 协作。

### 故事规划

维护 Story Core，并从当前对象查看来源、人物、Story Beat、伏笔、血缘和下游影响。它不是“资产提取阶段”，也不是默认展开的全局关系大图。

### 审阅决策

集中处理 Ralph Loop、Revision、Decision、格式、风格、一致性、来源忠实度和 Cascade。问题可以定位到正文，也可以指向上游 Story Core。

### 上下文工具

完整版本历史、Branch、Growth Tree、Source Canon 管理和项目设置从当前对象或项目菜单进入。工具打开后保留返回来源，不成为新的日常工作模式。

### 交付入口

导出从项目级“交付”入口进入。用户选择范围、格式和当前采用版本，运行导出前检查，并形成可重复下载的 Export Job。

## 核心任务模型

每个主要创作动作遵循同一交互循环：

```text
提出目标 → Agent 展示计划/上下文 → 产出候选或 Revision
→ 用户比较/编辑 → 用户采用或拒绝 → 系统记录血缘与偏好
```

这个循环同时适用于 Idea、Structure、Scene、Chapter、改编映射和审查修订。只有“输出对象”和“审查标准”不同，控制逻辑不应重复实现。

## 产品首页的工作

Dashboard 不展示虚假的统一进度。每个项目卡只回答四个问题：

1. 上次写到哪里？
2. 下一步建议是什么？
3. 是否有必须处理的风险或决策？
4. Agent Team 是否正在工作？

默认主操作是“继续创作”，而不是打开一个抽象阶段。

## 产品差异化

ScriptFlow 不以模型数量、单次生成长度或模板数量作为主要差异化。核心优势来自：

- 同一 Story Core 跨小说与剧本复用
- 原创与改编使用同一套创作控制逻辑
- AI 修改先进入 Revision，用户可以比较和拍板
- Source Reference 让改编不再是黑盒改写
- Growth Tree 与 Cascade 让长期创作保持连续
- Agent Activity 让“团队协作”成为可见过程

## 设计不变量

详细的人机协作规则以 [`V6-HUMAN-AI-INTERACTION-CONSTITUTION.md`](./V6-HUMAN-AI-INTERACTION-CONSTITUTION.md) 为准。产品评审必须同时检查作品主语、AI 自主级别、打断理由、证据、影响、恢复与撤销。

以下约束在任何页面和新功能中都成立：

- 正文始终比 Agent 对话更重要，编辑器占据视觉中心。
- 一个页面只有一个主要任务和一个高强调主操作。
- 生成不是结束状态；必须落到可编辑对象。
- AI 修改不静默覆盖采用版本。
- 风险必须能定位到对象，并给出下一步。
- 来源、版本、审查结果都可追溯。
- 媒介术语必须准确：小说不显示 EP，剧本不显示 Chapter。
- 长期状态必须进入 URL、数据库或 Revision，不藏在临时组件状态中。

## V6 成功的产品证据

V6 不是以“所有页面完成”验收，而以两段真实创作证据验收：一位用户能从一句话灵感完成 3 集原创剧本；一位用户能从小说 Source Canon 完成 3 个可追溯的改编 Scene。两条路径中，用户都能直接编辑正文、比较 AI 修改、拒绝建议、回到来源并成功导出。
