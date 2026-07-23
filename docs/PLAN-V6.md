# ScriptFlow V6 工作计划

- **Status**: Accepted（Phase 0 已完成，Phase 1 issues 已就绪）
- **Date**: 2026-07-16
- **Planning horizon**: 12 周基线
- **Depends on**: [`CONTEXT.md`](../CONTEXT.md)、[`PRD-V5.md`](./PRD-V5.md)、ADR-0001～0003
- **Supersedes for execution**: `PRD-V5.md` 中 Phase 3.4 之后的交付顺序；不推翻 V5 已完成的基础设施

## 1. 计划目标

V6 要把 ScriptFlow 从“支持多种项目入口的短剧生成器”升级为“围绕同一 Story Core，支持原创/改编与小说/剧本两种交付形态的 AI 创作团队”。

V6 结束时，至少要有两条完整可用的主路径：

1. **原创剧本**：创意种子 → Story Core → 剧本结构 → Scene 编辑 → AI 审查 → 导出。
2. **小说改编剧本**：上传原著 → Source Canon → 改编映射 → Story Core → 剧本 Scene → 来源追溯 → 导出。

原创小说、改编小说在 V6 中完成领域模型与基础编辑能力，但不要求与剧本路径达到完全相同的专业深度。

## 2. 产品范围与原则

### 2.1 产品矩阵

项目不再由四套独立流程实现，而由两个正交维度组合：

| 维度 | 选项 | 说明 |
|---|---|---|
| 创作来源 | `original` / `adaptation` / `rewrite` | 从创意、Source Canon 或既有草稿开始 |
| 交付形态 | `novel` / `script` | 产出 Chapter 或 Episode/Scene |

`video_prompt` 不再作为顶层项目类型；它是 Script/VisualAsset 的下游交付物。

### 2.2 共同领域层

四类项目共用 Story Core：

- Premise、World、Character、Relationship
- Timeline Event、Story Beat、Plot Thread、Foreshadow
- Style Profile、Source Reference、Revision

媒介专属 Manuscript：

- Script：Episode、Scene、Action、Dialogue、Prop、VisualAsset
- Novel：Volume、Chapter、POV、Narrative Thread、Motif

### 2.3 实施原则

1. **端到端切片优先**：每个阶段必须形成用户可见闭环，不接受“后端完成、UI 长期 deferred”作为阶段完成。
2. **Story Core 优先于四套流程**：共同能力只实现一次，媒介差异通过策略和编辑器呈现。
3. **编辑优先于生成**：生成内容必须可编辑、可比较、可回滚，才算完成。
4. **Tree 负责血缘，不负责全部导航**：Growth Tree 是版本与影响视图；日常创作以作品目录和编辑器为主。
5. **用户拍板**：Agent 可自主执行低风险任务；采用方案、覆盖正文、接受 Cascade 必须由用户决定。

## 3. V5 资产处置

### 3.1 直接继承

- JWT 与项目隔离
- SQLAlchemy/Alembic 数据基础
- AgentTeam 单一 LLM 路径与 Toolkit
- Scene 独立表
- Character/Foreshadow/Prop 后端能力
- Ralph Loop 后端服务
- Growth Tree schema/API
- 剧本格式检查、DOCX 导出、AI 味检测器

### 3.2 调整后继承

- `pipeline`：降级为 Creation Journey 推荐步骤，不再承担核心领域模型。
- Growth Tree UI：旧 issue #11 暂停直接实施，按 V6 信息架构重拆。
- Living Assets：扩展为跨媒介 Story Core + 媒介专属资产。
- Ralph Loop：拆成共同审查框架 + Script/Novel 两套 rubric。

### 3.3 退出或延后

- `video_prompt` 顶层项目类型
- 旧 7-stage 主导航与“经典视图”长期双轨维护
- VisualAsset 生图、FDX、多人协作、移动端
- 跨用户风格学习和复杂商业化

## 4. 阶段计划

## Phase 0 · 产品定界与契约冻结（第 1 周）

**目标**：先统一产品承诺，停止入口、PRD、领域模型互相矛盾。

### 交付物

- PRD-V6：四类项目矩阵、P1 用户、核心旅程、Out of Scope。
- CONTEXT V6：Story Core、Manuscript、Source Canon、Story Beat、Revision 等术语。
- ADR-0004：双维度项目模型，替代按项目类型硬编码 pipeline。
- ADR-0005：Growth Tree / Creation Journey / Story Map 三者边界。
- 四条用户旅程线框，其中原创剧本、小说改编剧本达到详细状态。
- 数据迁移草案与 V5 issue 映射表。
- Agent × Skill 创作操作系统：Agent Task、Artifact、Revision、Decision、Delivery 状态机与权限边界。
- 两条 tracer workflow 的 Skill Contract、Golden Project 与质量 Gate。
- 人机协作交互宪法：AI 自主级别、注意力/打断规则、Decision Budget、三种输入方式与六条关键交互闭环。
- 第三方创作机制融合：Context Pack、Revision Brief、Task Depth、Batch/Checkpoint、Novelty Ledger 与 Living Asset Candidate。

