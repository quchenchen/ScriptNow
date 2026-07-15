# Agent 剧本创作平台 — 技术方案 V2.1

> 基于：AgentScope 多 Agent 框架 + DashScope 模型底座 + Toonflow 决策路由模式
> 核心理念：Decision Router + SubAgent 工厂 + 三层记忆隔离
> 框架决策：AgentScope 替代 LangGraph（详见 FRAMEWORK-COMPARISON.md）

---

## 一、为什么选阿里云 Agent 体系

### 1.1 团队现有基础
- 已深度使用 DashScope API（DeepSeek-v4-pro 等模型）
- MuMuAINovel、Digital Studio 均构建在阿里云生态上
- Seedance 2.0 通过火山方舟接入，同属国内云生态

### 1.2 阿里云百炼 Agent 体系能力

| 能力层 | 阿里云提供 | 我们如何使用 |
|--------|-----------|-------------|
| **LLM 推理** | 百炼兼容 OpenAI/DashScope 双协议 | 使用 DashScope compatible-mode API，一个端点访问 DeepSeek/Qwen/GLM 全家桶 |
| **Agent 编排** | 百炼智能体（控制台可视化 + API） | **自建** Decision Router 模式（学习 Toonflow），因为创作流程是 DAG 而非自由对话 |
| **RAG 知识库** | 百炼知识库（向量检索+全文检索） | 用于爆款剧本库/编剧理论库/类型片模板的检索增强 |
| **Memory** | 百炼会话记忆（单会话级） | **自建**三层记忆系统（参考 Toonflow Memory 实现），实现跨会话/跨项目的长期记忆 |
| **Plugin/Tool** | 百炼插件市场 + 自定义工具 | 自建 Domain Tool Set（剧本 CRUD、评估评分、导出格式化） |
| **多模态** | 图像/视频/音频生成模型 | 下游集成 Seedance 2.0 / Wan 2.7 等视频模型（非本期范围） |

### 1.3 核心决策：复用百炼底座 + 自建 Agent 编排

**不用百炼内置 Agent Builder 的原因**：
- 百炼智能体是通用对话 Agent，适合"客服/问答"场景
- 剧本创作是有向无环图（DAG）：结构 → 写作 → 审核 → 润色，有明确的阶段依赖和循环控制（Ralph Loop）
- 需要精确控制 Agent 间的状态传递和版本管理

**复用百炼的部分**：
- LLM 推理（多模型接入）
- 知识库 RAG（可选，后续阶段）
- Embedding 服务（向量化用于记忆检索）

**自建的部分**：
- Decision Router + SubAgent 编排（参考 Toonflow）
- 三层记忆隔离系统
- Skill 系统（Markdown DSL）
- Domain Tools

---

## 二、核心架构：Decision Router + SubAgent 工厂

### 2.1 灵感来源：Toonflow 的双 Agent 架构

Toonflow 将 Agent 分为两层：

```
┌──────────────────────────────────────────────┐
│           Toonflow Agent 架构                  │
├──────────────────────────────────────────────┤
│                                               │
│  ┌─────────────────────────┐                  │
│  │   Decision Agent(决策层)  │ ← 接收用户消息   │
│  │   分析意图 → 选择SubAgent  │   决定"做什么"   │
│  └───────────┬─────────────┘                  │
│              │ 调用 tool                       │
│     ┌────────┼────────┬──────────┐            │
│     ▼        ▼        ▼          ▼            │
│  ┌──────┐┌──────┐┌──────┐┌──────────┐        │
│  │Structure││Writing││Review││Supervision│       │
│  │ SubAgent││SubAgent││SubAgent││ SubAgent │       │
│  └──────┘└──────┘└──────┘└──────────┘        │
│     ▲        ▲        ▲          ▲            │
│     └────────┴────────┴──────────┘            │
│           Supervision 监督层                   │
│                                               │
└──────────────────────────────────────────────┘
```

