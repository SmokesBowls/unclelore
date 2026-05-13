# Authority Scoring Rules v1.0

## Purpose
Defines deterministic, explainable authority weights for Phase 6 codex candidates.
Scoring operates strictly on already-ingested evidence layers. Tier 0 prose is explicitly deferred.

## Evidence Hierarchy
| Tier | Layer | Authority Type | Weight | Condition |
|------|-------|----------------|--------|-----------|
| 1 | Canon Decisions | Binding | +100 | `Status: resolved` or `active` in `wiki/canon_decisions/` |
| 2 | Continuity Findings | Conflict/Review | +20 | `Status: resolved` |
| | | | -30 | `Status: open`, `Severity: high/canon-breaking` |
| | | | -10 | `Status: open`, `Severity: medium/low` |
| 3 | Source Summaries | Derived | +5 | Per exact match in `wiki/sources/*.md` |
| 4 | Registry | Existence | +1 | Present in `wiki/registry.md` Column 1 |

## Aggregation Logic