# AgentScope 2.0.4 能力验证记录

> 验证时间：2026-07-18 · 验证方式：对项目 venv 内已安装的 `agentscope 2.0.4` 进行 Python 反射（inspect.signature / model_fields / dir），**非文档转述**。
> 作用：PRD-V7 §2「技术宪法」的证据文件。PRD 中引用的每一个框架机制均在此可查。
> 环境：`agent-script-platform/backend/.venv`（Python 3.11）· agentscope 2.0.4 · opentelemetry-sdk 1.43.0 已装

---

## 1. 顶层模块图谱

```
agentscope/
├─ agent        Agent · ContextConfig · ModelConfig · ReActConfig
├─ skill        Skill · SkillLoaderBase · LocalSkillLoader
├─ mcp          MCPClient · StdioMCPConfig · HttpMCPConfig
├─ tool         Toolkit · ToolGroup · FunctionTool · MCPTool · ToolMiddlewareBase
│               内置: Bash · Edit · Glob · Grep · Read · Write
│               任务: TaskCreate · TaskUpdate · TaskGet · TaskList
├─ event        30 种事件类型（见 §5）
├─ middleware   AgenticMemoryMiddleware · Mem0Middleware · ReMeMiddleware
│               RAGMiddleware · TracingMiddleware · ReplyBudgetControlMiddleware · TTSMiddleware
├─ state        AgentState · Task · TaskContext
├─ workspace    LocalWorkspace · DockerWorkspace(DockerBackend) · E2BWorkspace · Offloader
├─ permission   PermissionEngine · PermissionRule · PermissionMode · PermissionBehavior
│               PermissionContext · AdditionalWorkingDirectory · PermissionDecision
├─ rag          TextParser · PDFParser · PPTParser · ImageParser · ApproxTokenChunker
│               MilvusLiteStore · QdrantStore · KnowledgeBase · Chunk · DocumentSummary
├─ model        见 §2
├─ app          FastAPI 应用组件（message_bus/middleware/rag/storage/workspace_manager/…）
│               ⚠️ import 需补装 apscheduler
└─ credential / formatter / embedding / message / tts / types / exception
```

## 2. 模型层

`agentscope.model.__all__`：

```
ChatUsage · ChatModelBase · ChatResponse · FinishedReason · ModelCard · StructuredResponse
AnthropicChatModel · DashScopeChatModel · DeepSeekChatModel · GeminiChatModel
OllamaChatModel · OpenAIChatModel · XAIChatModel · MoonshotChatModel · OpenAIResponseModel
```

→ 支撑 PRD FR-4.3.2「AgentScope 模型类」枚举列与 TR-2.1.1 模型实例化。
→ `ChatUsage` 是计量（TR-2.7.1）的数据载体，由 `ModelCallEndEvent` 携带。

## 3. Agent 构造与配置（TR-2.1 依据）

```python
Agent(name: str, system_prompt: str, model: ChatModelBase,
      toolkit: Toolkit | None = None,
      middlewares: list[Any] | None = None,
      state: AgentState | None = None,          # 跨请求状态注入/回写
      offloader: Offloader | None = None,
      model_config: ModelConfig | None = None,   # max_retries, fallback_model
      context_config: ContextConfig | None = None,
      react_config: ReActConfig | None = None)

Agent 公开方法: reply · reply_stream · observe · compress_context
```

配置对象字段（pydantic model_fields 实测）：

| 配置 | 字段 |
|---|---|
| `ContextConfig` | `trigger_ratio: float` · `reserve_ratio: float` · `compression_prompt: str` · `summary_template: str` · `summary_schema: dict` · `tool_result_limit: int` |
| `ReActConfig` | `max_iters: int` · `stop_on_reject: bool` · `interruption_message: str` · `interruption_raise_cancelled_error: bool` |
| `ModelConfig` | `max_retries: int` · `fallback_model: ChatModelBase \| None` |

→ `ContextConfig` 字段 = 管理后台「记忆策略」卡的配置面（FR-4.7.1）；`summary_schema` 支撑 BR-9「创作决策强制保留」。
→ `fallback_model` 支撑等级池内回退（TR-2.1.1）。

## 4. 技能与工具（TR-2.2 / TR-2.3 依据）

```python
Skill(name: str, description: str, dir: str, markdown: str, updated_at: float)  # dataclass
LocalSkillLoader(directory: str, scan_subdir: bool = False)  # .list_skills()

Toolkit(tools=None,
        skills_or_loaders: Sequence[str | Skill | SkillLoaderBase] | None = None,
        mcps: list[MCPClient] | None = None,
        tool_groups: list[ToolGroup] | None = None,
        meta_tool_response_template: str = ...,   # 工具组激活状态模板
        skill_instruction_template: str = ...)    # <agent-skills> 渐进披露模板
Toolkit 方法: call_tool · get_tool · get_tool_schemas · get_skill_instructions · check_tool_available · clear

FunctionTool(func, name=None, description=None,
             is_concurrency_safe: bool = True,
             is_read_only: bool = False,          # → story-read 组标记
             is_state_injected: bool = False,
             middlewares: list[ToolMiddlewareBase] | None = None)
```

框架内置的 `skill_instruction_template` 实测内容明确要求 Agent 通过 `skill_viewer` 工具读取技能全文后再执行——即**渐进披露是框架原生行为**（TR-2.2.2 的直接依据，V6「SKILL.md 全文当 system_prompt」应废止）。

