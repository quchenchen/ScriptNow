# Agent 驱动剧本创作平台 — 产品与技术方案

> 基于 StoryPlay 分析 + 数字制片厂 + Script2Video 经验，系统规划下一代产品。
> 版本: v1.0 | 日期: 2026-07-14

---

## 一、愿景定位

从"AI辅助按钮"进化为 **"Agent协同创作工作室"**。

- **StoryPlay 现状**: 用户点击按钮 → AI返回结果 → 用户手动编辑 → 进入下一步
- **本方案**: Agent自主规划创作流程 → 多Agent协同工作 → 用户审核决策 → Agent持续迭代优化

**一句话**: 让用户从"操作AI工具的人"变成"指挥AI团队的导演/制片人"。

---

## 二、产品全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AGENT 剧本创作平台                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐         │
│  │ 创意孵化  │ → │ 剧本创作  │ → │ 质量提升  │ → │ 全球化   │         │
│  │ IDEATION │   │ WRITING  │   │ POLISH   │   │ GLOBAL   │         │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘         │
│       │              │              │              │                │
│       ▼              ▼              ▼              ▼                │
│  ·灵感策划        ·剧本原创      ·剧本评估      ·多语言翻译          │
│  ·市场洞察        ·网文改编      ·深度诊断      ·文化适配            │
│  ·对标分析        ·剧本改写      ·智能润色      ·海外发行            │
│  ·趋势预测        ·多人协作      ·节奏优化      ·合规审查            │
│                                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                        AGENT 编排层                                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Orchestrator Agent (LangGraph StateGraph)                    │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐     │   │
│  │  │Research│ │Structure│ │Writing │ │Polish  │ │Export  │     │   │
│  │  │ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │     │   │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘     │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                        基础能力层                                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐    │
│  │ LLM     │ │ RAG     │ │ Memory  │ │ Skill   │ │ Tool     │    │
│  │ Gateway │ │ Engine  │ │ System  │ │ System  │ │ Registry │    │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └──────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、核心产品模块

### 3.1 创意孵化引擎 (Ideation Engine)

**从"输入想法 → AI生成设定"升级为"Agent主导的市场驱动创意孵化"**

| 模块 | StoryPlay 现状 | Agent 方案 |
|------|---------------|-----------|
| 灵感策划 | 手动输入+AI生成设定 | Research Agent 自动抓取热点/趋势 → 多方案生成 → A/B对比 → 用户选择方向 |
| 市场洞察 | 无 | 接入短剧平台热力值/播放量 API → Agent 分析爆款模式 → 生成市场报告 |
| 对标分析 | 手动拉片 | Analysis Agent 自动拆解对标剧 → 提取节奏/爽点/反转模式 → 输出创作参考 |
| 趋势预测 | 无 | Agent 追踪题材热度变化 → 预测下一波热点 → 提前储备选题 |

**Agent 工作流**:
```
用户输入创作意图(可选)
  → Research Agent: 抓取市场数据 + 热门题材
  → Ideation Agent: 生成 3-5 个差异化方案
  → Critique Agent: 评估每个方案的市场潜力/创新度/可行性
  → 呈现给用户对比选择
```

### 3.2 剧本创作引擎 (Writing Engine)

**从"AI生成初稿+用户手动编辑"升级为"多Agent流水线协作创作"**

