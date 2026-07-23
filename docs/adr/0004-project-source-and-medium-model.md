# ADR-0004: 用 Creation Source × Delivery Medium 建模项目

- **Status**: Accepted
- **Date**: 2026-07-16
- **Deciders**: Q老师、Codex
- **Supersedes**: 以 `type ∈ {novel, script, video_prompt}` 选择整条 pipeline 的产品模型
- **Depends on**: ADR-0001、ADR-0002

## Context

ScriptFlow 的创建入口已经同时出现原创、改编、改写、小说、剧本和视频提示词，但现有代码把 `type` 直接映射成三套 pipeline。来源与交付形态没有被明确分开，导致小说改编剧本、剧本改写小说等任务无法自然表达；工作台也容易把短剧的 Episode、Scene 和剧本纸交互错误地复用到小说项目。

用户实际提出的是四类创作目标：原创剧本、原创小说、改编剧本和改编小说。这四类目标包含两个彼此独立的选择：内容从哪里开始，以及最终以什么媒介交付。

## Decision

项目使用两个正交维度：

- **Creation Source**：`original / adaptation / rewrite`
- **Delivery Medium**：`script / novel`

`original` 可以从灵感、主题、梗概或大纲开始；这些属于 Seed Maturity，不再伪装成不同项目类型。`adaptation` 必须关联 Source Canon；`rewrite` 必须关联既有 Manuscript Revision 或用户上传的草稿。

四种主要产品入口由两个维度组合生成：

| 用户入口 | Creation Source | Delivery Medium |
|---|---|---|
| 创作一部小说 | original | novel |
| 创作一个剧本 | original | script |
| 把作品改编成小说 | adaptation | novel |
| 把作品改编成剧本 | adaptation | script |

`video_prompt` 不再作为新项目的 Delivery Medium。它属于 Script、Scene 或 VisualAsset 的下游导出。现有 `video_prompt` 数据保留兼容读取，迁移不直接删除。

原有 pipeline 降级为 **Creation Journey**：它可以根据两个维度、当前作品状态和用户目标推荐下一步，但不能决定领域对象的所有权或限制用户回到上游。

## Consequences

项目创建和工作台能直接对齐用户目标；Story Core 可以被 Script 和 Novel Manuscript 共同引用；未来从小说派生剧本时，可以创建新的 Manuscript Branch，而不必复制整个项目的故事事实。

代价是 Project schema、创建 API、Dashboard、工作台术语和 Agent 路由都需要迁移。迁移期间必须兼容现有 `type` 和 `source_mode`，不能静默破坏用户项目。

## Rejected alternatives

### 为四类项目各建一条 pipeline

这会复制 Story Core、审查、版本和 Agent 能力，后续新增“剧本转小说”时继续组合爆炸。

### 保留 `video_prompt` 为第三种媒介

视频提示词不是与小说、剧本同层的长篇叙事 Manuscript。把它放在顶层会让创建、资产和导出边界持续混乱。

### 只修改创建页文案

入口问题会暂时变得好看，但数据模型和工作台仍无法表达改编关系，属于 UI 掩盖领域冲突。

## Migration notes

- 现有 `type=novel` → `delivery_medium=novel`
- 现有 `type=script` → `delivery_medium=script`
- 现有 `source_mode=adapted` → `creation_source=adaptation`
- 现有 `source_mode=rewrite` → `creation_source=rewrite`
- 其他 `source_mode=original_*` → `creation_source=original`，原值映射到 `seed_maturity`
- 现有 `type=video_prompt` 保留 legacy 标记，只读兼容，迁移前不得删除
