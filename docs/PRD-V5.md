# ScriptFlow · PRD-V5

- **Status**: Draft（待 Q老师 review）
- **Date**: 2026-07-15
- **Supersedes**: `docs/archive/PRD-V3.md`、`docs/archive/SPEC-V4.md`
- **Depends on**: [CONTEXT.md](../CONTEXT.md)、[ADR-0001](./adr/0001-adopt-growing-metaphor.md)、[ADR-0002](./adr/0002-living-assets-horizontal-model.md)、[ADR-0003](./adr/0003-evolution-loop-three-tiers.md)

---

## Problem Statement

我是一个独立编剧（Q老师视角的 P1 用户）。我打开当前 ScriptFlow：

- **看不到 team 的存在**。产品定位说是"AI Agent 团队协作"，但我面前只有一个匿名 Agent 挂在聊天泡泡上，感受不到"创意总监 / 编剧架构师 / 撰写师 / 审稿人"这些分工。
- **感觉是在"填空"，不是在"创作"**。7 个 tab 分别是 7 段独立表格，从 A tab 切到 B tab，前一段的产出去了哪儿、怎么变成下一段的起点，全靠我脑补。像在拼积木，不像在种树。
- **产出物没有"作品感"**。剧本正文一坨纯文本 pre 标签、角色卡 3 行简介、大纲 markdown 列表、伏笔一行文字。没有版式感、没有骨架感、没有仪式感。跟传统创作工具比矮一截，跟 StoryPlay/Toonflow 那种精致卡片比也矮一截。
- **角色、伏笔、场景、道具没有活起来**。角色在 Structure 阶段定义完就冻结了，写作时想动没入口。伏笔状态字段设计得挺全，但只用到 planted / resolved 两个态。场景术语在数据库、代码、UI 里语义不一致。
- **AI 生成味重**。缺 few-shot、缺风格锚点、缺 "AI 味" 检测。
- **写完 → 想改 → 卡壳**。所有产出物都是只读渲染，想改只能上手改 markdown 源码。
- **AI 不长记性**。做完一部作品，下一部还是从零开始。用户在项目 1 里表达过的偏好（喜欢短句、恨旁白、爱悬念），项目 2 一点儿没继承。
- **视频制作衔接是断层**。剧本产完就完了，没有"从关键场景 → 视觉资产 → 视频 prompt"的可延续链路。

**根因诊断**（见 ADR-0001）：整个产品是 **assembling**（拼凑）架构 —— 7 段独立管道 + 无血缘的产出物 + 只读的 Living Asset + 缺失的 Evolution Loop。核心隐喻错了。

## Solution

把产品重新架构成 **growing**（生长式）系统，围绕三大机制 + 一条红线（详见 CONTEXT.md）：

1. **Continuity（有机连续性）** — 用 Growth Tree 血缘图谱替代 7-tab 流水线 UI。每个产出物有 lineage，上游改动 cascade 到下游。
2. **Living Assets（横向骨架）** — 5 类 Asset：Character / Foreshadow / Scene / Prop / VisualAsset。跨 stage 存活，可被多 Agent 读写，有独立 UI 视图。
3. **Evolution Loop（反馈进化循环）** — 3 层嵌套：Ralph Loop（单集） / Reflection（单作品跨集反哺） / Style Library（跨作品自我进化）。
4. **Craft Standard（质量红线）** — 拒绝 AI 味 + 剧本纸规范 + 可持续编辑 + 行业标准导出。

**用户价值主张**：AI Agent 团队让你的剧本"长出来"。你是总指挥，指定方向和审美；team 各司其职地灌溉、追踪、反哺。作品越写越有骨架感、越用越懂你。

## User Stories

按机制分组，每组内按优先级（P0 = MVP 必做，P1 = 第二批，P2 = 长尾）。

### 机制一：Continuity（Growth Tree）

1. **[P0]** 作为独立编剧，我想在**一张 Growth Tree 视图**上看到我的作品从 Idea 到 Episode 的完整血缘，这样我随时清楚"这段剧本是从哪根枝上长出来的"。
2. **[P0]** 作为独立编剧，我想**从任意 Episode 点击"追溯"**跳回它对应的 Outline / Structure / Idea，这样我改动前先看它的上游语境。
3. **[P0]** 作为独立编剧，我想在**任何一个上游节点看到"衍生了哪些下游"**（比如 Idea A 点开 → 看到基于它的 3 版 Structure + 4 版 Outline），这样我随时能对比分叉。
4. **[P0]** 作为独立编剧，我想在**修改上游节点后收到"下游可能要修"的可视化标记**（不自动改），这样我知道哪些 Episode 现在跟新的上游脱节了。
5. **[P1]** 作为独立编剧，我想在 Growth Tree 上**创建一个分叉**（"如果这一集改一下钩子会怎样"），保留两个版本并可对比。
6. **[P1]** 作为独立编剧，我想给某个上游节点标 `frozen`，阻止 Agent 继续改动它。

