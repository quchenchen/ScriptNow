# AgentScope vs LangGraph — 框架选型对比分析

> 决策：剧本创作 Agent 编排框架选型
> 日期：2026-07-14

---

## 一、两个框架的定位

| | AgentScope | LangGraph |
|---|---|---|
| **开发者** | 阿里达摩院 | LangChain Inc |
| **GitHub Stars** | 27.8k | 12k+ |
| **语言** | Python | Python / JS |
| **定位** | 多智能体系统框架 | LLM 应用状态机框架 |
| **设计哲学** | 消息驱动的 Agent 协作（MsgHub） | 图结构状态管理（StateGraph） |
| **生态** | 阿里云百炼/DashScope 原生集成 | LangChain/LangSmith 生态 |
| **许可证** | Apache 2.0 | MIT |

---

## 二、架构核心差异

### 2.1 AgentScope：消息驱动的 Actor 模型

```
┌─────────────────────────────────────────────┐
│              AgentScope 架构                  │
├─────────────────────────────────────────────┤
│                                              │
│   MsgHub (消息总线)                           │
│   ┌─────────────────────────────────────┐    │
│   │  Agent A ──→ msg ──→ Agent B        │    │
│   │     ↑                    ↓          │    │
│   │     └──── msg ◄─────────┘           │    │
│   │                                      │    │
│   │  Pipeline / MsgHub / User-Agent      │    │
│   │  三种通信模式                          │    │
│   └─────────────────────────────────────┘    │
│                                              │
│   ReActAgent (思考-行动-观察 循环)             │
│   ┌─────────────────────────────────────┐    │
│   │  UserAgent (有人参与)                 │    │
│   │  DialogAgent (对话)                   │    │
│   │  DictDialogAgent (结构化对话)          │    │
│   └─────────────────────────────────────┘    │
│                                              │
│   内置能力:                                    │
│   - Memory (短期+长期)                        │
│   - RAG (知识库检索)                          │
│   - Tool/Plugin 系统                         │
│   - WebUI 监控面板                            │
│   - 分布式部署 (Agent-as-Service)             │
│   - DashScope 原生集成 (qwen3.7/deepseek-v4)  │
└─────────────────────────────────────────────┘
```

### 2.2 LangGraph：状态驱动的图模型

```
┌─────────────────────────────────────────────┐
│              LangGraph 架构                   │
├─────────────────────────────────────────────┤
│                                              │
│   StateGraph (状态图)                         │
│   ┌─────────────────────────────────────┐    │
│   │  Node A ──→ Node B ──→ Node C       │    │
│   │     ↑          ↓          │         │    │
│   │     └── cond ──┘          │         │    │
│   │                           ↓         │    │
│   │                        Node D       │    │
│   │                                      │    │
│   │  条件路由 / 循环 / 并行 / 中断恢复      │    │
│   └─────────────────────────────────────┘    │
│                                              │
│   内置节点类型:                                 │
│   - LLM Node                                 │
│   - Tool Node                                │
│   - Human-in-the-loop Node (中断)             │
│                                              │
│   需要自己构建:                                 │
│   - Memory (需集成 LangMem/外部方案)            │
│   - RAG (需集成 LangChain RAG)                │
│   - WebUI (需自行开发)                         │
│   - 分布式 (需集成 LangGraph Cloud/自建)        │
│   - 模型接入 (需集成 LangChain LLM)             │
└─────────────────────────────────────────────┘
```

---

## 三、关键维度对比

### 3.1 多 Agent 协作模式

| 场景 | AgentScope | LangGraph |
|------|-----------|-----------|
| **顺序流水线** (A→B→C) | ✅ `pipeline` 模式原生支持 | ✅ `add_edge` 串行连接 |
| **条件分支** (if score>80→A else→B) | ⚠️ 需手动实现条件逻辑 | ✅ `add_conditional_edges` 原生支持 |
| **循环重试** (Ralph Loop) | ⚠️ 需手动实现循环控制 | ✅ `add_edge` 回环 + checkpointer |
| **并行执行** (同时生成角色+世界观) | ⚠️ 需 MsgHub 广播 | ✅ `Send` API 并行分发 |
| **人机协作** (审核中断) | ✅ `UserAgent` 原生支持 | ✅ `interrupt` 断点续传 |
| **对话式交互** (自由对话+工具调用) | ✅ `DialogAgent` 原生支持 | ⚠️ 需手动构建 Agent Executor |

### 3.2 阿里云生态集成

