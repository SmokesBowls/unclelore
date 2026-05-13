# MRLORE-AUDIT-003: Toolchain Dry-Run Integration Test
Run: 2026-05-11T13:28:37Z
Root: `/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore`
---
🔍 Testing: write_changed_manifest.py
Command: `python3 /home/mytruelove/Downloads/obsidianburdenNov25/_mrlore/tools/write_changed_manifest.py --dry-run`
EXIT Code: `0`
Stdout (truncated):

MrLore v2 — Changed File Manifest Writer
The single normalized gatekeeper between external systems and MrLore ingest.

ALL external systems (Trae, CocoIndex, watchdog, GUI, Obsidian plugin)
must use this script to submit ingest requests.
No external system may write to changed_files.txt directly.

Enforces:
  - vault-relative paths only
  - no .. traversal
  - no absolute paths
  - canonical slash normalization (forward slash)
  - deduplication
  - existence check against vault
  - optional tier pre-check (reject non-Tier-0 by default)
  - stable sort order
  - atomic write (temp file + rename)

Usage:
    # Add single file
    python3 write_changed_manifest.py book_01_book_of_genesis/001_the_ethereal_vigil.md

    # Add multiple files from stdin (one per line)
    echo "book_01/001.md" | python3 write_changed_manifest.py --stdin

    # Add from a raw list file (external system output)
    python3 write_changed_manifest.py --from-file /tmp/cocoindex_delta.txt

    # Add all Tier 0 sources (full rebuild trigger)
    python3 write_changed_manifest.py --tier0

    # Preview what would be written (no changes)
    python3 write_changed_manifest.py --dry-run book_01/001.md

    # Clear the manifest
    python3 write_changed_manifest.py --clear

    # Show current manifest
    python3 write_changed_manifest.py --show

Exit codes:
    0  manifest written cleanly
    1  validation error (bad path, missing file, tier rejected)
    2  no valid paths after filtering (manifest not written)


---
🔍 Testing: continuity_audit.py
Command: `python3 /home/mytruelove/Downloads/obsidianburdenNov25/_mrlore/tools/continuity_audit.py --dry-run`
EXIT Code: `0`
Stdout (truncated):
[continuity_audit] Loading registry...
[continuity_audit] Registry: 2 canonical, 1 variants
[continuity_audit] Loading world state rulesets...
[continuity_audit] Loaded 0 ruleset(s) with active descriptors
[continuity_audit] Loading character states...
[continuity_audit] No sources to audit.

---
🔍 Testing: promote_candidate.py
Command: `python3 /home/mytruelove/Downloads/obsidianburdenNov25/_mrlore/tools/promote_candidate.py --dry-run`
EXIT Code: `2`
Stderr:
usage: promote_candidate.py [-h] --candidate CANDIDATE [--dry-run] [--approve]
                            [--force]
promote_candidate.py: error: the following arguments are required: --candidate

---
🔍 Testing: build_registry.py
Command: `python3 /home/mytruelove/Downloads/obsidianburdenNov25/_mrlore/tools/build_registry.py --dry-run`
EXIT Code: `0`
Stdout (truncated):
[registry] Scanning wiki pages...
  found: Faction         Aeon Keepers
  found: Species         Nephoretti
  found: Arc             Cosmic Arc
  found: Timeline        Genesis Timeline
  found: Term            Vrill

[registry] Written to /home/mytruelove/Downloads/obsidianburdenNov25/_mrlore/wiki/registry.md
[registry] 5 entities registered
[registry] OK

---

**FINAL STATUS:**
**EXIT CODE:** `2`
**Result:** DRIFT OR EXECUTION GAP DETECTED