### 机制二：Living Assets

#### Character

7. **[P0]** 作为独立编剧，我想在**任何 stage 都能打开"角色面板"**，看到全部角色的名称 / 定位 / 性格 / 出场轨迹（EP1-EP12）/ 弧光进度。
8. **[P0]** 作为独立编剧，我想**在 Writing 阶段直接改角色的性格 / 弧光设定**，改完立刻触发 Cascade 提示（相关 Episode 变 dirty）。
9. **[P0]** 作为独立编剧，我想看到**每个角色的出场时间轴**（哪几集出场、每集戏份轻重、当前状态是"活跃 / 隐退 / 死亡"）。
10. **[P1]** 作为独立编剧，我想**看到角色之间的关系图谱**（谁跟谁是什么关系）。
11. **[P1]** 作为独立编剧，我想给角色加一张**肖像图**（可上传，也可用生图 LLM 生成 —— 关联到 VisualAsset）。
12. **[P2]** 作为编剧工作室主管，我想看到角色的**弧光完整度评分**（Review Agent 打分）。

#### Foreshadow

13. **[P0]** 作为独立编剧，我想有一个**伏笔看板**，列出所有伏笔的 status（`pending / planted / partially_resolved / resolved / abandoned`）+ 埋点集 + 目标回收集 + 实际回收集 + 重要性。
14. **[P0]** 作为独立编剧，我想在**接近 target_episode 但还没回收**时收到提醒（"⚠ 伏笔 X 目标回收在 EP15，你已经写到 EP14 了"）。
15. **[P0]** 作为独立编剧，我想在 Writing Agent 生成完一集后，**Agent 自动更新伏笔状态**（明确埋 → 状态转 `planted`；明确收 → `resolved`；模糊回应 → `partially_resolved` 让我 review）。
16. **[P1]** 作为独立编剧，我想给伏笔加**隐蔽度评分**（1-5），Review Agent 用来审 "太明显 / 太隐晦"。
17. **[P1]** 作为独立编剧，我想**手动废弃**一个伏笔（`abandoned`）并注明理由，防止 Review 一直提示。

#### Scene

18. **[P0]** 作为独立编剧，我想把 `episodes.scenes` 这个乱塞整集正文的字段**迁移成独立 Scene 实体**（每个 Scene 一行，字段：episode_id / scene_number / location / time / content / characters / props）。
19. **[P0]** 作为独立编剧，我想在**每集详情视图看到该集的 Scene 列表**（不是一坨 pre 文本），Scene 可折叠 / 单独编辑。
20. **[P1]** 作为独立编剧，我想在**任意场景点"打回 Agent 基于我的改再改"**（局部改写而不重生成整集）。

#### Prop

21. **[P0]** 作为独立编剧，我想有一个**道具面板**（"这部戏出现了哪些道具，各出现在哪集"）—— 用于剧本正文一致性 + 视频制作前拍摄清单。
22. **[P1]** 作为独立编剧，我想给关键道具标 `plot_device` / `macguffin` / `background`，让 Review Agent 关注 plot_device 类的一致性。

#### VisualAsset

23. **[P1]** 作为独立编剧，我想**从关键 Scene 一键触发"生成场景图"**，走"从剧本描述抽取 → 生图 prompt 生成 → 生图 LLM 出图 → 我 review → 迭代 prompt"这个链路。
24. **[P1]** 作为独立编剧，我想给**角色**、**场景**、**道具**各自维护一张（或多张）视觉参考图，视频制作前一起打包。
25. **[P2]** 作为独立编剧，我想让**图像风格在同一部作品内保持一致**（用户选定风格 → 后续所有 VisualAsset 用相同风格 prompt 前缀）。

### 机制三：Evolution Loop

#### Ralph Loop（Tier 1）

