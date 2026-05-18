# REGISTRY_SYMBOL_TABLE_SCHEMA.md

Status: draft contract  
Layer: symbol table / identity authority  
Authority: registry-level identity resolution  
Mutation rule: registry changes require explicit compiler recommendation or human/canon decision  

---

## Purpose

`REGISTRY_SYMBOL_TABLE_SCHEMA` defines the registry as MrLore's symbol table.

The registry is no longer a flat list of names.

It tracks:

```text
canonical entity id
display name
entity type
aliases
book appearances
chapter appearances
identity states
merge/split status
relationship labels
review status
source evidence
```

The registry's job is not to summarize lore.

Its job is to answer:

```text
What does this name refer to?
Is this entity already known?
Is this an alias?
Is this a relationship label?
Is this one entity, many entities, or unresolved?
Where does it appear?
What authority level does it have?
```

---

## Core principle

```text
The registry is the symbol table.
The wiki is the readable output.
STB/entity states are the evidence.
```

Scripts must read the registry for identity resolution instead of hardcoding story knowledge.

---

## Recommended file placement

Human-readable registry:

```text
_mrlore/wiki/registry.md
```

Machine-readable registry:

```text
_mrlore/wiki/registry/entities.yaml
```

or:

```text
_mrlore/semantic.db
```

Markdown may remain the review surface while SQLite stores the queryable index.

---

## Registry entry structure

```yaml
schema: registry_symbol
schema_version: 1

entity_id: CHR-0001-tran
display_name: Tran
canonical_name: Tran
entity_type: character

status: active | candidate | needs_review | deprecated | merged | split | rejected
canon_state: candidate | provisional | reviewed | approved
authority_level: evidence | compiler | human_review | canon_decision

aliases:
  - name: Tran Valenheart
    alias_type: identity_state | spelling | title | fused_identity | possessive_drift | uncertain
    status: candidate | approved | rejected
    first_seen: raw/chapters/path
  - name: Tran-Zaron
    alias_type: fused_identity
    status: needs_review

book_appearances:
  - book_id: book_11_blood_and_legacy
    book_number: 11
    profile_path: wiki/book_profiles/book_11/characters/tran.md
    confidence: high
  - book_id: book_12_forged_identity
    book_number: 12
    profile_path: wiki/book_profiles/book_12/characters/tran.md
    confidence: high

chapter_appearances:
  - chapter_id: 060_echoes_of_the_cradle
    state_id: EST-000120
    source_file: raw/chapters/book_11_blood_and_legacy_060_echoes_of_the_cradle.md
  - chapter_id: 068_brotherhood_revealed
    state_id: EST-000201
    source_file: raw/chapters/book_12_forged_identity_068_brotherhood_revealed.md

identity_states:
  - state_name: baseline
    scope: book_11_blood_and_legacy
    status: provisional
  - state_name: fused_with_zaron
    scope: book_05_the_nameless_one
    status: needs_review

merge_split:
  merge_status: none | merge_candidate | merged
  split_status: none | split_candidate | split
  related_symbols: []

relationship_labels:
  - label: brothers
    participants:
      - CHR-0001-tran
      - CHR-0002-vien
    status: needs_review

evidence:
  primary_sources:
    - raw/chapters/path
  entity_states:
    - EST-000120
  book_profiles:
    - wiki/book_profiles/book_11/characters/tran.md
  canon_decisions: []

review:
  needs_review: true | false
  review_reason: string | null
  last_reviewed: YYYY-MM-DD | null
  reviewed_by: human | compiler | null

timestamps:
  created_at: YYYY-MM-DD
  updated_at: YYYY-MM-DD
```

---

## Entity id format

Recommended prefixes:

```text
CHR = character
FAC = faction
SPE = species
LOC = location
SYS = system
ART = artifact
EVT = event
CON = concept
GRP = group
REL = relationship label
UNK = unresolved
```

Examples:

```text
CHR-0001-tran
FAC-0001-aeon-keepers
SPE-0001-nephoretti
SYS-0001-zaryonic-pattern
REL-0001-brothers-tran-vien
```

Numbering is type-scoped, not global.

---

## Entity type rules

Allowed registry entity types:

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

Rules:

- `relationship_label` must not be written to `wiki/characters/`.
- `group` must not be treated as a character unless it has explicit collective agency.
- `unknown` must not compile into global profiles.
- Possessive forms must be aliases or rejected drift, not entities.

---

## Alias types

Allowed alias types:

```text
spelling
transcription_drift
tts_drift
title
rank
epithet
identity_state
fused_identity
split_identity
possessive_drift
translation_variant
uncertain
```

Examples:

```yaml
aliases:
  - name: Neferati
    alias_type: transcription_drift
    status: approved
```

```yaml
aliases:
  - name: Tran's
    alias_type: possessive_drift
    status: rejected
```

```yaml
aliases:
  - name: Tran-Zaron
    alias_type: fused_identity
    status: needs_review
```

---

## Appearance tracking

### Book appearance

A book appearance means the entity has a compiled book-local profile or strong chapter-state evidence within that book.

```yaml
book_appearances:
  - book_id: book_12_forged_identity
    book_number: 12
    profile_path: wiki/book_profiles/book_12/characters/tran.md
    first_chapter: 067_the_shattered_mind
    last_chapter: 071_cosmic_teachers_arrive
    confidence: high
```

### Chapter appearance

A chapter appearance points to an entity state.

```yaml
chapter_appearances:
  - chapter_id: 068_brotherhood_revealed
    state_id: EST-000201
    source_file: raw/chapters/book_12_forged_identity_068_brotherhood_revealed.md
    presence_type: direct | mentioned | inferred
    confidence: high
```

---

## Identity states

Identity states represent approved or candidate phases of an entity.

Examples:

```text
baseline
pre_transformation
post_transformation
fused_with_zaron
memory_fragmented
disguised
title_bearing
dead
absent
unknown
```

Structure:

```yaml
identity_states:
  - state_id: IDSTATE-0001
    state_name: fused_with_zaron
    scope:
      books: [5]
      chapters: []
    status: needs_review
    evidence:
      - EST-000088
    notes: string
```

Identity states let the system preserve change without splitting entities prematurely.

---

## Merge handling

A merge candidate means two or more symbols may refer to the same entity.

```yaml
merge_split:
  merge_status: merge_candidate
  merge_candidates:
    - entity_id: CHR-0001-tran
    - entity_id: CHR-0042-tran-valenheart
  reason: shared identity evidence across book profiles
  status: needs_review
```

Rules:

- Compiler may recommend merges.
- Registry may record merge candidates.
- Only human/canon authority may approve merges.
- Approved merges must preserve old aliases.

---

## Split handling

A split candidate means one symbol may actually refer to multiple entities or a label.

Example:

```yaml
entity_id: REL-0001-brothers
entity_type: relationship_label
merge_split:
  split_status: split_candidate
  proposed_targets:
    - CHR-0001-tran
    - CHR-0002-vien
  reason: "Brothers appears to label a relationship, not an independent character."
  status: needs_review
```

Rules:

- Split candidates must not be deleted automatically.
- Split candidates must preserve evidence.
- Relationship labels may resolve into relationship records instead of profiles.

---

## Relationship label handling

Relationship labels are first-class registry symbols when recurring or meaningful.

Examples:

```text
Brothers
Sisters
Companions
Survivors
Freed Slaves
Five Mikas
Wise Ones
```

They should be typed as:

```yaml
entity_type: relationship_label
```

or:

```yaml
entity_type: group
```

They should not be typed as `character` unless they demonstrate individual identity or collective agency.

---

## Registry status values

```text
candidate
active
needs_review
deprecated
merged
split
rejected
```

Meanings:

- `candidate`: observed but unresolved.
- `active`: usable symbol.
- `needs_review`: conflict or ambiguity exists.
- `deprecated`: replaced by newer symbol.
- `merged`: merged into another symbol.
- `split`: split into multiple symbols.
- `rejected`: not a valid entity.

---

## Canon state values

```text
candidate
provisional
reviewed
approved
```

Meanings:

- `candidate`: extracted or compiler-suggested.
- `provisional`: usable but not final.
- `reviewed`: human has inspected.
- `approved`: canon decision exists.

---

## Authority levels

```text
evidence
compiler
human_review
canon_decision
```

Rules:

- Extraction can create `evidence`.
- Entity compiler can create `compiler`.
- Human review can create `human_review`.
- Canon decision files create `canon_decision`.

---

## Registry update triggers

The registry may be updated when:

```text
new chapter state introduces a candidate
book profile confirms repeated appearance
continuity comparison detects alias drift
continuity comparison detects merge candidate
continuity comparison detects split candidate
human approves canon decision
relationship label recurs across chapter states
entity type changes across profiles
```

The registry must not update when:

```text
single weak extraction finds a capitalized common word
candidate has no evidence ledger
candidate is a possessive-only form
candidate is only a chapter heading
candidate is only a color/body part/concept word
```

---

## Required registry operations

The registry system should support these operations:

```text
create_candidate_symbol
promote_symbol
deprecate_symbol
merge_symbols
split_symbol
add_alias
reject_alias
add_book_appearance
add_chapter_appearance
add_identity_state
add_relationship_label
mark_needs_review
resolve_review
```

Each operation must be logged.

---

## Registry operation log

Recommended path:

```text
wiki/registry/log.md
```

Entry format:

```markdown
## [YYYY-MM-DD] registry_update | <operation>

Entity: CHR-0001-tran
Operation: add_alias
Input: Tran-Zaron
Authority: compiler
Status: needs_review
Source: wiki/continuity/entity_deltas/tran.md
```

---

## Registry and global profile relationship

The registry is not the global profile.

Registry:

```text
identity resolution and symbol tracking
```

Global profile:

```text
human-readable lore synthesis
```

A global profile must reference a registry symbol.

A registry symbol may exist before a global profile exists.

---

## Query contract

The registry must support simple knowledge questions:

```text
Who is this name?
Where does this entity appear?
Is this an alias?
Is this a character or a relationship label?
What books contain this entity?
What unresolved conflicts affect this entity?
```

The query layer should not require the user to inspect STB files manually.

---

## Example: character symbol

```yaml
entity_id: CHR-0001-tran
display_name: Tran
canonical_name: Tran
entity_type: character
status: active
canon_state: provisional
authority_level: compiler

aliases:
  - name: Tran Valenheart
    alias_type: identity_state
    status: needs_review
  - name: Tran's
    alias_type: possessive_drift
    status: rejected

book_appearances:
  - book_id: book_12_forged_identity
    book_number: 12
    profile_path: wiki/book_profiles/book_12/characters/tran.md
    confidence: high

chapter_appearances:
  - chapter_id: 068_brotherhood_revealed
    state_id: EST-000201
    source_file: raw/chapters/book_12_forged_identity_068_brotherhood_revealed.md
    presence_type: direct
    confidence: high
```

---

## Example: relationship label symbol

```yaml
entity_id: REL-0001-brothers
display_name: Brothers
canonical_name: brothers
entity_type: relationship_label
status: needs_review
canon_state: candidate
authority_level: evidence

relationship_labels:
  - label: brothers
    participants:
      - CHR-0001-tran
      - CHR-0002-vien
    status: needs_review

book_appearances:
  - book_id: book_12_forged_identity
    book_number: 12
    profile_path: null
    confidence: medium
```

---

## Non-authority statement

The registry resolves identity.

It does not rewrite prose.

It does not decide canon without approved authority.
