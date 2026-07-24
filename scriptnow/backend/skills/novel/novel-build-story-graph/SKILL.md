---
name: novel-build-story-graph
description: Use long-form novel source material to build or update an evidence-grounded narrative graph. Apply chapter-aware extraction of characters, relationships, events, world rules, promises, payoffs, and state changes when planning an adaptation, checking continuity, or assembling later-chapter context.
metadata:
  scriptnow:
    roles: [architect, reviewer]
    stages: [source-analysis, planning, review]
    selection_priority: 90
---

# Build Novel Story Graph

Extract creative logic without rewriting the manuscript. Treat every node and edge as a claim that must cite one or more supplied text-unit ordinals.

## Workflow

1. Process only the supplied semantic units; never rely on model memory of the work.
2. Read [graph contract](references/graph-contract.md) before extraction.
3. Canonicalize repeated entities with stable lowercase keys such as `character:sera-voss`.
4. Extract explicit facts first. Mark interpretation as inference and lower its confidence.
5. Represent change as events or state transitions, not as a timeless character attribute.
6. Keep setup and payoff separate and connect them only when both have evidence.
7. Return JSON matching the requested contract. Do not wrap it in Markdown.

## Boundaries

- Do not invent missing motives, relationships, chronology, or payoffs.
- Do not copy long source passages into descriptions or summaries.
- Do not convert uncertainty into canon.
- Do not emit UI labels, database IDs, runtime commentary, or hidden reasoning.
- Prefer a small supported graph over a comprehensive speculative graph.
- Do not auto-mount this Skill by genre, platform, or language; graph extraction is an explicit source-analysis operation.