26. **[P0]** 作为独立编剧，我想在 Writing Agent 完成一集后，**Review Agent 自动打六维分**（人物 / 情节 / 对白 / 节奏 / 钩子 / 类型契合度）+ 输出 issue 列表。
27. **[P0]** 作为独立编剧，我想看到 **Ralph Loop 的过程展示** —— 界面上明确能看到 "EP5 · Ralph #1 · 72 分（人物不足）→ 修改中 → #2 · 84 分 → 通过 ✅"。这是"过程感"的最小可见单元。
28. **[P0]** 作为独立编剧，我想**配置 Ralph Loop 的阈值和最大次数**（默认：pass 85 / revise 60 / max_retries 3）。
29. **[P1]** 作为独立编剧，我想在 Ralph 达到 max_retries 仍不通过时收到"需要人来看看"的标记（`human_review_needed`），并看到过去几轮的详细 diff。

#### Reflection（Tier 2）

30. **[P1]** 作为独立编剧，我想让 Reflection Agent **定期扫描当前剧本**（每写完 5 集触发），发现跨集矛盾（角色前后不一致 / 伏笔失控 / 世界观漏洞），生成"上游可能要修" 的建议。
31. **[P1]** 作为独立编剧，我想**决策 Reflection 的建议**（接受 → 触发 Cascade / 忽略 → Reflection 学到这类问题不介意）。
32. **[P2]** 作为独立编剧，我想看到 Reflection 的**历史记录**（在这部作品里，AI 反哺过多少次、我通过了多少、忽略了多少）。

#### Style Library（Tier 3）

33. **[P1]** 作为独立编剧，我想有一个**"我的风格档案"**页面，列出 AI 学到的关于我的偏好（"这类爱短句、这类恨旁白、伏笔喜欢短平快、对白偏文艺"等），我可以查看 / 编辑 / 删除任何一条。
34. **[P1]** 作为独立编剧，我想在**创建新项目时选择"复用现有风格档案 / 从零开始"**。
35. **[P2]** 作为独立编剧，我想选定一个 **genre 风格档案**（都市 / 古偶 / 悬疑）作为项目起点。

### 贯穿红线：Craft Standard

#### 拒绝 AI 味

36. **[P0]** 作为独立编剧，我想 skill prompts 里塞**高质量 few-shot**（每类 stage 至少 3 个人工挑选 + 标注的样例）。
37. **[P0]** 作为独立编剧，我想 Writing Agent 输出后**自动过一遍 "AI 味" 检测**（词频黑名单 + 短句/长句比 + LLM 判官），检出问题反哺给 Writing 重写。
38. **[P1]** 作为独立编剧，我想**上传一段我自己写的样本**作为 style reference，Agent 生成时对齐它的语感。

#### 剧本纸规范

39. **[P0]** 作为独立编剧，我想 Episode 详情视图**按剧本纸格式**渲染 —— `【场景N】地点·时间` 独立行、`△ 动作描述` 首行缩进、`角色：对白` 姓名列对齐、宋体 / 阅读字号。
40. **[P0]** 作为独立编剧，我想 Writing Agent 生成的内容**严格遵守剧本纸格式**（有格式校验器，不合规 → Ralph Loop 里当作 issue）。

#### 持续打磨

41. **[P0]** 作为独立编剧，我想**每个产出物都是可编辑的实体**（Episode / Scene / Character / Foreshadow 都能改），改动带版本、可 diff、可回滚。
42. **[P0]** 作为独立编剧，我想**点某段剧本"让 AI 基于我的改再改"**（inline reprompt），不重生成整集。
43. **[P1]** 作为独立编剧，我想 Episode 有**修订历史**（谁改的 / AI 还是我 / 改了什么），可以 rollback。

#### 行业标准导出

44. **[P0]** 作为独立编剧，我想导出 `.docx`（标准短剧格式）。
45. **[P1]** 作为独立编剧，我想导出 `.fdx`（Final Draft，好莱坞标准）。
46. **[P1]** 作为独立编剧，我想导出**资产包**（角色 + 场景 + 道具 + 视觉资产的 JSON + Excel）用于剧组。
47. **[P2]** 作为独立编剧，我想导出**视频提示词包**（Seedance 2.0 / Wan 兼容格式），一键喂给下游工具。

### 系统级 & 基础工程

