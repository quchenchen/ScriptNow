# Multi-pass distillation contract

## Passes

1. **Inventory**: identify units, ordering, language, parse gaps, and source offsets.
2. **Atomic evidence**: extract one claim per item with dimension, source unit, quote-free paraphrase, offset, and confidence.
3. **Cross-unit synthesis**: connect state changes, causal chains, relationship movement, recurring imagery, promises, and payoffs.
4. **Conflict and gap check**: record mutually incompatible claims, missing transitions, unresolved identities, and uncovered units.
5. **Candidate profile**: propose story mechanisms, character engines, world constraints, voice features, quality risks, and safe reusable guidance.
6. **Human decision**: approve, revise, or reject. Only an approved version may enter the project's context pack.

## Required evidence fields

- `source_file_id`, `chunk_id`, `source_unit`, and offset or ordinal;
- dimension and atomic claim;
- confidence and whether the claim is explicit or inferred;
- related evidence IDs and contradiction group when applicable;
- extraction pass and run checkpoint.

Coverage is reported, not gamed. Numeric thresholds are configurable diagnostics. A run may finish as `ready_with_gaps`; it must not invent evidence to become `ready`.

## Candidate profile boundaries

Allowed: causal patterns, role functions, relationship dynamics, pacing observations, viewpoint distance, sentence/rhythm tendencies, setup/payoff mechanisms, and quality risks.

Excluded: copied prose, unique proper nouns unless required for project adaptation, scene-by-scene substitution recipes, author impersonation, and claims without citations.
