# 16 · 故事圣经到正文的传播契约

- **Status**: done
- **Type**: product / domain / agent / frontend
- **Blocked by**: 15.1 Project Plan, 15.2 Story Map, 15.3 Story Bible
- **Blocks**: 专业写作 Agent、Cascade、连续性 Gate
- **Est**: L，必须拆分
- **Source**: docs/product/V6-CREATOR-CENTERED-CORRECTION.md §设定变化传播契约

## Problem

当前人物、关系和伏笔只被序列化进 Context Pack；demo runtime 不消费这些字段，当前候选不失效，已写正文没有影响分析，伏笔正文动作与伏笔账本也未统一。

## Required slices

1. Story Bible Change 与生效范围。
2. Manuscript/Outline Impact 计算和 dirty/stale 标记。
3. 当前单元 Revision Task。
4. 未来单元 Context Assembly 与必用事实。
5. 已采用正文 Cascade Candidate。
6. Agent Delivery 正文证据与状态变化候选。
7. demo runtime 与真实 runtime 使用同一字段消费契约。

## 2026-07-16 implementation evidence

- 已实现 Character Introduction Change 候选：身份、叙事功能、人物声音、首次出场位置及与现有人物关系必须显式填写。
- 创建变化时计算逐单元影响：当前候选 `mark_stale`、未来计划 `future_context`、已采用正文 `cascade_candidate`；变化确认前不改故事圣经和正文。
- 确认变化后才创建角色与关系；从首次出场单元起进入 Context Pack，之前单元不会提前读取。
- 当前候选被标记 stale；已采用正文生成独立 Cascade Revision，保存原文、基线版本、候选文本、理由与设定证据，不自动覆盖。
- Gate tracer 自动化证明“二丫第 9 章以对手身份出场”：第 9 章候选失效，第 10–12 章继承，第 1–8 章逐字不变。
- UI 已提供“预览影响范围 → 待确认 → 确认并传播”，用章节和创作者动作表达，不暴露内部 Entity/Context Pack。
- Cascade Revision 只有证据存在时可采用；采用创建新正文版本，基线变化则标记 stale，拒绝则保留原正文。
- 自动化验证已采用第 9 章的 Cascade：变化确认后正文仍为 v1；采用 Cascade 后才生成 v2，且可定位“二丫”正文证据。
- 人物关系、世界规则和伏笔计划现已共用同一传播协议；关系保存双方认知与隐藏信息，世界规则保存戏剧约束与例外，伏笔保存埋入方式、强化位置和回收意图。
- 自动化验证生效边界：伏笔从计划埋入章进入上下文，关系从指定章生效，世界规则不会提前进入 Agent 输入。
- 待完成：Agent 常规交付正文证据定位，以及当前单元 Revision Task 的统一任务展示。

## Gate

新增“二丫为主角对手、在第 9 章首次出场”后，用户能看到影响范围；第 9 章候选被标记 stale；要求修订后正文出现可定位证据；采用后人物出场、关系状态和下一章上下文同步更新；第 1～8 章不被静默改写。

**Gate evidence**: `tests/test_story_bible_propagation.py` 覆盖影响预览、确认前隔离、stale、同单元 Revision Task、正文证据、未来上下文、Cascade 版本采用和第 1～8 章保护；运行预览已验证四类变化表单。