48. **[P0]** 作为**任何用户**，我登录后**只能操作自己的项目**（当前 auth 是装饰品，任何 user_id 都能操作任何项目 —— 见评审 P0 #4）。
49. **[P0]** 作为**任何用户**，我想 JWT_SECRET 环境变量缺失时**启动失败**而不是静默 fallback（当前重启每次换密钥 → 用户静默掉线）。
50. **[P0]** 作为**开发者**，我想有 `pyproject.toml` + `requirements.lock` + 一份 README，从头 setup 环境 < 5 分钟。
51. **[P0]** 作为**开发者**，我想数据库 schema 有**单一 source of truth**（当前 `main.py` 裸 SQL 和 `models.py` SQLAlchemy 并存 —— 见评审 P0 #1）。
52. **[P0]** 作为**开发者**，我想 LLM 访问有**单一路径**（当前 `llm_gateway` / `llm_client` / `agent_orchestra` 三份实现 —— 见评审 P0 #2）。
53. **[P0]** 作为**开发者**，我想没被 caller 使用的 `agents/*_agent.py` 死代码**要么复活要么删除**（当前死存着，会误导后来者 —— 见评审 P0 #3）。
54. **[P0]** 作为**开发者**，我想 Agent 工具调用走 **AgentScope 原生 Toolkit**，不走正则解析 hallucinated JSON。
55. **[P1]** 作为**开发者**，我想有 backend + frontend 的 pytest / vitest 骨架 + 至少一个通过的端到端冒烟测试。

## Implementation Decisions

### Seams（测试锚点，遵循"接口即测试面"原则）

一份好的实现里 seam 越少越好。V5 建议的核心 seam：

1. **`LivingAssetRepo`（后端）** — 一个接口，5 个 impl（Character / Foreshadow / Scene / Prop / VisualAsset）。所有 Agent 读写 Living Asset 走这个接口，不直接接 SQL。这是最重要的 seam —— 有它，Living Asset 的 CRUD 逻辑单测覆盖率能到 100%；缺它，测试就得 mock 数据库。
2. **`GrowthTreeService`（后端）** — 血缘查询 + Cascade 传播的入口。纯函数式（输入 lineage graph + 事件 → 输出 dirty markers），可以纯单测。
3. **`EvolutionEngine`（后端）** — Ralph / Reflection / Style Library 的统一入口。三层各自是纯策略函数（`should_pass(review)` / `should_reflect(episode_history)` / `merge_styles(scopes)`），可以纯单测。集成层负责调度。
4. **`AgentTeam`（后端）** — 唯一的 LLM 调用出口。替换掉当前的三份并存（llm_gateway / llm_client / agent_orchestra）。每个 Agent 是 `AgentTeam` 里注册的一员，用 AgentScope 原生 Agent + Toolkit。
5. **`SkillLibrary`（后端）** — Skill markdown + Style Library merge 的产出，喂给 `AgentTeam` 作为 system prompt。可纯单测。
6. **`useGrowthTree` / `useLivingAssets` / `useEvolution`（前端）** — Vue composables 作为前后端交互的边界。UI 组件只跟这几个 composable 打交道，可以在测试里 mock 掉它们。

### 模块划分（backend）

```
backend/app/
├── main.py                          # FastAPI app, lifespan, middleware
├── config.py                        # 单一配置源（合并现有 core/config.py + settings）
├── db.py                            # 单一 DB 连接管理 + migration 入口
├── models/                          # SQLAlchemy 模型（single source of truth，移除 main.py 里的裸 SQL）
│   ├── __init__.py
│   ├── user.py
│   ├── project.py
│   ├── growth_tree.py               # GrowthNode + Lineage 边表
│   ├── episode.py
│   └── living_assets/
│       ├── character.py
│       ├── foreshadow.py
│       ├── scene.py                 # 新增，独立表
│       ├── prop.py                  # 新增
│       └── visual_asset.py          # 新增
├── repos/                           # Repository 层，隐藏 SQL 细节
│   ├── living_asset_repo.py         # 统一接口 + 5 个 impl
│   ├── growth_tree_repo.py
│   └── evolution_repo.py
├── services/                        # 领域服务
│   ├── growth_tree_service.py       # 血缘 + cascade
│   ├── evolution_engine.py          # ralph / reflection / style
│   └── skill_library.py             # 合并 skill markdown + style
├── agents/                          # Agent 定义（用 AgentScope 原生 API）
│   ├── team.py                      # AgentTeam：注册 + 路由 + 编排
│   ├── ideation.py
│   ├── structure.py
│   ├── writing.py
│   ├── review.py                    # 复活当前死代码
│   ├── polish.py
│   ├── asset_curator.py
│   └── visual_director.py           # 生图 LLM 集成
├── api/
│   ├── auth.py                      # JWT 校验 middleware / dependency
│   ├── projects.py
│   ├── living_assets.py             # 一个 CRUD 端点，5 类 asset 走同一入口
│   ├── growth_tree.py               # tree + lineage 查询 + cascade 触发
│   ├── evolution.py                 # ralph 状态 / reflection 决策 / style 编辑
│   ├── workspace.py                 # 保留但精简
│   └── export.py                    # .docx / .fdx / asset pack
├── skills/                          # 保留结构，但内容重写（few-shot 加强 + 术语对齐）
│   ├── ideation/
│   ├── structure/
│   ├── writing/
│   ├── review/                      # 六维评审 skill
│   ├── polish/
│   ├── assets/
│   └── visual/
└── tests/                           # 新增
    ├── test_living_asset_repo.py
    ├── test_growth_tree.py
    ├── test_evolution_engine.py
    ├── test_skill_library.py
    └── test_agent_team_integration.py
```