### 2.2 我们改造为：三阶段流水线 Router

剧本创作不同于视频制作，它有明确的阶段依赖关系。我们的 Decision Router 不仅"按意图分发"，还"按阶段推进"：

```
用户输入 "我要创作一个都市爽剧"
  │
  ▼
Decision Router (判断当前阶段 + 用户意图)
  │
  ├── 阶段=ideation → dispatch StructureAgent
  │     └── 产出: 故事架构 JSON
  │
  ├── 阶段=structure_done → dispatch WritingAgent × N
  │     └── 产出: 逐集剧本 × N
  │
  ├── 阶段=writing_done → dispatch ReviewAgent
  │     ├── score ≥ 80 → dispatch PolishAgent → dispatch AssetPromptAgent
  │     └── score < 80 → dispatch WritingAgent (修改) → 循环
  │
  └── 阶段=done → dispatch ExportAgent
```

### 2.3 SubAgent 清单

| Agent | Key | 职责 | 输入 | 输出 |
|-------|-----|------|------|------|
| **DecisionAgent** | `script:decision` | 意图识别 + 阶段路由 | 用户消息 + 项目状态 | SubAgent 调用指令 |
| **StructureAgent** | `script:structure` | 故事架构设计 | 用户创意 + 偏好 | title, characters[], outlines[] |
| **WritingAgent** | `script:writing` | 逐集剧本撰写 | 大纲 + 角色 + 前集摘要 | scenes[], cliffhanger |
| **ReviewAgent** | `script:review` | 多维度质量审核 | 剧本正文 | 评分 + 问题列表 + 修改建议 |
| **PolishAgent** | `script:polish` | 文案润色 | 审核标注问题 + 原文 | 修改后剧本 |
| **AssetAgent** | `script:asset` | 资产提取 | 完成剧本 | characters[], locations[], props[], continuity_ledger |
| **PromptAgent** | `script:prompt` | Seedance提示词 | 资产 + 剧本 | shot_prompts[] |
| **SupervisionAgent** | `script:supervision` | 监督审核 | 其他Agent输出 | 质量报告 + 仲裁决策 |
| **ExportAgent** | `script:export` | 格式化导出 | 剧本 + 资产 + 提示词 | .docx / .md / .json |

### 2.4 SubAgent 通信模式（参考 Toonflow XML Tag）

每个 SubAgent 通过 XML Tag 将结构化产出写入"工作区"：

```xml
<!-- StructureAgent 输出 -->
<storyStructure>
{ "title": "...", "characters": [...], "outlines": [...] }
</storyStructure>

<!-- WritingAgent 输出 -->
<scriptItem name="第1集">
【场景1】写字楼 · 深夜
△林北北疲惫地敲击键盘
...
</scriptItem>

<!-- ReviewAgent 输出 -->
<reviewResult>
{ "overall_score": 82, "issues": [...], "strengths": [...] }
</reviewResult>

<!-- AssetAgent 输出 -->
<characterAssets>
[{ "name": "林北北", "visual_description": "...", "seedance_tag": "LIN_BEIBEI" }]
</characterAssets>

<!-- PromptAgent 输出 -->
<shotPrompt shotId="1" sceneId="1">
{ "seedance_prompt_cn": "...", "visual_keywords": [...] }
</shotPrompt>
```

前端通过 WebSocket SSE 流式接收 XML Tag，实时渲染到对应工作区面板。

---

## 三、三层记忆隔离系统

这是整个方案中最关键的架构决策。参考 Toonflow 的 Memory 实现，但增强为**三层隔离**。

### 3.1 隔离模型

