# V5/V6 Legacy Inventory

- Date: 2026-07-18
- Rule: `reuse` 仅用于语义和接口均匹配；`migrate` 表示重写进 V7 并用 characterization test 对照；V7 禁止直接 import legacy。

## scriptflow-v6 backend modules

| Module | Decision | V7 destination / reason |
|---|---|---|
| `agent_runtime.py` | migrate | 提取 AgentScope 组装经验到 `platform/runtime`；以 P0 tracer tests 为新契约 |
| `cascade_revisions.py` | isolate | 旧领域级联语义不属于 V7 基线 |
| `continuity.py` | isolate | 与旧 Living Assets/continuity 模型耦合 |
| `continuity_ledger.py` | isolate | 不是 V7 project_events 或 usage ledger |
| `db.py` | migrate | 仅参考 SQLite/aiosqlite 连接模式；schema 全新 |
| `directives.py` | isolate | 旧 CreativeDirective 领域模型不直接继承 |
| `living_assets.py` | archive/delete | 旧产品领域，V7 禁止导入 |
| `main.py` | replace | V7 使用新 composition root |
| `manuscript_documents.py` | migrate | 版本/候选行为分别迁入 Script/Novel，不复用混合 schema |
| `manuscript_edits.py` | migrate | diff/selection 算法可参考；分别实现 ScriptPatch/NovelPatch |
| `manuscript_impacts.py` | isolate | 依赖旧 StoryBible/Cascade |
| `medium_profiles.py` | migrate | 配置数据拆成 Script/Novel 各自 direction catalog |
| `models.py` | replace | 旧 28 表不作为 V7 schema 起点 |
| `project_planning.py` | migrate | 仅迁移创建不变式和可验证参数，不迁移组合类型 |
| `projects.py` | migrate | API 行为可作 characterization；所有 repository 重写 tenant scope |
| `revisions.py` | migrate | candidate/adopt/stale 行为迁入新版本契约 |
| `runtime_config.py` | migrate | 通用配置解析迁至 platform；增加 config snapshot/version |
| `schemas.py` | replace | Script/Novel 已建立独立 Pydantic contract |
| `story_architecture.py` | migrate | 业务规则分别进入 Script/Novel blueprint |
| `story_bible_changes.py` | isolate | 旧 StoryBible/Cascade 语义不继承 |
| `story_structures.py` | migrate | 公认结构模板作为数据源复制并按领域验证，不共享运行模型 |
| `tasks.py` | migrate | Agent task 状态语义并入 P1 ProjectRun，不直接复用表 |
| `writing.py` | replace | 旧混合 Writer；由 Script Writer 与 Novel Writer 分别实现 |

### V6 skills

| Skill | Decision | Rule |
|---|---|---|
| `story-core-shaping` | fork/migrate | Script/Novel 各自版本，保留高质量样例需人工复核 |
| `story-architecture` | fork/migrate | 按领域输入输出契约重写 |
| `opening-draft` | migrate to Script | 不进入 Novel |
| `selection-edit` | fork/migrate | 分别输出 ScriptPatch/NovelPatch |

### V6 tests

- `test_manuscript_documents/edits/revision_workflow`：保留为迁移行为参考，不能直接加入 V7 suite。
- `test_project_planning/growth`：只提取创建与 adopted 唯一性场景。
- continuity/living_assets/story_bible/cascade 测试：归档，不迁移需求。

## Root V5 backend

| Area | Decision | Rule |
|---|---|---|
| `api/auth.py`, `security.py`, ownership tests | migrate | 提取攻击用例；实现以 V7 ADR-0002 为准 |
| parser/chunker/source index/retriever | migrate/reuse after tests | 先做恶意文件、配额、tenant workspace characterization |
| `docx_exporter.py` | fork/migrate | 排版工具可提取；Script/Novel 导出器独立 |
| `llm_client.py`, pipelines | replace | AgentScope runtime 取代旧 LLM path |
| Growth Tree/Ralph/Living Asset/Cascade services and models | archive/delete | 旧领域，不进入 V7 |
| old ORM models/migrations | archive | 不作为 V7 migration baseline |
| old skills | isolate | 逐个做样例质量审查后才可 fork |

## Frontend

| Area | Decision | Rule |
|---|---|---|
| root `frontend/` | isolate/replace | 旧 V5 信息架构，不进入 V7 workspace |
| `scriptflow-v6/frontend/` | migrate selectively | ndjson、revision diff、router 测试可参考；SFC 不直接复制 |
| V7 frozen prototypes | reference | 只作为视觉/交互验收，不是生产代码 |
| design V2–V7 HTML | archive | 研究材料，禁止被运行时 import/serve |

## Documentation

| Area | Decision |
|---|---|
| `docs/v7-spec-v1.1/` | authoritative |
| `scriptflow-v6/docs/v7-spec-v1.0/` | frozen reference |
| root CONTEXT/PRD-V5/ADR and V6 product docs | archive/pre-v7 |
| V3/V4 archive | retain historical archive |

## Deletion gates

业务源码暂不删除，直到对应 `migrate` 项满足：

1. V7 目标模块和公共接口存在；
2. characterization 与 V7 contract tests 通过；
3. `rg` 证明 V7 无 legacy import；
4. 构建、完整后端测试和相关 E2E 通过；
5. 删除记录说明 Git/归档恢复方式。

可立即删除：`.DS_Store`、`__pycache__`、pytest/ruff/vite cache、dist 和可由 lockfile 恢复的 node_modules。
