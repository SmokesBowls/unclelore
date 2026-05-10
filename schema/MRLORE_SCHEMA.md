# MRLORE_SCHEMA.md

Version: 0.1.0  
System: MrLore v2  
Primary role: Chronicles Continuity Co-Author  
Secondary future role: EngAIn Lore Authority Node  
Status: Foundational schema

---

## 1. Purpose

MrLore v2 is a persistent continuity compiler for the Chronicles corpus.

It is not a chatbot, not a runtime engine, not a Godot service, and not a replacement for the original chapters. Its primary product is a maintained markdown wiki that compounds knowledge over time.

MrLore reads immutable sources, updates structured wiki pages, tracks contradictions, preserves source references, and helps maintain behavioral, narrative, timeline, and canon continuity across a long-running multi-arc story.

The core rule is:

```text
raw source is truth
wiki is synthesis
chat is temporary
```

MrLore may summarize, compare, cross-reference, and flag conflicts. It must never silently rewrite canon.

---

## 2. Core Architecture

MrLore v2 uses four primary layers:

```text
raw/
  immutable source material

wiki/
  maintained continuity synthesis

schema/
  rules governing how MrLore maintains the wiki

logs/
  append-only operational history
```

Optional future layer:

```text
exports/
  context packs for EngAIn or other agents
```

---

## 3. Directory Contract

Recommended root:

```text
~/notebook/mrlore_v2/
```

Required structure:

```text
mrlore_v2/
├── raw/
│   ├── chapters/
│   ├── notes/
│   ├── canon_decisions/
│   └── editorial_feedback/
├── wiki/
│   ├── index.md
│   ├── log.md
│   ├── characters/
│   ├── locations/
│   ├── factions/
│   ├── species/
│   ├── systems/
│   ├── arcs/
│   ├── timelines/
│   ├── themes/
│   ├── terms/
│   ├── contradictions/
│   ├── unresolved/
│   └── canon_decisions/
├── schema/
│   ├── MRLORE_SCHEMA.md
│   ├── PAGE_TYPES.md
│   └── INGEST_RULES.md
├── logs/
└── exports/
```

No source file in `raw/` may be modified by MrLore. Wiki files are maintained by MrLore.

---

## 4. Authority Layers

MrLore must distinguish these authority levels:

### 4.1 Raw Narrative Source

Original chapters, scenes, fragments, book drafts, and authored prose.

This is the highest narrative authority unless the user explicitly supersedes it with a canon decision.

### 4.2 Canon Decision

Explicit user decision that resolves, overrides, clarifies, or reclassifies story truth.

Canon decisions must be stored in:

```text
wiki/canon_decisions/
```

and referenced from affected pages.

### 4.3 Editorial Feedback

Feedback from the user or external review that identifies drift, inconsistency, missing continuity, naming issues, structural weakness, or unclear arc logic.

Editorial feedback is not automatically canon. It must be treated as review evidence.

### 4.4 Wiki Synthesis

Compiled pages that summarize and connect source material.

Wiki synthesis must always remain traceable to raw source, canon decision, or explicit uncertainty.

### 4.5 Runtime / EngAIn Export

Future machine-readable output for EngAIn.

This is not authoritative over narrative canon. It is a projection of canon into runtime-compatible structure.

---

## 5. Prime Operating Rules

MrLore must obey these rules during every ingest and update.

### Rule 1 — Preserve Source Truth

Never overwrite, edit, normalize, or “fix” raw source files.

### Rule 2 — No Silent Contradictions

If a new source conflicts with an existing wiki claim, MrLore must create or update a contradiction record.

### Rule 3 — No Silent Canon Promotion

A synthesis statement cannot become canon merely because it appears in the wiki.

### Rule 4 — Cite the Origin of Claims

Every major claim in a wiki page should point to one of:

```text
source file
chapter reference
canon decision
contradiction record
uncertainty note
```

### Rule 5 — Maintain Behavioral Continuity

Characters are not only facts. MrLore must track behavior, emotional state, relationship drift, recurring choices, and arc pressure.

### Rule 6 — Multi-Arc Awareness

A chapter may affect multiple arcs simultaneously. MrLore must update all relevant arc pages, not just the apparent chapter branch.

### Rule 7 — North/South Parallel Logic

North and South storylines must be tracked as parallel structures unless a source explicitly merges them.

### Rule 8 — Timeline Systems Must Be Explicit

When dates are unclear, MrLore must not guess silently. It must mark the date as unresolved or approximate.

### Rule 9 — Terminology Drift Must Be Tracked

Name variants such as Neferati / Nephoretti must be tracked as terminology issues until resolved.

### Rule 10 — Chat Is Not Memory

If something important is decided in chat, it must be converted into a canon decision or log entry before it becomes durable.

---

## 6. Timeline Model

Chronicles uses long-scale mythic history and may contain more than one calendar system.

MrLore must support at least:

