# Schema — Semantic Translation Buffer (STB)
schema/SEMANTIC_BUFFER_SCHEMA.md
Version: 1.0
Phase: 6.3
Status: candidate | review-only

Purpose
Defines the deterministic contract for capturing, validating, and promoting prose-derived signals from Tier 0 chapters into the MrLore wiki. Acts as an intermediate translation buffer that isolates raw extraction from canonical authority.

Authority Alignment
- Operates at the boundary between Raw Narrative Source (Tier 0) and Wiki Synthesis (Tier 4) per MRLORE_SCHEMA.md Section 4.
- Mirrors audit_only: true parity from CANON-world-state-schema.md and RELATIONSHIP_DECLARATION_SCHEMA.md.
- Enforces explicit promotion gating per Phase 5/6 workflows.
- Maintains provenance-over-truth principle per MRLORE_SCHEMA.md Rule 1 & Rule 4.

Required Buffer Record Structure (YAML Frontmatter)
buffer_id: unique-kebab-case-id  # deterministic hash or sequential STB-XXXX
source_file: relative/path/to/raw/chapters/file.md
line_start: integer
line_end: integer
raw_quote: "exact verbatim text snapshot from source"  # provenance fingerprint only
signal_type: entity | relationship | descriptor | timeline | terminology_placeholder
parsed_payload:
  # Structure varies by signal_type (see Signal Definitions below)
  entity_name: ""
  relationship:
    predicate: ""
    subject: ""
    target: ""
  descriptor_value: ""
  timeline_anchor: ""
  terminology_variant: ""
audit_only: true  # mandatory. Buffer never mutates source or auto-promotes.
status: captured | validated | promoted | archived
created_date: YYYY-MM-DD
last_reviewed: YYYY-MM-DD
supersedes: null | buffer_id-string  # for corrections/updates

Signal Type Payload Definitions
- entity: 
    entity_name: str
    entity_type: CHR|FAC|SPEC|SYS|LOC|ART|EVT
    confidence: high|medium|low
- relationship: 
    predicate: str (must exist in RELATIONSHIP_PREDICATES.md)
    subject: str
    target: str
    temporal_scope: point_in_time|range|unresolved
- descriptor: 
    descriptor_key: str
    state_value: str
    context_tags: [str]
- timeline: 
    event_ref: str
    absolute_date: null|str
    relative_anchor: str
    certainty: exact|approximate|unresolved
- terminology_placeholder: 
    variant: str
    context_note: "DEFERRED TO 6.3-STB-2"  # explicitly scoped; no normalization until future ticket

Governance & Boundary Rules
1. audit_only: true is mandatory. The STB is an observability layer, not an authority layer.
2. raw_quote is provenance-only. The cited source chapter file at line_start/line_end is always authoritative. Buffer quotes are read-only fingerprints and must never override source truth.
3. Buffer records are immutable once written. Corrections require a new record with supersedes: <previous_buffer_id>. Original records are archived, never deleted or overwritten.
4. No buffer record may auto-promote to wiki/ or canon_decisions/. Promotion requires explicit human review and a future --apply gate (TASK 6.3-STB-PROMOTE).
5. Contradicting signals between buffer records or against existing wiki/canon truth must generate CONT- continuity references. Never overwrite or suppress.
6. Parsers (regex, NLP, or heuristic scanners) operate strictly on raw/ text. All outputs must land in the STB first. Direct wiki mutation from raw text is forbidden.
7. terminology_placeholder signals are capture-only. They flag potential drift or undefined terms but must not trigger normalization, alias resolution, or wiki updates until 6.3-STB-2 defines the normalization contract.
8. All records must include exact line bounds and verbatim raw_quote to enable deterministic re-scanning and human audit.

Validation & Promotion Workflow
1. Ingest: Scanner reads raw chapters, extracts signals, writes STB YAML records with status: captured.
2. Validate: Lint/audit tools check payload structure, predicate alignment, and citation integrity. Transitions records to status: validated.
3. Review: Human author reviews validated records. Confirms, corrects, or rejects.
4. Promote: Approved records transition to status: promoted. Future tooling (TASK 6.3-STB-PROMOTE) consumes only promoted records to synthesize wiki pages.
5. Archive: Obsolete or superseded records transition to status: archived with audit trail.

Dry-Run Validation Checklist
- [ ] Schema file exists at schema/SEMANTIC_BUFFER_SCHEMA.md
- [ ] All required frontmatter fields present and typed correctly
- [ ] audit_only: true enforced as mandatory
- [ ] raw_quote explicitly marked as read-only provenance
- [ ] terminology_placeholder explicitly deferred
- [ ] Promotion gating clearly separated from capture
- [ ] Zero wiki mutation rules stated
- [ ] Alignment with MRLORE_SCHEMA Sections 2, 4, 13, 19, 20 confirmed