### Gate 0

- 创建入口、项目模型、工作台术语没有互相冲突。
- 团队可用一句话解释 Growth Tree、Story Map、Creation Journey 的不同职责。
- 明确 V6 不追求四条路径同等深度。
- 团队不再把 `Agent delivered`、`review passed` 与“用户已采用”混为同一状态。
- 生产 Skill 具备输入输出、工具白名单、不变量、rubric、版本与回归夹具。
- 所有 P0 交互均能标注 A0–A4 自主级别；只有数据丢失、权限、不可逆动作或无法继续时使用阻塞式打断。

## Phase 1 · 导航与创建体验 tracer bullet（第 2～3 周）

**目标**：用户能按任务创建项目，并进入与项目形态匹配的工作台。

### 工作包

1. 创建向导改成四类任务式入口。
2. 将来源和输出形态保存为独立字段；兼容迁移现有 `source_mode` / `type`。
3. 移除 `video_prompt` 新建入口，保留旧数据只读兼容。
4. 建立路由和新的工作台壳：专注创作 / 故事规划 / 审阅决策；来源、版本与导出使用上下文子路由。
5. Dashboard 改为显示正文进度、质量状态、风险和 Agent 状态，删除伪线性百分比。
6. 建立 Vitest 标准脚本及创建、导航冒烟测试。

### Gate 1

- 四类项目创建后显示正确的单位、术语和工作区。
- Novel 项目不出现 EP、剧本纸、Seedance 主操作。
- Script 项目不出现 Chapter/POV 主操作。
- `npm run test` 可执行并通过。

## Phase 2 · Story Core 与可编辑创作核心（第 4～6 周）

**目标**：产品从“生成结果查看器”变成可持续编辑的创作工具。

### 工作包

1. Story Core schema/API：World、Relationship、Timeline Event、Story Beat、Plot Thread、Source Reference、Revision。
2. Script Editor：Episode → Scene → Action/Dialogue 的结构化编辑。
3. Novel Editor：Volume → Chapter → 段落/POV 的基础编辑。
4. 自动保存、保存状态、冲突保护、未保存离开提醒。
5. Revision：版本快照、diff、回滚、AI/用户修改来源。
6. 选区 AI 操作：改写、扩写、缩写、保持人物口吻；先支持 Script Scene，再复用到 Chapter。
7. Character 详情、状态、弧光、出场轨迹；删除与剧情死亡语义分离。

### Gate 2

- 用户无需修改 Markdown 或 JSON 即可完成一集剧本和一章小说的编辑。
- 任意 AI 修改可预览 diff、接受或拒绝。
- 刷新页面不丢内容；保存失败有可恢复提示。
- Character 修改可展示受影响内容，但不会自动覆盖下游。

## Phase 3 · 原创剧本完整闭环（第 7～8 周）

**目标**：先把最成熟的一条主路径做深，形成可演示、可真实创作的版本。

### 工作包

1. 创意候选 → 采用/分叉 → Story Core 固化。
2. Structure 与 Story Beat/Outline 的结构化编辑和血缘记录。
3. Scene 生成、局部返工、格式检查。
4. Ralph Loop 自动触发与过程可视化。
5. Agent Activity：成员、任务、使用的上下文、交付物、待决策事项。
6. 剧本纸阅读/编辑视图和 DOCX 导出验收。
7. Growth Tree 作为“版本与血缘”页面，支持 lineage、branch、dirty 影响查看。

### Gate 3

- 从一句话灵感到 3 集可编辑剧本全程在平台内完成。
- 用户能说清每集来自哪个 Structure/Story Beat 版本。
- Ralph 审查记录、问题和修改 diff 可查看。
- DOCX 可打开且符合既定剧本格式。

## Phase 4 · 小说改编剧本闭环（第 9～10 周）

**目标**：验证 Source Canon 是产品的第二条核心能力，而不只是文件上传。

### 工作包

1. Source Canon：上传、解析状态、章节目录、检索和错误恢复。
2. Source Reference：原著片段与 Character/Story Beat/Scene 的引用关系。
3. Adaptation Map：保留、合并、删除、重排、原创新增。
4. 改编策略：忠实 / 平衡 / 自由，并可项目级调整。
5. Scene 生成时展示来源依据；用户可回看原文。
6. 改编审查 rubric：人物偏移、关键情节遗漏、来源冲突、媒介转换质量。

### Gate 4

- 上传一部样本文本后，可完成“原著章节 → 改编结构 → 3 个剧本 Scene”。
- 每个改编 Scene 至少能追溯到来源或明确标注为原创新增。
- Adaptation Map 能解释主要删改，不以黑盒方式改写。

## Phase 5 · 收敛、质量与发布准备（第 11～12 周）

**目标**：将两条主路径从 demo 提升到可持续试用版本。

### 工作包

1. 全面 UI 可访问性与键盘操作修复。
2. Loading、empty、error、retry、undo、unsaved 等状态统一。
3. 前后端关键路径集成测试；真实 fixture 的非 LLM 回归测试。
4. 性能检查：长篇 Source、100 Chapter/80 Episode、260+ tree node。
5. 埋点与产品指标仪表：创建完成、首个有效产出、采用、编辑、导出、继续创作。
6. 3～5 个真实项目试用，形成问题清单与 V6.1 backlog。