```
┌─────────────────────────────────────────────────────────────┐
│                    剧本创作 Agent 流水线                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Structure Agent           Writing Agent                     │
│  ┌─────────────────┐      ┌─────────────────┐               │
│  │ · 故事架构设计    │ ───→ │ · 逐集正文撰写    │               │
│  │ · 人物关系图谱    │      │ · 对话生成       │               │
│  │ · 情节节奏规划    │      │ · 场景描写       │               │
│  │ · 爽点分布设计    │      │ · 反转设计       │               │
│  │ · 分集大纲生成    │      │ · 情绪曲线控制    │               │
│  └─────────────────┘      └─────────────────┘               │
│           │                        │                         │
│           ▼                        ▼                         │
│  Continuity Agent          Polish Agent                      │
│  ┌─────────────────┐      ┌─────────────────┐               │
│  │ · 人物一致性检查  │      │ · 语言润色       │               │
│  │ · 时间线验证     │      │ · 节奏优化       │               │
│  │ · 道具连续性     │      │ · 桥段打磨       │               │
│  │ · 伏笔回收追踪   │      │ · 对白精修       │               │
│  │ · 情感弧线检查   │      │ · 格式标准化     │               │
│  └─────────────────┘      └─────────────────┘               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**关键创新: Ralph Loop 质量门禁**

```
Writing Agent 产出 → Review Agent 审核
  ├── 评分 ≥ 80 → 通过，进入下一阶段
  ├── 评分 60-79 → 标注问题，Writing Agent 针对性修改
  └── 评分 < 60 → 拒绝，Structure Agent 重新规划
```

### 3.3 小说改编引擎 (Adaptation Engine)

**从"上传文件→AI拆解"升级为"多层次改编策略决策+分阶段改编执行"**

| 阶段 | Agent | 产出 |
|------|-------|------|
| 内容分析 | Analysis Agent | 角色图谱、场景清单、情节线提取、世界观要素 |
| 策略决策 | Strategy Agent | 保留/删减/合并/新增决策表 + 理由 |
| 结构调整 | Structure Agent | 短剧节奏适配（1-2分钟/集，每集一个钩子） |
| 分集改编 | Adaptation Agent | 逐集剧本（保持原著精髓+适配短剧格式） |
| 质量审核 | Review Agent | 原著忠实度评分 + 短剧适配度评分 |

**策略决策示例（Agent自主判断）**:
```
原著章节: 第3章 "宗门大比" (8000字)
├── 保留: 主角越级挑战核心桥段 → 改编为第5集高潮
├── 删减: 次要弟子的战斗描写 (2000字) → 压缩为10秒蒙太奇
├── 合并: 赛前准备+赛后庆祝 → 合并为1个过渡场景
└── 新增: 增加对手嘲讽钩子 → 强化爽点密度
```

### 3.4 质量提升引擎 (Quality Engine)

**超越 StoryPlay 的"快速评估+深度评估"，构建专业编剧级质量体系**

```
┌────────────────────────────────────────────────────────────────┐
│                      多维度评估矩阵                               │
├──────────────┬─────────────────┬──────────────────────────────┤
│ 评估维度      │ 评估内容         │ Agent 分析方法                │
├──────────────┼─────────────────┼──────────────────────────────┤
│ 商业维度      │ 市场匹配度       │ 对比爆款数据库 → 题材热度评分   │
│              │ 受众精准度       │ 目标人群画像匹配 → 触达率预估   │
│              │ 平台适配度       │ 竖屏/节奏/时长 → 平台规则校验   │
├──────────────┼─────────────────┼──────────────────────────────┤
│ 叙事维度      │ 钩子强度         │ 每集前5秒吸引力评分            │
│              │ 爽点密度         │ 反转/打脸/逆袭频次统计         │
│              │ 情绪曲线         │ 高潮低谷分布图 + 疲劳度预警     │
│              │ 人物弧光         │ 角色成长轨迹完整性检查          │
├──────────────┼─────────────────┼──────────────────────────────┤
│ 技术维度      │ 格式规范性       │ 短剧行业标准逐项检查            │
│              │ 连续性           │ 时间线/道具/人物状态一致性      │
│              │ 合规性           │ 过审风险评估（国内+海外）       │
│              │ 对白质量         │ 信息密度/性格一致性/口语化      │
├──────────────┼─────────────────┼──────────────────────────────┤
│ 创新维度      │ 题材新颖度       │ 与现有剧本库相似度对比          │
│              │ 人设独特性       │ 角色原型偏离度分析              │
│              │ 反转设计         │ 可预测性评估 + 反转建议         │
└──────────────┴─────────────────┴──────────────────────────────┘
```

**可视化输出** (ECharts + 雷达图):
- 六维雷达图: 商业/叙事/技术/创新/节奏/情感
- 对标对比: 与爆款剧本并排比较
- 改进建议: 弱项自动生成提升方案

### 3.5 全球化引擎 (Globalization Engine)

**从"国产本子"到"全球本子"的完整适配链路**

```
┌──────────────────────────────────────────────────────────────┐
│                    全球化适配流水线                              │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  中文剧本                                                      │
│     │                                                         │
│     ▼                                                         │
│  Translation Agent (翻译层)                                    │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ · 文学性翻译（非机翻）                                  │     │
│  │ · 短剧对白口语化适配                                    │     │
│  │ · 文化梗本地化替换                                      │     │
│  │ · 支持: 英语/日语/韩语/西班牙语/阿拉伯语/印尼语          │     │
│  └──────────────────────────────────────────────────────┘     │
│     │                                                         │
│     ▼                                                         │
│  Cultural Adaptation Agent (文化适配层)                        │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ · 价值观冲突检测（孝道/个人主义/宗教禁忌）               │     │
│  │ · 人物关系再平衡（家庭结构/性别角色/权力距离）           │     │
│  │ · 情节合法性审查（各国内容法规差异）                     │     │
│  │ · 本土化建议：保留原味 vs 深度本地化 → 用户选择          │     │
│  └──────────────────────────────────────────────────────┘     │
│     │                                                         │
│     ▼                                                         │
│  Market Fit Agent (市场适配层)                                 │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ · 目标市场短剧趋势分析                                  │     │
│  │ · 平台分发策略（TikTok/YouTube Shorts/ReelShort...）   │     │
│  │ · 本地热门题材对标                                      │     │
│  │ · 定价和付费策略建议                                    │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

