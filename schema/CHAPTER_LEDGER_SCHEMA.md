schema/CHAPTER_LEDGER_SCHEMA.md
---
file_id: CHAPTER_LEDGER_SCHEMA
version: 0.1.1-candidate
phase: 6.0A
status: provisional
audit_only: true
review_required: true
generated: 2026-05-18
authority: candidate-draft
---

# Phase 6.0A — Chapter Extraction Ledger Schema

## 1. Core Principles
- **Extraction ≠ Interpretation**: The ledger captures observable tokens, claims, and spans. It does not infer truth, resolve contradictions, or promote canon.
- **Provisional by Default**: Every extracted record is `provisional: true` until explicitly validated by human review or deterministic cross-reference.
- **Audit-Only Enforcement**: `audit_only: true` is mandatory. No automated writer, normalizer, or override may mutate Tier 0 prose or promote ledger entries.
- **Source-Truth Anchored**: Every entry must trace to a verifiable span, quote_id, or line reference in the raw chapter.
- **Deterministic Ordering**: Entries are emitted in chapter-sequential order, sorted by object_class, then by source_span.

## 2. Base Ledger Object Contract
All ledger objects inherit the following required fields:
| Field | Type | Constraint |
|---|---|---|
| `object_class` | enum | Must match a defined class in §3 |
| `source_span` | string | Format: `<book_id>_ch<chapter_num>:<line_start>-<line_end>` or `quote_id:<hash>` |
| `confidence` | enum | `low`, `medium`, `high` (see §4) |
| `provisional` | bool | Always `true` at extraction |
| `audit_only` | bool | Always `true` |
| `extracted_value` | string | Raw or normalized claim from prose |
| `context_quote` | string | Exact 1–3 sentence window surrounding the span |
| `extraction_timestamp` | ISO-8601 | UTC |
| `extractor_id` | string | Tool/agent identifier |

## 3. Object Class Definitions
Each class extends the base contract with class-specific required fields:

### 3.1 `character_presence`
- `entity_name`: string
- `arc_context`: string (north/south/cosmic/etc.)
- `interaction_type`: enum (active, passive, referenced, implied)

### 3.2 `location_presence`
- `location_name`: string
- `spatial_relation`: enum (interior, exterior, transit, referenced, unknown)
- `environmental_state`: string (optional, free-text condition)

### 3.3 `faction_presence`
- `faction_name`: string
- `alignment_indicator`: enum (protagonist, antagonist, neutral, unknown)
- `manifestation`: enum (named_member, banner, decree, rumor, artifact)

### 3.4 `object_presence`
- `object_type`: string
- `object_name`: string (or `unnamed` if unspecified)
- `ownership_or_access`: string
- `state`: enum (intact, damaged, hidden, active, inert, unknown)

### 3.5 `spoken_claim`
- `speaker`: string
- `claim_text`: string
- `claim_target`: string
- `veracity_status`: enum (stated, contested, confirmed, refuted, unknown)

### 3.6 `action_taken`
- `actor`: string
- `action_verb`: string
- `target`: string
- `outcome_state`: string (observable result, if any)

### 3.7 `state_change`
- `subject`: string (character/location/faction/world)
- `previous_state`: string
- `new_state`: string
- `trigger`: string (event, decision, external force)

### 3.8 `relationship_observed`
- `entity_a`: string
- `entity_b`: string
- `relation_type`: string (allied, hostile, familial, hierarchical, transactional, etc.)
- `evidence_strength`: enum (explicit, implied, inferred)

### 3.9 `world_state_descriptor`
- `domain`: enum (atmospheric, environmental, cosmic, political, metaphysical, technological, factional)
- `descriptor_value`: string
- `contradicts_existing`: bool
- `matches_existing`: bool

### 3.10 `timeline_marker`
- `era_label`: string (RCS, BH, AH, relative, unknown)
- `sequence_anchor`: string (before/after X, during Y, Z days/years)
- `precision`: enum (exact_day, approximate, era_only, unordered)

