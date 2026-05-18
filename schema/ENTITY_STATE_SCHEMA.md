# ENTITY_STATE_SCHEMA.md

Status: draft contract  
Layer: chapter-local entity state  
Authority: derived evidence only  
Mutation rule: never edits Tier 0 prose; never writes global profiles directly  

---

## Purpose

`ENTITY_STATE_SCHEMA` defines the chapter-local state of an entity.

An entity state answers:

```text
Who or what is this entity in this chapter?
What role does it play here?
What relationships are visible here?
What changed by the end of this chapter?
What evidence supports that interpretation?
```

This schema exists to prevent extraction from immediately creating or mutating global wiki profiles.

Chapter-local states are evidence-bearing intermediate records. They may later compile into book-local profiles, registry updates, continuity reports, or global profile candidates.

---

## Core rule

```text
Extraction produces entity states.
Extraction does not produce canon.
Extraction does not produce global profiles.
```

Every field is provisional unless explicitly marked as approved by a later authority layer.

---

## File placement

Recommended path pattern:

```text
_mrlore/wiki/entity_states/<book_id>/<chapter_id>/<entity_slug>.md
```

Example:

```text
_mrlore/wiki/entity_states/book_12_forged_identity/068_brotherhood_revealed/tran.md
```

Large-scale implementations may store the same records in SQLite while rendering selected records to markdown for review.

---

## Required frontmatter

```yaml
schema: entity_state
schema_version: 1
state_id: EST-000000
entity_ref: unresolved | registry_id | candidate_id
display_name: string
entity_type: character | faction | species | location | system | artifact | event | concept | group | relationship_label | unknown
status: captured | compiled | needs_review | rejected | superseded
canon_state: evidence_only | provisional | reviewed | approved
audit_only: true

book_id: string
book_number: integer | null
chapter_id: string
chapter_title: string
source_file: raw/chapters/path
source_hash: string | null

created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
compiler_run_id: string | null
```

---

## Required body sections

Each entity state file must contain these sections in order.

```markdown
# <display_name> — Chapter State

## Chapter Role

## Identity Evidence

## State at Chapter Start

## State During Chapter

## State at Chapter End

## Relationships in This Chapter

## Actions / Agency

## Dialogue / Voice Evidence

## Location / Presence

## Arc Position

## Changes Detected

## Evidence Ledger

## Classification Notes

## Continuity Flags

## Compiler Notes
```

---

## Field definitions

### `state_id`

Unique identifier for this chapter-local state.

Recommended format:

```text
EST-<zero-padded-number>
```

Example:

```text
EST-000142
```

`state_id` identifies the record, not the entity. The same entity may have many state records.

---

### `entity_ref`

Reference to the registry symbol if known.

Allowed forms:

```yaml
entity_ref: CHR-0001-tran
entity_ref: candidate:tran
entity_ref: unresolved
```

Rules:

- Use a registry id only when the entity has already been resolved.
- Use `candidate:<slug>` when the candidate is plausible but not resolved.
- Use `unresolved` when the extraction cannot safely identify the entity.

---

### `display_name`

The name or label as used in this chapter.

Examples:

```yaml
display_name: Tran
display_name: Viên
display_name: Brothers
display_name: The Queen
display_name: Young Man
```

`display_name` is not canonical proof.

---

### `entity_type`

The chapter-local classification.

Allowed values:

```text
character
faction
species
location
system
artifact
event
concept
group
relationship_label
unknown
```

Important rule:

```text
relationship_label must not compile directly into wiki/characters/.
```

Examples:

```yaml
display_name: Brothers
entity_type: relationship_label
```

```yaml
display_name: Family of human slaves
entity_type: group
```

```yaml
display_name: Tran
entity_type: character
```

---

### `status`

Lifecycle of the entity state record.

Allowed values:

```text
captured
compiled
needs_review
rejected
superseded
```

Meanings:

- `captured`: extracted from source, not yet compiled.
- `compiled`: used by the entity compiler.
- `needs_review`: ambiguous or conflict-bearing.
- `rejected`: determined to be junk or invalid.
- `superseded`: replaced by a better state record.

---

### `canon_state`

Authority level of the record.

Allowed values:

```text
evidence_only
provisional
reviewed
approved
```

Rules:

- New extraction defaults to `evidence_only`.
- Compiler outputs may be `provisional`.
- Human review may mark `reviewed`.
- Only explicit canon decision may mark `approved`.

---

## Chapter Role

Short description of the entity's role in this chapter only.

Good:

```text
Tran appears as an active decision-maker during the confrontation and is linked to Viên through sibling language.
```

Bad:

```text
Tran is the main hero of the saga.
```

The chapter role must not summarize the entire corpus.

---

## Identity Evidence

Evidence that this entity is distinct, recurring, merged, split, or only a label.

Recommended structure:

```yaml
identity_evidence:
  named_directly: true
  speaks: true
  performs_actions: true
  receives_description: true
  has_internal_state: false
  appears_as_label_only: false
  identity_confidence: high
```

Confidence values:

```text
low
medium
high
```

Character eligibility requires at least one strong identity signal:

```text
named_directly + speaks
named_directly + performs_actions
named_directly + receives_description
```

A bare capitalized word is not enough.

---

## State at Chapter Start

The entity's known state at the beginning of the chapter.

Possible fields:

```yaml
state_start:
  location: string | null
  physical_state: string | null
  emotional_state: string | null
  social_status: string | null
  faction_alignment: string | null
  identity_state: string | null
  knowledge_state: string | null
```

Use `unknown` rather than inventing.

---

## State During Chapter

Observed state while the chapter unfolds.

This may include transformations, discoveries, revealed memories, injury, role changes, alliance shifts, or altered perception.