| 能力 | AgentScope | LangGraph |
|------|-----------|-----------|
| **DashScope LLM** | ✅ 原生 `DashScopeChatWrapper` | ✅ 通过 LangChain OpenAI 兼容 |
| **DeepSeek-v4-pro** | ✅ 已适配 (最新 commit) | ✅ 通过兼容 API |
| **Qwen 系列** | ✅ 原生支持 | ✅ 通过兼容 API |
| **Embedding** | ✅ DashScope Embedding | ✅ 通过 LangChain |
| **RAG 知识库** | ✅ 内置 `Knowledge` + `KnowledgeBank` | ⚠️ 需集成 LangChain RAG |
| **百炼控制台** | ⚠️ 独立框架，不依赖控制台 | ⚠️ 独立框架 |

### 3.3 开箱即用程度

| 能力 | AgentScope | LangGraph |
|------|-----------|-----------|
| **Agent 类型** | ReActAgent, UserAgent, DialogAgent, DictDialogAgent | 需手动构建 Node |
| **Memory** | ✅ 内置短期+长期记忆 | ⚠️ 需集成 LangMem 或自建 |
| **Tool 定义** | ✅ `@tool` 装饰器，自动注册 | ✅ `@tool` 装饰器 |
| **流式输出** | ✅ 原生支持 | ✅ 原生支持 |
| **WebUI 监控** | ✅ 内置 AgentScope Studio | ⚠️ 需 LangSmith 或自建 |
| **分布式部署** | ✅ Agent-as-Service (RPC) | ⚠️ 需 LangGraph Cloud |
| **Prompt 管理** | ⚠️ 手动管理 | ✅ LangSmith Hub |
| **示例丰富度** | ✅ `examples/` 目录 20+ 场景 | ✅ 官方 Cookbook |

### 3.4 适合场景

| 场景 | 推荐框架 | 原因 |
|------|---------|------|
| **多角色对话协作**（编剧+导演+制片人讨论） | **AgentScope** | 原生 MsgHub 消息总线，Agent 间自由通信 |
| **严格 DAG 流水线**（结构→写作→审核→润色） | **LangGraph** | StateGraph 天然适配有向无环图 |
| **人机混合工作流**（AI生成+人审核+AI修改） | 两者均可 | AgentScope: UserAgent / LangGraph: interrupt |
| **阿里云生态项目** | **AgentScope** | 与 DashScope/百炼 深度集成，同一团队维护 |
| **大规模生产部署** | **AgentScope** | Agent-as-Service 分布式原生 |
| **精细状态控制** | **LangGraph** | checkpointer 支持任意节点中断/恢复 |

---

## 四、针对剧本创作场景的决策

### 4.1 我们的核心需求

1. **阶段流水线**：Structure → Writing → Review → Polish → Asset → Prompt
2. **Ralph Loop**：Review 不通过时退回重写，最多 3 次
3. **并行生成**：角色设计 + 世界观设定 可并行
4. **人机协作**：关键节点（大纲完成/首集完成）人工审核
5. **长期记忆**：跨会话的用户偏好、项目上下文
6. **阿里云生态**：DashScope LLM + Embedding + 未来可能百炼知识库

### 4.2 推荐：AgentScope 为主，LangGraph 思想为辅

**理由**：

1. **阿里云生态原生**：AgentScope 由阿里达摩院开发，与 DashScope 深度集成，最新 commit 已适配 deepseek-v4-pro。同一生态减少适配成本。

2. **内置 Memory 系统**：AgentScope 有开箱即用的短期+长期记忆，不需要像 LangGraph 那样额外集成 LangMem。虽然我们仍需要自建三层隔离（Toonflow 模式），但基础能力已覆盖。

3. **Agent-as-Service 架构**：AgentScope 的设计天然支持将每个 Agent 作为独立服务部署，后续扩展到生产环境时不需要重构。

4. **MsgHub 模式**：对于"编剧+导演+编辑"多角色协作场景，AgentScope 的消息总线比 LangGraph 的图结构更自然。

5. **WebUI 监控**：AgentScope Studio 提供 Agent 运行的可视化监控，降低调试成本。

**但需要借鉴 LangGraph 的思想**：
- **阶段状态机**：虽然 AgentScope 没有原生 StateGraph，但我们可以通过 ReActAgent 的 state 机制模拟
- **条件路由**：在 Decision Agent 中手动实现 `if stage == 'review_failed'` 的分发逻辑
- **循环控制**：通过计数器 + Decision Agent 实现 Ralph Loop（Toonflow 也是这么做）