```
┌────────────────────────────────────────────────────────────┐
│                    记忆隔离层级                              │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Level 0: 全局记忆 (Global)                                  │
│  ├── 用户偏好（风格/节奏/爽点类型偏好）                        │
│  ├── 常用设置（默认受众/默认格式/默认模型）                    │
│  └── isolationKey: "global:{userId}"                        │
│                                                             │
│  Level 1: 项目记忆 (Project)                                 │
│  ├── 项目上下文（标题/题材/目标受众）                          │
│  ├── 角色设定（角色列表/人设/关系）                           │
│  ├── 世界观/伏笔/关键道具                                    │
│  ├── 创作历史（大纲版本/修改记录）                            │
│  └── isolationKey: "{userId}:project:{projectId}"           │
│                                                             │
│  Level 2: 会话记忆 (Session/Agent)                           │
│  ├── 当前对话历史（最近N轮）                                  │
│  ├── Agent 产出缓存（本次会话的结构/剧集/审核结果）            │
│  ├── Ralph Loop 状态（重试次数/修改记录）                     │
│  └── isolationKey: "{userId}:project:{projectId}:agent:{agentType}" │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

**关键原则**：
- 用户 A 永远访问不到用户 B 的任何记忆
- 用户 A 的项目 1 和项目 2 的记忆完全隔离
- 同一项目内，不同 Agent 的记忆独立但可共享（通过项目级记忆）

### 3.2 记忆数据结构（参考 Toonflow 实现）

```sql
CREATE TABLE memories (
    id TEXT PRIMARY KEY,           -- UUID
    user_id INTEGER NOT NULL,      -- 用户ID（第一层隔离）
    isolation_key TEXT NOT NULL,   -- 隔离键（第二层隔离）
    type TEXT NOT NULL,            -- 'message' | 'summary'
    role TEXT,                     -- 'user' | 'assistant:structure' | 'assistant:writing' | ...
    name TEXT,                     -- Agent 显示名称
    content TEXT NOT NULL,         -- 记忆内容
    embedding TEXT,                -- JSON array of floats (向量)
    related_message_ids TEXT,      -- JSON array (summary关联的原始消息ID)
    summarized INTEGER DEFAULT 0,  -- 是否已被总结
    importance REAL DEFAULT 0.5,   -- 重要性权重
    access_count INTEGER DEFAULT 0,-- 访问次数
    create_time INTEGER NOT NULL,  -- Unix timestamp ms
    update_time INTEGER
);

CREATE INDEX idx_memories_isolation ON memories(user_id, isolation_key);
CREATE INDEX idx_memories_type ON memories(isolation_key, type);
CREATE INDEX idx_memories_summarized ON memories(isolation_key, summarized);
```

### 3.3 记忆注入策略

每次 Agent 调用时，按以下优先级注入记忆：

```
Step 1: 加载 Level 2 (会话记忆) — 最近 N 条未总结消息
Step 2: 加载 Level 2 (会话摘要) — 最近 M 条 summary
Step 3: 向量搜索 Level 2 (RAG) — 与当前查询相关的历史消息
Step 4: 加载 Level 1 (项目记忆) — 项目上下文/角色/世界观
Step 5: 加载 Level 0 (全局记忆) — 用户偏好

最终 System Prompt 结构:
========================================
## 项目上下文 (Level 1)
- 标题：xxx
- 角色：[角色列表]
- 世界观：xxx

## 用户偏好 (Level 0)
- 偏好风格：沙雕搞笑
- 默认受众：男频

## 会话记忆 (Level 2)
### 近期对话
- user: 我要创作一个...
- assistant: 好的，我来设计...

### 历史摘要
1. 用户选择了都市脑洞题材...
2. 第1-5集已通过审核...

### 相关记忆 (RAG)
- [相似度 0.92] 用户之前提到喜欢反转密度高的剧本
========================================
```

### 3.4 记忆生命周期

```
新消息进入
  │
  ├── 存入 memories 表 (type=message)
  ├── 计算 embedding 向量
  │
  ├── 检查: 未总结消息数 ≥ N (默认 5)?
  │   ├── YES → 触发总结
  │   │   ├── 取最近 N 条消息
  │   │   ├── LLM 生成摘要 (≤ 500字)
  │   │   ├── 摘要存入 (type=summary, related_message_ids=[...])
  │   │   └── 标记原消息 summarized=1
  │   └── NO → 跳过
  │
  └── 用户下次对话 → get(text) 返回三层记忆
