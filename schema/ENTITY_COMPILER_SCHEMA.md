# ENTITY_COMPILER_SCHEMA.md

Status: draft contract  
Layer: entity compilation pipeline  
Authority: derived synthesis only  
Mutation rule: compiler writes derived profiles and reports, never Tier 0 prose  

---

## Purpose

`ENTITY_COMPILER_SCHEMA` defines how MrLore compiles entity knowledge from smaller evidence units into larger readable structures.

The compiler exists to prevent this broken flow:

```text
chapter extraction
  → global wiki/characters page
```

The corrected flow is:

```text
chapter extraction
  → chapter-local entity states
  → book-local profiles
  → continuity comparison
  → global profile candidates
  → approved global profiles
```

---

## Core principle

```text
Global profiles are compiled artifacts.
They are not extraction outputs.
```

Extraction sees fragments.  
The compiler builds continuity-aware profiles from fragments.

---

## Compiler layers

The entity compiler has five conceptual layers:

```text
Layer 0: Tier 0 source prose
Layer 1: STB evidence records
Layer 2: Chapter-local entity states
Layer 3: Book-local entity profiles
Layer 4: Cross-book continuity comparison
Layer 5: Global profile synthesis
```

No layer may skip directly from Layer 0 or Layer 1 into Layer 5.

---

## Required compiler inputs

The compiler reads:

```text
raw/chapters/
wiki/stb/ or _stb/
wiki/entity_states/
wiki/registry.md or registry symbol table
wiki/canon_decisions/
schema/RELATIONSHIP_PREDICATES.md
schema/RELATIONSHIP_PHRASE_REGISTRY.md
schema/ENTITY_STATE_SCHEMA.md
schema/REGISTRY_SYMBOL_TABLE_SCHEMA.md
```

Optional:

```text
wiki/world_states/
wiki/continuity/
wiki/book_profiles/
```

---

## Compiler outputs

The compiler may produce:

```text
wiki/book_profiles/<book_id>/characters/<entity_slug>.md
wiki/book_profiles/<book_id>/factions/<entity_slug>.md
wiki/book_profiles/<book_id>/species/<entity_slug>.md
wiki/book_profiles/<book_id>/locations/<entity_slug>.md

wiki/continuity/entity_deltas/<entity_id>.md
wiki/continuity/entity_conflicts/<conflict_id>.yaml

wiki/characters/<entity_slug>.md
wiki/factions/<entity_slug>.md
wiki/species/<entity_slug>.md
```

Rules:

- Book profiles may be provisional.
- Global profiles require registry resolution.
- Approved global profiles require human or canon-decision authority.
- Compiler may emit candidates and reports without approval.
- Compiler must not edit Tier 0 prose.

---

## Book-local profile

A book-local profile answers:

```text
Who is this entity in this book?
What chapters do they appear in?
What changes across the book?
What relationships exist in this book?
What unresolved issues remain?
```

Book-local profiles preserve narrative phase.

They prevent a single global profile from flattening twenty-seven books into one blended identity.

---

## Recommended book profile frontmatter

```yaml
schema: book_entity_profile
schema_version: 1
profile_id: BEP-000000
entity_ref: registry_id | candidate_id | unresolved
display_name: string
entity_type: character | faction | species | location | system | artifact | event | concept | group
book_id: string
book_number: integer | null
status: compiled | needs_review | rejected | superseded
canon_state: provisional | reviewed | approved
audit_only: true

chapter_states:
  - EST-000001
  - EST-000002

source_files:
  - raw/chapters/path

compiled_at: YYYY-MM-DD
compiler_run_id: string
```

---

## Required book profile sections

```markdown
# <display_name> — <Book Title> Profile

## Book-Level Summary

## Chapter Appearances

## Identity State Across This Book

## Relationship State Across This Book

## Location / Presence Across This Book

## Actions and Agency Across This Book

## Changes Across This Book

## Evidence Summary

## Continuity Questions Raised

## Registry Recommendations

## Compiler Notes
```

---

## Book profile compilation rules

A book profile may be compiled when one of these is true:

```text
same resolved entity appears in at least one chapter state
same candidate appears in multiple chapter states
single chapter state has strong identity evidence
human explicitly requests a book-local profile
```

A book profile must not be compiled when:

```text
candidate is only a sentence word
candidate is only possessive drift
candidate is only relationship label
candidate is only body-part or descriptor language
candidate lacks source evidence
```

Relationship labels may compile into relationship reports, not character profiles.

---

## Chapter-to-book aggregation

The compiler groups chapter states by:

```text
entity_ref
canonical alias
candidate slug
book_id
entity_type
```

Then it builds a sequence:

```yaml
chapter_sequence:
  - chapter_id: 060_echoes_of_the_cradle
    state_id: EST-000120
    start_state: ...
    end_state: ...
    changes: [...]
  - chapter_id: 061_the_hier
    state_id: EST-000121
    start_state: ...
    end_state: ...
    changes: [...]
```

This sequence is required for continuity comparison.

---

## Change detection

The compiler must explicitly compare adjacent chapter states inside the same book.

Change types:

```text
identity_change
relationship_change
location_change
status_change
faction_change
knowledge_change
emotional_change
physical_change
timeline_change
name_or_alias_change
type_change
no_change
```

Every change must include:

```yaml
change:
  change_type: identity_change
  before_state_id: EST-000120
  after_state_id: EST-000121
  description: string
  confidence: low | medium | high
  evidence:
    - Q-0001
    - Q-0002
  requires_review: true | false
```

---

## Continuity comparison triggers

