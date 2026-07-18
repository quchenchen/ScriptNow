# ScriptFlow V7 「Revision Focus」开发计划

> 原型: `scriptflow-v7-revision-focus.html`（Open Design 项目 e9895ce5，6408 行）
> 基线: `scriptflow-v6/`（FastAPI 28 表 60+ 路由 + Vue3 App.vue 单文件）
> 日期: 2026-07-18 · 状态: **待确认**

---

## 一、原型解读 — V7 的产品主张

V6 解决了「从 0 生长出一部作品」（发散→采纳→蓝图→逐场写作）。
V7 原型回答的是下一个问题：**「写出来之后，怎么把它改好？」** —— 把「修订」提升为一等公民，同时补齐商业化外壳。

### 四大产品支柱

**支柱 1 · 五维修订体系（本版核心，文件名 revision-focus 所指）**
- 审读编辑 Agent 对正文做五维扫描：**世界观 / 人物 / 弧线 / 事件 / 伏笔**
- 每条修订 = 严重度（blocker/major/minor）+ 维度 + 来源（AI 责编 / 人工意见）+ **锚点卡**（关联到蓝图中的具体实体：角色、世界规则条目、弧线节拍、事件链、伏笔编号）+ 原文块 + 诊断 + 建议稿 + 置信度
- 三层渐进聚焦：按严重度（分组排序）/ 按维度（Layer1 汇总→点击下钻）/ 按场次
- 「📍 定位」→ 正文呼吸高亮滚动；采纳→应用替换；忽略→留痕
- 修订痕迹在 Writer 右栏与「上下文」并列为双 Tab，有计数徽标
- 关键洞察：**修订不是浮空的意见，每条都锚定在故事蓝图的实体上**——这正是 V6 蓝图层（entities/arcs/foreshadows）的变现时刻

**支柱 2 · Agent 事件总线（全项目唯一 append-only 事件流）**
- 四类事件：chat 对话 / node 节点 / decision 决策 / system 系统；一个写入口 `notify()` = toast 即时通知 + 入流永久留痕
- 修订时间线、历史版本、导出记录都是**这条流的过滤投影**（"记录类视图=流的投影"是架构级理念）
- Agent Dock：底部悬浮对话（跨视图常驻），ticker 滚动最新事件、未读徽标、过滤 chips、同 group 聚合防噪
- Agent 自管理透明化：上下文占用 %、越阈自动压缩留痕、记忆条数——**用户可审查/纠正 Agent 记忆的入口**
- Agent Status Bar：当前视图对应的 Agent 角色 + 模式（总览/项目设置/发散/蓝图/目录/修订）+ 上下文 chips

**支柱 3 · Agent 团队（4 角色人格化）**
- 创意导演 Director（向导+StoryCore）/ 架构规划师 Architect（蓝图+StoryMap）/ 写作者 Writer（逐场写作）/ 审读编辑 Editor（修订）
- 名称与 Soul 可自定义；职责与系统能力预设只读；**模型绑定从会员等级池内选择**
- 视图切换 = Agent 角色接管（agent bar 头像/角色随视图变化，phase 切换事件入流）

**支柱 4 · 商业化外壳（账户体系）**
- 登录页 → Welcome 页（「让好故事长出来」）→ 控制台
- 等级 Plus/Pro/Max：月度 token 额度 + 不过期点数包，各档点数只能驱动相应等级模型
- User Center：会员与额度 / 当前项目 LLM（模型池按等级开放）/ 点数充值
- 侧栏账户卡 + topbar 用量徽章，实时 token 计量

