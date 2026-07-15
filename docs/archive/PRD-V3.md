# Agent 剧本创作平台 — 完整 PRD V3.0

> 基于：StoryPlay 全量产品走查 + Toonflow Agent 深度分析 + AgentScope 2.0
> 版本：V3.0 | 2026-07-14

---

## 目录

- [一、产品定位与市场分析](#一产品定位与市场分析)
- [二、StoryPlay 竞品分析](#二storyplay-竞品分析)
- [三、Toonflow 技术参考](#三toonflow-技术参考)
- [四、产品功能全景](#四产品功能全景)
- [五、核心业务流程（用户旅程）](#五核心业务流程用户旅程)
- [六、会员体系与商业模式](#六会员体系与商业模式)
- [七、技术架构总览](#七技术架构总览)
- [八、Agent 编排设计](#八agent-编排设计)
- [九、记忆与隔离系统](#九记忆与隔离系统)
- [十、数据模型](#十数据模型)
- [十一、前端设计](#十一前端设计)
- [十二、实施路线图](#十二实施路线图)

---

## 一、产品定位与市场分析

### 1.1 一句话定位

**AI Agent 驱动的短剧剧本全生命周期创作平台** — 让创作者从"操作 AI 工具的人"升级为"指挥 AI 团队的导演"。

### 1.2 目标用户画像

| 用户角色 | 画像特征 | 核心痛点 | 典型场景 |
|---------|---------|---------|---------|
| **独立编剧** | 个人创作者，月产 2-3 部 | 灵感枯竭、效率低、无专业反馈 | 从创意到成稿全流程 AI 辅助 |
| **编剧工作室** | 3-10 人团队，月产 10-20 部 | 协作混乱、风格不统一、质量参差 | 多人协作 + Agent 统一风格 + 质量门禁 |
| **MCN/平台方** | 批量采购剧本 | 筛选效率低、缺乏量化评估标准 | 批量评估 + 对标分析 + 过审预测 |
| **网文作者** | 想将小说改编为短剧 | 不懂剧本格式、改编策略缺失 | 上传小说 → 自动生成改编方案 → 逐章转化 |

### 1.3 市场规模

- 2026 年中国短剧市场预计突破 **800 亿元**
- ReelShort/DramaBox 等出海平台全球扩张，**海外剧本需求年增 300%**
- AI 视频生成模型（Seedance 2.0/Wan 2.7）成熟，**AI 短剧生产成本降至传统 1/10**
- 传统编剧培养周期 3-5 年，**AI 辅助可降低创作门槛 80%**

---

## 二、StoryPlay 竞品分析

### 2.1 产品概况

- **URL**: storyplay.cn | **Slogan**: "让AI辅助故事创作者成为超级个体"
- **技术栈**: Vue 3 + Vite + GSAP + Lexical + ECharts + AliOSS + nginx
- **商业模式**: 会员订阅 + 剧点消费

### 2.2 功能全景

**核心创作流（4 Tab 递进）**：

| Tab | 用户操作 | AI 能力 | 消耗 |
|-----|---------|---------|------|
| 故事梗概 | 填写结构化表单（受众/题材/设定/风格/世界观/梗概） | 「灵感策划」一键生成多方案 | 50点 |
| 人物小传 | 10个角色管理（姓名/定位/年龄/性格/背景） | 「AI生成」一键生成全部人物 | 50点 |
| 分集大纲 | 粗纲 + 逐集大纲 (N集) | 「AI生成全部粗纲」 | 80点 |
| 剧本正文 | 专业短剧格式正文撰写 | AI快速初稿 + AI单集润色 | — |

**辅助能力**：
- **剧本改写** (/rewriting): 上传剧本 → AI 拆解 → 改写
- **网文改编** (/adaptation): 上传小说 → AI 章纲拆解 → 改编
- **剧本评估** (/coverage): SCRIPTCOVERAGESYSTEM V1.0，快速+深度+批量
- **短剧拉片** (/hot): 50+热门剧海报网格，整合播放量/热力值，AI 拆解

**会员体系**：
- **剧本玩家（免费）**: 12 项基础创作权益
- **剧本专家（付费）**: 免费全部 + 11 项专业权益（拉片/折扣/投稿/定制等）

### 2.3 StoryPlay 的短板 → 我们的机会

| 短板 | 描述 | 我们的方案 |
|------|------|-----------|
| ⚠️ 无 Agent 模式 | 每步手动点击 AI 按钮，无自主推进 | Agent Team 自主推进阶段，用户仅审核 |
| ⚠️ 无长期记忆 | 每次创作从零开始 | 三层隔离记忆：用户偏好→项目上下文→会话历史 |
| ⚠️ 无质量循环 | 生成后无自动审核和修改循环 | Ralph Loop：审核→退回修改→再审核(≤3轮) |
| ⚠️ 无协作 | 单用户模式 | 多人实时协作 + 角色权限 |
| ⚠️ 改编弱 | 仅"上传→拆解"，无策略 | Agent 自主决策保留/删减/合并/新增 |
| ⚠️ 无全球化 | 仅中文 | 翻译 + 文化适配 + 市场适配 |
| ⚠️ 评估浅 | 单次打分，无对标 | 六维雷达图 + 爆款对标 + 可操作建议 |

---

## 三、Toonflow 技术参考

### 3.1 Agent 架构：Decision Router + SubAgent 工厂

Toonflow 的两层 Agent 架构是我们的核心参考：

```
用户消息 → Decision Agent (决策层)
              │ 分析意图 → 选择 SubAgent
     ┌────────┼────────┬──────────┐
     ▼        ▼        ▼          ▼
 Structure  Writing  Review   Supervision
 SubAgent   SubAgent SubAgent  SubAgent
```

**关键实现细节**：
- Decision Agent 通过 **tool calling** 分发到 SubAgent，不是硬编码路由
- 每个 SubAgent 是**独立 LLM 调用**，有独立的 System Prompt + Memory
- SubAgent 产出通过 **XML Tag**（`<storyStructure>` `<scriptItem>`）写入工作区
- 前端通过 WebSocket SSE 流式接收 XML Tag，实时渲染到对应面板

### 3.2 Memory 系统：三层记忆 + 自动摘要

Toonflow 的 Memory 实现（`memory.ts`）是我们记忆系统的蓝本：

```
Memory.add(content) →
  存入 memories 表 (type=message)
  计算 embedding 向量
  检查未总结消息数 ≥ N?
    YES → LLM 生成摘要 → 存入 (type=summary) → 标记原消息 summarized=1

Memory.get(query) →
  shortTerm: 最近未总结消息 (5条)
  summaries: 最近摘要 (10条)
  rag: 向量相似搜索 (3条最相关)
```

**隔离键设计**：`isolationKey = "{projectId}:{agentType}:{episodesId}"`

### 3.3 前端模式：Pinia Store + WebSocket + XML Tag

```
Pinia Store (productionAgent.ts / scriptAgent.ts)
  ├── state: FlowData (script / scriptPlan / storyboardTable / assets / storyboard)
  ├── WebSocket: Socket.IO 双向通信
  │   ├── auth({isolationKey, projectId})
  │   ├── chat(text) → SSE stream
  │   └── onXmlTag({tag, value, attrs, status}) → 更新 state
  ├── 轮询: 5秒间隔轮询图片/视频生成状态
  └── 持久化: setFlowData() → POST /production/saveFlowData
```

### 3.4 关键模式总结

| 模式 | Toonflow 实现 | 我们如何采纳 |
|------|-------------|-------------|
| **Agent Discovery** | Decision Agent 通过 tool calling 选择 SubAgent | 直接用 AgentScope Agent Team 的 leader-worker 模式 |
| **结构化产出** | XML Tag 写入工作区面板 | 扩展为剧本专用 XML schema |
| **记忆隔离** | isolationKey = `projectId:agentType:episodesId` | 扩展为 `userId:projectId:agentType:sessionId` |
| **流式通信** | WebSocket SSE + XML Tag 解析 | AgentScope Event System 替代 |
| **前后端状态同步** | Pinia Store + API 持久化 | 同模式，AgentScope 事件驱动更新 |

---

## 四、产品功能全景

### 4.1 功能架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent 剧本创作平台                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────── 创作引擎 ───────────────┐                      │
│  │                                         │                      │
│  │  剧本原创    网文改编    剧本改写        │                      │
│  │  (4Tab递进)  (策略决策)  (结构拆解)     │                      │
│  │                                         │                      │
│  │  Agent Team 自主推进:                    │                      │
│  │  灵感→架构→写作→审核→润色→资产→提示词    │                      │
│  │                                         │                      │
│  └─────────────────────────────────────────┘                      │
│                                                                  │
│  ┌─────────────── 质量引擎 ───────────────┐                      │
│  │                                         │                      │
│  │  多维评估    对标分析    Ralph Loop      │                      │
│  │  (六维雷达图) (爆款对比) (自动审核循环)   │                      │
│  │                                         │                      │
│  └─────────────────────────────────────────┘                      │
│                                                                  │
│  ┌─────────────── 数据引擎 ───────────────┐                      │
│  │                                         │                      │
│  │  短剧拉片    市场洞察    趋势预测        │                      │
│  │  (热门剧库)  (热度追踪)  (题材风向)     │                      │
│  │                                         │                      │
│  └─────────────────────────────────────────┘                      │
│                                                                  │
│  ┌─────────────── 全球化引擎 ─────────────┐                      │
│  │                                         │                      │
│  │  文学翻译    文化适配    市场适配        │                      │
│  │  (非机翻)    (价值观检查) (平台分发)    │                      │
│  │                                         │                      │
│  └─────────────────────────────────────────┘                      │
│                                                                  │
│  ┌─────────────── 协作引擎 ───────────────┐                      │
│  │                                         │                      │
│  │  多人实时协作  角色权限    版本管理      │                      │
│  │  (WebSocket)  (总编/分集/责编) (diff)   │                      │
│  │                                         │                      │
│  └─────────────────────────────────────────┘                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 功能对比：StoryPlay vs 本方案

| 功能模块 | StoryPlay | 本方案 |
|---------|-----------|--------|
| **剧本原创** | 用户手动推进 4 个 Tab | Agent 自主推进 7 个阶段，用户只需审核 |
| **智能生成** | 点击按钮 → AI 生成单次结果 | Agent 对话 → 理解上下文 → 生成 + 自审核 |
| **质量保障** | SCRIPTCOVERAGESYSTEM 单次评估 | Ralph Loop 循环 + 六维雷达图 + 爆款对标 |
| **网文改编** | 上传文件 → AI 拆解 | 策略 Agent 决策保留/删减/合并/新增 → 分阶段改编 |
| **剧本改写** | 上传 → AI 拆解 → 改写 | 结构分析 → 风格保持 → 逐集改写 + 连续性检查 |
| **拉片分析** | 浏览海报 → 点击详情 | Agent 对话式："帮我分析这部爆款的爽点模式" |
| **全球化** | 无 | 翻译 + 文化适配 + 市场适配，一键输出多语言版 |
| **协作** | 无 | 多人实时协作 + 角色权限 + 版本 diff |
| **记忆** | 无 | 记住用户偏好/项目上下文/修改历史 |
| **资产输出** | 仅导出 Word 剧本 | 剧本 + 角色资产 + 场景资产 + 道具资产 + 连续性台账 + Seedance 提示词 |

---

## 五、核心业务流程（用户旅程）

### 5.1 流程一：从零创作短剧剧本（核心流程）

```
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 1: 项目创建 (30秒)                                          │
│ 用户: "我要创作一部都市脑洞短剧，男频，爽点密集"                    │
│ Agent: 确认偏好 → 创建项目 → 进入灵感阶段                          │
├─────────────────────────────────────────────────────────────────┤
│ 阶段 2: 灵感孵化 (1-2分钟)                                       │
│ ResearchAgent: 抓取当前都市脑洞热门趋势                           │
│ StructureAgent: 生成 3 个差异化方案供用户选择                      │
│   方案A: 社畜绑定吐槽系统，靠直播怼人逆袭                           │
│   方案B: 外卖小哥觉醒美食系统，打造全球顶级餐厅                     │
│   方案C: 被辞退后绑定神豪系统，打脸前公司全员                       │
│ 用户: "选方案A，但主角改成女生"                                   │
│ StructureAgent: 调整方案 → 生成完整架构                            │
├─────────────────────────────────────────────────────────────────┤
│ 阶段 3: 故事架构 (2-3分钟)                                       │
│ StructureAgent 产出:                                              │
│   ✓ 剧本标题: 《我的系统是"神级吐槽"，靠毒舌震惊全网》              │
│   ✓ 核心梗概 (200字)                                              │
│   ✓ 10个角色 (姓名/定位/年龄/性格/背景/视觉标签)                   │
│   ✓ 80集分集大纲 (每集: 钩子→发展→反转→悬念)                      │
│   ✓ 爽点分布图 (标注每集爽点类型和强度)                            │
│                                                                    │
│ ReviewAgent 自动审核:                                              │
│   评分 85/100 → 通过 ✅                                            │
│   建议: 第5-7集爽点密度偏低，建议增加一个打脸桥段                    │
│                                                                    │
│ 用户: "同意，按建议调整后进入写作"                                  │
├─────────────────────────────────────────────────────────────────┤
│ 阶段 4: 逐集写作 (每集 20-40秒)                                   │
│ WritingAgent 逐集撰写:                                             │
│   第1集:                                                           │
│   【场景1】深夜写字楼 · 内景                                      │
│   △林北北疲惫地敲击键盘，屏幕上闪烁着未完成的代码                   │
│   突然，一道金色光流冲入她的脑海...                                 │
│                                                                   │
│   系统零零一(vo): 恭喜宿主绑定"神级吐槽系统"！                      │
│                                                                   │
│   每集 → ReviewAgent 自动审核 → 评分 ≥ 80 自动进入下一集            │
│   评分 < 80 → 带修改建议重写 → 最多 3 次                           │
│                                                                   │
│ 用户: 可以在任何时候喊停，手动修改某一集                           │
├─────────────────────────────────────────────────────────────────┤
│ 阶段 5: 全文润色 (1-2分钟)                                        │
│ PolishAgent:                                                       │
│   ✓ 对白口语化检查                                                 │
│   ✓ 节奏优化（每200字一个情绪转折）                                 │
│   ✓ 角色性格一致性校验                                             │
│   ✓ 格式统一为专业短剧标准                                         │
├─────────────────────────────────────────────────────────────────┤
│ 阶段 6: 资产提取 (30秒)                                            │
│ AssetAgent 自动提取:                                               │
│   ✓ 角色资产: 10个角色的视觉描述/服装/典型表情/Seedance标签         │
│   ✓ 场景资产: 15个场景的空间描述/关键道具/光线/氛围                │
│   ✓ 道具资产: 关键道具的视觉描述和剧情意义                          │
│   ✓ 连续性台账: 跨场景必须保持一致的元素清单                         │
├─────────────────────────────────────────────────────────────────┤
│ 阶段 7: Seedance 提示词生成 (1分钟)                                │
│ PromptAgent 生成:                                                  │
│   每个关键场景 → Director Formula → Seedance 2.0 中文提示词         │
│   输出: shot_prompts[] — 直接喂给 Digital Studio / Seedance API     │
├─────────────────────────────────────────────────────────────────┤
│ 阶段 8: 导出                                                       │
│ 用户选择: 导出完整剧本(.docx) / 导出资产包(.json) / 导出提示词(.json)│
│ 自动打包下载                                                       │
└─────────────────────────────────────────────────────────────────┘
```

**总耗时：约 10-15 分钟完成一部 80 集短剧从创意到成稿 + 制作资产的全流程。**
（对比传统编剧 3-5 天，StoryPlay 手动模式 1-2 小时）

### 5.2 流程二：网文改编短剧

```
用户: "帮我把这本小说改编成短剧"
  → 上传小说文件 (.txt/.docx)
  → AdaptationAgent 分析:
      章节数: 1200章
      主要角色: 15个
      核心情节线: 3条
  
  → StrategyAgent 决策:
      【保留】主线: 女主逆袭 + 男主追妻 (核心爽点)
      【删减】支线: 配角感情线 (与主线无关，删除)
      【合并】第3-5章 "宗门入门" → 合并为 1 集过渡
      【新增】每集开头增加钩子回顾 (短剧观众需要)
  
  → 用户确认策略 → StructureAgent 生成 80 集大纲
  → WritingAgent 逐集改编 (保持原著精髓 + 适配短剧节奏)
  → ReviewAgent 审核:
      原著忠实度: 78/100 (删减了配角支线)
      短剧适配度: 92/100
      → 通过
  
  → 输出: 剧本 + 资产 + 提示词
```

### 5.3 流程三：全球化出海

```
用户: "把这部剧本翻译成英文版，目标美国市场"
  → TranslationAgent:
      "系统提醒宿主" → "System alert: Host notified"
      保持文学性和口语化，非机翻
  
  → CulturalAgent:
      检测到冲突: "孝道" → 美国观众无此概念
      建议: 替换为 "family loyalty" (家庭忠诚)
      
      检测到风险: 第15集涉及敏感政治隐喻
      建议: 替换为商业竞争桥段
  
  → MarketAgent:
      美国短剧市场当前热点: Revenge Rom-Com
      建议: 强化女主打脸前男友线，弱化职场线
      
      TikTok/ReelShort 平台要求:
      - 每集开头 3 秒必须有冲突
      - 字幕必须内嵌
      
  → 用户确认 → 输出英文版剧本 + 市场适配建议
```

---

## 六、会员体系与商业模式

### 6.1 分层定价（参考 StoryPlay + 增强）

| 层级 | 月费 | 核心权益 | 目标用户 |
|------|------|---------|---------|
| **免费版** | ¥0 | 基础创作(单Agent)、3个活跃项目、每月100 Agent Credit、导出限制 | 体验用户 |
| **专业版** | ¥299/月 | 全Agent流水线、无限项目、Ralph Loop质量门禁、拉片数据库、每月1000 Credit | 独立编剧 |
| **团队版** | ¥999/月 | 专业版全部 + 多人协作(≤10人)、版本管理、审批流、API接入、每月5000 Credit | 编剧工作室 |
| **企业版** | 定制 | 团队版全部 + 私有化部署、定制Skill、专属模型微调、SLA | MCN/平台方 |

### 6.2 Agent Credit 计费

| Agent | Credit/次 | 说明 |
|-------|----------|------|
| StructureAgent | 10 | 生成完整故事架构（角色+大纲+爽点图） |
| WritingAgent | 2/集 | 逐集剧本撰写 |
| ReviewAgent | 3/次 | 多维度审核 |
| PolishAgent | 5/次 | 全文润色 |
| AssetAgent | 5/次 | 资产提取 |
| PromptAgent | 1/镜头 | Seedance提示词生成 |
| AdaptationAgent | 20 | 小说→剧本改编策略+执行 |
| TranslationAgent | 1/500字 | 多语言翻译 |

### 6.3 增值服务

- **定制 Skill 开发**: ¥5000-20000/个（客户专属创作模板）
- **私有模型微调**: ¥50000起（基于客户历史剧本微调）
- **剧本交易市场**: 平台撮合编剧与采购方，抽佣 10-15%
- **企业 API**: 按量计费，¥0.1/Credit

---

## 七、技术架构总览

### 7.1 核心决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent 框架 | **AgentScope 2.0** | 阿里达摩院开发，原生 DashScope 集成，内置 Multi-tenancy/Agent Team/Memory/Event System |
| LLM 接入 | **DashScope** (百炼) | 已深度使用，支持 deepseek-v4-pro / qwen3.7 / embedding |
| 后端框架 | **FastAPI** | 与 MuMuAINovel/Digital Studio 一致，AgentScope 内置 Agent Service 基于 FastAPI |
| 前端框架 | **Vue 3 + Vite** | 与 StoryPlay/Toonflow 一致，团队最熟悉 |
| 数据库 | **SQLite** (MVP) → **PostgreSQL** (生产) | 快速启动，后续平滑迁移 |
| 通信协议 | **AgentScope Event System** (SSE) | 替代自建 WebSocket，内置流式事件推送 |
| 文件存储 | **AliOSS** | 与 StoryPlay 一致，可信赖 |

### 7.2 系统架构图

```
┌──────────────────────────────────────────────────────────────┐
│                    Vue 3 前端 (自建)                           │
│  ┌──────────┬───────────┬──────────┬──────────────────┐      │
│  │Agent Chat│ 剧本编辑器 │ 评估看板  │ 资产浏览器        │      │
│  │(对话流)  │(Lexical)  │(ECharts) │(卡片+表格)       │      │
│  └──────────┴───────────┴──────────┴──────────────────┘      │
├──────────────────────────────────────────────────────────────┤
│              FastAPI (薄业务层 — 自建)                         │
│  /api/auth /api/projects /api/export /api/admin               │
├──────────────────────────────────────────────────────────────┤
│         AgentScope Agent Service (Agent 编排层 — 复用)         │
│  ┌────────────────────────────────────────────────────────┐   │
│  │  Agent Team: Leader + 7 Workers                         │   │
│  │  Multi-tenancy: user_id → tenant 隔离                    │   │
│  │  Multi-session: project_id → session 隔离                │   │
│  │  Agentic Memory: 长期记忆 (ReMe/AgenticMemory)           │   │
│  │  RAG: 爆款剧本库 / 编剧理论库 / 文化规范库                │   │
│  │  Event System: SSE 流式推送到前端                        │   │
│  └────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────┤
│              DashScope (模型层 — 复用)                         │
│  deepseek-v4-pro / qwen3.7-plus / text-embedding-v3          │
├──────────────────────────────────────────────────────────────┤
│              Storage (存储层)                                  │
│  SQLite/PostgreSQL(业务) + AliOSS(文件) + Redis(缓存/队列)    │
└──────────────────────────────────────────────────────────────┘
```

### 7.3 技术选型对比：自建 vs AgentScope 复用

| 模块 | 自建方案 | AgentScope 方案 | 节省 |
|------|---------|----------------|------|
| Agent 编排 | 手动 Decision Router + SubAgent 工厂 | Agent Team (leader+workers) | ~500行 |
| 多租户隔离 | 手动三层隔离系统 | Multi-tenancy + Multi-session | ~800行 |
| 长期记忆 | 自建 Memory + embedding + LLM摘要 | Agentic Memory / ReMe | ~600行 |
| 事件推送 | 自建 WebSocket SSE | Event System 内置 | ~300行 |
| RAG | 自建向量检索管道 | 内置 RAG (2026.6新增) | ~400行 |
| **总计** | | | **~2600行** |

---

## 八、Agent 编排设计

### 8.1 Agent Team 结构

```
Leader Agent (Decision Router — "创作导演")
  │
  ├── Worker 1: StructureAgent ("编剧架构师")
  │    输入: 用户创意 + 偏好
  │    产出: <storyStructure> (title, characters[], outlines[], pleasure_map)
  │
  ├── Worker 2: WritingAgent ("剧本撰写师")
  │    输入: 大纲 + 角色 + 前集摘要
  │    产出: <scriptItem name="第N集"> (scenes[], cliffhanger)
  │
  ├── Worker 3: ReviewAgent ("审稿编辑")
  │    输入: 剧本正文
  │    产出: <reviewResult> (overall_score, dimensions{}, issues[])
  │
  ├── Worker 4: PolishAgent ("润色师")
  │    输入: 审核通过的剧本 + 修改建议
  │    产出: <scriptItem> (润色后剧本)
  │
  ├── Worker 5: AssetAgent ("资产分析师")
  │    输入: 完整剧本
  │    产出: <characterAssets> <locationAssets> <propAssets> <continuityLedger>
  │
  ├── Worker 6: PromptAgent ("提示词工程师")
  │    输入: 资产 + 剧本
  │    产出: <shotPrompt shotId="N"> (seedance_prompt_cn, visual_keywords, references)
  │
  └── Worker 7: ExportAgent ("导出师")
       输入: 所有产出
       产出: 格式化文件 (.docx / .json / .md)
```

### 8.2 Ralph Loop 实现

```
WritingAgent 产出
  ↓
ReviewAgent 审核
  ├── score ≥ 85: 通过 ✅ → 进入下一阶段
  ├── score 70-84: 标注问题 → WritingAgent 针对性修改 → 再审核 (retry++  )
  ├── score 50-69: 结构问题 → StructureAgent 调整大纲 → WritingAgent 重写 (retry++)
  └── score < 50: 方向问题 → Leader Agent 重新构思 → StructureAgent 重新生成

最大循环: 3 次
3 次后仍不达标: 标记为"需人工介入"，保留所有版本供用户选择
```

### 8.3 Skill 系统

每个 Worker Agent 的 System Prompt 从 Markdown Skill 文件加载：

```
skills/
├── agents/
│   ├── decision.md          # Leader Agent: 阶段路由 + 意图识别
│   ├── structure.md         # StructureAgent: 故事架构设计规范
│   ├── writing.md           # WritingAgent: 短剧写作规范
│   ├── review.md            # ReviewAgent: 多维度审核标准
│   ├── polish.md            # PolishAgent: 润色规则
│   ├── asset.md             # AssetAgent: 资产提取规范
│   └── prompt.md            # PromptAgent: Seedance Director Formula
│
├── domains/                  # 领域知识 (按需激活)
│   ├── genres/               # 类型片模板 (20+)
│   ├── formats/              # 格式规范
│   └── markets/              # 市场规范 (各国审查/文化)
│
└── quality/                  # 质量检查清单
    ├── hook_check.md
    ├── pace_check.md
    └── continuity_check.md
```

---

## 九、记忆与隔离系统

### 9.1 隔离模型（基于 AgentScope Multi-tenancy）

```
AgentScope Multi-tenancy 提供:
  Tenant (用户) ──→ Session (项目) ──→ Message (会话)

我们在此之上叠加:
  Tenant = user_id           ← 用户 A 永远看不到用户 B 的数据
  Session = project_id       ← 项目间记忆完全隔离
  Message = agent_session    ← 同项目内不同 Agent 的会话记忆

额外存储（业务层）:
  UserPreferences (全局级): 风格偏好、默认设置、常用题材
  ProjectContext (项目级): 角色列表、世界观、伏笔、修改历史
```

### 9.2 记忆注入策略

每次 Agent 调用时，按优先级注入：

```
Step 1: Project Context (项目级)
  "当前项目: 《xxx》，角色: [林北北(女主), 苏小棠(闺蜜), ...]"

Step 2: Agent Session Memory (会话级)
  短期: 最近 5 条消息
  摘要: 最近 10 条 AI 压缩摘要
  RAG: 向量搜索最相关的 3 条历史消息

Step 3: User Preferences (全局级)
  "用户偏好: 男频、沙雕搞笑、高密度爽点、每集反转"

Step 4: Active Skills (领域级)
  当前激活的 Skill 内容（类型片模板/格式规范等）
```

### 9.3 记忆生命周期（参考 Toonflow 实现）

```
每次 Agent 交互:
  → memory.add(role, content)
  → 计算 embedding
  → 检查未总结消息 ≥ 5?
      YES → LLM 生成摘要 (≤500字) → 存入 → 标记原消息已总结

每次 Agent 调用前:
  → memory.get(query)
  → 返回 { shortTerm[], summaries[], rag[] }
  → 注入 System Prompt
```

---

## 十、数据模型

### 10.1 核心表

```sql
-- 用户表
users (id, phone, password_hash, nickname, avatar, membership_tier, membership_expires, created_at)

-- 项目表
projects (
  id, user_id, title, type(original|adaptation|rewrite),
  genre[], target_audience, cultural_background,
  target_markets[], status(draft|in_progress|completed|archived),
  created_at, updated_at
)

-- 剧本产出（版本化）
script_versions (
  id, project_id, stage(structure|writing|polish|final),
  version_number, parent_version_id,
  content(JSONB),  -- {title, characters[], episodes[]}
  agent_name, review_score,
  created_at
)

-- 分集
episodes (
  id, project_id, version_id, episode_number,
  title, scenes(JSONB), cliffhanger,
  word_count, status,
  created_at
)

-- 审核记录
reviews (
  id, project_id, version_id, episode_id,
  reviewer_agent, overall_score,
  dimensions(JSONB),   -- {commercial:85, narrative:72, ...}
  issues(JSONB[]),     -- [{type, severity, location, suggestion}]
  created_at
)

-- 资产
assets (
  id, project_id, version_id,
  asset_type(character|location|prop),
  name, visual_description(JSONB),
  seedance_tag, reference_shots,
  created_at
)

-- Seedance 提示词
shot_prompts (
  id, project_id, episode_id, scene_id,
  seedance_prompt_cn, visual_keywords[],
  director_formula(JSONB),
  references(JSONB),   -- {first_frame_url, reference_images[], ...}
  generation_params(JSONB),
  created_at
)

-- 记忆（AgentScope 管理 + 业务扩展字段）
-- 使用 AgentScope 内置 Memory，额外扩展 business_context 字段
```

### 10.2 版本管理

```
script_versions 表支持完整版本链:
  v1 (StructureAgent 产出)
  v2 (WritingAgent 产出)
  v3 (ReviewAgent 退回)
  v4 (WritingAgent 修改) 
  v5 (PolishAgent 润色)
  v6 (Final — 导出用)

能力:
  - 任意版本回退
  - 版本间 diff
  - A/B 双版本对比选择
```

---

## 十一、前端设计

### 11.1 页面结构

```
/login                          # 登录页（手机号+验证码）
/workspace                      # 工作台（项目列表）
/workspace/:projectId            # 创作工作台（主界面）

创作工作台布局:
┌──────────────────────────────────────────────────────┐
│ Header: 项目名称 | 阶段进度条 | 导出 | 设置            │
├──────────┬───────────────────┬───────────────────────┤
│          │                   │                       │
│ 左侧     │   中央             │   右侧                │
│ Agent    │   工作区           │   属性面板            │
│ Chat     │   (Tab 切换)       │   (上下文感知)        │
│          │                   │                       │
│ · 对话流 │  [大纲] [人物]     │  · 当前阶段信息       │
│ · 思考   │  [剧集] [评估]     │  · 角色/设定编辑       │
│   过程   │  [资产] [提示词]   │  · 审核结果           │
│ · 工具   │                   │  · 版本历史           │
│   调用   │                   │                       │
│          │                   │                       │
│ 输入框   │                   │                       │
└──────────┴───────────────────┴───────────────────────┘
```

### 11.2 工作区面板（从 Toonflow XML Tag 驱动）

| 面板 | 数据来源 | 渲染方式 |
|------|---------|---------|
| **大纲面板** | `<storyStructure>` XML Tag | 结构化 JSON → 表格/卡片 |
| **人物面板** | storyStructure.characters | 卡片列表 + 关系图(ReactFlow) |
| **剧集面板** | `<scriptItem name="第N集">` | Lexical 富文本编辑器 |
| **评估面板** | `<reviewResult>` XML Tag | ECharts 六维雷达图 + 问题列表 |
| **资产面板** | `<characterAssets>` `<locationAssets>` | 卡片网格 + 详情弹窗 |
| **提示词面板** | `<shotPrompt>` XML Tag | 代码块 + 复制按钮 |

### 11.3 关键技术组件

| 组件 | 技术 | 用途 |
|------|------|------|
| Agent Chat | AgentScope Event System → SSE | 流式对话 + 思考过程 + 工具调用展示 |
| 剧本编辑器 | Lexical | 富文本编辑，支持短剧格式高亮 |
| 评估看板 | ECharts | 六维雷达图 + 柱状图 + 对比图 |
| 人物关系图 | React Flow (xyflow) | 可视化人物关系图谱 |
| 版本对比 | Monaco Diff Editor | 版本间 diff 对比 |

---

## 十二、实施路线图

### Phase 1: Agent 核心流水线 (3周 → 2周)

> AgentScope 内置能力减少 1 周

- [ ] AgentScope 安装 + DashScope 配置
- [ ] Agent Team 搭建 (Leader + Structure/Review 2个Worker)
- [ ] Skill 文件编写 (decision.md, structure.md, review.md)
- [ ] Ralph Loop 基础实现
- [ ] FastAPI Agent Service 启动
- [ ] Vue 3 基础前端 (Agent Chat + 大纲面板 + 评估面板)
- [ ] **里程碑**: 输入创意 → Agent 生成大纲 → 自动审核 → 返回结果

### Phase 2: 创作闭环 (3周)

- [ ] WritingAgent + PolishAgent
- [ ] 完整 Ralph Loop (3次重试 + 降级策略)
- [ ] Lexical 剧本编辑器集成
- [ ] ECharts 评估看板
- [ ] 版本管理 + diff
- [ ] **里程碑**: 输入创意 → Agent 完成 80 集剧本 + 审核

### Phase 3: 资产 + 改编 (2周)

- [ ] AssetAgent + PromptAgent
- [ ] AdaptationAgent (小说→剧本)
- [ ] 连续性台账
- [ ] 导出功能 (.docx / .json)
- [ ] **里程碑**: 产出一部完整可交付的剧本 + 制作资产包

### Phase 4: 全球化 + 协作 (3周)

- [ ] TranslationAgent + CulturalAgent
- [ ] 多人协作 (AgentScope Multi-tenancy 之上扩展)
- [ ] 角色权限系统
- [ ] Skill 市场 (用户自定义)
- [ ] **里程碑**: 多语言剧本输出 + 团队协作

### Phase 5: 商业上线 (2周)

- [ ] 付费体系 + Agent Credit 计费
- [ ] 剧本交易市场 MVP
- [ ] API 开放平台
- [ ] 性能优化 + 安全审计
- [ ] **里程碑**: 正式上线运营

---

*文档完。合计 12 章，覆盖产品/业务/技术/实施全部维度。*
