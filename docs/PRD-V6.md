# ScriptFlow · PRD-V6

- **Status**: Accepted for Phase 0 execution
- **Date**: 2026-07-16
- **Product owner**: Q老师
- **Supersedes**: PRD-V5 的产品范围、主用户旅程和 Phase 3.4 之后的执行顺序
- **Preserves**: PRD-V5 已交付的基础设施与领域能力
- **Depends on**: [`CONTEXT.md`](../CONTEXT.md)、[产品蓝图](./product/V6-PRODUCT-BLUEPRINT.md)、[UI 交互体系](./product/V6-UI-INTERACTION-SYSTEM.md)、[ADR-0004](./adr/0004-project-source-and-medium-model.md)、[ADR-0005](./adr/0005-separate-tree-journey-and-story-map.md)、[`PLAN-V6.md`](./PLAN-V6.md)

## 产品定义

ScriptFlow 是面向长篇叙事创作者的 AI 创作团队。它围绕同一份 Story Core，支持从原创灵感或既有作品出发，创作小说或剧本；用户负责方向、审美和关键决策，Agent Team 负责研究、构思、撰写、审查和持续修订。

产品的核心价值不再是“一次生成很多文字”，而是让作品在可追溯、可编辑、可反复打磨的结构中持续生长。

## 当前问题

现有产品的入口已经允许用户选择小说、剧本、改编和改写，但进入工作台后，主要领域对象和交互仍围绕短剧的 Episode、Scene、剧本纸和视频提示词展开。PRD-V5 又明确把网文改编和剧本改写列为 Out of Scope，形成了入口承诺、产品文档与实际能力之间的直接冲突。

Growth Tree、Living Assets 和 Evolution Loop 已经建立了正确的基础方向，当前需要解决的不是推翻这些机制，而是重新确定它们在多媒介创作中的职责：Story Core 承担跨媒介故事事实，Manuscript 承担小说或剧本正文，Growth Tree 记录版本与血缘，Agent Activity 呈现团队工作过程。

## 目标用户与首发场景

### P1：独立叙事创作者

用户独立完成故事创意、结构设计、正文创作和修订，希望 AI 能持续理解人物、世界观和个人风格，同时保留创作控制权。用户可能创作短剧、长剧本或小说，也可能把已有小说改编为剧本。

### V6 发布必须走通的两条路径

#### 原创剧本

用户输入一句话灵感、梗概或已有大纲，和创意总监共同选择方向；编剧架构师形成 Story Core 和 Story Beat；撰写师生成可编辑 Scene；审稿人执行 Ralph Loop；用户完成修订并导出 DOCX。

#### 小说改编剧本

用户上传有权使用的小说文本，系统形成 Source Canon；改编策划师把原著章节映射为 Story Beat 和 Scene，明确保留、合并、删除、重排与原创新增；用户能从每个 Scene 回到来源片段，并完成剧本修订和导出。

### V6 基础支持路径

原创小说与改编小说使用同一 Story Core，并具备 Volume、Chapter、POV、正文编辑、自动保存和 Revision 基础能力。V6 不要求小说路径同时具备与剧本相同深度的专业排版、审查 rubric 和导出能力。

## 项目模型

项目由两个正交维度组成：

| 维度 | 值 | 用户含义 |
|---|---|---|
| Creation Source | `original` | 从灵感、主题、梗概或大纲开始 |
| Creation Source | `adaptation` | 从一部 Source Canon 改编 |
| Creation Source | `rewrite` | 从已有草稿创建新 Revision 或 Branch |
| Delivery Medium | `script` | 交付 Episode/Scene 结构的剧本 |
| Delivery Medium | `novel` | 交付 Volume/Chapter 结构的小说 |

`video_prompt` 不再是新建项目类型。视频提示词属于 Script、Scene 或 VisualAsset 的下游交付物；已有 `video_prompt` 项目保持可读取，不在 V6 创建入口继续暴露。

## 核心领域对象

### Story Core

Story Core 是同一故事跨媒介共享的事实与结构，包括 Premise、World、Character、Relationship、Timeline Event、Story Beat、Plot Thread、Foreshadow、Style Profile 和 Source Reference。

