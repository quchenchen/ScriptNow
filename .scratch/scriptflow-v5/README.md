# ScriptFlow V5 · Issue Tracker

本目录是 V5 重构的本地 markdown issue tracker。issue 文件按 `NN-slug.md` 编号，Status 见 [`docs/agents/triage-labels.md`](../../docs/agents/triage-labels.md)。

## 依赖图（tracer bullet 顺序）

```
Phase 3.1 · 清坏疮
  01 (deps) ─┬─→ 02 (schema) ─┬─→ 04 (auth) ─┬─→ 06 (scene) ──┬─→ 07 (character)
             │                 │              │                 ├─→ 08 (foreshadow+prop)
             │                 │              │                 └─→ 12 (script-sheet)
             ├─→ 03 (llm) ────┴─→ 05 (dead)  │                 └─→ 10 (tree-schema)
             │                                                        │
Phase 3.2 · Living Assets                                              ▼
Phase 3.3 · Ralph Loop        05 + 07 ────→ 09 (ralph)              11 (tree-ui)
Phase 3.4 · Growth Tree       07 + 08 + 10 → 11 (tree-ui) ─────────────┘
Phase 3.5 · Craft             05 ────→ 13 (anti-ai-tell)
                              06 ────→ 12 (script-sheet + docx export)
```

## 状态

- `proposed` — 刚拆出来，等 Q老师 approve
- `ready-for-agent` — Approved，agent 可以离线接单
- `in-progress` — 正在做
- `blocked` — 卡在依赖
- `done` — 全部 AC 打勾 + commit + 通过 review

## 完成的 slice

（暂无）
