# ScriptFlow V6 创作者中心执行计划

- **Status**: Active execution baseline
- **Date**: 2026-07-16
- **Supersedes for execution**: PLAN-V6 的旧实现顺序；产品范围与 Release Gate 保持不变
- **Depends on**: V6-CREATOR-CENTERED-CORRECTION、V6-IMPLEMENTATION-AUDIT-2026-07-16

## Phase A · 项目计划与作品目录

1. Project 双维度字段、目标规模、创作方式和迁移。
2. 创建向导收集计划输入，创建 Project Plan 候选。
3. Story Map：Volume/Chapter、Episode/Scene 的 CRUD、排序和状态。
4. 工作台真实路由、目录选择和刷新恢复。
5. Dashboard 使用计划与正文真实状态。

**Gate A**：用户创建“12 章小说”或“3 集×8 场剧本”后，看到可编辑目录，并能定位任一章/场。

## Phase B · 故事圣经与传播

1. Premise、World、Character、Organization、Relationship、Timeline、Story Beat、Foreshadow、Style。
2. 故事圣经主工作区与对象详情编辑。
3. Chapter/Scene Intent 与开始/结束连续性快照。
4. Story Bible Change、影响计算、dirty/stale 和传播选择。
5. 当前单元 Revision、未来继承、既有正文 Cascade Candidate。

**Gate B**：新增“二丫第 9 章以对手身份出场”能产生影响范围、正文 Revision 证据和下一章状态传递。

## Phase C · 正文编辑与版本

1. 先建立与编辑器内核无关的正文文档、选区锚点、版本和 AI Edit Command 协议。
2. Script/Novel 可编辑正文、autosave、失败恢复和离开保护。
3. 结构化 Scene 块与 Chapter 段落/POV 元数据。
4. 选区支持缩写、扩写、润色、对白、节奏和自定义要求；AI 只创建局部 Candidate Revision。
5. 通用 Revision、diff、历史、回滚和 Branch。
6. 参考 Lobe Editor 的可见 AI 协作者和局部流式修改，但 Vue 主应用不直接引入其 React UI 运行时。

**Gate C**：用户直接完成一场剧本和一章小说编辑；刷新不丢失；所有 AI 修改可比较、拒绝和回滚。

## Phase D · 原创剧本专业闭环

1. Structure、Story Beat、Episode Plan、Scene Intent。
2. 写作者 Skill 严格消费上下文并提供使用证据。
3. Ralph Loop、剧本 rubric、格式检查与局部 Revision。
4. Script Sheet、Agent Activity、Decision Inbox。
5. DOCX 导出、Branch、Growth Tree 和 Cascade。

**Gate D**：一句话灵感完成 3 集可编辑剧本、审稿、血缘解释和 DOCX 导出。

## Phase E · 小说改编剧本闭环

1. Source Canon 上传、解析、章节目录、检索和恢复。
2. Source Reference 与 Adaptation Map。
3. 改编策略和来源并排对照。
4. 改编 rubric 与来源覆盖率。

**Gate E**：样本文本完成“来源章节 → 改编结构 → 3 个可追溯 Scene”。

## Phase F · 发布

迁移体系、认证边界、错误状态、可访问性、端到端与性能测试、埋点、真实项目试用。

## 执行规则

- 每个 slice 必须包含真实 UI、公开 API、状态处理和测试。
- demo runtime 与真实 runtime 使用同一输入输出契约。
- UI 不暴露 Entity、Node、Context Pack 等内部术语。
- 不以 issue done、表或接口数量代替 Gate 证据。
