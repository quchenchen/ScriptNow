# 10 · Growth Tree schema + 血缘 API

- **Status**: proposed
- **Type**: feature
- **Blocked by**: 02, 06
- **Blocks**: 11
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #1-#4; ADR-0001

## What to build

血缘图谱基础设施。

**后端：**
- 新建表 `growth_nodes`：
  - `id`, `project_id`, `node_type` (`idea` / `structure` / `outline` / `episode` / `scene` / `asset`), `ref_id` (指向具体实体), `label`, `created_at`, `metadata` (JSON)
- 新建表 `growth_edges`：
  - `id`, `project_id`, `from_node_id`, `to_node_id`, `edge_type` (`derived_from` / `revised_from` / `references`), `created_at`
- SQLAlchemy 模型 + Alembic 迁移
- **回填脚本**：从现有 project 产出反推初始 tree（每次 stage 输出 → 创建 node + 连边）
- 新建 `backend/app/services/growth_tree_service.py`：
  - `get_tree(project_id) -> Tree` (纯函数，读 DB 后组装)
  - `lineage(node_id) -> [ancestors]`（追溯）
  - `descendants(node_id) -> [nodes]`（衍生）
  - `mark_dirty(source_node_id) -> [affected_downstream]`（Cascade 计算）
- 新建 API：
  - `GET /api/projects/{pid}/tree` → 全景
  - `GET /api/projects/{pid}/tree/lineage/{node_id}` → 追溯路径
  - `POST /api/projects/{pid}/tree/mark-dirty` → Cascade

**新产出物写入约定：**
- Agent 每次 stage 产出成功 → 自动创建 growth_node + edge（不能忘）

## Acceptance criteria

- [ ] 回填脚本能对现有 project 生成初始 tree（idea → structure → outline → episodes 完整血缘）
- [ ] `GET /tree` 返回节点数 + 边数与产出物数一致
- [ ] `lineage(episode_5.node)` 能回溯到对应 outline → structure → idea
- [ ] `mark_dirty(character_A.node)` 返回所有涉及 A 的 Episode nodes
- [ ] `pytest test_growth_tree_service.py` 覆盖纯函数 lineage / descendants / mark_dirty
- [ ] 新产出的 Episode / Structure 自动写入 growth_nodes + growth_edges

## Notes

- 用普通表存图，不用 graph DB（SQLite 足够）
- `metadata` JSON 里存 UI 需要的辅助信息（比如 outline 的一句话摘要）
- Character / Foreshadow / Prop 这些 Living Asset 本身也是 node，可以被 lineage 引用
