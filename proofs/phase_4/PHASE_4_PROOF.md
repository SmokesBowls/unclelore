# Phase 4 Proof — CocoIndex Delta Layer

First run:
- 8 added
- 8 flags emitted
- 8 Tier 0 paths accepted
- 8 files ingested
- Registry OK
- Lint OK
- EXIT 0

Second run:
- 8 unchanged
- 0 flags emitted
- 0 ingest work

Conclusion:
CocoIndex delta detection works and feeds MrLore through the hardened manifest boundary.

## Known Phase 4 Constraint

`coco_flow.py` currently uses an explicit `source_roots` list instead of a full vault walk.

Reason:
`localfs.walk_dir` observed only the immediate directory level in this environment during full-vault mode.

Impact:
New book directories must be added manually to `source_roots` until recursive full-vault walking is resolved.

Current proven roots:
- book_01_book_of_genesis
- book_02_age_of_servitude
