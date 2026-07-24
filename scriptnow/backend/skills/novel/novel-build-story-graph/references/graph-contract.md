# Narrative graph contract

## Node types

- `character`: named or clearly recurring actor.
- `relationship`: a relationship state that changes independently of either character.
- `event`: an action or revelation that changes later possibilities.
- `world_rule`: a constraint whose violation has a consequence.
- `foreshadow`: an explicit setup, warning, object, secret, or promise awaiting development.
- `location`: a recurring place that constrains or enables action.
- `faction`: an organized group with goals or pressure.
- `motif`: a repeated image or thematic object only when recurrence is evidenced.

## Edge types

Use concise stable verbs: `participates_in`, `causes`, `opposes`, `protects`, `betrays`, `reveals`, `depends_on`, `changes`, `sets_up`, `pays_off`, `located_in`, `member_of`, or `related_to`.

## Evidence rules

1. Every node and edge cites supplied unit ordinals.
2. Evidence must support the exact claim, not merely mention an entity.
3. Cross-unit inference must cite all contributing units and set `inference=true`.
4. Confidence above 90 is reserved for explicit statements or directly observed actions.
5. Contradictions remain separate claims until a later reconciliation pass resolves them.

## Description rules

Describe creative function and present state in one or two original sentences. Do not quote distinctive source prose. Chapter summaries state what changes and what remains unresolved.