```

---

## 四、Skill 系统（参考 Toonflow + 扩展）

### 4.1 三级 Skill 体系

Toonflow 使用三级 Skill（主技能/二级/三级），我们简化为两级：

```
skills/
├── agents/                    # Agent 行为定义（决策/执行/监督）
│   ├── structure.md           # StructureAgent 系统提示词
│   ├── writing.md             # WritingAgent 系统提示词
│   ├── review.md              # ReviewAgent 系统提示词
│   └── supervision.md         # SupervisionAgent 系统提示词
│
├── domains/                   # 领域知识（按需激活）
│   ├── genre/
│   │   ├── urban_brainhole.md # 都市脑洞类型片模板
│   │   ├── rebirth_revenge.md # 重生复仇模板
│   │   └── ceo_romance.md     # 霸总甜宠模板
│   ├── format/
│   │   ├── short_drama.md     # 短剧格式规范
│   │   └── screenplay.md      # 标准剧本格式
│   └── quality/
│       ├── hook_check.md      # 钩子检查清单
│       └── pace_check.md      # 节奏检查清单
│
└── tools/                     # 工具使用说明
    ├── create_scene.md
    └── generate_prompt.md
```

### 4.2 Skill 激活机制（参考 Toonflow activate_skill）

```
Decision Agent 分析用户意图
  │
  ├── 检测到类型片关键词 → activate_skill("genre/urban_brainhole")
  ├── 进入审核阶段 → activate_skill("quality/hook_check")
  └── 进入导出阶段 → activate_skill("format/short_drama")
```

### 4.3 Skill 文件格式

```markdown
---
name: urban_brainhole
description: 都市脑洞类型片创作模板。适用于系统流、神豪流、重生都市等题材。
category: genre
tags: [都市, 脑洞, 系统流, 爽文]
version: 1.0
---

# 都市脑洞类型片创作指南

## 核心爽点模式
1. **金手指觉醒**：第1集结尾激活系统/能力
2. **首次打脸**：第3集内用能力碾压第一个对手
3. **身份揭露**：第10集左右揭示隐藏身份
...

## 禁止事项
- 系统说明不得超过3句话
- 升级过程不能超过30秒
- 不能出现现实政治人物
...
```

---

## 五、Decision Router 实现详解

### 5.1 Decision Agent 的 System Prompt 逻辑

Decision Agent 不是自由对话，它有明确的"阶段状态机"：

```markdown
# Decision Agent — 创作路由决策者

你是一个剧本创作项目的总导演。你的职责是根据项目当前阶段和用户输入，
决定调用哪个 SubAgent 来执行具体任务。

## 项目阶段状态机

[ideation] → 用户刚输入创意，需要生成故事架构
  → 调用: run_sub_agent_structure

[structure_done] → 故事架构已完成，可以开始写剧本
  → 调用: run_sub_agent_writing (逐集)
  或 → 回退: run_sub_agent_structure (用户不满意)

[writing_in_progress] → 正在撰写剧本中
  → 继续: run_sub_agent_writing (下一批)
  → 审核: run_sub_agent_review (检查已完成部分)

[review_passed] → 审核通过
  → 润色: run_sub_agent_polish
  → 资产: run_sub_agent_asset
  → 提示词: run_sub_agent_prompt

[review_failed] → 审核不通过
  → 修改: run_sub_agent_writing (带修改建议)
  → 或 → 重架构: run_sub_agent_structure (评分 < 50)

