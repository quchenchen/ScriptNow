# AgentScope 2.0 深度分析 — Plan 修正

> 基于 AgentScope README 实际内容，更新技术方案
> 日期：2026-07-14

---

## 核心发现：AgentScope 2.0 已内置我们计划自建的核心能力

| 我们计划自建的能力 | AgentScope 2.0 已有 | 影响 |
|-------------------|---------------------|------|
| **多租户+多会话隔离** | ✅ **Multi-tenancy & Multi-session Service** | 不需要自建三层隔离的基础层！ |
| **Decision Router 模式** | ✅ **Agent Team** — leader agent spawns workers | 原生支持，不需要手动实现 |
| **长期记忆** | ✅ **ReMe + Agentic Memory** (2026.7/6 新增) | 不需要从零写 Memory 系统 |
| **RAG 知识库** | ✅ **内置 RAG** (2026.6) | 爆款剧本库直接接入 |
| **WebSocket 事件流** | ✅ **Event System** — 统一事件总线 | 前端直接消费事件流 |
| **前端 UI** | ✅ `examples/web_ui` 预构建 | 可复用或参考 |
| **沙箱执行** | ✅ **Workspace/Sandbox** — Docker/E2B/Daytona | Agent 工具安全隔离 |
| **权限控制** | ✅ **Permission System** | 工具调用粒度控制 |
| **中间件** | ✅ **Extensible Middleware** | 自定义 Agent 行为钩子 |

---

## 结论：大幅简化架构

### 之前（自建）：
```
FastAPI + 自建三层隔离 + 自建 Decision Router + 自建 Memory + 自建 WebSocket 事件
```

### 现在（AgentScope 2.0）：
```
AgentScope Agent Team (leader+workers) ← 替代 Decision Router
AgentScope Multi-tenancy                    ← 替代三层隔离基础层
AgentScope Agentic Memory / ReMe            ← 替代自建 Memory（保留隔离扩展）
AgentScope Event System                     ← 替代自建 WebSocket 事件
AgentScope RAG                              ← 替代自建 RAG 管道
FastAPI + AgentScope Agent Service          ← 薄 API 层
```

### 我们仍需自建的部分（业务层）：
- **Skill 文件体系**（剧本创作 Domain Skills）
- **Domain Tools**（剧本 CRUD、评估评分、格式化导出）
- **隔离策略扩展**（在 Multi-tenancy 之上叠加项目级+Agent级隔离）
- **前端工作区面板**（Vue 3 剧本编辑器 + 评估看板）
- **XML Tag 解析**（Toonflow 模式的结构化产出渲染）

---

## 修正后的架构

```
┌─────────────────────────────────────────────────────────┐
│                 Vue 3 前端 (自建)                         │
│  Agent Chat + 工作区面板 + 剧本编辑器 + 评估看板          │
├─────────────────────────────────────────────────────────┤
│          FastAPI (薄 API 层 — 自建)                       │
│  /api/auth /api/projects /api/export                    │
├─────────────────────────────────────────────────────────┤
│          AgentScope Agent Service (复用)                  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Agent Team (Leader + Workers)                     │  │
│  │  ├── Leader Agent (Decision Router)                │  │
│  │  ├── Structure Worker                             │  │
│  │  ├── Writing Worker                               │  │
│  │  ├── Review Worker                                │  │
│  │  ├── Polish Worker                                │  │
│  │  ├── Asset Worker                                 │  │
│  │  └── Prompt Worker                                │  │
│  │                                                    │  │
│  │  Multi-tenancy → 用户隔离                           │  │
│  │  Multi-session → 项目隔离                           │  │
│  │  Agentic Memory → 长期记忆                          │  │
│  │  RAG → 剧本知识库                                   │  │
│  │  Event System → SSE 流式推送                       │  │
│  └───────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│          DashScope (模型层)                               │
│  deepseek-v4-pro / qwen3.7 / embedding                 │
└─────────────────────────────────────────────────────────┘
```

---

## Agent Team 模式（原生替换 Decision Router）

```python
from agentscope.agent import Agent
from agentscope.team import Team

# Leader Agent — 决策路由
leader = Agent(
    name="创作导演",
    system_prompt="decision_router.md",
    model=DashScopeChatModel(...),
)

# Worker Agents — 执行层
structure_worker = Agent(
    name="编剧架构师",
    system_prompt="structure_agent.md",
    model=DashScopeChatModel(...),
)

writing_worker = Agent(
    name="剧本撰写师", 
    system_prompt="writing_agent.md",
    model=DashScopeChatModel(...),
)

review_worker = Agent(
    name="审稿编辑",
    system_prompt="review_agent.md",
    model=DashScopeChatModel(...),
)

# Team 编排
team = Team(
    name="剧本创作团队",
    leader=leader,
    workers=[structure_worker, writing_worker, review_worker],
)
```

**对比之前的手动实现**：之前需要写 Decision Agent + dispatch tool + SubAgent 工厂 + 状态管理，现在 AgentScope Team 已内置这些能力。

---

## Multi-tenancy 直接解决隔离问题

之前 PLAN-V2 中用了大量篇幅设计三层隔离系统。AgentScope 的 Multi-tenancy 已内置：

```
Tenant (用户) ──→ Session (项目) ──→ Message (会话)
    │                  │
    └── 隔离 ──────────┘
```

我们只需在此基础上：
1. 将 `tenant_id = user_id` 
2. 将 `session_id = project_id`
3. Agent 内部的 Memory 天然隔离

**不需要再自建 `memories` 表！**（除非需要额外的业务字段）

---

## 实施计划更新

### Phase 1: AgentScope 集成 (2周，减少1周)
- [x] ~~自建 Memory 系统~~ → 直接使用 AgentScope Agentic Memory
- [x] ~~自建 Decision Router~~ → 使用 AgentScope Agent Team
- [x] ~~自建 SSE 事件流~~ → 使用 AgentScope Event System
- [ ] AgentScope 安装 + DashScope 配置
- [ ] Skill 文件适配 AgentScope System Prompt 格式
- [ ] Domain Tools 开发（剧本 CRUD）
- [ ] Agent Team 配置（Leader + 3 Workers）
- [ ] FastAPI Agent Service 启动
- [ ] 参考 `examples/web_ui` 搭建前端基础

### Phase 2-4 时间不变，但代码量减少 ~40%

---

## 风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| AgentScope 2.0 较新（2026.5 发布） | 中 | 27.8k stars，阿里达摩院持续维护，403 commits |
| API 可能变动 | 中 | 锁定版本，关注 release notes |
| Team 模式不够灵活 | 低 | 可回退到手动编排（Toonflow 模式备用） |
| 前端 Web UI 质量未知 | 低 | 只作参考，前端仍自建 Vue 3 |

---

## 最终决策

**AgentScope 2.0 是正确选择**——它不仅没有降低灵活性，反而因为内置 Multi-tenancy、Agent Team、Event System、Agentic Memory 等能力，让我们从"基础设施搭建"转向"业务逻辑开发"。

预计减少 40% 基础设施代码量，Phase 1 缩短 1 周。