### 其余增量
- **Wizard 重构**：4 步 = ①作品方向（9 个 direction，类型×媒介互锁：竖屏短剧/横屏网剧/电影/动画/长篇小说/中短篇/互动叙事/舞台剧/自定义）②创作来源（原创灵感 / 改编+多文件上传）③叙事结构（8 种，含哈蒙圆环、自定义）+ **剧本格式（中国/好莱坞，创建时锁定不可切换）** ④故事体量（3 个随方向动态变化的 scale 标签 + 项目预览卡）
- **StoryCore 卡升级**：5 角度 tag + 展开详情（叙事引擎/视角锚定/节奏配方/市场判断 pills）
- **Blueprint 6 Tab**：世界观 6 卡（时代/地理/规则/社会/基调/媒介参数）、人物小传卡、叙事弧线 SVG 曲线+12 阶段（含集数范围）、人物弧线进度、关键事件时间线、伏笔网络（埋设→回收）
- **StoryMap**：集×场树形目录 + 每集弧线归属 + 场次时长
- **Writer 三栏**：场景目录（done/writing/draft 状态点）| 编辑器（**中国/好莱坞双格式 CSS 渲染**：slugline/action/character/dialogue 结构化段落）| 右栏 上下文/修订 双 Tab
- **选区→Agent 引用**：编辑器划选 → popover（扩写/缩写/润色/修订）→ 引用 chip 停靠 Agent 输入上方 → 发送后 Agent 按引用+附加指令响应（对接 V6 ai-edits 五模式）
- **导出剧本**：DOCX，集×场勾选（含全选/仅完稿门槛/半选状态），纯净稿/工作稿两种形态，导出记录入流
- **历史版本**：文稿级快照，**仅手动保存**+命名，预览/diff 对比/回滚（回滚=把旧版内容按锚点应用回编辑器）
- 侧栏项目切换器（多项目并存直切）、保存状态指示、侧栏拖拽收起（⌘B）

### 信息架构（V7 导航）

```
侧栏
├─ 当前项目 [切换器 select + 新建]
├─ 创作:  ◇创意发散(badge=候选数) ▦蓝图规划 ⊞StoryMap ▸逐场写作
├─ 项目:  ◈项目仪表盘 ✦创建项目 ↓导出剧本(modal) ↺历史版本(modal)
└─ 账户:  头像卡(等级pill+用量条) → User Center(modal)
主区 = topbar(保存状态+用量徽章) + Agent Bar(角色+模式+ctx chips) + 视图容器
全局 = Agent Dock(底部悬浮) + Agent设置modal + 登录/Welcome 屏
```

---

## 二、V6 → V7 差距矩阵

### 后端：能力复用度高，缺 4 个模块

| V7 需求 | V6 现状 | 判定 |
|---|---|---|
| 项目/计划/StoryMap/StoryCore/架构/连续性/实体/伏笔/指令 | 28 表 + 60 路由全有 | ✅ 直接复用 |
| 逐场写作 opening/next/adopt/revise + 上下文打包 | writing.py 完整 | ✅ 复用 |
| 选区 AI 编辑（扩/缩/润/对白/节奏）+ 流式 | manuscript_edits + ai-edits/stream | ✅ 复用（前端接 popover 即可）|
| 文稿版本化 | manuscript_document_versions（unit 级） | 🔶 扩展：项目级手动快照+命名+diff+回滚 |
| 蓝图变更级联 | story_bible_changes + cascade_revisions | ✅ 复用（作为修订采纳的下游）|
| **五维修订 findings** | creative_revisions 是「场景改稿候选」，语义不同 | 🆕 新表 `review_findings` + 审读编辑 skill + 扫描/采纳/忽略 API |
| **事件总线** | 各模块各自记录，无统一流 | 🆕 新表 `project_events` + 写入口函数 + GET/SSE 路由，关键操作全部入流 |
| **Agent 团队配置** | agent_runtime 单模型；ADR-0002 平台路由 | 🆕 `agent_team_configs` 表（role/name/soul/model_key）+ 模型池 API（⚠️ 决策点 #3）|
| **账户/等级/计量** | users 表已存在但无 auth 路由、无计量 | 🆕 auth(JWT) + tiers + token_usage 计量 + 点数（可 Phase 后置/简化）|
| 剧本格式 | ProjectPlan 无 script_format；正文非结构化段落 | 🆕 字段全链路 + 写作 skill 输出结构化标记 + 校验 |
| DOCX 导出 | 无（V5 线有参考实现 commit 436d111） | 🆕 python-docx + 集×场勾选 + 双形态 |

### 前端：信息架构级重构

V6 App.vue（466 行，dashboard/create/workspace 三屏）与 V7 原型（侧栏+6 视图+3 modal+Dock，交互面 ≈ 6400 行原型）不在一个量级。**结论：这不是 patch，是以 V7 原型为蓝本的前端重写**，但所有 API 对接逻辑、类型定义（App.vue 里 40+ 个与后端对齐的 type）可整体迁移。单文件 SFC 模式已到极限（skill 中已记录白屏陷阱），必须组件化拆分。

