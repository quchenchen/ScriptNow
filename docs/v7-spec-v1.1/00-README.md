# ScriptFlow V7 规格包 v1.1

| | |
|---|---|
| 版本 | `v7-spec-v1.1` |
| 日期 | 2026-07-18 |
| 状态 | 已批准，允许启动 P0 |
| 取代 | `scriptflow-v6/docs/v7-spec-v1.0/` |

## 基线声明

V7 是基于既有技术资产启动的**全新产品开发**，不是 V5 产品领域模型的增量实现。根目录旧 `CONTEXT.md`、`docs/PRD-V5.md`、旧 ADR 和 V5/V6 产品文档仅作历史研究材料，不构成 V7 产品约束。

V7 的唯一规格基线是本目录。`v7-spec-v1.0` 保持冻结，原型继续引用其冻结副本：

- `scriptflow-v6/docs/v7-spec-v1.0/prototypes/creator-revision-focus.html`
- `scriptflow-v6/docs/v7-spec-v1.0/prototypes/admin-console.html`

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
- `adr/`：V7 独立 ADR 编号空间，不覆盖根目录历史 ADR。
- `references/AGENTSCOPE-2.0.4-VERIFICATION.md`：API 表面验证；其中未实测项必须在 P0 tracer bullet 中完成。

## 批复

本版本已经完成产品方向和架构原则批复。P0 可以开展规格固化、技术 tracer bullet、资产分类和新工程骨架工作；P0 验收前不得将未验证的 V6 业务模块直接导入 V7。