### 3.6 多人协作引擎 (Collaboration Engine)

**StoryPlay 缺失的关键能力**

| 角色 | 权限 | Agent 辅助 |
|------|------|-----------|
| 总编剧 | 全流程管控 + 最终审核 | 统筹 Agent 汇总各角色产出 |
| 分集编剧 | 指定集数编写 | Writing Agent 保持风格一致 |
| 编辑/责编 | 审核+批注+修改建议 | Review Agent 辅助审稿 |
| 制片人 | 商业评估+进度管理 | Analytics Agent 数据看板 |
| 翻译/本地化 | 多语言版本 | Translation Agent + 术语库 |

---

## 四、技术架构

### 4.1 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js 15)                     │
│  ┌──────────┬───────────┬───────────┬──────────────────┐    │
│  │ Agent    │ 剧本编辑器  │ 评估看板   │ 协作中心         │    │
│  │ Chat UI  │ (Lexical) │ (ECharts) │ (实时同步)       │    │
│  └──────────┴───────────┴───────────┴──────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                    API Gateway (FastAPI)                      │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  REST API (CRUD)  │  SSE (Agent Streaming)           │    │
│  │                    │  WebSocket (协作同步)            │    │
│  └──────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                  Agent Orchestration Layer                    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  LangGraph StateGraph (核心编排)                       │    │
│  │  ├── ResearchAgent                                   │    │
│  │  ├── StructureAgent                                  │    │
│  │  ├── WritingAgent                                    │    │
│  │  ├── PolishAgent                                     │    │
│  │  ├── ReviewAgent (Ralph Loop)                        │    │
│  │  ├── ContinuityAgent                                 │    │
│  │  ├── AdaptationAgent                                 │    │
│  │  ├── TranslationAgent                                │    │
│  │  ├── CulturalAgent                                   │    │
│  │  └── ExportAgent                                     │    │
│  └──────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                    Capability Layer                           │
│  ┌──────────┬──────────┬──────────┬──────────────────┐       │
│  │ LLM      │ RAG      │ Memory   │ Skill System     │       │
│  │ Gateway  │ Engine   │ (LangMem)│ (Markdown DSL)   │       │
│  └──────────┴──────────┴──────────┴──────────────────┘       │
├─────────────────────────────────────────────────────────────┤
│                    Data Layer                                 │
│  ┌──────────┬──────────┬──────────┬──────────────────┐       │
│  │PostgreSQL│ Redis    │ MinIO    │ Elasticsearch    │       │
│  │(主存储)  │ (缓存/队列)│(文件)   │ (剧本全文搜索)    │       │
│  └──────────┴──────────┴──────────┴──────────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Agent 框架选型

