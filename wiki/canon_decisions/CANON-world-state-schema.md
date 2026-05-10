# CANON — World State Declaration Schema
# wiki/canon_decisions/CANON-world-state-schema.md
#
# Every world-state canon declaration follows this schema.
# MrLore Phase 5c reads these files to know what to check.
# MrLore never enforces — it only flags possible drift.

---

## Schema

```yaml
# Required fields
world_state_id: unique-kebab-case-id
world_state_tag: machine_readable_tag
description: human readable description of the state
state_value: the canonical value (true/false/string/enum)
audit_only: true  # always true — MrLore never rewrites

# Scope — what chapters does this apply to
scope:
  arcs: []              # arc names from wiki/arcs/ — empty means all arcs
  books: []             # book numbers — empty means all books
  locations: []         # location names — empty means all locations
  excludes: []          # explicit exclusions (dream, memory, vision, flashback)

# Descriptor lists — what to look for in chapter text
contradicting_descriptors: []   # phrases that suggest the state is wrong
confirming_descriptors: []      # phrases that confirm the state is correct

# Metadata
established_by: who/what established this state
reference_chapters: []  # source chapters that establish this canon
status: active | inactive | pending | superseded
notes: free text
```

---

## Rules for all world-state declarations

1. `audit_only: true` is mandatory. Phase 5c never rewrites prose.
2. Scope must be as narrow as the evidence supports.
3. `excludes` must list known valid exceptions (dream, memory, vision, flashback, pre-event).
4. Contradicting descriptors should be specific enough to avoid false positives.
5. When state changes (e.g. occupation ends), create a new declaration — do not edit the old one.
6. Declarations stack — multiple active states can apply to the same chapter.