## 路由规则
1. 阶段推进必须是线性的（不能跳过 structure 直接 writing）
2. review 不通过时最多重试 3 次
3. 任何时候用户可以要求回到任意阶段
4. 如果用户输入的是自由对话（非指令），调用 run_supervision_agent 响应
```

### 5.2 WebSocket 通信流程

```
客户端                          服务端
  │                               │
  │──── connect ─────────────────→│
  │──── auth(isolationKey) ──────→│ 验证用户+项目权限
  │                               │ 加载记忆
  │←─── history(messages[]) ─────│ 返回历史消息
  │                               │
  │──── chat("创作一个都市爽剧") ──→│
  │                               │ DecisionAgent 分析
  │                               │ → 判断阶段=ideation
  │                               │ → dispatch StructureAgent
  │                               │
  │←─── thinking("分析中...") ────│
  │←─── text("好的，我来设计...") ─│ SSE 流式文本
  │←─── xml(storyStructure) ─────│ XML 工作区更新
  │←─── complete() ──────────────│ 阶段完成
  │                               │ 自动触发 Review
  │←─── thinking("审核中...") ────│
  │←─── xml(reviewResult) ───────│
  │←─── complete() ──────────────│
```

### 5.3 前端状态管理（参考 Toonflow productionAgent store）

```typescript
// Pinia Store — 项目级 Agent 状态
const useScriptAgentStore = (projectId: string) => defineStore({
  state: () => ({
    // 项目状态
    stage: 'ideation',             // ideation|structure_done|writing|review|done
    stageHistory: [],

    // 工作区数据（从 XML Tag 解析）
    storyStructure: null,          // StructureAgent 产出
    episodes: [],                  // WritingAgent 产出
    reviewResults: [],             // ReviewAgent 产出
    characterAssets: [],           // AssetAgent 产出
    shotPrompts: [],               // PromptAgent 产出

    // Agent 通信
    connected: false,
    messages: [],                  // 对话历史
  }),

  actions: {
    async chat(text: string) {
      // 通过 WebSocket 发送消息
      // 监听 XML Tag 更新工作区
      // 自动推进阶段
    }
  }
})
```

---

## 六、关键技术决策对比

| 决策点 | Toonflow 做法 | 本方案做法 | 理由 |
|--------|-------------|-----------|------|
| **Agent 编排** | Decision Router + SubAgent | 同，加阶段状态机 | 创作是 DAG，阶段依赖明确 |
| **通信协议** | Socket.IO WebSocket | 同 | 需要双向流式通信 |
| **LLM 协议** | AI SDK (`ai` package) | DashScope OpenAI 兼容 | 复用现有基础设施 |
| **记忆存储** | SQLite (`memories` 表) | 同，加 `user_id` 隔离 | 简单可控，不需要额外向量数据库 |
| **向量化** | 独立 Embedding 服务 | 复用 DashScope Embedding API | text-embedding-v3 |
| **Skill 系统** | Markdown + frontmatter + activate_skill | 同，简化三级为两级 | 降低复杂度 |
| **前端框架** | Vue 3 + TDesign + Pinia | 同 | 与 StoryPlay/Toonflow 一致 |
| **XML Tag** | 自定义标签输出工作区 | 同，扩展剧本专用标签 | 前后端解耦，支持多面板并行渲染 |

---

## 七、数据流总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据流全链路                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  用户输入                                                        │
│     │                                                            │
│     ▼                                                            │
│  ┌──────────────────────┐                                       │
│  │   Decision Agent     │ ← Phase Router (阶段状态机)            │
│  │   意图识别 + 阶段判断  │                                       │
│  └──────┬───────────────┘                                       │
│         │ dispatch                                               │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────┐               │
│  │              SubAgent Layer                   │               │
│  │                                               │               │
│  │  Structure ─→ Writing ─→ Review ─→ Polish     │               │
│  │      │          │          │         │        │               │
│  │      │          │          │    ┌────┴────┐   │               │
│  │      │          │          │    │ Ralph    │   │               │
│  │      │          │          │    │ Loop     │   │               │
│  │      │          │          │    │ (≤3次)   │   │               │
│  │      │          │          │    └─────────┘   │               │
│  │      │          │          │         │        │               │
│  │      ▼          ▼          ▼         ▼        │               │
│  │  ┌──────────────────────────────────────┐    │               │
│  │  │         工作区 (XML Tag 产出)          │    │               │
│  │  │  <storyStructure> / <scriptItem> /    │    │               │
│  │  │  <reviewResult> / <characterAssets>   │    │               │
│  │  └──────────────────────────────────────┘    │               │
│  └──────────────────────────────────────────────┘               │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────┐                                      │
│  │   Asset + Prompt     │ ← 剧本完成后                         │
│  │   资产提取 + 提示词    │                                      │
│  └──────────────────────┘                                      │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────┐                                      │
│  │   Export              │ ← 格式化导出                          │
│  │   剧本 + 资产 + 提示词 │                                      │
│  └──────────────────────┘                                      │
│         │                                                       │
│         ▼                                                       │
│  ┌──────────────────────────────────────────────┐              │
│  │              下游消费者                        │              │
│  │  Digital Studio / Seedance 2.0 / 人工拍摄     │              │
│  └──────────────────────────────────────────────┘              │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  记忆系统 (贯穿全链路)                                            │
│  ┌──────────────────────────────────────────────┐              │
│  │  Memory.add() ← 每次 Agent 交互               │              │
│  │  Memory.get()  → 每次 Agent 调用前注入          │              │
│  │  isolationKey = "{userId}:project:{projectId}:agent:{type}"  │
│  └──────────────────────────────────────────────┘              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 八、实施计划

### Phase 1: 核心骨架 (3周)
- [ ] 项目初始化（FastAPI + SQLite + WebSocket）
- [ ] Memory 系统实现（参考 Toonflow 直接移植）
- [ ] Skill Loader（Markdown + frontmatter）
- [ ] Decision Agent + Structure/Review 两个 SubAgent（验证 Router 模式）
- [ ] 基础前端（Vue 3 Agent Chat + 工作区面板）

### Phase 2: 创作闭环 (3周)
- [ ] Writing Agent（逐集剧本撰写）
- [ ] Polish Agent（文案润色）
- [ ] Ralph Loop 完整实现（3次重试 + 降级策略）
- [ ] 前端剧本编辑器（Lexical 集成）
- [ ] 评估看板（ECharts 六维雷达图）

### Phase 3: 资产+提示词 (2周)
- [ ] Asset Agent（角色/场景/道具提取）
- [ ] Prompt Agent（Seedance Director Formula）
- [ ] 连续性台账
- [ ] 导出功能（.docx / .md / .json）

### Phase 4: 高级特性 (3周)
- [ ] 小说改编 Agent（保留/删减/合并/新增策略）
- [ ] 全球化 Agent（翻译 + 文化适配）
- [ ] 多人协作（WebSocket 实时同步）
- [ ] Skill 市场（用户自定义 Skill）

---

## 九、与 StoryPlay 的核心差异

| 维度 | StoryPlay | 本方案 |
|------|-----------|--------|
| **交互范式** | 用户点击按钮 → AI 返回 → 手动编辑 | Agent 自主规划 → 用户审核决策 |
| **Agent 架构** | 无（简单 API 调用） | Decision Router + 8个 SubAgent |
| **记忆系统** | 无长期记忆 | 三层隔离记忆（全局/项目/会话） |
| **质量保证** | 一次性评估 | Ralph Loop 循环审核（≤3次） |
| **资产提取** | 无 | 角色/场景/道具/连续性台账 |
| **提示词生成** | 无 | Seedance Director Formula 自动化 |
| **LLM 基础设施** | 未知 | 阿里云 DashScope 全家桶（百炼底座） |
| **增量策略** | 全量重建 | 每个 SubAgent 独立记忆，修改单集不影响其余 |

---

*文档版本: V2.0 | 基于 Toonflow 架构深度分析 + 阿里云百炼生态*
