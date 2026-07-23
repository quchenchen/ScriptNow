# ScriptFlow V6 第三方创作机制融合报告

> 研究对象：Toonflow-app、MuMuAINovel。目的为吸收产品与工程模式，不复制源代码、Prompt 原文或其特定商业创作价值判断。

## 1. 结论

两个项目值得吸收，但不能以“合并 Skills 文件”的方式接入。

- Toonflow 的核心价值是 **Agent 职责分层 + Skill 渐进加载 + 工作区工具化读取 + 多层记忆检索**。
- MuMuAINovel 的核心价值是 **长篇分块与恢复 + 章节级连续性 + 选择性修订 + Living Asset 自动提取候选 + 质量门控**。
- ScriptFlow 应把这些能力放进现有的 `Task → Artifact → Revision → Decision` 闭环，由人机协作宪法约束自主程度。

融合后的差异化不应是“拥有更多 Prompt”，而是形成一套 **可持续创作协议 Creative Continuity Protocol**：每次创作都知道依据、范围、保留项、变化、影响和恢复点。

## 2. 模式评估

| 参考模式 | 来源 | 价值 | ScriptFlow 处理 |
|---|---|---|---|
| 决策 / 执行 / 监督分层 | Toonflow | 避免一个 Agent 同时定方向、写作和自我验收 | 改造后吸收：映射为 Task 阶段和角色责任，不必创建三个常驻 Agent |
| 主 Skill / 工作区 Skill / 附加 Skill | Toonflow | 能力与项目、类型知识分层 | 直接吸收为 Skill Bundle 三层上下文 |
| `activate_skill` + 资源按需读取 | Toonflow | 降低 Prompt 膨胀 | 直接吸收，并增加版本、预算和使用记录 |
| 最近对话 + 摘要 + RAG + 深度回溯 | Toonflow | 长会话可恢复细节 | 改造后吸收：对话记忆只服务协作，不替代作品事实 |
| 先读工作区/事件表再执行 | Toonflow | 生成前检查已有产物 | 直接吸收为 Context Assembly 必经步骤 |
| 结构化骨架与改编约束 | Toonflow | 把媒介规则前置到规划阶段 | 改造后吸收为可配置 Craft Profile，拒绝硬编码单一商业公式 |
| Skill + references 目录 | MuMu | 主工作流和知识材料分离 | 直接吸收，references 必须按需而非全量拼接 |
| 快速 / 深度模式路由 | MuMu | 同一目标按规模选择不同成本 | 吸收为 Task Depth：Quick / Standard / Deep |
| 分块、阶段产物、断点恢复 | MuMu | 适合 100–500+ 章长篇 | 直接吸收为 Batch Task + Checkpoint Artifact |
| 置信度 / 覆盖率 / 重叠率门控 | MuMu | 长文聚合前可检查完整性 | 改造后吸收：门槛按 Skill 类型定义，不做虚假通用分数 |
| 建议选择 + 自定义要求 + 重点方向 + 保留项 | MuMu | 把“重写”变成受约束修订 | 直接吸收为 Revision Brief |
| 已使用事件与前批摘要 | MuMu | 降低批量章节重复 | 吸收为 Novelty Ledger，不依赖单纯 Prompt 提醒 |
| 角色心理状态与章节锚点 | MuMu | 长篇人物连续性更具体 | 改造后吸收为 Character State Event 候选 |
| 伏笔链与上下文开关 | MuMu | 控制哪些伏笔进入生成上下文 | 直接吸收为 Plot Thread Context Policy |

## 3. 不吸收的部分

### 不把线性管道重新变成产品导航

内部可以有“分析—执行—监督”步骤，用户界面仍围绕当前作品对象和三种工作模式。用户不需要管理子 Agent 流水线。

### 不全量拼接 references

知识文件全部注入会造成上下文拥挤和规则冲突。Skill 激活只加载能力摘要，参考材料根据当前步骤、媒介和问题按需读取。

### 不把对话记忆当作作品事实

对话摘要可能丢细节或保存错误推断。Character、Timeline、Source Canon、已采用 Decision 必须进入结构化 Artifact；记忆只帮助恢复协作上下文。

### 不把单一类型经验写成全局真理