### 3.11 `unresolved_term`
- `term_variant`: string
- `canonical_candidate`: string (empty if none)
- `drift_type`: enum (spelling, alias, faction_split, era_split, transcription, TTS)
- `requires_resolution`: bool (always `true`)

### 3.12 `contradiction_candidate`
- `conflict_axis`: string (character_behavior, location_state, timeline, terminology, faction_allegiance)
- `claim_a_span`: string
- `claim_b_span`: string
- `severity_estimate`: enum (cosmetic, structural, canon-breaking)

### 3.13 `group_agency_check`
- `group_name`: string
- `group_type`: enum (faction, collective_character, military_unit, crowd, species, unknown)
- `exhibits_unified_action`: bool
- `unified_action_evidence`: string
- `agency_signal`: enum (shared_command, coordinated_motion, shared_speech, collective_decision, single_identity_reference, unknown)
- `identity_implication`: enum (individuals_only, collective_actor, ambiguous)

## 4. Confidence & Source-Span Requirements
| Confidence | Criteria | Ledger Behavior |
|---|---|---|
| `high` | Explicit, unambiguous prose. Single interpretation. Valid `source_span`. | Proceeds to math layer. |
| `medium` | Strong contextual support. Minor ambiguity in scope or reference. Valid `source_span`. | Proceeds to math layer with `confidence_warning` flag. |
| `low` | Inferred, fragmented, or ambiguous. Missing precise span or relies on cross-chapter assumption. | Triggers EXIT 2 safety stop. Requires human review. |

- **Source Span**: Must resolve to a verifiable offset. Unresolvable spans default to `low` confidence and `provisional: true`.
- **Quote Anchoring**: `context_quote` must exactly match raw source. Normalization is forbidden.

## 5. Exit Code Semantics
| Code | Condition | Action |
|---|---|---|
| `EXIT 0` | All entries valid. Spans resolvable. Confidence ≥ `medium` or explicitly handled. | Ledger written atomically to `raw/ledgers/`. Manifest updated. |
| `EXIT 1` | Structural failure: malformed schema, missing required fields, invalid enum, tooling crash. | Halt. Diagnostic written to `logs/error_YYYY-MM-DD.md`. No ledger persisted. |
| `EXIT 2` | Safety stop triggered by: any `low` confidence entry, unresolvable span, `contradiction_candidate` with `canon-breaking` severity, or `world_state_descriptor` conflicting with active canon. | Halt. Ledger staged in `raw/ledgers_pending/`. Human review required. |

## 6. Validation & Processing Rules
1. **Required Output Directories**: The extraction tool must create and maintain the following directories before runtime:
   - `raw/ledgers/` — EXIT 0 canonical ledger storage
   - `raw/ledgers_pending/` — EXIT 2 staged ledgers awaiting review
   - `raw/ledgers_cache/` — temporary/idempotent working state for resumable runs
2. **Manifest-Gated Ingest**: Ledger extraction runs only after `tools/write_changed_manifest.py` confirms new or modified chapter files.
3. **No Silent Promotion**: `provisional: true` is immutable at extraction. Promotion requires explicit human approval or deterministic resolution workflow.
4. **Atomic Writes**: Ledger files are written via temp + rename to prevent partial state.
5. **Stable Ordering**: Entries are serialized in deterministic order: `book → chapter → line_offset → object_class → field_name`.
6. **Dry-Run Support**: `--dry-run` outputs schema validation report without writing to disk.
7. **Contradiction Routing**: `contradiction_candidate` objects automatically reference existing `wiki/contradictions/` pages if a matching axis exists. New candidates are flagged for review.
8. **Terminology Drift Isolation**: `unresolved_term` objects are routed to `wiki/terms/` pending canon decision. No automatic aliasing.

---
**CANDIDATE STATUS**: This schema is provisional. It defines structure, validation, and exit semantics only. No extraction logic, parsing rules, or runtime behavior is implemented. Awaiting human approval before tooling integration.