# ScriptNow V7 — 产品定义文档

> **版本**: v2.0 · **日期**: 2026-08-05 · **状态**: 现行基线  
> **用途**: 面向 AI Coding Agent 与人类协作者的完整产品定义，涵盖架构、领域模型、Agent 系统、Skill 体系、前端架构和开发约定。

---

## 1. 产品概述

### 1.1 定位

ScriptNow 是 **AI Agent 团队驱动的剧本/小说创作平台**。核心隐喻是 **Growing（生长）**：用户与一支人格化的 Agent 团队（创意导演、架构规划师、写作者、审读编辑）协作，让作品从创意种子逐步生长为可交付内容。

**V7 是全新产品基线**，不继承 V5/V6 的领域模型约束。

### 1.2 一句描述

> 把 AI 生成变成可控的创作生产线——从一句话到大纲、分集、剧本、分镜 Prompt、角色图 Prompt，全程有上下文记忆和 Agent 审读把关。

### 1.3 目标用户

- 短剧编剧/制作团队（竖屏 1-2 分钟/集）
- 小说作者（网文连载）
- 小说→短剧改编需求方
- 需要 Prompt 资产（分镜/角色图/投流素材）的视频制作团队

---

## 2. 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | FastAPI (Python 3.11+) |
| Agent 运行时 | AgentScope 2.0.4 |
| 数据库 | SQLite + SQLAlchemy + Alembic |
| 前端 | Vue 3 + Vite + TypeScript (npm workspaces) |
| 包管理 | Python: uv (`pyproject.toml` + `uv.lock`) · 前端: npm |
| 向量检索 | MilvusLite (RAG 索引) |

### 2.1 项目结构

```
agent-script-platform/
├── AGENTS.md                     # Agent 协作约定
├── Makefile                      # 构建/测试/lint
├── docs/v7-spec-v1.1/            # 唯一规格基线
└── scriptnow/                    # 唯一可执行应用
    ├── backend/
    │   ├── src/scriptnow/
    │   │   ├── platform/         # 共享平台：认证、租户、事件、计量、DB
    │   │   ├── script/           # 剧本域：StoryMap、写作、审读、导出
    │   │   └── novel/            # 小说域：StoryMap、写作、审读、导出
    │   ├── skills/               # AgentScope Skill 目录
    │   └── tests/
    └── frontend/
        ├── apps/creator/         # 创作端 (:5174)
        ├── apps/admin/           # 管理后台 (:5173)
        └── packages/shared/      # 共享类型/工具
```

---

## 3. 架构概览

```
┌────────────────────┐  ┌────────────────────┐
│ 创作端 Creator SPA  │  │ 管理后台 Admin SPA   │
│ (Vue3 · 6 视图)    │  │ (Vue3 · 7 视图)     │
└─────────┬──────────┘  └─────────┬──────────┘
          │ REST + SSE            │ REST
┌─────────▼────────────────────────▼──────────────────────┐
│                    FastAPI 应用层                         │
│  领域 API · 治理 API · 认证中间件 · 计量中间件            │
├──────────────────────────────────────────────────────────┤
│                 AgentScope 2.0 运行时                     │
│  AgentFactory · Skill(Loader) · Toolkit · MCP · Memory   │
│  EventBridge · Tracing · PermissionEngine · Workspace    │
├──────────────────────────────────────────────────────────┤
│  SQLite + Alembic · 工作区文件 · RAG(MilvusLite)         │
└──────────────────────────────────────────────────────────┘
```

---

## 4. 领域模型

### 4.1 双域隔离

| 域 | 核心实体 | 不可共享的 |
|----|---------|-----------|
| **Script** | Episode → Scene → ScriptStoryBeat · ScriptBlock | StoryMap、正文块、Writer、审读、格式、导出 |
| **Novel** | Volume → Chapter → NovelStoryBeat · NovelBlock | 同上 |
| **Platform** | Tenant、User、Project、Event、Usage、Workspace | —（共享基础设施） |

### 4.2 Script Block 类型

`slugline / action / character / dialogue / transition`

### 4.3 Novel Block 类型

`heading / prose / dialogue / quote / divider`

### 4.4 候选不变式

Agent 所有写操作产出 `Candidate`（候选），**永不直写用户已采纳的创作事实**。用户采纳后 Candidate 升级为 adopted revision。

### 4.5 修订系统

- 审读 Editor Agent 五维扫描：事实/StoryMap、因果、人物策略、连续性、可拍摄性
- 严重度：`blocking` / `major` / `minor`
- Finding 锚定到蓝图实体（角色/规则/弧线/事件/伏笔）
- 三层渐进聚焦修订面板

