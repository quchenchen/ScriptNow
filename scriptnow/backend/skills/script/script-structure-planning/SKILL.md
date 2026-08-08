---
name: script-structure-planning
description: Use when a screenplay project selects or migrates a recognized narrative structure and needs its dramatic functions mapped to filmable beats without forcing a template or overwriting accepted material.
metadata:
  scriptnow:
    roles: [architect]
    stages: [planning]
    structures: [hero-journey, three-act, five-act, save-the-cat, eight-sequence, harmon-circle, freytag, custom]
    selection_priority: 70
    keywords: [叙事结构, 三幕, 五幕, 英雄之旅, 救猫咪, 节拍表]
---

# 剧本叙事结构应用

## 一、读取与确认

1. 从 CreativeProfile 读取用户选定的叙事结构。
2. 不得静默替换为其他结构方法。
3. 使用核心 `script-storymap` skill 暴露的匹配方法。
4. 如果项目是竖屏短剧，结构需适配 1-2 分钟/集的节奏——不要机械套用电影的三幕比例。

---

## 二、节拍映射

将选定结构的每个必需功能映射到可观察的 Story Beat 和完成条件：

- 每个节拍必须有：人物行动、戏剧功能、可观察的完成信号
- 不把「主题」「情绪」作为节拍的完成条件——必须是可拍摄的行动

```
❌ 「第二幕中点：主角意识到自己必须改变」
    → 不可拍、不可验证

✅ 「中点：主角撕碎辞职信，拿起电话拨出那个十年没拨的号码」
    → 可拍、可观察、有后果
```

---

## 三、短剧适配

对于短制式作品（竖屏短剧、微短剧），节拍合并规则：

- 合并节拍时，每个被合并的功能必须在文本中保持显式可识别
- 不因缩短时长而删除不可替代的戏剧功能
- 竖屏短剧的「三幕」比例通常为：前 10% 钩子 + 70% 冲突升级 + 20% 收束钩子——不是电影的三等分

---

## 四、变更管理

- 跨场景发现通过 CreativeChangeProposal 提出，不静默修改已有 canon
- 结构变更时，返回：节拍映射、受影响的场景清单、风险、未被映射的已采纳素材

---

## 五、可识别的叙事结构

| 结构 | 典型节拍数 | 适配短剧？ |
|------|----------|-----------|
| 三幕结构 (Three-Act) | 3 幕 | ✅ 最常用 |
| 五幕/弗赖塔格 (Five-Act) | 5 幕 | ⚠️ 需压缩 |
| 英雄之旅 (Hero's Journey) | 12 阶段 | ⚠️ 市时长限制 |
| 救猫咪 (Save the Cat!) | 15 节拍 | ⚠️ 需合并 |
| 八序列法 (Eight-Sequence) | 8 序列 | ✅ |
| 起承转合 (Kishōtenketsu) | 4 段 | ✅ |
| 自定义 (Custom) | 按项目定义 | - |
