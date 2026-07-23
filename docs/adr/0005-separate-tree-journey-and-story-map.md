# ADR-0005: 分离 Growth Tree、Creation Journey 与 Story Map

- **Status**: Accepted
- **Date**: 2026-07-16
- **Deciders**: Q老师、Codex
- **Supersedes**: 用单一阶段图同时承担流程、目录和血缘导航的方案
- **Depends on**: ADR-0001、ADR-0004

## Context

ADR-0001 用 Growing 替代线性流水线，这是正确的产品方向。后续的 Growth Tree UI 方案仍试图把 Idea、Structure、Character、Episode、Scene 和 Asset 全部铺在一张永久可见的树上，同时保留阶段栏和旧 tab 作为跳转。对于 80 集剧本或 100 章小说，这张图会同时承担版本历史、作品目录、当前任务和流程进度，信息密度过高。

三个不同问题被混在了一起：用户想知道“内容从哪里来”，想知道“现在建议做什么”，以及想知道“作品内部有哪些章、集和场景”。它们需要不同的数据和交互。

## Decision

明确分离三个概念：

### Growth Tree

记录 artefact、Revision 和 Branch 之间的派生、分叉、冻结与影响。它回答：

- 这版内容从哪里来？
- 哪个版本被采用？
- 上游修改会影响哪些下游？
- 两个 Revision 有什么差异？

Growth Tree 位于“版本与血缘”一级区域，不作为所有页面永久展开的主导航。

### Creation Journey

根据项目目标、当前状态和依赖给出下一步建议。它回答：

- 当前最有价值的下一步是什么？
- 哪项工作在等待用户决策？
- 哪个 Agent 正在工作或被阻塞？

Creation Journey 是动态建议，不是禁止回退的 stage gate，也不拥有领域数据。

### Story Map

表示作品内部的叙事顺序。Script 使用 Episode → Scene → Story Beat；Novel 使用 Volume → Chapter → Story Beat。它回答：

- 正文有哪些单位？
- 当前编辑哪一章、哪一集、哪一个 Scene？
- Story Beat 在作品中如何排列？

Story Map 作为“创作”区域的作品目录，承担高频导航。

## UI consequences

默认工作台使用作品目录 + 编辑器 + Agent Team/上下文三栏结构。用户可以进入“版本与血缘”查看 Growth Tree，也可以从编辑器的 lineage 面包屑跳转到相关节点。Cascade dirty、human review 和来源缺失等重要状态会在目录和编辑器中显示摘要，不要求用户打开树才能发现风险。

旧 7-stage bar 不作为长期经典视图保留。迁移期允许短期存在 feature flag，但必须设置删除条件，避免两套信息架构长期并存。

## Consequences

日常写作导航更符合创作者习惯，Growth Tree 也能专注表达真正有价值的版本关系。代价是前端不能简单把全部节点交给一张 Vue Flow 图，需要分别设计 Story Map、Activity 和 Growth Tree 的投影。

## Rejected alternatives

### Growth Tree 永久占据左栏

它在小 demo 中直观，但大项目会迅速变成节点海洋，并挤压正文编辑器。

### 保留阶段 tab 作为经典视图

长期维护两套主导航会使新旧隐喻同时存在，增加开发和用户认知成本。迁移逃生口必须是临时机制，而不是产品承诺。

### 只做 Story Map，不做 Growth Tree

这会失去 ScriptFlow 最有辨识度的 lineage、branch 和 cascade 能力，退化为普通 AI 编辑器。