付费卡点、强钩子、爽点密度等适合部分短剧，但不能成为原创小说或所有剧本的默认价值观。它们进入可选择的 `Craft Profile`，并显示适用媒介、受众和代价。

### 不直接覆盖整章

“分析后重新生成整章”升级为 Candidate Revision。基线已变化时必须重新比较；用户可只采用解决某个问题的修改块。

## 4. 融合后的创作核心：Creative Continuity Protocol

每次写作 Task 在生成前后都执行五个步骤。

### Step 1 · Assemble：组装最小充分上下文

Context Assembler 根据当前对象生成 Context Pack：

```yaml
target:
  artifact_id: scene-03
  base_revision: rev-3
intent:
  goal: 延后林夏的明确指控
  scope: dialogue-block-2
anchors:
  story_beat: beat-02@rev-2
  characters: [linxia@state-ep01, zhoujin@state-ep01]
  source_refs: [chapter-3#p18-p22]
open_threads: [foreshadow-f07]
preserve:
  - 邮戳事实
  - 铁链声线索
constraints:
  - 不改变场景目标
  - 不提前揭示周谨身份
```

Context Pack 不是 Prompt 文本，而是可检查、可记录、可复用的 Task 输入产物。

### Step 2 · Plan：形成 Revision Brief

复杂 Task 先交付一行 Brief；深度任务交付可编辑计划。Brief 至少包含目标、范围、依据、保留项、允许变化与交付类型。

### Step 3 · Execute：按深度和范围生成

- Quick：单点诊断、局部候选，通常一次完成。
- Standard：Scene/Chapter 级任务，包含上下文检查和一次自检。
- Deep：长篇拆解、跨章规划、批量 Cascade；分批运行并创建 Checkpoint。

### Step 4 · Supervise：结构规则与创作审阅分离

先做确定性检查（Schema、引用、Frozen 权限、范围），再做创作性审阅（人物、因果、节奏、风格）。监督 Agent 不能采用自己的修订。

### Step 5 · Deliver：交付可处理的变化

Delivery 必须包含：候选内容、与基线的 diff、解决的问题、仍存在的风险、影响对象和下一动作。只有用户采用后才更新当前 Revision。

## 5. Context Pack 分层

借鉴 Toonflow 的三层 Skill 与 MuMu 的章节上下文，ScriptFlow 使用四层 Context Pack：

1. **Immutable Guardrails**：人机协作权限、Frozen、来源权利和安全边界。
2. **Project Truth**：当前采用 Story Core、Source Canon、用户明确决定。
3. **Task Locality**：当前对象、相邻单位、相关 Character State、Plot Thread。
4. **Craft Bundle**：媒介 Skill、当前任务 Skill、可选 Craft Profile 与按需 reference。

冲突时按 1 → 4 的顺序处理。Context Assembler 记录每项为何被纳入，并设置 token/字符预算；超预算时优先保留事实和当前对象，压缩历史，不压缩硬约束。

## 6. 长篇创作机制

### Batch Task 与 Checkpoint

Deep Task 按自然边界分块：卷、章、Episode、Scene 或 Source 章节，不按任意 token 截断。每批产生 Checkpoint：

- 已处理范围
- 使用的 Revision 与 Skill 版本
- 新增/变化的角色、事件、伏笔候选
- Novelty Ledger
- 质量门控结果
- 下一批所需最小状态

失败后从最后一个完整 Checkpoint 恢复，不能把部分结果伪装为完成。

### Novelty Ledger

记录已使用的关键事件、开场方式、冲突形态、结尾钩子和意象。它只提供“可能重复”的证据，不机械禁止有意复现、回环或母题重复。

### Living Asset Candidate

章节写作或审稿后，Agent 可以提取：

- Character State Event
- Relationship Change
- Timeline Event
- Foreshadow / Resolve Event
- New World Fact

这些先进入候选队列。可从正文确定推导的低风险事实可按 A3 批量采用；涉及动机解释或设定变化的内容进入 A4 Decision。

## 7. Revision Brief：重写前的核心交互

融合 MuMu 的选择性重写后，用户不再只看到一个“重新生成”按钮。

```text
修订目标：解决林夏怀疑过早
选择问题：人物动机 #2、来源偏移 #1
重点方向：对白、悬念
必须保留：邮戳事实、铁链声、Scene 目标
允许改变：两句对白和一个动作
禁止改变：Story Beat、人物关系、下一场入口
交付：一个可逐块采用的 Candidate Revision
```