## 5. 事件体系（TR-2.5 依据）

`Agent.reply_stream(inputs) -> AsyncGenerator[...]` 实测返回联合类型（30 种）：

```
生命周期  ReplyStartEvent · ReplyEndEvent(ReplyEndReason) · ExceedMaxItersEvent
模型调用  ModelCallStartEvent · ModelCallEndEvent          ← 携带 usage（计量单点）
文本流    TextBlockStart/Delta/End
思考流    ThinkingBlockStart/Delta/End
结构化流  DataBlockStart/Delta/End                          ← Finding 等 JSON 产出
提示      HintBlockEvent
工具调用  ToolCallStart/Delta/End · ToolResultStart/TextDelta/DataDelta/End
人机协作  RequireUserConfirmEvent · UserConfirmResultEvent   ← 采纳/确认卡
          RequireExternalExecutionEvent · ExternalExecutionResultEvent
          UserInterruptEvent                                 ← 打断
自定义    CustomEvent · AgentEvent(基类) · ConfirmResult
```

**关键机制**：`Agent.reply()` / `reply_stream()` 的 `inputs` 参数除 `Msg` 外**直接接受** `UserConfirmResultEvent | UserInterruptEvent | ExternalExecutionResultEvent` —— 确认/打断后的续跑是框架原语，无需自建会话恢复（FR-3.10、TR-2.3.4 依据）。

## 6. 中间件（TR-2.1.1 middlewares 链依据）

```python
MiddlewareBase 钩子面: on_system_prompt · on_reasoning · on_acting · on_model_call
                      · on_reply · on_compress_context · list_tools

AgenticMemoryMiddleware(workdir: str, memory_dir: str = 'Memory', parameters=None, backend=None)
  Parameters: memory_max_tokens · memory_instructions · retrieval_async
            · retrieval_model · retrieval_max_tokens_per_md · retrieval_max_files
            · retrieval_max_tokens_per_frontmatter · retrieval_instructions
  → 长期记忆 = workdir 下 markdown 文件（记忆治理 FR-4.7 的文件事实源）

RAGMiddleware(knowledge_bases: list[KnowledgeBase], parameters=None)
ReplyBudgetControlMiddleware(token_budget: float, input_token_weight=1, output_token_weight=1,
                             hint_message='...预算耗尽收尾提示...')
TracingMiddleware(...)   # OTel；配合已装 opentelemetry-sdk/exporter-otlp 1.43
Mem0Middleware / ReMeMiddleware  # 可选增强（PRD 开放问题 ③）
```

自研中间件（UsageMetering / TierBudget / EventBridge）实现路径：继承 `MiddlewareBase`，挂 `on_model_call`（计量+预算）与 `on_reply`/`on_compress_context`（事件桥+压缩审计）。

## 7. MCP（TR-2.4 依据）

```python
StdioMCPConfig: type='stdio_mcp' · command · args · env · cwd · encoding_error_handler
HttpMCPConfig:  type='http_mcp'  · url · headers · timeout
MCPClient 方法: connect · close · is_connected · list_raw_tools · list_tools · get_tool
```

→ 两种传输与 admin 原型「StdIO / Streamable HTTP」一致；`list_tools → 白名单 → get_tool(MCPTool)` 即透传组装配链（FR-4.6.2）。

## 8. 状态 / 权限 / 沙箱 / RAG

- `AgentState`：pydantic 模型（`model_dump_json`/`model_validate_json` 可直接落库回灌）；含 `append_context`、`has_awaiting_tool_calls` —— `agent_states` 表设计依据。
- `permission`：`PermissionEngine/Rule/Mode/Behavior` + `AdditionalWorkingDirectory`（限定工具可写目录）——TR-2.8.1。
- `workspace`：`LocalWorkspace`（开发）→ `DockerWorkspace`（生产沙箱）→ `E2BWorkspace`（云沙箱备选）——FR-4.5.3 三档策略落点。
- `rag`：`TextParser/PDFParser` + `ApproxTokenChunker` + `MilvusLiteStore/QdrantStore` + `KnowledgeBase` —— 改编 RAG 全链（TR-2.10）本地可跑（MilvusLite 无外部服务依赖）。

## 9. 缺口与待验证项（P0 任务）

| 项 | 状态 | P0 动作 |
|---|---|---|
| `agentscope.app` | import 缺 `apscheduler` 依赖 | 补装后评估其 FastAPI 组件（message_bus/storage）与自研 API 层的取舍 |
| AgentScope Studio | 未安装 | 安装并验证 OTLP 上报 + trace 深链 URL 格式（FR-4.2.4） |
| agentscope-runtime | 未安装 | 验证沙箱执行器与 DockerWorkspace 的关系，确定 FR-4.5.3 实现层 |
| DataBlock 结构化输出的 schema 约束方式 | 未实测 | 用 review_finding schema 做端到端试跑（BR-8 校验链） |
| `Toolkit` 工具组运行时激活/停用（meta tool）细节 | 模板已见，调用面未实测 | P1 编写 fixture 回放测试 |

---

*本记录由 API 反射生成，随框架升级需重新验证（锁定 2.0.4，见 PRD §10 风险表）。*
