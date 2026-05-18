schema/PASS2_MATH_SCHEMA.md
---
file_id: PASS2_MATH_SCHEMA
version: 0.1.0-candidate
phase: 6.0A-PASS2
status: provisional
audit_only: true
review_required: true
generated: 2026-05-18
authority: candidate-draft
---

# Phase 6.0A — Pass 2: Surface Form Statistics Schema

## 1. Core Principles
- **Pure Math, No Semantics**: Pass 2 performs deterministic aggregation over Pass 1 artifacts. No LLM inference, no entity classification, no canon logic.
- **Surface-Form Keyed**: All computation is keyed by `surface_form` string exactly as captured. No normalization, aliasing, or variant merging occurs at this stage.
- **Chronological Anchoring**: Every statistic preserves temporal provenance. Identity emerges from evidence density, not extraction-time assertion.
- **Provisional by Default**: All output records are `provisional: true`. No automated promotion to wiki, registry, or canon occurs.
- **Audit-Only Enforcement**: `audit_only: true` is mandatory. Pass 2 outputs are immutable read-only evidence for downstream Pass 3 ledger mapping.

## 2. Input Contract
Pass 2 consumes only Pass 1 artifact batches:
- **Source**: `raw/artifacts/batch_*.jsonl`
- **Schema**: `schema/ARTIFACT_SCHEMA.md` v0.1.0+
- **Key Fields Used**:
  - `surface_form` (grouping key)
  - `chapter` (unique chapter counting)
  - `chronological_order` (span computation)
  - `surrounding_quote` (speech-pattern detection)
  - `source_file` (book extraction for cross-book persistence)

## 3. Output Record Schema
Each unique `surface_form` produces exactly one record in `raw/math/surface_form_stats.jsonl`:

| Field | Type | Description | Computation Rule |
|---|---|---|---|
| `surface_form` | string | Exact token/phrase from Pass 1 | Grouping key; no normalization |
| `total_mentions` | integer | Count of all artifacts with this surface_form | `COUNT(artifact_id WHERE surface_form == key)` |
| `chapter_count` | integer | Number of unique chapters containing this form | `COUNT(DISTINCT chapter)` |
| `speech_count` | integer | Mentions where surrounding_quote matches speech pattern | `COUNT WHERE surrounding_quote =~ /\b[key]\s+(said\|asked\|replied\|continued)\b/i` |
| `action_count` | integer | Mentions where surface_form is grammatical subject | `COUNT WHERE artifact spans subject position of active verb` (see §4) |
| `book_count` | integer | Number of unique books containing this form | Extracted from `source_file` path; `COUNT(DISTINCT book_id)` |
| `cross_chapter_persistence` | bool | Appears in 3+ distinct books | `book_count >= 3` |
| `first_seen_chapter` | string | Earliest chapter by chronological_order | `MIN(chapter WHERE chronological_order == MIN(chronological_order))` |
| `last_seen_chapter` | string | Latest chapter by chronological_order | `MAX(chapter WHERE chronological_order == MAX(chronological_order))` |
| `chronological_span` | integer | Difference between last and first chronological_order | `MAX(chronological_order) - MIN(chronological_order)` |
| `artifact_ids` | array[string] | List of contributing artifact_id values | For traceability; sorted deterministically |
| `provisional` | bool | Always `true` | Immutable at Pass 2 |
| `audit_only` | bool | Always `true` | Immutable at Pass 2 |
| `computation_timestamp` | ISO-8601 | UTC timestamp of aggregation run | Tool-generated |
| `input_batch_hashes` | array[string] | SHA-256 of consumed artifact batches | For reproducibility |

## 4. Pattern Detection Rules (Deterministic Only)
### 4.1 Speech Pattern Detection (`speech_count`)
- Match regex: `/\b{surface_form}\s+(said|asked|replied|continued|whispered|shouted|murmured)\b/i`
- Case-insensitive; word-boundary enforced
- Only counts if `surface_form` appears immediately before speech verb
- Does not detect indirect speech, thought, or reported speech

### 4.2 Action Subject Detection (`action_count`)
- Uses simple syntactic heuristic: `surface_form` appears as first noun phrase before an active verb in `surrounding_quote`
- Regex heuristic: `/\b{surface_form}\b\s+[^.]*\b(went|took|saw|held|moved|struck|opened|closed|walked|ran|spoke|looked)\b/i`
- Excludes passive constructions (`was/were + verb`)
- Excludes possessive or attributive uses (`{form}'s`, `{form} of`)
- Flagged as `heuristic_approximation: true` in metadata; exact NLP parsing deferred to Pass 3

### 4.3 Cross-Book Persistence
- Book ID extracted from `source_file` via pattern: `raw/chapters/{book_id}_ch*.md`
- `cross_chapter_persistence = (book_count >= 3)`
- Threshold is configurable via `--persistence-threshold N` flag; default = 3

## 5. Exit Code Semantics
| Code | Condition | Action |
|---|---|---|
| `EXIT 0` | All surface_forms processed. No structural errors. Output written atomically. | Stats written to `raw/math/surface_form_stats.jsonl`. Manifest updated. |
| `EXIT 1` | Structural failure: malformed input artifact, missing required field, hash mismatch, tooling crash. | Halt. Diagnostic written to `logs/error_YYYY-MM-DD.md`. No output persisted. |
| `EXIT 2` | Safety stop: input batch hash mismatch, chronological_order inversion detected, or `--dry-run` flag present. | Halt. Stats staged in `raw/math_pending/`. Human review or explicit `--force` required. |

## 6. Processing Rules
1. **Manifest-Gated Ingest**: Pass 2 runs only after `tools/write_changed_manifest.py` confirms new or modified artifact batches.
2. **Deterministic Ordering**: Output records sorted by `surface_form` lexicographically, then by `first_seen_chapter`.
3. **Atomic Writes**: Output file written via temp + rename to prevent partial state.
4. **Idempotent Execution**: Same input batches + same tool version = byte-identical output. `input_batch_hashes` recorded for verification.
5. **Dry-Run Support**: `--dry-run` outputs validation report and sample records without writing to disk.
6. **No Silent Promotion**: `provisional: true` is immutable. Downstream Pass 3 must explicitly request promotion via manifest boundary.
7. **Heuristic Transparency**: `action_count` and `speech_count` include `heuristic_approximation: true` flag in record metadata to signal downstream uncertainty.
8. **Monologue Test Compatibility**: Output structure supports downstream monologue-stack analysis:
   - High `speech_count` + low `action_count` → candidate coherent speaker (Lyaris pattern)
   - Low `speech_count` + high `action_count` → candidate referenced actor (Pelagor pattern)
   - Low both + high `total_mentions` → candidate world-state descriptor or metaphor (Reality pattern)
   - Plural surface_form + low individual speech → candidate group label (Students pattern)
   *(Note: These patterns are documentation only. Pass 2 does not classify or tag.)*

## 7. Downstream Handoff
- **Pass 3 Input**: `raw/math/surface_form_stats.jsonl` + `schema/CHAPTER_LEDGER_SCHEMA.md`
- **Pass 3 Responsibility**: Map high-density surface forms to ledger classes (`character_presence`, `world_state_descriptor`, etc.) using evidence thresholds and human-approved rules.
- **No Circular Dependency**: Pass 2 never reads ledger schema or wiki state. It operates on raw artifacts only.

---
**CANDIDATE STATUS**: This schema defines Pass 2 deterministic aggregation only. It explicitly defers classification, identity resolution, and ledger mapping to Pass 3. Awaiting human approval before pipeline integration.