Story Core 中的对象可以被小说 Chapter 和剧本 Scene 同时引用。修改人物、时间线或 Story Beat 时，系统通过 Cascade 计算受影响的 Manuscript，不直接覆盖正文。

### Manuscript

Manuscript 是实际交付文本。Script Manuscript 由 Episode、Scene、Action 和 Dialogue 组成；Novel Manuscript 由 Volume、Chapter、POV 和段落组成。两者共享保存、Revision、diff、回滚和选区 AI 修改能力。

### Source Canon

Source Canon 是改编项目中被允许作为依据的原始作品或资料集合。它保留文档、章节、片段、解析状态和 Source Reference。系统生成的改编内容必须能追溯到来源，或明确标注为原创新增。

### Growth Tree

Growth Tree 记录 Idea、Story Core、Manuscript 和 Revision 之间的派生、分叉与影响。它回答“这版内容从哪里来、改动会影响哪里”，不承担日常章节目录和流程导航。

### Agent Activity

Agent Activity 记录团队成员、任务、使用的上下文、交付物、决策请求和失败状态。聊天是自由指令入口，Agent Activity 才是团队过程的结构化呈现。

## 信息架构

工作台使用三个按用户意图组织的一级模式：

1. **专注创作**：作品目录与正文编辑器，是默认入口。
2. **故事规划**：Story Core、人物、关系、时间线、Story Beat、伏笔、Source Canon 与当前对象的血缘/影响。
3. **审阅决策**：Review、Revision Compare、Decision Inbox、一致性、来源忠实度和 Cascade 处理。

版本历史、完整 Growth Tree、来源管理和导出作为当前对象或项目的上下文入口，不与三种工作模式平级。专注创作默认采用“目录 + 大幅编辑纸面”；Agent Task 只在相关时以可收起状态出现，不形成永久第三栏。

## 核心用户旅程

### Journey A：原创剧本

1. 用户选择“创作一个剧本”，指定从灵感、梗概或大纲开始。
2. 创意总监给出差异化候选，用户可以采用、编辑或创建分叉。
3. 编剧架构师把采用方案转为 Story Core 和 Story Beat。
4. 用户确认本轮创作范围，例如前 3 集，而不是默认生成 80 集。
5. 撰写师按 Story Beat 创建 Scene；用户在结构化编辑器中修改。
6. 审稿人自动执行 Ralph Loop，列出分数、问题、修改建议和 diff。
7. 用户接受、拒绝或局部重写，并保留 Revision。
8. 用户导出符合剧本格式的 DOCX。

### Journey B：小说改编剧本

1. 用户选择“把作品改编成剧本”，确认拥有使用权并上传原著。
2. 系统展示解析进度、章节目录和失败恢复入口。
3. 改编策划师生成 Adaptation Map，用户设置忠实、平衡或自由策略。
4. 用户逐项确认主要保留、合并、删除、重排和原创新增决策。
5. Story Core 从 Source Canon 中形成，并保留 Source Reference。
6. 撰写师创建 Scene；每个 Scene 展示来源依据或“原创新增”。
7. 审稿人检查人物偏移、情节遗漏、来源冲突和媒介转换质量。
8. 用户完成修订、追溯来源并导出 DOCX。

### Journey C：原创小说（基础）

用户选择“创作一部小说”，建立 Story Core 和章节大纲，在 Chapter Editor 中持续写作。工作台使用章、卷和 POV 术语，不出现 EP、剧本纸或视频提示词主操作。

### Journey D：改编小说（基础）

用户选择“把作品改编成小说”，建立 Source Canon 和 Adaptation Map，在 Chapter Editor 中完成改编，并保留章节到来源片段的追溯关系。

## 功能需求

### P0：项目与工作台

- 创建入口直接呈现四个用户目标，而不是先要求用户理解数据库中的来源模式。
- 项目持久化 Creation Source 与 Delivery Medium，并兼容现有数据。
- 工作台根据 Delivery Medium 使用正确的单位、目录、编辑器和操作。
- Dashboard 分别展示正文进度、质量状态、风险和 Agent 状态，不使用跨流程统一百分比。
- URL 能反映项目、一级区域和当前 Chapter/Episode/Scene。

