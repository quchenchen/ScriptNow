# CONTEXT — ScriptFlow 领域语言

> 这是本项目的 **ubiquitous language** —— 所有代码、UI、文档、Agent prompt、issue 标题都用这里的术语。
> 遇到新概念，先在这里定义了再写代码。
> 词汇过时，改这里而不是改别的地方。

---

## 一句话产品定位

**ScriptFlow 是让好剧本"长出来"的 AI Agent 团队协作平台。**

用户输入创意种子，Agent 团队接力灌溉，用户是总指挥兼审美裁判。产出的不是一坨文档，是一棵有血缘、有骨架、能进化的**剧本树**。

---

## 核心隐喻：Growing vs Assembling

我们**不做**"7 阶段流水线"（把创意 → 大纲 → 剧本当作 7 段独立管道）。

我们做**生长式创作系统**：

- **Growth（生长）** — 每一步产出都是上一步的**延续**，不是独立文件。灵感种子长出大纲芽，大纲芽长出剧本树，剧本树结出资产果。
- **Assembling（拼凑）** — 反面示例，也是当前架构的病症。7 张独立表、7 个空白 tab、Agent 之间靠 SQL 传纸条。

**代码约束**：任何"stage 独立表 / 独立文件 / 独立空白 tab"的设计，都要经过 ADR 举证才能引入。默认走血缘图谱（见 Lineage）。

---

## 三大机制

产品的三根支柱。任何 issue、代码、UI 都必须能对应到这三根之一（或红线）。

### 机制一：Continuity（有机连续性）

产出物之间的**血缘关系**贯穿整棵剧本树。

- **Growth Tree（剧本树）** — 一部作品从种子到成品的完整血缘图谱。节点是产出物（Ideation / Structure / Episode / Asset），边是"产自"关系。
- **Lineage（血缘）** — 任何产出物都能追溯到它的上游。Episode 5 追溯到 Outline 5 追溯到 Structure v2 追溯到 Idea A。
- **Cascade（级联）** — 上游改动传递到下游的规则。改了角色 A 的性格 → 所有 A 出场的 episode 拿到"可能要修"的标记，不自动改，等用户决定。
- **Trace View（追溯视图）** — UI 上"这段剧本是从哪根枝上长出来的"，双向可跳。不叫"tab"，叫"树视图"。

### 机制二：Living Assets（横向骨架）

**跨阶段、有生命周期的实体**，是剧本树的"骨骼"。不属于任何单一 stage。

五类 Living Asset：

- **Character（角色）** — 有出场轨迹、状态演化、弧光进度、关系图谱。字段涵盖：`first_appearance`、`last_appearance`、`career_stage`、`current_state`、`state_episode`（这些字段当前 schema 已有，但没 UI 用起来 —— 我们要用起来）。
- **Foreshadow（伏笔）** — 状态机：`pending → planted → partially_resolved → resolved | abandoned`。有埋点集、目标回收集、实际回收集、重要性、隐蔽度。
- **Scene（场景）** — **注意**：这里的 Scene 是"剧本里的场景片段"（`【场景N】地点·时间`），**不是**"整集正文的容器"。当前 `episodes.scenes` 字段的用法是历史错误，见 ADR-0002 附录。
- **Prop（道具）** — 道具在哪集首次出现、在哪些集出场、有没有关键作用。
- **VisualAsset（视觉资产）** — 新增。关键场景/角色的图像。从 Prompt → 生图 LLM → 图像 → 反馈 → Prompt 迭代。用于视频制作前置。

每个 Living Asset：
- 有独立生命周期（不随 stage 切换而消失）
- 有跨 episode 的时间轴
- 可被 UI 单独查阅、编辑、干预
- 可被多个 stage 的 Agent **读写**（而不是被某个 stage 独占）

### 机制三：Evolution Loop（反馈进化循环）

三层嵌套循环。让好剧本"长得越来越好"。

- **Ralph Loop（单集内循环）** — 写 → 审 → 打分（六维）→ 修 → 再审，直到通过（默认阈值 85，可配置）或达到最大重试次数（默认 3）。**当前代码里是死的，Phase 3 优先复活。**
- **Reflection（单作品跨集反哺）** — 写第 15 集发现角色 A 前后矛盾 → 触发 Reflection → 提示用户"上游可能要修"（Structure 里的 A 人设 / Outline 5 里对 A 的描述）→ 用户决策 → 触发 Cascade。
- **Style Library（跨作品自我进化）** — 用户在每部作品里的选择、修改、反馈，沉淀到**风格库**：
  - `project.style_profile` — 单作品的风格偏好
  - `user.style_preferences` — 用户累积的偏好（这类爱短句、这类恨旁白）
  - `genre.style_conventions` — 类型/题材的通用惯例（都市 vs 古偶 vs 悬疑）
  - 下一部同类型作品生成时，Agent 读回来做 few-shot 或 constraint

---

## 贯穿红线：Craft Standard（质量规范）