---

## 三、开发分期计划

> 原则：每期结束都是可运行、可验收的产品；创作主链路永远保持绿色。
> 铁律执行：原型中的《长安十二时辰》内容全部是**演示数据**，实现中一律由 Agent 生成/用户输入，禁止硬编码进代码。

### Phase 0 · 定案与地基（本计划确认后 0.5 天内完成）
- 决策点拍板 → 写 ADR-0003（模型池与等级，覆盖/修订 ADR-0002）、ADR-0004（事件总线为记录类视图唯一事实源）
- 前端组件化架构方案：`views/`（6 视图）+ `components/`（AgentDock/AgentBar/RevisionPanel/...）+ `stores/`（Pinia: project/events/user/agents）+ `api/` 客户端层
- DB：确认继续「删库重建」策略（无迁移系统），V7 新表一次性入 models.py
- 交付物：ADR ×2、前端目录骨架、本文档状态改为「已确认」

### Phase 1 · 前端骨架 + 主链路搬家（V7 壳跑 V6 功能）
- App Shell：侧栏（项目切换器/导航/账户卡）、topbar、Agent Bar、视图容器、设计 token（oklch 暖纸色系 + Iowan/Charter 显示字体）落地
- 6 视图迁移对接现有 API：Dashboard / Wizard（4 步新结构，direction×9、结构×8、格式选择、动态 scale）/ StoryCore（卡片+展开详情）/ Blueprint（6 Tab）/ StoryMap（树形）/ Writer（三栏，先只有「上下文」Tab）
- Wizard→创建→发散→采纳→规划→写作全链路在新 UI 打通（阶段门控沿用 V6 currentPhase 推导）
- 后端配套：ProjectPlan 增加 `direction_key`/`script_format` 字段；`/mediums` 扩为 9 direction 定义
- 验收：新 UI 完成一次「原创竖屏短剧」全流程创作；`pytest` + `npm run build` 绿

### Phase 2 · 五维修订体系（后端）
- `review_findings` 表：project_id/unit_id/domain(worldview|character|arc|event|foreshadow)/severity(blocker|major|minor)/source(ai|human)/anchor(entity_id|arc_id|foreshadow_id|thread_id 多态)/original_excerpt+locator/diagnosis/suggestion/confidence/status(open|accepted|dismissed)
- 审读编辑 skill（`skills/editorial-review/SKILL.md`）：输入 context_pack（蓝图五层数据）+ 正文 → 输出五维 findings JSON；严格要求锚点引用真实实体 ID，禁止幻觉锚点
- API：`POST /units/{id}/review/scan`（触发扫描）/ `GET findings` / `POST findings/{id}/accept`（应用建议稿→正文 patch→新版本→入流）/ `dismiss` / `POST findings`（人工意见创建）
- accept 联动：涉及蓝图实体状态变化时走既有 story_bible_changes/cascade 通道
- 验收：pytest 覆盖扫描→采纳→正文变更→留痕全链；血缘可回溯

### Phase 3 · 五维修订体系（前端，revision-focus 主战场）
- Writer 右栏双 Tab + 修订面板：三层聚焦（severity 分组/domain 汇总下钻/scene 过滤）、来源过滤、展开卡（锚点卡/原文/诊断/建议/置信度）、采纳/忽略动效
- 📍 定位：locator→正文呼吸高亮滚动；正文修订标记点
- 修订时间线（事件流投影 modal）
- 人工意见入口：正文划选 →「添加人工意见」
- 验收：Playwright 实测三层聚焦/定位/采纳全交互

### Phase 4 · 事件总线 + Agent Dock + 选区引用
- 后端：`project_events` 表 + 统一写入口（项目创建/候选生成/采纳/修订/导出/版本全部入流）+ `GET /projects/{id}/events`（增量拉取或 SSE）
- 前端：Agent Dock（对话+事件流渲染+过滤 chips+未读+ticker）、Agent Bar 状态条、decision 流视图；Dock 对话按 phase 路由到对应 Agent（chat 也入流）
- 选区→引用：popover（扩写/缩写/润色/修订）→ 引用 chip → 对接 ai-edits/stream，diff 候选回到对话流采纳（V6 已有 API）
- Agent 自管理指标：上下文 %/压缩事件/记忆条数（对接 agent_runtime 真实统计，不做假数字）
- 验收：跨视图操作全部留痕；刷新不丢流（DB 持久化，非 localStorage）