### P0：Story Core

- 用户能查看和编辑 Character、Relationship、World、Timeline Event、Story Beat、Plot Thread 和 Foreshadow。
- Manuscript 可以引用 Story Core；Story Core 修改能计算受影响内容。
- 删除 Character 与剧情状态（活跃、隐退、死亡）必须分离。
- 所有重要变更形成 Revision 或可追溯 history。

### P0：可编辑 Manuscript

- Script 提供 Episode/Scene/Action/Dialogue 结构化编辑。
- Novel 提供 Volume/Chapter/POV/段落基础编辑。
- 支持自动保存、保存中/成功/失败状态和未保存离开保护。
- AI 修改必须提供 diff，并允许接受、拒绝和回滚。
- 支持选区改写、扩写、缩写和保持人物口吻；不要求重生成整个单位。

### P0：原创剧本闭环

- Idea 候选可采用、编辑、分叉和比较。
- Story Beat 可以派生 Episode/Scene，并记录 lineage。
- Ralph Loop 自动触发并可见，达到重试上限时请求人工判断。
- 剧本正文通过格式检查，并可导出 DOCX。

### P0：改编闭环

- Source Canon 提供上传、解析、章节目录、检索和错误恢复。
- Adaptation Map 记录保留、合并、删除、重排和原创新增。
- 用户可选择忠实、平衡或自由策略。
- 改编 Scene 能展示 Source Reference；无来源时标注原创新增。
- Review rubric 检查人物偏移、关键情节遗漏、来源冲突和媒介转换质量。

### P1：团队过程与进化

- Agent Activity 展示成员、当前任务、上下文、交付物和决策请求。
- Reflection 扫描跨单位冲突并提出上游修改建议，用户决定是否触发 Cascade。
- Style Profile 对用户可见、可编辑、可删除，且区分项目级与用户级偏好。
- Growth Tree 支持 Branch、Frozen、Dirty 和 Revision 比较。

## 关键交互状态

所有核心页面必须覆盖 loading、empty、success、error、retry、disabled、unsaved 和 long-content 状态。异步生成不能只显示旋转图标，需要说明当前 Agent、任务和可取消性。破坏性操作提供确认或撤销；错误信息包含下一步处理方式。

## 成功指标

### 北极星指标

**有效创作推进率**：进入项目的创作会话中，产生并保留至少一个被用户采用或编辑后的 Story Core/Manuscript Revision 的比例。

### V6 观测指标

- 项目创建完成率
- 首次有效产出时间
- 候选采用与轻改采用率
- 平台内编辑率
- 全量重生成率
- AI 修改接受/拒绝率
- Source Reference 覆盖率
- 一致性或改编建议接受率
- 7 日继续创作率
- 导出完成率

V6 阶段先建立可测量能力，不在缺少真实使用基线时预设虚假的提升百分比。发布试用后再制定目标值。

## Release Gate

V6 发布必须满足：

- 原创剧本从一句话灵感走到 3 集可编辑剧本并成功导出。
- 小说改编剧本从上传样本文本走到 3 个可追溯 Scene 并成功导出。
- 小说项目不出现剧本专属主操作，剧本项目不出现小说专属主操作。
- 用户可直接编辑正文，AI 修改可 diff、接受、拒绝和回滚。
- Growth Tree 能说明主要内容的血缘和受影响范围。
- 前后端关键路径测试通过，无 P0 数据丢失、安全或不可恢复错误。

## Out of Scope

- 多人实时协作、权限矩阵和冲突合并
- 移动端完整创作体验
- FDX、影视工业全套制片管理
- VisualAsset 生图和跨镜头一致性
- 把视频提示词作为独立项目
- 公共网站作品抓取或绕过版权限制
- 跨用户风格训练和隐式共享用户数据
- 四条项目路径在 V6 同时达到完全相同的专业深度

## 交付顺序

具体阶段、依赖、Gate、风险和 issue 规划见 [`PLAN-V6.md`](./PLAN-V6.md)。任何不在关键路径上的新功能，必须说明它如何提高有效创作推进率，否则进入 V6.1 backlog。