不是机制，是**横切三个机制**的质量红线。任何产出都要过这道线。

- **拒绝 AI 味（Anti-AI-Tell）** — 具体动作：skill prompts 加高质量 few-shot / style-ref 对齐 / "AI 味"检测器（可用词频黑名单 + LLM 判官）。
- **剧本纸规范（Script Format）** — 短剧标准版式：`【场景N】地点 · 时间`、`△ 动作描述`、`角色：对白`。行业标准（Final Draft `.fdx` / `.docx` 剧本纸）作为导出目标。
- **持续打磨（Editability）** — 每个产出物都是可编辑的实体，不是只读渲染。改动可 diff / 可回滚 / 可"打回 Agent 基于我的改再改"。
- **行业标准输出（Standard Export）** — 剧本 `.docx`/`.fdx`/`.pdf`、资产包 Excel/JSON、视频提示词 Seedance 兼容格式。

---

## 术语速查表

按字母排序，方便命名代码时对照。

| 术语 | 定义 | ⚠ 别写成 |
|---|---|---|
| **Cascade** | 上游 Living Asset 改动向下游 Episode 传播的机制 | ~~propagate~~、~~sync~~ |
| **Character** | Living Asset 的一种，人物实体 | ~~role~~、~~persona~~ |
| **Craft Standard** | 质量红线，横切三机制 | ~~quality gate~~ |
| **Evolution Loop** | 反馈进化循环（三层嵌套） | ~~feedback~~、~~review loop~~ |
| **Foreshadow** | Living Asset 的一种，伏笔/钩子/悬念，有状态机 | ~~clue~~、~~hint~~ |
| **Growth Tree** | 一部作品的完整血缘图谱 | ~~pipeline~~、~~workflow~~ |
| **Ideation** | 灵感孵化 stage，产出 Idea 候选 | ~~inspiration~~ |
| **Idea** | 一个候选创意方案（题材/钩子/一句话梗概） | ~~plan~~、~~concept~~ |
| **Lineage** | 一个产出物的血缘链 | ~~parent~~、~~ancestor~~ |
| **Living Asset** | 横向骨架层的实体（Character/Foreshadow/Scene/Prop/VisualAsset） | ~~entity~~、~~resource~~ |
| **Outline** | 分集大纲，Structure 的一部分 | ~~synopsis~~ |
| **Prop** | Living Asset 的一种，道具 | ~~item~~ |
| **Ralph Loop** | 单集内 写-审-改 循环 | ~~retry~~、~~review cycle~~ |
| **Reflection** | 单作品跨集反哺 | ~~backprop~~ |
| **Scene** | 剧本里的场景片段（`【场景N】...`）；Living Asset 的一种 | ~~episode~~、~~chapter~~ |
| **Skill** | Agent 使用的领域 prompt 模板（住在 `backend/app/skills/`） | ~~template~~、~~preset~~ |
| **Structure** | 故事架构 stage，产出角色 + 大纲 + 爽点分布 | ~~outline~~（Outline 是子集） |
| **Style Library** | Evolution Loop 的第 3 层沉淀 | ~~preferences~~、~~config~~ |
| **VisualAsset** | Living Asset 的一种，图像资产（用生图 LLM 产出） | ~~image~~、~~picture~~ |
| **Writing** | 剧本撰写 stage，产出 Episode 正文 | ~~generation~~ |

---

## Agent 角色词汇（映射到 team 隐喻）

用户面前"team 感"的具体呈现。以下角色名是**产品面向用户可见的名字**，代码里可用英文变量。

| Agent | 中文可见名 | 负责 stage | 用户看到的样子 |
|---|---|---|---|
| Ideation Agent | **创意总监** | Ideation | 生成 3 个差异化方案 |
| Structure Agent | **编剧架构师** | Structure | 世界观 + 角色 + 大纲 + 爽点 |
| Writing Agent | **撰写师** | Writing | 逐集短剧正文 |
| Review Agent | **审稿人** | Review（Ralph Loop 里跑） | 六维打分 + 问题列表 + 建议 |
| Polish Agent | **对白导演** | Polish | 对白优化、格式统一 |
| Asset Agent | **制片主任** | Assets | 从剧本抽出资产台账 |
| Prompt Agent | **视觉总监** | Prompts / VisualAsset | 生图 prompt + 图像迭代 |

---

## 反 Living Asset 反面示例（勿模仿）

- ❌ 在 `episodes.scenes` 字段里塞整集正文当"一个 scene"
- ❌ 用中文正则从 LLM 输出里"猜"新角色名并直接写库（当前 `context_engine.save_episode_context` 就这么做）
- ❌ Character 只在 Structure 阶段被创建，Writing 只读不改
- ❌ Foreshadow 只有"埋"和"回收"两个状态（缺 `partially_resolved` 和 `abandoned` 等实际必需态）
- ❌ 前端 tab 切换等同于 stage 切换（tab 是拼凑，Growth Tree 才是生长）

正例见 ADR-0002。
