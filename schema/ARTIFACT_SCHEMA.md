schema/ARTIFACT_SCHEMA.md
---
file_id: ARTIFACT_SCHEMA
version: 0.1.0-candidate
phase: 6.0A-RESET-1 (Pass 1)
status: provisional
audit_only: true
review_required: true
generated: 2026-05-18
authority: candidate-draft
---

# Phase 6.0A — Pass 1: Raw Artifact Capture Schema

## 1. Core Principles
- **Extraction ≠ Classification**: Pass 1 captures raw surface tokens and chronological anchors only. No entity typing, identity resolution, or confidence scoring occurs at this stage.
- **Chronological Primacy**: Identity and state emerge downstream via evidence density and chronological stacking. Pass 1 must preserve raw sequence without flattening.
- **Provisional by Default**: All artifacts are `provisional: true`. No automated promotion or canon logic is applied.
- **Audit-Only Enforcement**: `audit_only: true` is mandatory. Pass 1 outputs are immutable read-only evidence for downstream phases.
- **Downstream Routing**: `schema/CHAPTER_LEDGER_SCHEMA.md` is explicitly reserved for Pass 2/3 ledger classification and math. It is not a Pass 1 target.

## 2. Required Artifact Fields
Every Pass 1 artifact must contain exactly these fields. No additional classification, metadata, or inference fields are permitted.

| Field | Type | Description | Constraint |
|---|---|---|---|
| `artifact_id` | string | Deterministic hash/UUID per extracted token | Format: `art_<hash_prefix>` |
| `surface_form` | string | Exact raw text token/phrase as it appears in source | No normalization, no stemming, no lowercasing |
| `source_line` | integer | Line number offset in source file | 1-indexed |
| `source_span` | string | Character offset or line-range in source | Format: `<line_start>-<line_end>` |
| `chapter` | string | Canonical chapter identifier | Format: `<book_id>_ch<chapter_num>` |
| `chronological_order` | integer | Sequential extraction order for timeline stacking | Monotonically increasing per ingest batch |
| `surrounding_quote` | string | Exact 1–3 sentence context window | Must match raw source byte-for-byte |

## 3. Allowed System Metadata
The following metadata fields are automatically attached for traceability and idempotency. They do not carry semantic or canonical weight.

| Field | Type | Constraint |
|---|---|---|
| `extractor_id` | string | Tool/agent identifier |
| `extraction_timestamp` | ISO-8601 | UTC timestamp of capture |
| `source_file` | string | Absolute or repo-relative path to source |
| `source_hash` | string | SHA-256 of source file at ingest time |
| `audit_only` | bool | Always `true` |
| `provisional` | bool | Always `true` |

## 4. Strict Prohibitions (Pass 1 Boundary)
The Pass 1 extractor **MUST NOT** perform or output:
- [ ] Entity classification or type tagging (e.g., `character`, `faction`, `location`)
- [ ] Confidence scoring or reliability metrics
- [ ] Canon logic, truth assertion, or contradiction detection
- [ ] Registry promotion or wiki routing
- [ ] Relationship mapping or state inference
- [ ] Any field beyond those defined in §2 and §3

## 5. Pipeline Phase Mapping
```text
Pass 1 (Current): ARTIFACT_SCHEMA.md
  → Raw surface tokens + chronological anchors + source spans
  → Output: raw/artifacts/batch_<id>.jsonl

Pass 2 (Downstream): Chronological Comparison / Monologue Stacks
  → Groups artifacts by surface_form variant clusters
  → Computes chronological evidence density
  → Identifies monologue/test anchors

Pass 3 (Downstream): Identity Resolution & Ledger Extraction
  → Applies schema/CHAPTER_LEDGER_SCHEMA.md
  → Maps resolved artifacts to ledger classes (character_presence, world_state_descriptor, etc.)
  → Feeds deterministic math layer