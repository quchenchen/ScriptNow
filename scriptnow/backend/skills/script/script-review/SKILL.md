---
name: script-review
core: true
description: Use when reviewing screenplay scenes, episodes, or a full script for StoryMap fidelity, filmability, dramatic action, character tactics, subtext, pacing, continuity, runtime, production risk, and delivery-format compliance.
metadata:
  scriptnow:
    roles: [reviewer]
    stages: [review]
    selection_priority: 100
---

# Review a screenplay

1. Compare each scene with its accepted StoryMap beat and identify intended versus actual state change.
2. Flag unfilmable interior prose, exposition without conflict, passive protagonists, duplicate beats, and dialogue without tactics.
3. Check continuity of props, geography, time, wardrobe, injuries, knowledge, and entrances/exits.
4. Estimate runtime and distinguish story problems from production-cost observations.
5. Check the selected delivery format only after dramatic and continuity checks; formatting cannot rescue an inert scene.
6. Rank findings as blocking, major, or minor, with an exact scene/block anchor, quoted evidence, impact, and minimal repair direction.
7. Separate fact violations, craft risks, optional taste, and production observations.
8. Return the task's requested report or revision candidate; do not mutate accepted script.

## Dialogue review: seven-dimension sweep (台词七维)

For every dialogue line, check in order; dimensions 1-3 are hard gates, the rest are craft:

1. **角色辨识度**：遮住角色名能否凭语气认出说话人？全员同腔是 blocking。
2. **潜台词**：表层与里层是否分层？直白解释剧情/情绪是 major。
3. **冲突推进力**：这句是否改变目标/权力/关系/信息/风险至少一项？无推进的寒暄是 major。
4. **类型语感**：古装混入网络梗、都市整段文言——越界即 major。
5. **信息效率**：exposition 灌设定（双方都知道的信息）应删；一句话能说完别用两句。
6. **节奏与音乐性**：连续长句、无停顿、语气词堆叠；单句过长建议拆。
7. **金句潜力**：加分项不是底线；一集 1-3 句，满篇金句等于没有。

## Vertical short-drama format check (竖屏短剧)

当项目为 `chinese-short` 格式时，额外校验分镜式交付：
- slugline 符合“场-镜 地点·细地点 时间 内外”；画面用 ▲ 开头、单段 20-30 字。
- 场景开头有“出场人物”；对白带（语气/动作）注，单句不超过 15 字。
- OS/VO/旁白显式标注且克制（约每 25-35 个分镜一次）；【特写】【闪回】标记成对/有明确落点。

Read [review rubric](references/review-rubric.md) for evidence and severity rules.