### Phase 5 · 剧本格式 + 导出 + 历史版本
- 写作 skill 按 script_format 输出结构化段落（slugline/action/character/dialogue/转场），后端校验器（V5 线 436d111 可参考），前端双格式 CSS 渲染 + 格式徽章（锁定提示）
- DOCX 导出：python-docx 双格式排版，集×场勾选+完稿门槛+纯净/工作稿，导出记录入流
- 历史版本：`project_snapshots` 表（手动保存+命名+范围+字数+delta），预览/结构化 diff/回滚（回滚生成新版本而非覆盖，入流留痕）
- 验收：导出的 DOCX 在 Word/Pages 排版正确；回滚可再回滚（无损）

### Phase 6 · Agent 团队 + 账户体系
- Agent 设置 modal：4 角色卡（名称/Soul 可编辑，职责/能力只读，模型选择器）；`agent_team_configs` 落库；agent_runtime 按角色取模型
- 账户：登录页/JWT 会话/Welcome 屏；tier 模型池过滤（Plus=DeepSeek，Pro=+Claude，Max=全部——池内容做成配置不硬编码）；token 计量中间件（每次 LLM 调用记录 usage→用量条/徽章真数据）；点数包（支付先 mock，记账逻辑真实）
- User Center 三卡：会员额度/项目 LLM/点数充值
- 验收：两账户数据隔离；用量随创作真实增长；降级/越权有明确拒绝

### Phase 7 · QA 与打磨
- 全链路 QA（新 QA-REPORT）：原创+改编双路径 × 双格式 × 修订循环 × 导出回滚
- 空态/加载态/错误态、响应式（侧栏拖拽收起/移动端）、动效细节（呼吸高亮/采纳消散/ticker tick）
- 性能：80 集项目的事件流分页、修订列表虚拟滚动
- 黑名单词检查、文档更新（skill 补丁、PRODUCT-DESIGN V7 版）

---

## 四、需要确认的决策点

| # | 问题 | 建议 |
|---|---|---|
| 1 | **代码基线**：scriptflow-v6/ 原地演进为 V7，还是复制新目录 scriptflow-v7/？ | 原地演进（后端复用 90%，git 在上层仓库有完整历史；V6 前端保留在 git 历史里即可）|
| 2 | **前端重写方式**：组件化拆分（Pinia+views/components）vs 继续单文件 App.vue | 组件化。V7 交互面太大，单文件已在 V6 造成白屏事故 |
| 3 | **ADR-0002 冲突**：原 ADR 规定「用户不可见模型名称」，V7 原型 User Center/Agent 设置明确展示模型名（DeepSeek/Claude/Gemini...）供等级内选择。以原型为准修订 ADR？ | 以 V7 原型为准 → ADR-0003「等级模型池」：池内可见可选，路由细节（降级/重试）仍不可见 |
| 4 | **账户体系排期**：Phase 6（创作核心优先）vs 提前到 Phase 1（原型以登录开场） | Phase 6。开发期用 dev 自动登录；但 Phase 1 起 UI 预留账户卡/用量位（假数据禁令→显示「未接入」态而非假数字）|
| 5 | **支付**：点数充值做真支付通道还是 mock 记账？ | mock 记账（记账逻辑真实、支付网关后置）|
| 6 | **事件流传输**：轮询增量拉取 vs SSE 推送 | 先增量拉取（简单可靠），Dock 打开时 3s 轮询；SSE 留到性能期 |

## 五、风险

- **审读编辑扫描质量**是本版灵魂：findings 必须锚定真实实体、引用真实原文（locator 精确），skill 需要多轮调优 + 输出 JSON schema 严格校验（幻觉锚点直接丢弃并降级重试）
- 正文结构化（格式段落标记）是修订定位/导出/渲染三者的共同地基，Phase 1 就要定契约（建议正文存储采用轻量标记或 JSON 段落数组，一次定型）
- 事件流是横切面，接入点多——用统一装饰器/服务层写入，避免散落
- 计量中间件要在 agent_runtime 单点埋点，禁止各调用方自报

---

*产出者：Hermes（CPO+架构+UX 三重视角）· 依据 memory 铁律：先规划确认，后编码*
