---
world_state_id: descriptor-audit-system
world_state_tag: world_state_descriptor_audit
audit_only: true

scope:
  books: []
  arcs: []
  locations: []

contradicting_descriptors: []
confirming_descriptors: []

status: active
version: "1.0"
---

# CANON — World-State Descriptor Audit

## Purpose

Defines the ruleset convention for detecting atmospheric, environmental, cosmic, political, metaphysical, technological, or factional world-state drift.

The engine scans for `contradicting_descriptors` only when `audit_only: true` and the chapter falls within the declared `scope`.

## Usage

- Leave `contradicting_descriptors` empty for a silent framework.
- Add regex patterns only in specific scoped world-state declarations.
- Authors may reference this file in prose; the scanner only reads the frontmatter.
- Prose belongs below the second `---`.

## Rule

Code owns audit mechanics.

Canon files own audit rules.

MrLore must not rewrite prose automatically.
