# Relationship Predicates Schema v1.0
Status: candidate
Review Only: true
Generated: 2026-05-11
Schema Authority: MRLORE_SCHEMA.md Section 8 & 11
Purpose: Define deterministic relationship vocabulary, provenance requirements, and governance boundaries for Phase 6.2B graph synthesis. No inference. No autonomous edge creation.

## Global Evidence Authority Rules
Required Evidence Authority:
- Tier 0 explicit prose OR resolved Canon Decision may create an edge.
- Source summaries may propose an edge_candidate only.
- Continuity records may qualify/block existing edge candidates, but may not create edges.
- Registry presence alone may not create edges.

## Contradiction & Coexistence Policy
- Direct conflicts between Tier 0 prose and resolved Canon Decision → Canon Decision overrides. Edge must be updated with `overridden_by: <canon_id>` and previous state archived.
- Conflicting Tier 0 statements across chapters → Flag as `status: conflicted`. Edge cannot be promoted until resolved via Canon Decision or explicit author ruling.
- Source summary proposals → Stored as `edge_candidate` with `confidence: low`. Requires Tier 0/Canon backing for promotion.
- Continuity flags → Add `qualified_by: <continuity_id>` or `blocked_by: <continuity_id>`. Does not delete edges; suppresses promotion eligibility.

## Temporal Scope Policy
- All edges must declare temporal boundaries.
- Immutable events (`created_by`, `originates_from`) require `temporal_scope: point_in_time`.
- Mutable states (`member_of`, `serves`, `located_in`, `allied_with`, `opposes`) require `temporal_scope: range` or `temporal_scope: snapshot`.
- Unknown timelines must use `temporal_scope: unresolved` and block promotion until anchored.
- Temporal format: `YYYY-MM-DD` | `ARC_NAME` | `BOOK_ID` | `unresolved` | `ongoing`

## Allowed Predicates

### `member_of`
- Definition: Subject belongs to or is formally part of a Faction, Group, or Collective.
- Directionality: Subject (Entity) → Object (Group/Faction)
- Required Evidence Authority: Tier 0 explicit declaration OR resolved Canon Decision
- Contradiction Policy: Block if canon explicitly states independence, exile, or dissolution
- Temporal Policy: Mutable range. Requires start anchor. End anchor optional (`ongoing` permitted)

### `allied_with`
- Definition: Subject maintains a cooperative, non-hostile, or mutually supportive stance with Object.
- Directionality: Subject (Entity/Faction) ↔ Object (Entity/Faction) [bidirectional]
- Required Evidence Authority: Tier 0 explicit pact, treaty, or coordinated action OR resolved Canon Decision
- Contradiction Policy: Qualify with `condition: temporary` or `condition: contextual` if scope is limited. Block if canon states active hostility
- Temporal Policy: Mutable range. Must include `start_anchor`. `end_anchor` optional

### `opposes`
- Definition: Subject actively conflicts with, competes against, or resists Object.
- Directionality: Subject (Entity/Faction) → Object (Entity/Faction)
- Required Evidence Authority: Tier 0 explicit conflict, war, or stated opposition OR resolved Canon Decision
- Contradiction Policy: Coexist if asymmetrical (A opposes B, B unaware of A). Block if canon explicitly states alliance or merger
- Temporal Policy: Mutable range or snapshot. Must declare `scope_type: active_hostility | political_rivalry | ideological_conflict`

### `located_in`
- Definition: Subject is physically or spatially situated within Object during a specific narrative moment.
- Directionality: Subject (Entity/Location/Artifact) → Object (Location/Region/Realm)
- Required Evidence Authority: Tier 0 explicit placement OR resolved Canon Decision
- Contradiction Policy: Warn if conflicting locations appear without temporal context. Block if canon establishes impossible spatial overlap
- Temporal Policy: Snapshot or short-range. Requires `temporal_scope: snapshot` or `range_start/range_end`

### `created_by`
- Definition: Subject was originated, forged, authored, or brought into existence by Object.
- Directionality: Subject (Entity/Artifact/System) → Object (Creator/Entity/Faction)
- Required Evidence Authority: Tier 0 explicit origin event OR resolved Canon Decision
- Contradiction Policy: Block on conflict. Creation is treated as singular unless canon explicitly establishes multiple creators or retcons
- Temporal Policy: Point-in-time. Immutable once anchored

### `serves`
- Definition: Subject performs subordinate, functional, or duty-bound roles for Object.
- Directionality: Subject (Entity) → Object (Authority/Faction/Leader)
- Required Evidence Authority: Tier 0 explicit oath, assignment, or operational chain OR resolved Canon Decision
- Contradiction Policy: Block if canon explicitly states independence, rebellion, or severed ties
- Temporal Policy: Mutable range. Requires `start_anchor`. `end_anchor` or `ongoing` permitted

### `originates_from`
- Definition: Subject was born, hatched, generated, or first appeared at Object location.
- Directionality: Subject (Entity) → Object (Location/Region/Realm)
- Required Evidence Authority: Tier 0 explicit birth/origin event OR resolved Canon Decision
- Contradiction Policy: Block unless overridden by explicit Canon Decision. Treated as immutable baseline
- Temporal Policy: Point-in-time. Immutable once anchored

## Edge Storage Contract (Future 6.2B Implementation)
- Edges stored in candidate frontmatter as structured lists before promotion
- Format: `relations: - predicate: member_of | target: faction_name | status: candidate | provenance: [source_ids, canon_ids] | temporal_scope: ...`
- Promotion to official codex requires `status: promoted` and `provenance_verified: true`
- No edge may be synthesized without explicit `provenance` array referencing ingested files or canon IDs

## Governance Boundary
This schema is review-only. Extraction, validation, and graph synthesis are gated behind:
1. `6.2B-LINT-SCHEMA` (structural validation)
2. `6.2B-EXTRACT` (deterministic pattern matching, no inference)
3. `6.2B-LINT-EDGES` (edge integrity & temporal validation)
4. `6.2B-PROMOTE` (human-gated graph promotion)