### 4.3 最终架构

```
┌────────────────────────────────────────────────────────────┐
│              AgentScope (编排层)                             │
│                                                             │
│  DecisionAgent (ReActAgent)                                 │
│  ├── System: decision_router.md                            │
│  ├── Tools: dispatch_structure / dispatch_writing / ...    │
│  └── State: { stage, retry_count, project_id }            │
│                                                             │
│  ┌────────────────── MsgHub ──────────────────┐            │
│  │                                              │            │
│  │  StructureAgent   WritingAgent   ReviewAgent │            │
│  │  (ReActAgent)     (ReActAgent)   (ReActAgent)│            │
│  │  Skill: structure  Skill: writing  Skill: review     │
│  │                                              │            │
│  │  PolishAgent      AssetAgent     PromptAgent  │            │
│  │  (ReActAgent)     (ReActAgent)   (ReActAgent) │            │
│  └──────────────────────────────────────────────┘            │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐          │
│  │ Memory   │  │ RAG      │  │ AgentScope Studio │          │
│  │ (自建三层)│  │ (百炼)    │  │ (WebUI 监控)      │          │
│  └──────────┘  └──────────┘  └──────────────────┘          │
│                                                             │
│  ┌──────────────────────────────────────────────┐          │
│  │         DashScope (模型层)                     │          │
│  │  deepseek-v4-pro / qwen3.7 / embedding       │          │
│  └──────────────────────────────────────────────┘          │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### 4.4 AgentScope 代码示例（对比 LangGraph）

```python
# ===== AgentScope 方式 =====
import agentscope
from agentscope.agents import ReActAgent, UserAgent
from agentscope.message import Msg

# 1. 初始化 AgentScope（自动连接 DashScope）
agentscope.init(model_configs="./model_configs.json")

# 2. 定义 SubAgent
structure_agent = ReActAgent(
    name="编剧架构师",
    sys_prompt="...",        # 从 skill 文件加载
    model_config_name="deepseek_v4",  # DashScope 配置
    memory_config={},        # 内置 Memory
    tool_list=[],            # Domain Tools
)

# 3. 定义 Decision Agent（Pipeline 模式）
decision_agent = ReActAgent(
    name="创作导演",
    sys_prompt="decision_router.md",
    model_config_name="deepseek_v4",
)

# 4. Pipeline 编排
async def run_pipeline(user_input):
    # Phase 1: Structure
    structure_result = await structure_agent(
        Msg("user", user_input, role="user")
    )
    
    # Phase 2: Review
    review = await review_agent(structure_result)
    
    if review.score < 80 and retry_count < 3:
        # Ralph Loop
        structure_result = await structure_agent(
            Msg("user", f"根据以下意见修改：{review.issues}")
        )
        retry_count += 1
    
    # Phase 3: Writing...
```

对比 LangGraph 需要先定义 StateGraph、添加所有 Node、配置条件边、编译 graph、用 checkpointer...

**AgentScope 的优势在于**：Agent 是独立可复用的实体，你可以自由编排它们，不需要预定义整个图结构。这更接近 Toonflow 的 Decision Router + SubAgent 模式。

---

## 五、最终建议

| 决策 | 选择 | 理由 |
|------|------|------|
| **Agent 编排框架** | **AgentScope** | 阿里云生态原生、内置 Memory、Agent-as-Service、MsgHub 多Agent协作 |
| **Ralph Loop 实现** | 借鉴 LangGraph 思想 | 在 Decision Agent 中手动实现状态机+重试计数 |
| **LLM 接入** | AgentScope DashScope wrapper | 已适配 deepseek-v4-pro |
| **Embedding** | AgentScope 内置 | 用于记忆向量检索 |
| **记忆系统** | 自建三层（参考 Toonflow） | AgentScope 内置 Memory 为基础，扩展三层隔离 |
| **前端** | Vue 3 + WebSocket | 不变 |

---

## 六、风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| AgentScope 版本不稳定 | 锁定版本，持续关注 release notes |
| 文档不如 LangGraph 完善 | AgentScope 有完整中文文档 + 20+ 示例 |
| 社区不如 LangChain 活跃 | 27.8k stars，Issue 响应快（209 open） |
| 与 Toonflow Node.js 生态不一致 | AgentScope 是 Python，FastAPI 后端天然适配 |

---

*结论：切换为 AgentScope 作为 Agent 编排框架，LangGraph 作为参考思想但不引入依赖。*