| 框架 | 用途 | 理由 |
|------|------|------|
| **LangGraph** | 核心编排 | StateGraph 天然适合多阶段创作流水线，支持条件分支/循环/并行 |
| **LangChain** | LLM 调用抽象 | 成熟的工具链，与 LangGraph 深度集成 |
| **CrewAI** | 角色化 Agent 协作 | 可选方案，适合需要强角色分工的创作场景 |
| **Dify** | 低代码 Agent 构建 | 用于快速实验和原型验证，Compose 模式编排简单工作流 |
| **DSPy** | 提示词自动优化 | 针对评估/润色等重复性任务，自动调优 prompt 效果 |

**为什么选 LangGraph 而非多 Agent 对话框架？**

剧本创作是**有向无环图(DAG)**而非自由对话：
```
灵感 → 架构 → 撰写 → 审核 → 润色 → 导出
         ↑       ↓       ↓
         └─── 修改循环 ───┘
```

LangGraph 的 StateGraph 原生支持：
- 条件路由: `if score < 60: goto fix_structure else: continue`
- 并行执行: 人物小传 + 世界观 可并行生成
- 循环控制: Ralph Loop 最多重试 3 次
- 状态持久化: checkpointer 支持断点续传/人工介入

### 4.3 Agent 定义规范

每个 Agent 定义为独立的 Skill Markdown + LangGraph Node：

```python
# Agent 定义示例
class StructureAgent:
    """故事架构 Agent — 负责故事架构设计、人物关系、情节节奏"""

    system_prompt: str  # 从 skills/structure.md 加载
    tools: List[Tool]   # create_scene, create_character, update_outline
    llm: str            # deepseek-v4-pro / claude-sonnet-4

    async def run(self, state: AgentState) -> AgentState:
        """
        输入: state.idea (用户创意) + state.research (市场数据)
        输出: state.structure (大纲/人物/世界观)
        """
```

```markdown
# skills/structure.md — 故事架构 Agent 系统提示词

你是一个经验丰富的短剧故事架构师。

## 核心能力
1. 故事架构：三幕/四幕结构设计，确保每集有钩子
2. 人物设计：主角必须有缺陷和成长弧光，配角要有独立动线
3. 节奏控制：短剧每集 1-2 分钟，每 15 秒一个情绪变化点
4. 爽点分布：前 3 集必须建立核心爽点模式，每 5 集一个高潮

## 输出格式
- 总纲（500 字内）
- 人物小传（每个角色：姓名/年龄/定位/性格标签/背景故事/成长弧光）
- 分集大纲（每集：钩子→发展→反转→悬念）
- 爽点分布图（标注每集爽点类型和强度）

## 质量规则
- 配角数量 ≤ 8 个（短剧容量限制）
- 每集场景 ≤ 3 个（拍摄成本控制）
- 主角第一次高光必须在第 3 集内出现
```

### 4.4 LangGraph 创作流水线

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

# 状态定义
class CreationState(TypedDict):
    project_id: str
    stage: str                    # ideation | structure | writing | polish | review
    idea: dict                    # 用户创意输入
    research: dict                # 市场研究数据
    structure: dict               # 大纲/人物/世界观
    episodes: list[dict]          # 逐集剧本
    review_results: list[dict]    # 审核结果
    polish_suggestions: list      # 润色建议
    retry_count: int              # Ralph Loop 重试计数
    final_script: str             # 最终产出

