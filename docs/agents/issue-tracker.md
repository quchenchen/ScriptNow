# Issue Tracker — 本地 markdown

本项目没有 git remote / GitHub / GitLab 集成。issue 用本地 markdown 文件维护。

## 位置

- **进行中 / 未完成的 issue**：`.scratch/scriptflow-v5/NN-slug.md`
- **已完成 issue**：加 `~` 前缀改名，或移到 `.scratch/scriptflow-v5/done/`（视规模决定）

编号 `NN` 从 `01` 开始，两位数（`01-schema-consolidation.md`、`02-jwt-auth-gate.md` …）。

## 单个 issue 文件模板

```markdown
# NN · <title>

- **Status**: proposed / ready-for-agent / in-progress / blocked / done / wontfix
- **Type**: bug / feature / refactor / chore / spike
- **Blocked by**: #NN, #NN 或 "None"
- **Blocks**: #NN
- **Est**: S / M / L（S ≤ 半天，M ≤ 2 天，L 需要拆更细）
- **Parent PRD**: docs/PRD-V5.md §<section>

## What to build

<一段描述，端到端行为，不是分层实现>

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Notes

<任意补充：图片、上下文、决策原因>
```

## Skill 集成

- **`/to-prd`** — 产出的 PRD 写到 `docs/PRD-V5.md`（或按需要新增版本号）
- **`/to-issues`** — 拆出的 issue 写到 `.scratch/scriptflow-v5/NN-*.md`
- **`/triage`** — 通过修改 issue 文件 frontmatter 的 `Status:` 行推进状态
- **`/implement`** — 读某个 issue 文件，按 Acceptance criteria 干，干完更新 `Status: done`

## PR / external contribution

无 PR surface（无 remote）。所有工作在本地分支进行。

## Priority / ordering

按 `Blocked by` 图拓扑排序。同批可干的按 `Est` 从小到大先干（tracer bullet 精神：先端到端跑通薄的一刀）。