### Schema 变更

- **删除**：`episodes.scenes` 列（数据迁移到独立 `scenes` 表）
- **新增表**：`scenes`、`props`、`visual_assets`、`growth_nodes`、`growth_edges`、`reflections`、`style_profiles`
- **保留 & 强化**：`characters`（复活未使用字段）、`foreshadows`（补全状态机代码路径）
- **删除死表**：无（`reviews` 表复活，映射到 Ralph Loop 输出）
- **迁移策略**：一次性迁移脚本，用 alembic 或简单 Python 脚本。**破坏性变更**，会 flag 给用户 confirm 后执行。

### API 契约

- `GET /api/projects/{id}/tree` — 返回 Growth Tree 全景（节点 + 边）
- `GET /api/projects/{id}/tree/lineage/{node_id}` — 追溯 + 衍生
- `POST /api/projects/{id}/tree/cascade` — 触发 cascade（改上游后 mark 下游 dirty）
- `GET/POST/PUT/DELETE /api/projects/{id}/assets/{asset_type}` — Living Asset CRUD，`asset_type ∈ {character, foreshadow, scene, prop, visual}`
- `GET /api/projects/{id}/evolution/ralph/{episode_id}` — 一集的 Ralph loop 历史
- `POST /api/projects/{id}/evolution/reflect` — 触发 Reflection 扫描
- `POST /api/projects/{id}/evolution/reflect/{id}/decide` — 决策 Reflection 建议
- `GET/PUT /api/users/{id}/style-profile` — 编辑风格档案
- `POST /api/projects/{id}/export?format={docx,fdx,assets,prompts}` — 导出

### Agent 编排

用 AgentScope 原生 `Agent + Toolkit` 替代当前的正则解析。每个 Agent 注册工具函数（`save_scene`, `update_character`, `plant_foreshadow`, `resolve_foreshadow`, `mark_dirty` 等）。工具调用走 AgentScope 的 ReAct 循环，不 hallucinate JSON。

### 前端模块划分

```
frontend/src/
├── main.ts
├── App.vue
├── router.ts                       # 新增，避免 App.vue 里手工 route 逻辑
├── api/                             # 抽出，替代当前 api.ts
│   ├── client.ts                    # axios 实例 + interceptor
│   ├── projects.ts
│   ├── living-assets.ts
│   ├── growth-tree.ts
│   └── evolution.ts
├── composables/                     # 前后端交互的 seam
│   ├── useGrowthTree.ts
│   ├── useLivingAssets.ts
│   └── useEvolution.ts
├── components/
│   ├── growth-tree/                 # 树视图核心
│   │   ├── TreeView.vue
│   │   ├── TreeNode.vue
│   │   └── LineageBreadcrumb.vue
│   ├── living-assets/
│   │   ├── CharacterPanel.vue
│   │   ├── ForeshadowBoard.vue
│   │   ├── ScenePanel.vue
│   │   ├── PropPanel.vue
│   │   └── VisualAssetGallery.vue
│   ├── evolution/
│   │   ├── RalphLoopView.vue        # 关键：Ralph loop 可视化
│   │   ├── ReflectionInbox.vue
│   │   └── StyleProfileEditor.vue
│   ├── editor/
│   │   ├── ScriptSheet.vue          # 剧本纸样式渲染
│   │   ├── SceneEditor.vue
│   │   └── InlineRepromptDialog.vue
│   └── shared/
│       ├── AgentAvatar.vue          # team 感的具体呈现
│       └── DirtyBadge.vue
├── pages/
│   ├── LoginPage.vue
│   ├── Dashboard.vue
│   └── Workspace.vue                # 大改 —— 不是 tab 布局，是 Tree + Panels 布局
└── styles/                          # 抽出，避免 Workspace.vue 里 200 行内联 CSS
    ├── tokens.css                   # 设计令牌
    └── script-sheet.css             # 剧本纸样式
```