### Gate 5 / V6 Release Gate

- Gate 1～4 全部通过，无 P0 数据丢失、安全或不可恢复错误。
- 两条主路径各有至少一个真实项目走通。
- 前端 build/test、后端 test/ruff 全绿。
- 首次有效产出、继续编辑、导出可被埋点测量。

## 5. 依赖关系与关键路径

```text
Phase 0 产品契约 + Agent/Skill 执行契约
  └─→ Phase 1 创建与工作台壳
        └─→ Phase 2 Story Core + Editor + Revision
              ├─→ Phase 3 原创剧本闭环
              │     └─→ Phase 5 收敛发布
              └─→ Phase 4 改编闭环 ─────────┘
```

关键路径为：**产品契约 → 动态工作台 → Revision/Editor → 原创剧本闭环 → 改编闭环 → 发布验收**。

任何不在关键路径上的 VisualAsset、FDX、视频 Prompt、复杂关系图不得插队。

## 6. 建议的 issue 切片

确认本计划后，新建 `.scratch/scriptflow-v6/`，按以下 epic 拆分，每个 issue 控制在 S/M，L 必须继续拆：

| Epic | 建议切片 |
|---|---|
| E0 产品契约 | PRD-V6、CONTEXT-V6、ADR-0004、ADR-0005 |
| E1 项目与导航 | 双维度字段迁移、四类创建入口、路由/工作台壳、Dashboard 指标、Vitest |
| E2 Story Core | 通用模型、Story Core API、Story World UI、引用关系 |
| E3 Manuscript | Script Editor、Novel Editor、autosave、Revision/diff、inline reprompt |
| E4 Agent Team | Activity 事件、成员视图、决策 Inbox、任务状态 |
| E5 Script 闭环 | Idea 分叉、Structure/Beat、Ralph UI、Script Sheet、DOCX 验收 |
| E6 Adaptation | Source Canon、Adaptation Map、Source Citation、改编 rubric |
| E7 Release | 可访问性、错误状态、性能、集成测试、埋点、试用反馈 |

旧 V5 #11 不直接标记完成或删除；改为 `wontfix/superseded-by-v6`，其 composable、dirty badge、lineage breadcrumb 等可复用要求迁入 E5。

## 7. 决策与协作机制

### 7.1 角色

| 事项 | 用户/产品负责人 | 执行 Agent | 真实试用者 |
|---|---|---|---|
| 产品范围、术语、Gate 验收 | A | R/C | C |
| PRD/ADR/issue 拆分 | A | R | I |
| 设计与开发实现 | C/A（关键交互） | R | I |
| 创作质量样本与 rubric | A | R/C | C |
| 发布判断 | A | R（提供证据） | C |

### 7.2 Checkpoint

- 每个 Phase 开始：确认目标、依赖、演示脚本。
- 每个 Phase 结束：按 Gate 演示，不按“代码写了多少”汇报。
- 破坏性 schema、删除旧入口、跨模块重写：执行前单独确认。
- Phase 内按 issue 自动推进；出现产品方向分歧才暂停。

## 8. 指标

### 北极星验证指标

**有效创作推进率**：进入项目的创作会话中，产生并保留一个用户采用或编辑后的新 Story Core/Manuscript Revision 的比例。

### V6 过程指标

- 创建项目完成率
- 首次有效产出时间
- 候选方案采用/轻改采用率
- 平台内编辑率与全量重生成率
- AI 修改接受/拒绝率
- Source Reference 覆盖率
- 一致性建议接受率
- 7 日继续创作率
- 导出完成率

## 9. 主要风险

| 风险 | 等级 | 应对 |
|---|---|---|
| 四类项目同时做深导致范围失控 | Critical | V6 只把原创剧本、小说改编剧本作为发布 Gate |
| Story Core 抽象过度 | High | 先用两条真实旅程验证字段，不先做万能 schema |
| 编辑器复杂度吞噬周期 | High | 先做结构化 textarea/block MVP，不在 V6 自研完整富文本内核 |
| Growth Tree 再次成为主流程负担 | High | 放入版本与血缘页；用作品目录承担日常导航 |
| LLM 输出不稳定破坏结构 | High | schema 校验、工具写入、fixture 回归、失败可恢复 |
| 改编来源与版权边界不清 | High | 记录来源、用户权利确认、默认私有，不提供公共作品抓取 |
| 后端完成而前端延期 | High | 所有 Gate 必须包含真实 UI 和用户行为验收 |

## 10. 下一步

计划获确认后，按顺序执行：

1. 编写 `docs/PRD-V6.md` 和两份 ADR。
2. 新建 `.scratch/scriptflow-v6/`，把 Phase 0～1 拆成可执行 issues。
3. 将 V5 #11 标记为被 V6 替代，但保留文件作为决策历史。
4. 完成 Phase 0 Gate 后再开始代码变更。
