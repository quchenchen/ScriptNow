# ScriptNow 规格包 v1.1

| | |
|---|---|
| 版本 | `v7-spec-v1.1` |
| 初始批准 | 2026-07-18 |
| 最近修订 | 2026-07-28 |
| 状态 | 已批准，持续修订 |
| 取代 | 已归档的 v1.0 规格 |

## 基线声明

V7 是基于既有技术资产启动的**全新产品开发**，不是旧产品领域模型的增量实现。旧代码、旧规格和冻结原型已移出开发树并保存于外部归档，不构成当前产品约束。

V7 的唯一规格基线是本目录。需要核对历史决策时，先按
`02-LEGACY-DECONTAMINATION.md` 明确研究目标，再从归档提取单项材料。

## 已批准决策

1. 复用契约匹配且经过测试的旧技术资产；不匹配时采用新框架或重新实现，不保留污染新领域的兼容分支。
2. Script 与 Novel 是两套产品领域能力，不复用正文、StoryMap、Writer、审读、格式或导出契约；仅共享平台基础设施。
3. 领域表是业务事实源；`project_events` 是不可变活动日志；聚合只发生在查询投影层。
4. Candidate 不变式只保护用户已经采纳的创作事实；诊断、运行状态、审计和派生索引不属于 Candidate。
5. 额度采用 `reserve → consume/finalize → release`，要求事务、幂等、冲正和价格快照。
6. V7 首期即建立 tenant scope、认证会话、CSRF、防重放、凭据加密、管理审计和文件工作区安全。

## 包内文件

- `01-PRD-V7.md`：修订后的开发基线。
- `02-LEGACY-DECONTAMINATION.md`：旧资源复用、归档与删除规则。
- `03-DEVELOPMENT-PLAN.md`：从 P0 到完整测试 Release Candidate 的 WBS、测试体系和退出门槛。
- `04-DOMAIN-CONTRACTS.md`：Script 与 Novel 的独立 StoryMap、正文和 patch 不变式。
- `05-ADAPTIVE-SKILLS-CONTRACT.md`：CreativeProfile、SkillPlan、角色调度与受控能力进化契约。
- `06-DYNAMIC-CREATIVE-PLANNING.md`：结构 Skill 映射、短篇覆盖规划与创作中动态增补机制。
- `07-NARRATIVE-GRAPH-TAXONOMY.md`：小说素材图谱的稳定节点、关系类型与国际化规范。
- `08-I18N-THEME-GOVERNANCE.md`：界面语言、作品语言、素材语言边界，以及日夜主题与文案迁移规范。
- `09-WEBNOVEL-WRITER-FUSION-PLAN.md`：外部长篇网文系统审计、机制取舍、融合架构与分阶段验收规划。
- `10-NOVEL-GENRE-SKILL-QUALITY.md`：37 类题材覆盖地图、质量锚点、成对基准评测与 Skill 准入规则。
- `12-CHAPTER-PIPELINE.md`：章节生产单元、状态机、上下文快照、审读、人工修订与采纳边界。
- `13-CREATIVE-FLOW-TECHNICAL-AUDIT.md`：四类创作流程的时延、失败模式与技术审计。
- `14-AGENTSCOPE-ALIGNED-IMPLEMENTATION-PLAN.md`：AgentScope 对齐矩阵、分阶段实施任务和退出门槛。
- `15-HEADLESS-CREATIVE-PARTNER-ARCHITECTURE.md`：无界面创作搭档、Creative Session Protocol、CLI 与外部 Agent 接入规划。
- `16-GOVERNED-DREAMING-AND-EXPERIENCE-EVOLUTION.md`：跨会话经验沉淀、离线 Dream、受控记忆与 Skill 进化架构。
- `17-SYSTEM-UPGRADE-ITERATION-ROADMAP.md`：当前系统成熟度、完整流程断点、统一升级路线与分阶段退出门。
- `18-CREATIVE-FLOW-GOLDEN-BASELINE.md`：四领域黄金场景、真实完成不变式、证据格式与阶段 0 验收办法。
- `19-SYSTEM-BUSINESS-FLOW-MAP.md`：全系统参与者、四领域业务管线、AgentScope 运行边界、产物血缘与治理回路。
- `20-WORKTREE-INTEGRATION-MANIFEST.md`：当前工作树改动分组、归档边界、建议提交序列与集成检查清单。
- `adr/`：V7 独立 ADR 编号空间，不覆盖根目录历史 ADR。
- `references/AGENTSCOPE-2.0.4-VERIFICATION.md`：API 表面验证；其中未实测项必须在 P0 tracer bullet 中完成。

## 批复

本版本已经完成产品方向和架构原则批复，并按修订单持续吸收已批准的运行协议、四领域
管线与治理契约。`01-PRD-V7.md` 是产品与系统不变式，`14`—`20` 是实施、验收和现状证据；
任何“已实现”结论都必须由代码、迁移和自动化测试共同支持。
