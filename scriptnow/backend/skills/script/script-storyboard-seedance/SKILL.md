---
name: script-storyboard-seedance
description: Use for converting short-drama episode scripts into Seedance-compatible storyboard prompts; breaks scripts into 15-second video segments with structured tags for roles, locations, props, dialogue, sound effects, camera movement, and visual style.
metadata:
  scriptnow:
    roles: [architect, writer]
    stages: [planning, writing]
    languages: [zh-CN]
    selection_priority: 73
    keywords: [分镜, Seedance, 视频, Prompt, 镜头, 15秒, 角色, 场景, 音效]
---

# Seedance 分镜 Prompt 生成器

分镜 Prompt 的目标是把剧本转成"视频生成工具能精确执行的指令"，而不是"再描述一遍剧情"。继承 `script-cn-short-drama` 的分镜书写规则，本 Skill 输出 Seedance 兼容的结构化 Prompt。

## 一、核心原则：一个 15 秒段 = 一场微型戏

- 每段包含完整的微小叙事：发生什么 → 有什么变化 → 观众感觉到什么
- 一个视频段建议 4-6 个分镜，每个分镜 2-5 秒
- 镜头数量不是越多越好——3 个有力的镜头优于 8 个仓促的

## 二、Seedance Prompt 标签规范

```
画面风格和类型: [风格描述]
生成一个由以下[N]个分镜组成的视频:

分镜1<duration-ms>[毫秒]</duration-ms>: [时间]，场景图片：<location>[场景]</location>。
<role>[角色名]</role>[动作描述]。
[如需要] 音效 <[音效描述]>。

分镜2<duration-ms>[毫秒]</duration-ms>: ...
```

### 标签说明

| 标签 | 用途 | 示例 |
|------|------|------|
| `<duration-ms>` | 毫秒时长 | `3000`（3秒）、`4000`（4秒） |
| `<location>` | 场景描述 | `垃圾场`、`总裁办公室落地窗前` |
| `<role>` | 角色名（剧中名字） | `林凡`、`林夏` |
| 音效 `<...>` | 环境音效 | `<远处金属碰撞声>`、`<车门关闭声>` |
| 背景音乐 `(...)` | BGM | `（低沉鼓点渐强）`、`（钢琴单音持续）` |

## 三、分镜节奏分配

对于一个 15 秒（4 个分镜）的标准段：

| 分镜 | 时长 | 功能 |
|------|------|------|
| 分镜 1 | 2000-3000ms | 建立场景和当前状态 |
| 分镜 2 | 3000-4000ms | 关键动作或对话发生 |
| 分镜 3 | 3000-4000ms | 反应或冲突升级 |
| 分镜 4 | 3000-4000ms | 情绪落点或悬念抛出 |

## 四、完整示例

```
画面风格和类型: 真人写实, 现代都市逆袭短剧, 深蓝灰色调, 金色高光

生成一个由以下4个分镜组成的视频:

分镜1<duration-ms>3000</duration-ms>: 时间：日，场景图片：<location>垃圾场</location>。
<role>林凡</role>蹲在废品堆旁翻找，两个拾荒者指着他说：「看那个穷鬼」。音效 <远处金属碰撞声>。

分镜2<duration-ms>4000</duration-ms>: 黑色商务车停在垃圾场入口，镜头快速推近车门，音效 <车门关闭声>。

分镜3<duration-ms>4000</duration-ms>: <role>律师</role>递出文件，<role>律师</role>说：「林先生，您父亲留下的资产终于解封了。」

分镜4<duration-ms>4000</duration-ms>: <role>林凡</role>慢慢摘下破旧手套，抬头看向嘲笑他的人，背景音乐（低沉鼓点渐强）。
```

## 五、分镜写作规则

1. **一个分镜只做一件事**：不要在一个分镜里塞"他站起来、走过去、推开门、说话"
2. **角色用剧中名字**：不编号为 R1/R2——Seedance 可以从名字推断性别和语境
3. **场景要画面化**：不是"办公室"而是"落地窗前的总裁办公室，黄昏光线斜照"
4. **动作要可拍**：不是"他感到愤怒"而是"他攥紧拳头，指节发白"
5. **台词要精简**：一个分镜最多 1-2 句台词，超过 2 句应该拆成多个分镜
6. **音效只在关键节点使用**：不是每换一个镜头都加音效

## 六、从剧本到分镜的拆解流程

1. **选择一集剧本**（优先选择反转多、对话少、视觉强的集）
2. **标记关键节点**：钩子、冲突升级、反转、爽点、悬念
3. **按 15 秒分段**：每个关键节点+前后过渡 ≈ 一个 15 秒段
4. **列出该段资源**：角色 × 场景 × 关键道具 × 核心台词 × 必要音效
5. **写出分镜 Prompt**：按本 Skill 标签规范组织

## 七、常见错误

- 一段里塞太多镜头导致节奏仓促
- `<role>` 标签使用编号（R1）而非角色名
- 场景描述过于抽象无法生成
- 忘记标注画面风格类型导致风格不统一
- 台词太长一个分镜装不下
