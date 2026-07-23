# ScriptFlow V6 UI Demo 说明

- **Status**: Accepted demo baseline
- **Date**: 2026-07-16
- **Demo**: [`design/scriptflow-v6-ui-demo.html`](../../design/scriptflow-v6-ui-demo.html)
- **Depends on**: [`V6-PRODUCT-BLUEPRINT.md`](./V6-PRODUCT-BLUEPRINT.md)、[`V6-UI-INTERACTION-SYSTEM.md`](./V6-UI-INTERACTION-SYSTEM.md)

## 设计命题

这套 Demo 使用主流桌面创作工具的稳定结构：Dashboard 负责恢复工作，项目工作台采用目录、编辑器、协作区三栏布局，一级空间使用清晰导航，长任务进入持久 Activity。差异化不依赖夸张视觉，而来自 ScriptFlow 的产品价值被转译为可感知行为。

| 产品价值 | Demo 中的交互表达 |
|---|---|
| 生长，而非拼装 | Dashboard 文案、Creation Journey、Story Core 到 Manuscript 的连续入口 |
| 用户是总指挥 | Agent 修改先进入候选 Revision，提供采用、拒绝与保持当前版本 |
| AI 团队协作 | 右侧展示具名成员、Task、Delivery、Decision 与证据 |
| 有机连续性 | 正文 lineage 面包屑、版本与血缘空间、Branch 与 Cascade |
| Living Story Core | 故事世界独立空间，人物、关系、情节线和时间线跨阶段存在 |
| 可持续打磨 | 正文直接编辑、自动保存、局部 AI 工具、diff drawer |
| 改编可解释 | Source Canon、来源引用、Adaptation Map 语义和忠实度审查 |

## 视觉策略

界面采用“安静的编辑器 + 有生命的状态信号”。正文纸张保持克制、清晰和高可读性；生长、运行和风险只使用少量稳定色彩编码，不把每个对象做成彩色卡片。品牌标识使用种子/新芽的微型几何符号，避免直接套用机器人或魔法星星作为核心隐喻。

圆角、间距和细边框遵循现代桌面 SaaS 的成熟密度；差异化集中在纸张的非对称页角、live orbit、血缘节点和候选 Revision 交互。动画仅服务状态变化，尊重 reduced motion。

## 已覆盖页面与状态

### Dashboard

- 继续上次创作
- 项目实际状态、待决策、Agent 状态
- 原创小说、原创剧本、小说改编剧本三种项目卡
- 新建创作入口

### 四步创建流程

1. 选择原创/改编与小说/剧本目标
2. 输入创作种子或上传 Source Canon、确认权利
3. 定义项目名称、题材、受众和风格起点
4. 确认首个 Agent Task 后创建项目

### 创作工作台

- Script 的 Episode/Scene 目录与剧本编辑器
- Novel 的 Volume/Chapter/POV 编辑状态
- 自动保存反馈
- 局部改写、调整口吻、对照原著
- 来源面包屑和 Dirty 状态

### 第一版：五个产品空间（已被第二版取代）

- 创作：Story Map + 编辑器
- 故事世界：Story Core 概览
- 审查：Ralph 分数、证据和候选修改
- 版本与血缘：当前版本、Branch、Revision、Cascade
- 导出：范围、格式与导出前检查

### Agent Team 与决策

- 团队/上下文切换
- 审稿人 Decision
- 改编策划师 Delivery
- 自由指令输入
- diff drawer 与接受修改

## 交互验证

### 第二版模式化 Demo

`design/scriptflow-v7-ui-demo.html` 用三种工作模式验证新的闭环：

- 专注创作：可编辑正文、自动保存反馈、选区创建候选 Revision，Agent 状态可收起。
- 故事规划：只展示当前 Scene 的来源、决定与下游影响，不默认铺开整棵 Growth Tree。
- 审阅决策：问题、来源证据、当前版本与候选版本同屏，按钮直接描述采用结果。
- 决策收件箱：从全局入口直达待拍板事项；采用后数量和反馈同步更新。

第二版不是对第一版的视觉换肤。它用于验证“Agent 在后台推进、用户只在关键节点决定”的产品价值。

第一版 Demo 已验证 Dashboard → Workspace、五个产品空间、审查 → diff drawer、四步创建流程、Script/Novel 媒介切换和 600px 窄屏无横向溢出。该信息架构保留为探索历史，不再作为生产导航基线；第二版三模式结构为当前基线。

## 开发使用方式

Demo 是产品与交互基线，不是需要原样复制的生产代码。后续页面开发应复用其信息架构、状态命名、操作层级与行为契约；视觉 token 和组件实现应进入正式 Vue 设计系统。任何偏离“正文中心、候选 Revision、具名 Agent Activity、血缘可追溯”的设计，需要在对应 issue 中说明理由。