A continuity comparison is triggered when any of the following occurs:

```text
same entity has two book profiles
same entity has conflicting identity states
same entity changes type
same entity has incompatible location sequence
same entity has incompatible relationship state
alias appears in one book but not registry
candidate resembles existing registry entry
relationship label repeatedly attaches to same participants
world-state scope conflicts with entity state
human requests comparison
```

---

## Cross-book comparison

Cross-book comparison reads book profiles, not raw chapters first.

Flow:

```text
book profile A
  + book profile B
  + registry symbol
  + canon decisions
  → entity delta report
```

The compiler may drill back into chapter states and STB evidence when needed.

---

## Entity delta report

Recommended path:

```text
wiki/continuity/entity_deltas/<entity_slug>.md
```

Purpose:

```text
Show how an entity changes across books.
```

Required sections:

```markdown
# <display_name> — Entity Continuity Delta

## Compared Book Profiles

## Stable Identity Signals

## Changed Identity Signals

## Relationship Changes

## Location / Timeline Changes

## Alias / Name Drift

## Possible Contradictions

## Possible Merges

## Possible Splits

## Recommended Registry Action

## Evidence Index
```

---

## Conflict report

When continuity comparison detects a contradiction, emit a conflict record.

Recommended path:

```text
wiki/continuity/entity_conflicts/ECON-0000.yaml
```

Required structure:

```yaml
schema: entity_continuity_conflict
conflict_id: ECON-0000
entity_ref: registry_id | candidate_id | unresolved
conflict_type: identity_conflict | relationship_conflict | location_conflict | timeline_conflict | type_conflict | alias_conflict | merge_conflict | split_conflict
severity: info | warning | conflict
status: needs_review | resolved | rejected

book_profiles:
  - path: wiki/book_profiles/book_11/characters/tran.md
  - path: wiki/book_profiles/book_12/characters/tran.md

claims:
  - claim_id: C-0001
    source_state: EST-000120
    claim: string
  - claim_id: C-0002
    source_state: EST-000121
    claim: string

question_for_human: string
recommended_actions:
  - create_alias
  - split_entity
  - merge_entities
  - mark_identity_state
  - reject_candidate
```

Conflict reports never resolve themselves.

---

## Global profile synthesis

A global profile answers:

```text
Who is this entity across the corpus?
What are their book-by-book states?
What identity transformations are approved?
What relationships persist?
What contradictions remain unresolved?
```

Global profiles are compiled from book profiles and continuity reports.

They are not compiled directly from raw chapter extraction.

---

## Recommended global profile frontmatter

```yaml
schema: global_entity_profile
schema_version: 1
profile_id: CHR-0001-tran
display_name: Tran
entity_type: character
canon_state: provisional | reviewed | approved
status: active | needs_review | deprecated | split | merged
audit_only: false

source_book_profiles:
  - wiki/book_profiles/book_11/characters/tran.md
  - wiki/book_profiles/book_12/characters/tran.md

continuity_reports:
  - wiki/continuity/entity_deltas/tran.md

registry_entry: CHR-0001-tran
last_compiled: YYYY-MM-DD
compiler_run_id: string
```

---

## Required global profile sections

```markdown
# <display_name>

## Canon Summary

## Identity Across Books

## Book-by-Book Continuity

## Approved Aliases and Identity States

## Relationships Across Books

## Timeline / Location Spine

## Major Transformations

## Unresolved Continuity Questions

## Evidence Index

## Compiler Notes
```

---

## Global profile eligibility

A global profile may be compiled when:

```text
entity has a registry symbol
entity has one strong book profile
entity has multiple chapter states with consistent identity
entity has human-approved canonical status
```

A global profile must be marked `needs_review` when:

```text
identity merge is uncertain
entity type changes across books
aliases are unresolved
book profiles conflict
timeline position conflicts
relationship predicates conflict
```

---

## Merge and split handling

### Merge

Use when multiple names likely refer to the same entity.

```yaml
merge_candidate:
  primary: CHR-0001-tran
  candidates:
    - candidate:tran-valenheart
    - candidate:tran-zaron
  reason: shared source evidence or identity continuity
  status: needs_review
```

### Split

Use when one name may refer to multiple entities.

```yaml
split_candidate:
  source_symbol: candidate:brothers
  proposed_entities:
    - CHR-0001-tran
    - CHR-0002-vien
  reason: label refers to relationship between two resolved characters
  status: needs_review
```

---

## Compiler authority rules

The compiler may:

```text
create book-local profiles
create provisional global profile candidates
create continuity delta reports
create conflict reports
recommend registry actions
```

The compiler may not:

```text
edit Tier 0 prose
declare canon without approval
merge entities without registry authority
split entities without registry authority
promote relationship labels to characters
delete evidence records
overwrite approved profiles without review
```

---

## File-size and density rule

Profile richness must come from evidence count and evidence quality, not from hardcoded names.

A profile may be considered underdeveloped when:

```text
profile body contains only template text
profile has no chapter states
profile has no evidence ledger
profile has no relationship state
profile has no changes detected
```

The compiler should mark such profiles:

```yaml
status: needs_review
compiler_note: insufficient evidence density
```

---

## Recommended pipeline

```text
1. Extract STB evidence from chapter.
2. Compile chapter-local entity states.
3. Compile book-local entity profiles.
4. Run intra-book continuity comparison.
5. Run cross-book continuity comparison.
6. Recommend registry updates.
7. Compile or update global profiles only after registry resolution.
```

---

## Non-authority statement

The entity compiler is a synthesis layer.

It organizes evidence but does not decide canon by itself.