# 构建流水线
graph = StateGraph(CreationState)

# 添加节点
graph.add_node("research", ResearchAgent().run)
graph.add_node("structure", StructureAgent().run)
graph.add_node("writing", WritingAgent().run)
graph.add_node("review", ReviewAgent().run)
graph.add_node("polish", PolishAgent().run)
graph.add_node("export", ExportAgent().run)

# 条件路由
def should_retry(state: CreationState) -> str:
    score = state["review_results"][-1]["score"]
    if score >= 80:
        return "polish"
    elif state["retry_count"] >= 3:
        return "polish"  # 最多重试3次，强制进入润色
    else:
        state["retry_count"] += 1
        return "writing"  # 退回重写

graph.add_conditional_edges("review", should_retry, {
    "polish": "polish",
    "writing": "writing"
})

# 并行节点
graph.add_node("characters", CharacterAgent().run)
graph.add_node("worldbuilding", WorldBuildingAgent().run)
graph.add_edge("structure", "characters")
graph.add_edge("structure", "worldbuilding")
graph.add_edge("characters", "writing")
graph.add_edge("worldbuilding", "writing")

# 编译
app = graph.compile(checkpointer=SqliteSaver.from_conn_string("checkpoints.db"))
```

### 4.5 LLM Gateway — 多模型智能路由

```
用户请求 → LLM Gateway
  ├── 创作类任务 → deepseek-v4-pro / claude-sonnet-4 (创意能力强)
  ├── 评估类任务 → claude-opus-4 (分析能力强)
  ├── 翻译类任务 → deepseek-v4-pro (多语言能力强)
  ├── 简单任务   → deepseek-v4-pro (成本低)
  └── 质量审核   → 双模型交叉验证 (一致则通过)
```

**关键策略**: 创作任务用同一模型保持风格一致，评估任务用不同模型实现交叉验证。

### 4.6 RAG 引擎 — 创作知识库

```
┌───────────────────────────────────────────────┐
│                RAG 知识库架构                    │
├───────────────────────────────────────────────┤
│                                                │
│  ┌─────────┐  ┌─────────┐  ┌──────────────┐   │
│  │ 爆款剧本库│  │ 编剧理论库│  │ 类型片模板库  │   │
│  │(1000+部)│  │(经典教材)│  │(20+ 类型)    │   │
│  └─────────┘  └─────────┘  └──────────────┘   │
│                                                │
│  ┌─────────┐  ┌─────────┐  ┌──────────────┐   │
│  │ 文化规范库│  │ 法律法规库│  │ 用户剧本库    │   │
│  │(20+国家)│  │(各国审查)│  │(用户私有)    │   │
│  └─────────┘  └─────────┘  └──────────────┘   │
│                                                │
│  向量数据库: Milvus / Qdrant                    │
│  嵌入模型: bge-large-zh-v1.5 / text-embedding-3│
└───────────────────────────────────────────────┘
```

**RAG 注入时机**:
- 灵感阶段: 检索相似爆款 → 差异化分析
- 创作阶段: 检索类型片模板 → 结构参考
- 评估阶段: 检索行业标准 → 对标评分
- 全球化阶段: 检索目标市场文化规范 → 合规检查

### 4.7 Memory 系统 — 长期创作记忆

```
┌───────────────────────────────────────────────┐
│              Memory 系统 (LangMem)              │
├───────────────────────────────────────────────┤
│                                                │
│  Short-term: 当前会话上下文 (最近20轮对话)       │
│  Long-term:  跨会话记忆                         │
│    ├── 用户偏好 (风格/节奏/爽点偏好)             │
│    ├── 项目记忆 (角色设定/世界观/伏笔)           │
│    ├── 创作习惯 (常用模板/喜欢的人设类型)         │
│    └── 修改历史 (用户纠正过的问题，避免重复)      │
│                                                │
│  实现: LangMem + PostgreSQL JSONB               │
│  注入: 每次 Agent 调用前注入相关记忆             │
└───────────────────────────────────────────────┘
```

### 4.8 Skill 系统 — 可插拔创作能力

继承 Script2Video 的 Skill 模式并扩展：

```
skills/
├── structure/           # 架构类
│   ├── three_act.md     # 三幕结构
│   ├── four_act.md      # 四幕结构（短剧专用）
│   └── episode_hook.md  # 集末钩子设计
├── character/           # 人物类
│   ├── protagonist.md   # 主角设计
│   ├── antagonist.md    # 反派设计
│   └── ensemble.md      # 群像设计
├── genre/               # 类型片
│   ├── urban_brainhole.md  # 都市脑洞
│   ├── rebirth_revenge.md  # 重生复仇
│   ├── ceo_romance.md      # 霸总甜宠
│   ├── family_drama.md     # 家庭伦理
│   └── ... (20+ types)
├── quality/             # 质量类
│   ├── hook_check.md       # 钩子检查
│   ├── dialogue_check.md   # 对白检查
│   ├── pace_check.md       # 节奏检查
│   └── continuity_check.md # 连续性检查
├── adaptation/          # 改编类
│   ├── novel_to_script.md  # 小说改编
│   ├── manga_to_script.md  # 漫画改编
│   └── game_to_script.md   # 游戏改编
├── globalization/       # 全球化类
│   ├── cultural_norms_us.md    # 美国文化规范
│   ├── cultural_norms_jp.md    # 日本文化规范
│   ├── cultural_norms_kr.md    # 韩国文化规范
│   └── platform_tiktok.md      # TikTok 平台适配
└── export/              # 导出类
    ├── screenplay_format.md   # 标准剧本格式
    ├── shooting_script.md     # 拍摄脚本
    └── pitch_deck.md          # 提案文档