默认值由当前问题和选区补全，用户只修改有分歧的部分。生成期间若基线变化，系统将 Delivery 标记为 stale，重新计算 diff 后才能采用。

## 8. Skill 体系升级

### Skill 三层结构

```text
Core Skill       当前任务的可执行协议
Workspace Pack   项目/媒介/类型的工作区能力
Reference Pack   按需读取的技法、范例和检查表
```

每个 Skill 在现有契约上新增：

- `depth_modes`: quick / standard / deep
- `context_requirements`: 必须与可选的 Context Pack 槽位
- `checkpoint_policy`: 分块和恢复规则
- `extraction_policy`: 可产生哪些 Living Asset Candidate
- `quality_gates`: 确定性门槛与创作性 rubric
- `reference_routing`: 何时读取哪份 reference
- `incompatible_profiles`: 不可同时启用的 Craft Profile

### 首批十个生产 Skill

1. idea-divergence
2. story-core-shaping
3. story-beat-planning
4. scene-draft
5. chapter-draft
6. selection-revision
7. continuity-review
8. adaptation-map
9. source-grounded-draft
10. longform-decomposition

“去 AI 味”、短剧商业节奏等作为 Craft Profile 或 Review Lens，不单独劫持整个写作流程。

## 9. UI 与人机交互变化

### 专注创作

选区工具新增“修订 Brief”。简单操作直接运行；展开后可调整保留项、禁止项和重点方向。后台 Task 显示当前步骤而非笼统思考过程。

### 故事规划

增加 Continuity Strip：显示当前 Scene/Chapter 的 Character State、关系变化、伏笔和来源引用。写作后出现“发现 4 个作品变化”的候选入口，不弹窗打断。

### 审阅决策

Decision 按根因合并。Compare 不只显示文字差异，还显示“解决了什么 / 保留了什么 / 影响了什么”。长篇 Deep Task 使用批次时间线和 Checkpoint 恢复入口。

## 10. 实施优先级

### P0 · 先证明一个闭环

1. Context Pack schema 与 Context Assembler。
2. Revision Brief 与 stale base 检测。
3. selection-revision Skill Contract。
4. Candidate Revision + diff + adopt/reject。
5. 写作后的 Character/Foreshadow 候选提取。

### P1 · 长篇可持续推进

1. Deep Task、Batch、Checkpoint 与恢复。
2. Novelty Ledger。
3. Living Asset Candidate Inbox。
4. longform-decomposition 和 continuity-review Golden Project。

### P2 · 能力生态

1. Craft Profile 管理。
2. Skill/reference 路由与上下文预算观测。
3. Skill 版本对比、质量回归与项目锁定版本。

## 11. 参考证据

- Toonflow 的 Skill 三层与按需加载：[skillsTools.ts](/Users/quchenchen/Documents/github/Toonflow-app/src/utils/agent/skillsTools.ts:22)
- Toonflow 的决策记忆与监督入口：[scriptAgent/index.ts](/Users/quchenchen/Documents/github/Toonflow-app/src/agents/scriptAgent/index.ts:65)
- Toonflow 的短期/摘要/RAG/深度回溯：[memory.ts](/Users/quchenchen/Documents/github/Toonflow-app/src/utils/agent/memory.ts:134)
- MuMu 的深度分块、质量门控与恢复：[story-long-analyze/SKILL.md](/Users/quchenchen/Documents/github/MuMuAINovel/backend/app/skills/story-long-analyze/SKILL.md:50)
- MuMu 的问题选择、重点方向和保留项：[chapter_regenerator.py](/Users/quchenchen/Documents/github/MuMuAINovel/backend/app/services/chapter_regenerator.py:113)
- MuMu 的批次上下文和防重复机制：[plot_expansion_service.py](/Users/quchenchen/Documents/github/MuMuAINovel/backend/app/services/plot_expansion_service.py:164)
- MuMu 的章节锚定人物状态：[character.py](/Users/quchenchen/Documents/github/MuMuAINovel/backend/app/models/character.py:35)
- MuMu 的伏笔链与上下文策略：[foreshadow.py](/Users/quchenchen/Documents/github/MuMuAINovel/backend/app/models/foreshadow.py:69)