---

## 5. Agent 体系

### 5.1 四角色团队

| 角色 | 中文名 | 阶段 | 核心产出 |
|------|--------|------|---------|
| Director | 创意导演 | ideation | StoryCore 候选 ×3、方向修订 |
| Architect | 架构规划师 | planning | 蓝图、StoryMap、结构调整分析 |
| Writer | 写作者 | writing | 场景/章节正文候选、选区改稿 |
| Reviewer | 审读编辑 | review | 五维 Finding、修订建议稿 |

### 5.2 Agent 组装规则

`AgentFactory.build(tenant, project, role)` 按以下规则组装：

- `name/system_prompt`: Agent 模板 + 租户覆盖
- `model`: 租户项目级选择 → 角色默认 → 等级回退
- `toolkit`: 挂载矩阵（ToolGroup + FunctionTool + MCP + Skill）
- `middlewares`: Tracing → UsageMetering → TierBudget → EventBridge → Memory → RAG
- `state`: `AgentState` 跨请求持久化

### 5.3 工具体系

| 工具组 | 函数（示例） | 读写性 |
|--------|-------------|--------|
| `story-read` | `read_project_brief`, `read_blueprint`, `list_scenes`, `query_continuity` | 只读 |
| `blueprint-propose` | `propose_entity_change`, `propose_arc_adjustment` | 产出候选 |
| `manuscript-propose` | `propose_scene_draft`, `propose_selection_edit` | 产出候选 |
| `review-propose` | `propose_finding(domain, severity, anchor, ...)` | 产出候选 |
| `task-tracker` | `TaskCreate/Update/Get/List` | Agent 自我规划 |
| `source-workspace` | `Read/Grep/Glob` | 只读 |

---

## 6. Skill 体系（完整目录）

### 6.1 核心创作 Skill（原有 10 个）

| 阶段 | Skill | 角色 | 描述 |
|------|-------|------|------|
| 创意发散 | `script-develop` | Director | 开发剧本方向：主角行动、对抗系统、场景引擎、制作取舍 |
| 蓝图规划 | `script-storymap` | Architect | 蓝图因果 StoryMap：进入状态、目标、策略、转折、后果 |
| 蓝图规划 | `script-structure-planning` | Architect | 叙事结构映射（英雄之旅/三幕/五幕/救猫咪） |
| 逐场写作 | `script-write` | Writer | 场景写作：角色策略、对抗、潜台词、状态变化、后果 |
| 格式投影 | `script-format-chinese` | Writer | 中国剧本格式：场景三要素、人物、画面、台词、OS/VO |
| 格式投影 | `script-format-hollywood` | Writer | 好莱坞格式：场景标题、动作、角色提示、对白 |
| 质量审读 | `script-review` | Reviewer | 五维审读：事实、因果、策略、连续性、可拍摄性 |
| 通用短剧 | `script-cn-short-drama` | 全角色 | 竖屏短剧基础：情绪弹簧、单集闭环、台词七维、分镜书写 |
| 素材分析 | `script-source-distiller` | Director | 多轮证据提取：人物/关系/场景/伏笔/付费点 |
| 诊断 | `script-doctor-roundtable` | Director | 多角色圆桌诊断剧本问题 |

### 6.2 短剧类型 Skill（新增 6 个）🆕

| Skill | 中文 | priority | 核心规则 |
|-------|------|----------|---------|
| `script-drama-revenge` | 复仇短剧 | 72 | 被害→证据→反击→清算四阶段、4 种复仇爽点、复仇疲劳避免 |
| `script-drama-romance` | 女频甜虐 | 72 | 关系五段弧线、人设张力法则、"追妻火葬场"节奏 |
| `script-drama-counterattack` | 男频逆袭 | 72 | 羞辱→隐藏→揭露→碾压、敌人层级递进、盟友体系 |
| `script-drama-billionaire` | 霸总短剧 | 72 | 契约六段弧线、"只对你破例"法则、阶层 vs 感情 |
| `script-drama-wargod` | 战神归来 | 72 | 蛰伏→试探→震慑→王者归来、压场对白公式、身份揭露节奏 |
| `script-drama-werewolf` | 狼人短剧 | 72 | 族群世界观、命定羁绊、兽性 vs 人性双重张力 |

每个类型 Skill 继承 `script-cn-short-drama` 的通用规则，新增：
- 类型专属叙事弧线和阶段划分
- 类型专属爽点类型和密度要求
- 类型专属付费卡点策略
- 常见类型陷阱和避免方法