```

### 4.9 前端架构

```
frontend/
├── pages/
│   ├── workspace/[id]/          # 创作工作台（主界面）
│   │   ├── page.tsx             # Agent Chat + 工作区
│   │   ├── structure/           # 大纲/人物编辑
│   │   ├── writing/             # 逐集编辑器 (Lexical)
│   │   ├── evaluation/          # 评估看板 (ECharts)
│   │   └── export/              # 导出中心
│   ├── adaptation/              # 改编工作台
│   ├── globalization/           # 全球化工作台
│   └── collaboration/           # 协作中心
├── components/
│   ├── agent/                   # Agent 交互组件
│   │   ├── AgentChat.tsx        # SSE 流式对话
│   │   ├── AgentThinking.tsx    # Agent 思考过程可视化
│   │   ├── ToolCallCard.tsx     # 工具调用展示
│   │   └── ReviewPanel.tsx      # 审核结果面板
│   ├── editor/                  # 编辑器组件
│   │   ├── ScriptEditor.tsx     # Lexical 剧本编辑器
│   │   ├── CharacterGraph.tsx   # 人物关系图 (React Flow)
│   │   └── TimelineView.tsx     # 时间线视图
│   └── dashboard/               # 看板组件
│       ├── RadarChart.tsx       # 六维雷达图
│       ├── ComparisonView.tsx   # 对标对比
│       └── ProgressTracker.tsx  # 进度追踪
├── stores/                      # Zustand 状态管理
│   ├── project-store.ts
│   ├── agent-store.ts           # Agent 会话状态
│   ├── editor-store.ts          # 编辑器状态
│   └── collaboration-store.ts   # 协作状态
└── hooks/
    ├── useAgentStream.ts        # SSE 流式 Hook
    ├── useCollaboration.ts      # WebSocket 协作 Hook
    └── useMemory.ts             # 记忆系统 Hook