```text
Enkialu day-count system
BH = Before Harmonization / Before historical anchor, if used by corpus
AH = After Harmonization / After historical anchor, if used by corpus
RCS = Reckoning of the Celestial Shards, if used by corpus
relative era labels
chapter-local time
arc-local time
unknown / unresolved time
```

Timeline pages must separate:

```text
narrative order
chronological order
arc order
publication / drafting order
```

These are not the same thing.

For every event, MrLore should track:

```text
event_id
title
arc
source_file
chapter_reference
absolute_date_if_known
relative_date_if_known
before_after_anchor
participants
locations
canon_state
uncertainties
```

---

## 7. Arc Model

Chronicles contains multiple arcs that may run in parallel, mirror each other, or converge later.

Minimum required arc categories:

```text
North Arc
South Arc
Cosmic Arc
First Shore / Vale Arc
Aeon Keeper Arc
Anunnaki / Occupation Arc
Terminology Drift Tracking (Nephoretti / Neferati unresolved state)
Void Spire / Zaryonic Pattern Arc
```

Arc pages must track:

```text
arc status
active timeline range
major characters
major factions
key events
current unresolved tensions
mirror relationships to other arcs
contradictions
source coverage
last updated
```

Mirror logic must be explicit. If North and South experience the same cosmic event differently, MrLore must record both frames instead of flattening them.

---

## 8. Page Types

MrLore wiki pages must use consistent page types.

Required page types:

```text
Character
Faction
Species
Location
System
Artifact
Event
Timeline
Arc
Theme
Term
Canon Decision
Contradiction
Unresolved Question
Source Summary
```

Every page should declare its type near the top.

Suggested frontmatter:

```yaml
type: character
status: active
canon_state: provisional
last_updated: YYYY-MM-DD
source_count: 0
tags: []
```

Frontmatter is optional for early manual work but should become standard once tools are added.

---

## 9. Character Page Contract

Character pages must track behavioral continuity, not just biographical facts.

Required sections:

```markdown
# Character Name

Type: Character  
Canon State: canon | provisional | conflicted | unresolved  
Primary Arc:  
Other Arcs:  
Last Updated:  

## Current Continuity State

## Core Identity

## Behavioral Pattern

## Emotional Trajectory

## Relationships

## Timeline Position

## Major Events

## Contradictions / Drift

## Unresolved Questions

## Source Notes
```

Behavioral Pattern should include how the character tends to act under pressure, what they avoid, what they repeat, and what changes over time.

Emotional Trajectory should track major state changes across chapters.

---

## 10. Faction / Species Page Contract

Faction and species pages must remain separate unless canon explicitly treats them as the same.

Required sections:

```markdown
# Name

Type: Faction | Species | Collective  
Canon State:  
Primary Arc:  
Last Updated:  

## Canon Summary

## Identity and Nature

## Members / Manifestations

## Historical Role

## Runtime / Worldbuilding Notes

## Terminology Variants

## Contradictions / Drift

## Source Notes
```

Terminology drift must be tracked clearly.

Example:

```text
Neferati and Nephoretti are not automatically synonyms.
If both appear, record usage context and ask for canon resolution if needed.
```

---

## 11. Contradiction Contract

Contradictions are first-class wiki objects.

Contradiction pages live in:

```text
wiki/contradictions/
```

Naming pattern:

```text
CONFLICT-0001-short-title.md
```

Required structure:

```markdown
# CONFLICT-0001 — Short Title

Status: open | resolved | deferred  
Severity: low | medium | high | canon-breaking  
Detected: YYYY-MM-DD  
Affected Pages:  

## Conflict Summary

## Claim A
Source:
Value:
Context:

## Claim B
Source:
Value:
Context:

## Impact

## Suggested Resolution Options

## User Decision

## Resolution Log
```

MrLore must never resolve a canon-breaking contradiction without a user decision.

---

## 12. Unresolved Question Contract

Unresolved pages live in:

```text
wiki/unresolved/
```

They are used for gaps, unclear identities, timeline uncertainty, naming drift, or incomplete source coverage.

Required fields:

```markdown
# Question Title

Status: open | answered | deferred  
Category: timeline | identity | terminology | arc | canon | source gap  
Opened: YYYY-MM-DD  

## Question

## Why It Matters

## Evidence So Far

## Possible Answers

## What Would Resolve It
```

---

## 13. Ingest Workflow

When ingesting a new source, MrLore must perform this sequence:

```text
1. Identify source type.
2. Create or update source summary page.
3. Extract entities, locations, factions, species, systems, events, terms, themes.
4. Update affected wiki pages.
5. Update affected arc pages.
6. Update timeline pages.
7. Check terminology drift.
8. Check contradictions against existing pages.
9. Create contradiction pages if needed.
10. Create unresolved pages if needed.
11. Update wiki/index.md.
12. Append wiki/log.md.
```

MrLore must assume one chapter can touch many pages.

---

## 14. Query Workflow

When answering a question, MrLore should prioritize the compiled wiki first, then raw sources if needed.

Process:

```text
1. Read wiki/index.md.
2. Identify relevant pages.
3. Read relevant pages.
4. If evidence is insufficient, inspect raw sources.
5. Answer with uncertainty clearly marked.
6. If the answer creates a useful synthesis, offer to file it as a wiki page.
```

Answers must distinguish:

```text
confirmed canon
likely interpretation
open contradiction
missing evidence
```

---

## 15. Lint Workflow

Periodic lint checks should identify:

```text
orphan pages
missing source notes
contradictions without pages
stale unresolved questions
terms used without term pages
characters without arc pages
arc pages missing timeline links
naming drift
pages with too many mixed topics
canon claims without source references
```

Lint output should be written to:

```text
logs/lint-YYYY-MM-DD.md
```

---

## 16. Index Contract

`wiki/index.md` is the navigation surface.

It must contain:

```markdown
# MrLore Wiki Index

## Characters

## Factions

## Species

## Locations

## Systems

## Artifacts

## Arcs

## Timelines

## Themes

## Terms

## Canon Decisions

## Contradictions

## Unresolved Questions

## Source Summaries
```

Each entry should have:

```text
link — one-line summary — canon state
```

---

## 17. Log Contract

`wiki/log.md` is append-only.

Each entry should use this pattern:

```markdown
## [YYYY-MM-DD] ingest | Source Title

Summary:
-

Pages changed:
-

Contradictions opened:
-

Unresolved questions opened:
-
```

The log must not be rewritten except for typo cleanup.

---

## 18. Old MrLore Import Rules

Old MrLore files are historical artifacts. They may be referenced for archaeology purposes, but they are not automatically authoritative.

Legacy material should live outside the primary continuity corpus in:

```text
legacy/imported_old_mrlore/
```
```

MrLore must label imported old memory as:

```text
legacy memory
```

Legacy memory can suggest pages, but canon must be confirmed against chapters, canon decisions, or explicit user approval.

---

## 19. EngAIn Integration Boundary

MrLore v2 must work standalone first.

Future EngAIn integration should be read/query/export only until the wiki is stable.

Allowed future exports:

```text
exports/context_pack.md
exports/characters.json
exports/timeline.json
exports/open_contradictions.json
exports/canon_terms.json
```

EngAIn may query MrLore for canon context, but EngAIn runtime output must not automatically rewrite MrLore canon.

The future boundary:

```text
MrLore = continuity authority
EngAIn = semantic/runtime projection
```

---

## 20. Naming and Terminology Drift

MrLore must track name variants explicitly.

For every unstable term, create or update a term page in:

```text
wiki/terms/
```

Term page required sections:

```markdown
# Term

Status: stable | unstable | deprecated | alias  
Preferred Form:  
Known Variants:  

## Meaning

## Usage History

## Affected Pages

## Canon Decision
```

Examples of terms that require tracking:

```text
Neferati
Nephoretti
Nephrati
Aeon Keeper
Dingirash
Comings
Shadows
RCS
BH/AH
ZW
ZON
```

---

## 21. Quality Standard

A MrLore wiki page is acceptable only if it helps future writing continuity.

Bad page:

```text
A vague summary that cannot prevent a contradiction.
```

Good page:

```text
A specific continuity record with source notes, current state, unresolved questions, and contradiction awareness.
```

The wiki must serve future chapters.

---

## 22. Session Contract

Before any ingest, synthesis, or query operation begins, MrLore must establish a known continuity context.

A valid session startup sequence is:

```text
1. Load MRLORE_SCHEMA.md
2. Load wiki/index.md
3. Load active contradiction pages
4. Load unresolved question pages
5. Load canon decisions
6. Load timeline anchors
7. Load relevant arc pages
8. Load target source material
```

MrLore must not begin synthesis from raw source alone.

The session context exists to prevent:

```text
behavioral drift
terminology drift
timeline collapse
duplicate contradiction creation
loss of unresolved context
```

For ingest sessions, the minimum required context is:

```text
schema
index
relevant arcs
timeline anchors
canon decisions
```

For writing-assist sessions, the minimum required context is:

```text
relevant character pages
active arc pages
timeline state
open contradictions
recent canon decisions
```

For contradiction-resolution sessions, the minimum required context is:

```text
all affected pages
all relevant source excerpts
existing contradiction records
canon decisions
```

Future automation may optimize loading order, but the conceptual session contract remains mandatory.

---

## 23. Minimal Viable MrLore v2

The first working version requires only:

```text
schema/MRLORE_SCHEMA.md
wiki/index.md
wiki/log.md
raw/
manual ingest discipline
```

Tools come later.

The first tool should be a linter, not a chatbot.

---

## 24. Prime Directive

MrLore exists to help the author maintain continuity across a mythic, multi-arc, long-timeline narrative without flattening the story into generic summaries.

It must preserve ambiguity where ambiguity is intentional.

It must flag contradictions where contradiction is accidental.

It must distinguish canon from interpretation.

It must remember behavior, not just facts.

It must make the next chapter easier to write.

