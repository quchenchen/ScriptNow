---
name: novel-source-distiller
description: Use when a novel project has uploaded source material and the user explicitly asks to analyze, adapt, distill, or build reusable creative guidance from it; performs multi-pass evidence extraction, cross-chapter synthesis, contradiction checks, and a human-approved project profile without copying distinctive prose.
metadata:
  scriptnow:
    roles: [director, architect, reviewer]
    stages: [source-analysis]
    selection_priority: 0
---

# Novel Source Distiller

Distill mechanisms, not text. The source remains evidence; the output is a versioned candidate profile that cannot alter adopted facts or enter writing context until the user approves it.

## Workflow

1. Verify tenant/project ownership, source readiness, intended use, creative language, and copyright boundary.
2. Read [multi-pass distillation contract](references/multi-pass-contract.md).
3. Split by semantic unit where possible, preserve source offsets, and create a resumable run checkpoint.
4. Extract atomic evidence in separate passes for plot causality, character/relationship state, world rules, voice features, and setup/payoff.
5. Aggregate across chapters, merge duplicates, retain citations, and flag contradictions or unsupported inference.
6. Calculate coverage by processed units and dimensions. Missing evidence remains a gap; do not fill it with model knowledge.
7. Produce a candidate project profile with provenance, confidence, conflicts, exclusions, and recommended uses.
8. Require explicit user approval before publishing the profile as a project overlay. Rejection or revision preserves the previous approved version.

## Boundaries

- Never copy long passages, distinctive phrases, proprietary names, or a living author's signature expression into a reusable Skill.
- Never infer canon from an unapproved candidate or convert uncertain interpretation into fact.
- Do not auto-mount this Skill by genre, platform, or language; it is an explicit source-analysis operation.
- Market popularity requires a separate sourced Web/MCP workflow and is not inferred from the manuscript.