```

---

## 五、多层质量门禁体系

### 5.1 三层审核架构

```
┌──────────────────────────────────────────────────────────┐
│  Layer 1: 自动化审核 (Agent → Agent)                      │
│  ┌────────────────────────────────────────────────────┐   │
│  │ Review Agent 逐项检查 → 评分 → 自动修正/退回重写      │   │
│  │ 触发时机: 每个 Agent 产出后立即执行                   │   │
│  └────────────────────────────────────────────────────┘   │
│                          ↓                                 │
│  Layer 2: 同行审核 (Agent → Human)                        │
│  ┌────────────────────────────────────────────────────┐   │
│  │ Review Agent 标注问题区域 → 高亮显示 → 用户逐条确认    │   │
│  │ 触发时机: 关键节点（大纲完成/首集完成/全剧完成）       │   │
│  └────────────────────────────────────────────────────┘   │
│                          ↓                                 │
│  Layer 3: 专业审核 (Agent + 专业标准)                      │
│  ┌────────────────────────────────────────────────────┐   │
│  │ 对照行业标准/平台规范/法律要求 → 合规审计报告           │   │
│  │ 触发时机: 最终交付前                                  │   │
│  └────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### 5.2 Ralph Loop 重试策略

```
Writing Agent 产出
  → Review Agent 评分
    ├── score ≥ 85: 直接通过 ✅
    ├── score 70-84: 标注具体问题 → Writing Agent 针对性修改 → 再审核
    ├── score 50-69: 退回 Structure Agent → 调整大纲 → 重写
    └── score < 50: 退回 Ideation Agent → 重新构思方向

最大循环次数: 3
3次后仍不达标 → 标记为"需人工介入"，保留所有版本供用户选择
```

---

## 六、数据模型核心设计

### 6.1 核心表

```sql
-- 项目主表
projects (
    id, title, type(original|adaptation|rewrite),
    genre[], target_audience, cultural_background,
    language, target_markets[],
    status, created_by, collaborators[]
)

-- 创作产出
creations (
    id, project_id, stage(ideation|structure|writing|polish),
    version, content(JSONB), agent_name, agent_model,
    review_score, review_notes, parent_creation_id,
    created_at
)

-- Agent 会话
agent_sessions (
    id, project_id, agent_name, stage,
    messages(JSONB[]), tool_calls(JSONB[]),
    status, started_at, completed_at
)

-- 审核记录
reviews (
    id, creation_id, reviewer_agent, reviewer_model,
    dimensions(JSONB),      -- {商业:85, 叙事:72, ...}
    overall_score,
    issues(JSONB[]),        -- [{type, severity, location, suggestion}]
    recommendations(JSONB),
    created_at
)

-- 记忆条目
memories (
    id, user_id, project_id, memory_type,
    key, value, embedding(vector),
    importance, last_accessed
)

-- 知识库文档
knowledge_docs (
    id, doc_type(hot_script|genre_template|theory|cultural_norm),
    title, content, metadata(JSONB),
    embedding(vector), source_url
)
```

### 6.2 版本管理

```
每个 creation 保留完整版本链:
  v1 (Structure Agent) → v2 (Writing Agent) → v3 (Review 退回)
  → v4 (Writing Agent 修改) → v5 (Polish Agent) → v6 (Final)

支持:
  - 任意版本回退
  - 版本间 diff 对比
  - A/B 双版本并存（用户选择）
```

---

## 七、商业模式

### 7.1 分层定价

| 层级 | 价格 | 核心能力 |
|------|------|---------|
| **免费版** | ¥0 | 基础剧本创作（单Agent）、3个项目、导出限制 |
| **专业版** | ¥299/月 | 全Agent流水线、无限项目、Ralph Loop质量门禁、优先队列 |
| **团队版** | ¥999/月 | 多人协作、版本管理、审批流、API接入 |
| **企业版** | 定制 | 私有化部署、定制Skill、专属模型微调、SLA保障 |

### 7.2 计费维度

