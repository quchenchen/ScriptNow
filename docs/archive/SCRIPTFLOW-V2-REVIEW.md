# ScriptFlow V2 三维评审报告

> **评审日期**: 2026-07-15  
> **评审范围**: 产品设计 · 技术架构 · 业务应用  
> **对标系统**: Toonflow · MuMuAINovel · ViMax

---

## 一、量化基线

| 维度 | 数据 |
|------|------|
| 后端 | 2,205 行 Python (FastAPI) |
| 前端 | 1,060 行 Vue/TS |
| API | 21 个端点 (含4个memory) |
| 数据库 | 9 个表 |
| 技能文件 | 21 个 .md |
| Vue 组件 | 6 个 |

---

## 二、产品设计评审

### 2.1 用户旅程

```
登录 → Dashboard → 创建项目 → [灵感孵化] → 选择方案 → [故事架构] → 确认 → [剧本撰写] → 逐集生成 → [质量审核] → [润色] → [资产提取] → [提示词]
```

**✅ 已实现**: 7 阶段线性流水线，偏好筛选，方案卡片，剧集表格+详情，Chat 持久化，资产面板(角色/伏笔/场景)。

**❌ 缺失/断裂**:

| # | 问题 | 严重度 |
|---|------|--------|
| 1 | 登录无 Loading 态，注册成功后无引导 | P1 |
| 2 | Dashboard 空态太简陋，新用户不知道做什么 | P1 |
| 3 | 偏好筛选选择后无即时视觉反馈 | P2 |
| 4 | 方案卡片点击→架构阶段，中间无过渡提示 | P2 |
| 5 | 架构卡片渲染依赖 Agent 输出格式，不可靠 | P1 |
| 6 | 剧集表格无分页/搜索/排序 | P1 |
| 7 | Chat 对话无法编辑/重发/引用 | P2 |
| 8 | 资产面板编辑后不自动同步到 Agent 上下文 | P1 |
| 9 | 无项目导入(外部小说/大纲) | P2 |
| 10 | 无协作/分享功能 | P3 |

### 2.2 信息架构

```
当前:
├── App.vue (3 页: Login / Dashboard / Workspace)
└── Workspace.vue (1,400行, 包含所有阶段逻辑)

问题: 单文件怪兽，阶段逻辑未拆分，职责不清
```

### 2.3 对标 Toonflow 差距

| Toonflow 能力 | ScriptFlow | 差距 |
|--------------|-----------|------|
| TDesign 组件体系 | 无第三方 UI 库 | 手工 CSS，一致性差 |
| 设置/管理面板 | ❌ 无 | 无法管理 API Key/Prompt/模型映射 |
| 任务列表+历史 | ❌ 无 | 无任务跟踪，无历史记录 |
| 图片/视频预览 | ❌ 无 | 无资产管理预览 |
| 国际化 i18n | ❌ 无 | 仅中文 |
| Electron 桌面端 | ❌ 无 | 仅 Web |

---

## 三、技术架构评审

### 3.1 架构分层

```
当前:
┌──────────────────────────┐
│  Workspace.vue (1400行)   │  ← 视图层(臃肿)
├──────────────────────────┤
│  api.ts (52行)           │  ← 通信层(薄)
├──────────────────────────┤
│  FastAPI (2,205行)       │  ← 服务层(尚可)
│  ├─ agent_orchestra.py    │
│  ├─ context_engine.py     │
│  ├─ pipelines.py          │
│  └─ memory_api.py         │
├──────────────────────────┤
│  SQLite (9表)            │  ← 数据层
└──────────────────────────┘
```

**问题**: 无服务层(Service Layer)，业务逻辑散落在路由和 Agent 中。无 Repository 模式。无配置管理(硬编码 DashScope Key)。

### 3.2 对标 MuMuAINovel 技术差距

| MuMuAINovel | ScriptFlow | 差距 |
|------------|-----------|------|
| SQLAlchemy + Alembic 迁移 | 原始 aiosqlite | 无版本迁移，改表需删库 |
| Service 层(20+文件) | 无 | 逻辑散落 |
| PromptService(模板管理) | 硬编码系统提示 | 不可配置 |
| JSON 校验+重试 | 无 | Agent 输出不可靠 |
| 历史记录+回滚 | 无 | 无法回退 |
| 导入/导出服务 | 仅 txt 导出 | 无 Word/PDF |

### 3.3 对标 ViMax 技术差距

| ViMax | ScriptFlow | 差距 |
|-------|-----------|------|
| Agent Loop(50轮工具调用) | 单次 LLM 调用 | 无多轮推理 |
| ContextCompactor | 简单 token 估算 | 无真实压缩 |
| ToolSpec + Registry | 4 个手工工具 | 无工具注册体系 |
| PromptBuilder(6 Parts) | 字符串拼接 | 无结构化 Prompt |
| SessionIndex | 无 | Agent 状态不持久 |
| YAML Config | 无 | 不可配置 |