### 6.3 专项工具 Skill（新增 4 个）🆕

| Skill | 中文 | priority | 核心功能 |
|-------|------|----------|---------|
| `script-hook-generator` | 钩子生成器 | 74 | 5 种钩子类型库、开场/中段/集末三阶段、发失败模式 |
| `script-paywall-designer` | 付费点设计 | 74 | 5 种付费卡点、半兑现原则、分集密度、分题材策略 |
| `script-episode-planner` | 分集节奏规划 | 74 | 六节拍模板、20 集蓝图、情绪 K 线图、多集数适配 |
| `script-cliffhanger` | 集末悬念设计 | 73 | 4 种悬念类型、半兑现原则、分题材悬念策略、下集承诺 |

### 6.4 Prompt 资产 Skill（新增 3 个）🆕

| Skill | 中文 | priority | 核心功能 |
|-------|------|----------|---------|
| `script-character-prompt` | 角色图 Prompt | 73 | 五要素结构、分题材模板、可复用性规则、变体 Prompt |
| `script-storyboard-seedance` | Seedance 分镜 | 73 | `<duration-ms>` `<role>` `<location>` 标签、15 秒分段、4 镜节奏 |
| `script-ad-creative` | 投流素材生成 | 72 | 三段式广告、6 种钩子类型、卖点模板、多版本测试 |

### 6.5 跨域管道 Skill（新增 1 个）🆕

| Skill | 中文 | priority | 核心功能 |
|-------|------|----------|---------|
| `script-novel-adaptation` | 小说→短剧改编 | 72 | 素材分析→改编蓝图→分集拆分三阶段、改编原则、常见陷阱 |

---

## 7. Skill 选择机制

### 7.1 元数据匹配

每个 Skill 的 YAML frontmatter 声明：

```yaml
roles: [director, architect, writer, reviewer]  # 可挂载的角色
stages: [ideation, planning, writing, review]    # 适用阶段
languages: [zh-CN]                                # 语言
selection_priority: 72                            # 优先级（越高越先匹配）
keywords: [复仇, 证据链, 反击, ...]               # 关键词匹配
```

### 7.2 调度流程

```
CreativeProfile（用户输入+已采纳事实）
    → SkillResolver 根据硬规则和 CreativeProfile 生成 SkillPlan
        → AgentFactory 按 SkillPlan 挂载 Skills 到对应 Agent
            → Agent 运行时通过 skill_viewer 工具按需读取全文
```

### 7.3 调度主体

| 主体 | 职责 |
|------|------|
| WorkflowOrchestrator | 判断阶段、任务依赖、执行角色和完成条件 |
| SkillResolver | 根据硬规则和 CreativeProfile 生成 SkillPlan |
| Director | 收束 CreativeProfile 候选并请求用户采纳 |
| Architect | 将 CreativeProfile 转换为结构与连续性约束 |
| Writer | 消费 SkillPlan 写作 |
| Reviewer | 评价作品并产生能力缺口证据 |

---

## 8. 前端架构

### 8.1 应用

| 应用 | 端口 | 功能 |
|------|------|------|
| Creator SPA | :5174 | 项目仪表盘、创作向导、逐场写作工作台、修订面板、Agent Dock |
| Admin SPA | :5173 | 租户管理、等级配置、模型池、Agent 模板、工具挂载、MCP 注册 |

### 8.2 Creator 视图

1. **Dashboard** — 项目卡片、阶段进度、方向标签、最近事件
2. **Wizard** — 新项目创建：方向、结构、体量选择
3. **Blueprint** — 蓝图/StoryMap 可视化编辑
4. **Writer** — 沉浸式三栏工作台（左目录/中正文/右上下文+修订）
5. **Review** — 修订面板：三层渐进聚焦、Finding 锚点导航
6. **Export** — 格式导出

### 8.3 关键 UX 约定

- Writer 进入时自动收起全局侧栏（可逆）
- Agent Bar 只显示当前阶段角色和真实上下文
- Agent Dock 右下浮动，与正文/右栏安全避让
- 格式只改变投影不改变戏剧事实

---

## 9. API 面

### 9.1 领域 API

| 域 | 端点前缀 | 核心操作 |
|----|---------|---------|
| Script | `/script/` | 项目 CRUD、方向、蓝图、StoryMap、写作、审读、导出、修订 |
| Novel | `/novel/` | 同上（独立模型） |
| Platform | `/platform/` | 认证、租户、事件、计量、文件工作区 |
| Admin | `/admin/` | 租户管理、等级、模型、Agent 模板、工具挂载 |
| Translation | `/translation/` | 翻译项目、术语表、逐章/批量翻译 |