```yaml
state_during:
  active_conditions: []
  observed_traits: []
  active_conflicts: []
  temporary_roles: []
```

---

## State at Chapter End

The entity's state after the chapter's events.

```yaml
state_end:
  location: string | null
  physical_state: string | null
  emotional_state: string | null
  social_status: string | null
  faction_alignment: string | null
  identity_state: string | null
  unresolved_after_chapter: []
```

This section is required because continuity comparison depends on transitions.

---

## Relationships in This Chapter

Relationships visible in this chapter only.

Recommended structure:

```yaml
relationships:
  - predicate: sibling_of
    subject: Tran
    target: Viên
    evidence: direct | inferred | unresolved
    confidence: medium
    source_quote_id: Q-0001
    notes: "Relationship label appears in chapter context."
```

Rules:

- Relationship labels do not become character pages.
- Group terms must identify participants when possible.
- If participants cannot be resolved, use `UNRESOLVED`.

Allowed participant values:

```text
registry_id
candidate_slug
UNRESOLVED
```

---

## Actions / Agency

Actions performed by the entity.

```yaml
actions:
  - action: string
    target: string | null
    consequence: string | null
    confidence: low | medium | high
    source_quote_id: Q-0002
```

This is one of the strongest filters for real characterhood.

---

## Dialogue / Voice Evidence

Quotes spoken by the entity, or evidence that the entity has a distinct voice.

```yaml
dialogue:
  - quote_id: Q-0003
    speaker: Tran
    addressee: Viên | unknown
    quote_excerpt: short excerpt
    voice_note: string | null
```

If no dialogue exists:

```yaml
dialogue: []
```

---

## Location / Presence

Where the entity appears or is referenced.

```yaml
presence:
  direct_presence: true
  mentioned_only: false
  locations:
    - name: Sundrift
      confidence: high
      source_quote_id: Q-0004
```

Mentioned-only entities may still be valid, but should be lower confidence.

---

## Arc Position

Chapter-local arc placement.

```yaml
arc_position:
  arc_name: string | null
  role_in_arc: setup | escalation | revelation | reversal | resolution | aftermath | unknown
  chapter_function: string
```

---

## Changes Detected

What changed for this entity during the chapter.

```yaml
changes:
  - change_type: relationship_change | identity_reveal | location_change | status_change | knowledge_gain | transformation | contradiction | none
    before: string | unknown
    after: string | unknown
    confidence: low | medium | high
    source_quote_id: Q-0005
```

This section is the main input for continuity comparison.

---

## Evidence Ledger

Every claim must point back to source evidence.

Recommended structure:

```yaml
evidence:
  - quote_id: Q-0001
    source_file: raw/chapters/book_12_forged_identity_068_brotherhood_revealed.md
    line_start: null
    line_end: null
    excerpt: short exact excerpt
    supports:
      - relationship:sibling_of
      - identity:character
```

Rules:

- Do not use claims without evidence.
- If line numbers are unavailable, set them to `null`.
- Quotes should be short.
- Evidence must not be rewritten as canon.

---

## Classification Notes

Why this entity is classified the way it is.

Examples:

```text
Classified as relationship_label because "Brothers" describes a relationship between named participants and does not show independent agency.
```

```text
Classified as character because Tran is named directly, speaks, acts, and receives chapter-specific description.
```

---

## Continuity Flags

Potential issues detected by the chapter state extractor.

```yaml
continuity_flags:
  - flag_type: alias_drift | identity_merge_possible | identity_split_possible | relationship_conflict | location_conflict | timeline_conflict | type_conflict | none
    severity: info | warning | conflict
    note: string
```

Flags do not resolve conflicts. They only mark them.

---

## Compiler Notes

Notes for the book-level or global compiler.

```yaml
compiler_notes:
  eligible_for_book_profile: true
  eligible_for_global_profile: false
  requires_registry_resolution: true
  suggested_registry_action: create_candidate | link_existing | merge_candidate | reject_candidate | review
```

---

## Character eligibility rule

An entity may compile into a character profile only if chapter evidence shows at least two of the following:

```text
direct name
speech
agency/action
description as individual
relationship to another resolved entity
persistent identity state
```

Automatic rejection from character compilation:

```text
common sentence word
possessive-only form
color term without identity
body part
abstract concept
chapter heading
relationship label with no agency
group label with no individual identity
```

---

## Example: relationship label

```yaml
schema: entity_state
schema_version: 1
state_id: EST-000201
entity_ref: unresolved
display_name: Brothers
entity_type: relationship_label
status: captured
canon_state: evidence_only
audit_only: true

book_id: book_12_forged_identity
book_number: 12
chapter_id: 068_brotherhood_revealed
chapter_title: Brotherhood Revealed
source_file: raw/chapters/book_12_forged_identity_068_brotherhood_revealed.md
source_hash: null

created_at: 2026-05-16
updated_at: 2026-05-16
compiler_run_id: null
```

Classification:

```text
"Brothers" is treated as a relationship label unless later evidence gives it independent agency or identity.
```

---

## Example: character

```yaml
schema: entity_state
schema_version: 1
state_id: EST-000202
entity_ref: candidate:tran
display_name: Tran
entity_type: character
status: captured
canon_state: evidence_only
audit_only: true

book_id: book_12_forged_identity
book_number: 12
chapter_id: 068_brotherhood_revealed
chapter_title: Brotherhood Revealed
source_file: raw/chapters/book_12_forged_identity_068_brotherhood_revealed.md
source_hash: null

created_at: 2026-05-16
updated_at: 2026-05-16
compiler_run_id: null
```

Classification:

```text
Tran is treated as a character if the chapter evidence shows name, agency, dialogue, or individual description.
```

---

## Non-authority statement

Entity states are not canon.

They are evidence-bearing snapshots used by later compiler layers.