## Testing Decisions

### 好测试的标准（复用 tdd skill 精神）

- **只测 public interface** — 不 mock 内部函数、不测私有方法
- **不 tautological** — 期望值来自独立源头，不是"用被测代码同样公式算一遍"
- **一次一个 seam** — 一个测试 verify 一个行为，一片测试对应一层 seam
- **vertical slice** — 每个 tracer bullet issue 至少一个端到端测试

### 测试点

| 模块 | 测试内容 | 层级 |
|---|---|---|
| `LivingAssetRepo` (5 impl) | CRUD + 跨 episode 时间轴 + 状态转换 | 单测 + 集成（真 SQLite） |
| `GrowthTreeService` | 血缘查询、cascade dirty 传播 | 纯单测（无 DB） |
| `EvolutionEngine.ralph_should_pass` | 六维打分决策 | 纯单测 |
| `EvolutionEngine.style_merge` | 三级 scope merge 优先级 | 纯单测 |
| `SkillLibrary.assemble` | Skill markdown + style 合并 | 纯单测 |
| `AgentTeam.route` | stage → agent 分派 | 纯单测（mock model） |
| `agent 端到端` | Ideation → Structure → Writing 走通 | 集成（真 LLM 或 fixture） |
| Auth JWT | 缺 SECRET → 启动失败；错 token → 401 | 集成（TestClient） |
| Export `.docx` | 格式正确、可打开 | 单测（生成 → parse 校验） |
| Frontend composables | mock API → 组件行为 | vitest + @vue/test-utils |
| Growth Tree UI | 点击追溯 → 高亮 | e2e（后续，先不做） |

### 现有代码里的 Prior Art

**当前 backend 无测试**，frontend 也无。**这份 PRD 明确要求 tracer bullet #003 起就要建立 pytest / vitest 骨架**。

## Out of Scope

以下功能来自 PRD-V3 / 讨论，但 V5 明确**不做**：

1. **多人协作 / 编剧工作室** — 无实时同步、无权限矩阵、无冲突解决
2. **网文改编 / 剧本改写 / 拉片** — StoryPlay 的辅助能力，不做
3. **MCN 批量评估** — 无
4. **点数 / 会员体系** — 保留字段以免破坏 schema，但**不做业务逻辑**（所有用户等同）
5. **国际化 / 翻译 / 文化适配** — 保留数据库字段，不做业务
6. **移动端** — 桌面优先
7. **AgentScope Studio 监控接入** — 后续
8. **完全 event sourcing** — 不做，用 asset 内 `history` 字段够用

## Further Notes

### 交付节奏

V5 不是"重写"，是"重构 + 加骨架"。分阶段：

- **Phase 3.1 · 清坏疮**（P0 issues #48-#54）— schema / LLM / agent 三路合流；auth 上锁；死代码清理；启动 setup 补齐
- **Phase 3.2 · Living Assets 骨架**（Character / Foreshadow / Scene）— schema 迁移 + 独立 UI 面板 + 跨 stage 读写
- **Phase 3.3 · Ralph Loop 复活**（Evolution Tier 1）— 六维评审 + 循环可视化
- **Phase 3.4 · Growth Tree UI**（Continuity）— Workspace.vue 大改
- **Phase 3.5 · Craft Standard 打磨**（剧本纸样式 + 编辑器 + .docx 导出）
- **Phase 4+ · 长尾**（Reflection / Style Library / VisualAsset / .fdx / 视频 prompt）

### 风险

- **AgentScope 2.0 是较新框架**，某些边缘 API 可能不稳。缓解：锁定版本、维护 `docs/agentscope-notes.md` 记坑。
- **Growth Tree UI 是新范式**，用户可能不习惯。缓解：保留一个"经典 tab 视图"作为 escape hatch。
- **数据迁移破坏性**。缓解：迁移脚本前强制备份；分阶段迁移；提供回滚点。
- **skills prompt 重写涉及创作质量**。缓解：先在几个真实项目上 A/B 对比新旧 prompt 输出，再全量替换。

### 术语一致性

代码 / UI / 文档 / commit message 一律用 [`CONTEXT.md`](../CONTEXT.md) 术语。发现旧术语（`role` / `pipeline` / `workflow`）→ 顺手替换成正名（`character` / `growth_tree`）。