```
免费版: 每月 100 Agent Credits
专业版: 每月 1000 Agent Credits (1 Credit ≈ 1次 Agent 调用)
企业版: 按量或包年

Agent Credit 消耗:
  - Structure Agent: 5 Credits/次
  - Writing Agent: 2 Credits/集
  - Review Agent: 3 Credits/次
  - Translation Agent: 1 Credit/500字
```

### 7.3 增值服务

- 定制 Skill 开发: ¥5000-20000/个
- 私有模型微调: ¥50000起
- 剧本代写服务（平台撮合专业编剧）: 按项目收费
- 剧本交易市场（供需匹配）: 平台抽佣 10-15%

---

## 八、与现有项目的协同

```
┌───────────────────────────────────────────────────────────┐
│                    Agent 剧本平台（本文案）                   │
│                    创意 → 剧本 → 评估 → 全球化               │
└──────────┬────────────────────────┬───────────────────────┘
           │                        │
           ▼                        ▼
┌─────────────────────┐  ┌─────────────────────────────────┐
│  MuMuAINovel        │  │  Digital Studio (数字制片厂)      │
│  Script2Video       │  │  剧本 → 空间 → 摄影机 → 视频      │
│  剧本 → 分镜 → 视频  │  │                                 │
└─────────────────────┘  └─────────────────────────────────┘
           │                        │
           ▼                        ▼
┌─────────────────────────────────────────────────────────┐
│              Seedance 2.0 / 火山方舟                        │
│              视频生成 + 音频生成                            │
└─────────────────────────────────────────────────────────┘
```

**定位关系**:
- **Agent 剧本平台**: 上游文本创作（本文案），负责产出高质量剧本
- **Script2Video**: 中游转化，将剧本转化为可拍摄的分镜脚本
- **Digital Studio**: 下游制作，空间+运镜+视频生成

三者形成**创意→制作→成片**的完整链条。

---

## 九、实施路线图

### Phase 1: Agent 核心流水线 (8周)
- [ ] LangGraph 编排框架搭建
- [ ] Structure Agent + Writing Agent + Review Agent 开发
- [ ] Lexical 剧本编辑器集成
- [ ] SSE 流式 Agent Chat UI
- [ ] 基础 Ralph Loop 质量门禁

### Phase 2: 改编 + 评估 (6周)
- [ ] Adaptation Agent (小说→剧本)
- [ ] 多维度评估系统
- [ ] ECharts 评估看板
- [ ] RAG 爆款剧本库建设

### Phase 3: 全球化 + 协作 (6周)
- [ ] Translation Agent + Cultural Agent
- [ ] 多人协作 (WebSocket 实时同步)
- [ ] 版本管理系统
- [ ] 文化规范知识库

### Phase 4: 商业 + 生态 (4周)
- [ ] 付费体系 + 计费系统
- [ ] 剧本交易市场 MVP
- [ ] Skill 市场（用户自定义 Skill）
- [ ] API 开放平台

---

## 十、关键差异化总结

| 维度 | StoryPlay | 本方案 |
|------|-----------|--------|
| **交互模式** | 用户点击→AI返回→手动编辑 | Agent 自主规划→多Agent协作→用户审核决策 |
| **质量保障** | 基础评估+深度评估 | 三层审核+Ralph Loop循环+专业标准对标 |
| **改编能力** | 上传文件→AI拆解 | 多层次策略决策+分阶段改编+忠实度评分 |
| **全球化** | 无 | 翻译+文化适配+市场适配+合规审查 |
| **协作** | 无 | 多人实时协作+角色权限+审批流 |
| **创作记忆** | 无 | LangMem 长期记忆+用户偏好学习 |
| **知识库** | 拉片数据库 | RAG 6大知识库+爆款对标 |
| **Agent框架** | 无（简单API调用） | LangGraph+Dify+DSPy多框架融合 |
| **商业模式** | 会员+剧点 | 分层订阅+Agent Credit+增值服务+交易市场 |

---

*文档完。下一步建议：选择 Phase 1 中的 2-3 个核心 Agent 作为 MVP 快速验证。*