### 9.2 事件流

- 创作操作通过 SSE 推送实时事件（打字机效果）
- `project_events` 表 append-only 四类事件：chat / node / decision / system
- AgentScope `reply_stream` 30 种框架事件经 EventBridge 映射为产品事件

---

## 10. 开发约定

### 10.1 代码风格

- Python: `snake_case` 函数/变量，`PascalCase` 类，`SCREAMING_SNAKE` 常量
- TypeScript: `camelCase` 函数/变量，`PascalCase` 类型/组件
- 产品标识统一使用 `scriptnow` / `ScriptNow` / `SCRIPTNOW_`

### 10.2 关键红线

- 新配置必须来自设置、数据库策略、项目参数或 Agent 交互，不得写死在代码中
- 不得以"降级成功"掩盖契约、结构化输出或 AgentScope block 解析错误
- Script 与 Novel 禁止共享正文、StoryMap、Writer、审读、格式和导出
- Agent 写操作一律产出 Candidate，不可直写项目真理

### 10.3 测试

- 后端: `scriptnow/backend/tests/test_*.py` (pytest)
- 前端: `scriptnow/frontend/**/*.spec.ts` (vitest)
- 只测 public interface

### 10.4 常用命令

```bash
make setup          # 安装后端与前端依赖
make dev            # 同时启动后端 :8000 + 创作端 :5174 + 管理端 :5173
make test           # 运行全部测试
make lint           # 代码检查
make build          # 构建
```

---

## 11. 关键文件索引

| 文件 | 内容 |
|------|------|
| `AGENTS.md` | Agent 协作约定（此文件） |
| `docs/v7-spec-v1.1/01-PRD-V7.md` | 完整产品需求规格 |
| `docs/v7-spec-v1.1/04-DOMAIN-CONTRACTS.md` | Script/Novel 领域契约 |
| `docs/v7-spec-v1.1/05-ADAPTIVE-SKILLS-CONTRACT.md` | Skill 体系契约 |
| `docs/v7-spec-v1.1/22-SCRIPT-SKILL-SYSTEM.md` | 剧本 Skill 运行时分层 |
| `scriptnow/backend/skills/script/` | 所有 Script 域 Skill 文件 |
| `scriptnow/backend/src/scriptnow/platform/skills.py` | Skill 加载器 |
| `scriptnow/backend/src/scriptnow/platform/skill_benchmarks.py` | Skill 基准评测 |
| `Makefile` | 构建/测试/lint 目标 |

---

## 12. 与竞品对比

| 能力 | ScriptNow | DramaForge |
|------|-----------|-----------|
| Agent 团队协作 | ✅ 四角色人格化团队 | ❌ 无 Agent 概念 |
| 短剧类型模板 | ✅ 6 个类型 + 基础通用 | ✅ 12 个类型 |
| 钩子生成器 | ✅ `script-hook-generator` | ✅ 独立工具 |
| 付费点设计 | ✅ `script-paywall-designer` | ✅ 独立工具 |
| 分集节奏规划 | ✅ `script-episode-planner` | ✅ 分集工作台 |
| 上下文记忆面板 | ⚠️ HOT/WARM/COLD 层 | ✅ 人物档案+检查清单 |
| 集末悬念 | ✅ `script-cliffhanger` | ✅ 独立机制 |
| 分镜 Prompt | ✅ `script-storyboard-seedance` | ✅ Seedance 标签 |
| 角色图 Prompt | ✅ `script-character-prompt` | ✅ 专项生成器 |
| 投流素材 | ✅ `script-ad-creative` | ✅ 广告素材 |
| 小说改编 | ✅ `script-novel-adaptation` | ✅ 完整链路 |
| 修订系统 | ✅ 五维审读+锚点+三层面板 | ❌ |
| AgentScope 深度集成 | ✅ 工具/MCP/记忆/事件/Trace | ❌ |
| 双域架构 | ✅ Script + Novel | ❌ |
| 跨文化改编 | ✅ 翻译+归化 | ❌ |
| 会员/商业系统 | 🔄 规划中 | ✅ 4 档会员+积分 |

---

*本文档面向 AI Coding Agent 与人类协作者。所有 Skill 由 AgentScope `LocalSkillLoader` 自动发现，无需额外注册。*