### 3.4 安全性

| 检查项 | 状态 |
|--------|------|
| 密码哈希(SHA256+salt) | ✅ |
| Token 认证 | ⚠ 简易 token，无过期/JWT |
| SQL 注入防护 | ✅ (参数化查询) |
| CORS | ❌ 未配置 |
| 输入校验 | ⚠ 部分缺失 |
| API 限流 | ❌ 无 |

---

## 四、业务应用评审

### 4.1 核心业务闭环

```
灵感孵化 → 故事架构 → 剧本撰写 → 质量审核 → 润色 → 资产提取 → 提示词生成
   ✅          ✅           ✅          ⚠          ⚠        ⚠          ⚠
```

- 灵感→架构→撰写: 三阶段已打通 ✅
- 审核/润色/资产/提示词: 仅有按钮骨架，无实际 Agent 逻辑 ⚠

### 4.2 数据资产化

| 资产类型 | 自动提取 | 手动编辑 | Agent 查询 |
|---------|---------|---------|-----------|
| 角色 | ⚠ regex(有误报) | ✅ 面板编辑 | ❌ build_context 未触发 |
| 伏笔 | ❌ regex不匹配 | ✅ 手动添加 | ❌ 同上 |
| 场景 | ✅ 正则提取 | ❌ 无编辑 | ❌ 未注入 Agent |
| 钩子回收 | ❌ 无 | ✅ 手动标记 | ❌ 未提醒 |

### 4.3 用户价值指标

| 指标 | 当前 | 目标 |
|------|------|------|
| 首次创作时间 | ~3分钟(需手动输入) | <30秒(模板+引导) |
| 集均生成时间 | ~40秒 | ~25秒 |
| 内容可用率 | ~70%(需手动修正) | >90% |
| 项目留存率 | 未知 | >60%次日 |

---

## 五、三流图

### 5.1 业务流

```
用户 → 登录 → Dashboard → 新建项目(选择类型/偏好)
  → 灵感孵化(Chat输入创意 + AI生成3方案)
  → 点击方案卡片 → 故事架构(AI生成梗概+角色+大纲)
  → 确认架构 → 剧本撰写(AI逐集生成)
  → 剧本表格(点击查看详情) → 质量审核 → 润色 → 资产提取 → 提示词生成
  → 导出
```

### 5.2 数据流

```
projects ──→ episodes ──→ scene_assets
    │            │
    ├── characters    ├── foreshadows
    ├── chat_messages ├── script_versions
    └── reviews       └── (scene-level extraction)
```

### 5.3 信息流

```
用户消息 → workspace.py → AgentTeam.run()
  → build_context() (characters + foreshadows + prev_episodes)
  → PromptParts assembly (skill + memory + tools)
  → AgentScope Agent + DashScopeChatModel
  → reply_stream → SSE → 前端 chatMessages
  → onDone → save_episode → save_episode_context → loadEpisodes
```

---

## 六、优化提升计划

### Phase 1: 产品可用性 (P0-P1, 2-3天)

| # | 任务 | 影响 |
|---|------|------|
| 1 | 拆分 Workspace.vue → 7 个阶段组件 | 可维护性 |
| 2 | 引入 TDesign Vue 组件库 | UI 一致性 |
| 3 | 架构卡片渲染改为结构化组件(非正则解析) | 可靠性 |
| 4 | 资产编辑后实时同步到 Agent 上下文 | 闭环 |
| 5 | Dashboard 引导式空态(新手任务) | 激活 |

### Phase 2: 技术加固 (P1-P2, 3-5天)

| # | 任务 | 影响 |
|---|------|------|
| 6 | SQLAlchemy + Alembic 迁移替代原始 sqlite | 可维护性 |
| 7 | Service 层抽取(build_context/agent_orchestra 拆分) | 架构清洁 |
| 8 | Prompt 模板化(数据库存储+可编辑) | 可配置 |
| 9 | JWT Token + API 限流 | 安全性 |
| 10 | Agent Loop 多轮工具调用(对齐 ViMax) | Agent 能力 |

### Phase 3: 业务闭环 (P2-P3, 5-7天)

| # | 任务 | 影响 |
|---|------|------|
| 11 | 审核/润色/资产/提示词 四阶段完整 Agent 实现 | 闭环 |
| 12 | 项目导入(外部小说 txt/md) | 场景覆盖 |
| 13 | 导出 Word/PDF | 交付物 |
| 14 | 用户设置面板(API Key/Prompt/模型) | 配置化 |
| 15 | 多语言 i18n | 国际化 |
