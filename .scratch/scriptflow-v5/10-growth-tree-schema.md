# 10 · Growth Tree schema + 血缘 API

- **Status**: done
- **Type**: feature
- **Blocked by**: 02, 06
- **Blocks**: 11
- **Est**: M
- **Parent PRD**: docs/PRD-V5.md §User Stories #1-#4; ADR-0001

## What to build

血缘图谱基础设施。

- 新增表：`growth_nodes` (id/project_id/node_type/ref_id/label/metadata JSON) + `growth_edges` (from/to/edge_type)
- Alembic 0003：建表 + indexes
- SQLAlchemy 模型 GrowthNode / GrowthEdge
- Service `app/services/growth_tree_service.py` 6 个 public 函数：
  - `get_tree(project_id)` — {nodes, edges} snapshot
  - `lineage(node_id)` — 追溯路径（root → parent）
  - `descendants(node_id)` — BFS 顺序
  - `mark_dirty(source_node_id)` — 受影响的 episode/scene nodes
  - `record_artefact(...)` — idempotent 插节点
  - `record_derived_from(...)` — idempotent 插边
  - `backfill_project(project_id)` — 从现有 project 数据反推 tree
- API 端点 `/api/projects/{pid}/tree`：全景 / lineage / descendants / mark-dirty / backfill
- `save_episode` tool 自动写 episode + scene 节点及边（best-effort）

## Acceptance criteria

- [x] 回填脚本能对现有 project 生成初始 tree（idea → episode → scene + assets）
- [x] `GET /tree` 返回节点数 + 边数与产出物数一致
- [x] `lineage(episode.node)` 能回溯到 idea 层，root → parent 顺序
- [x] `mark_dirty(character_node)` 返回下游 episode 节点（node_type ∈ {episode, scene}）
- [x] `pytest test_growth_tree.py`：10/10（BFS 纯函数 + idempotency + backfill + API + owner isolation）
- [x] 新产出的 Episode → 自动写 growth_nodes + growth_edges (`save_episode` hook)

## Notes

- 用普通两张表存图（nodes + edges），不用 graph DB — SQLite BFS 几百节点毫秒级
- `metadata` JSON 存 UI 友好摘要（e.g. outline 一句话 pitch）
- `record_artefact` / `record_derived_from` 都 idempotent — 重复调用不产生重复记录
- Character/Foreshadow/Prop 这些 Living Asset 也是 nodes，`references` edge 挂到 episode
- **遗留**：其他 stage 产出（stage-agent chat 保存的 script_versions）自动写 node — 留给 issue #09 或 #11 落地（现在 backfill 也能覆盖历史）
