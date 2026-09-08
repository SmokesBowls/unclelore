#!/usr/bin/env python3
"""
MrLore v2 — Ingest Source Stub
Purpose: Register a vault source into MrLore's raw layer and create a
         source summary stub in wiki/sources/. No AI ingest. No canon writing.

Usage:
    python3 ingest_source_stub.py <vault-relative-path>

Example:
    python3 ingest_source_stub.py book_01_book_of_genesis/001_the_ethereal_vigil.md
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime

MRLORE_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT  = MRLORE_ROOT.parent

RAW_CHAPTERS  = MRLORE_ROOT / "raw" / "chapters"
WIKI_SOURCES  = MRLORE_ROOT / "wiki" / "sources"
LOG_PATH      = MRLORE_ROOT / "wiki" / "log.md"

WIKI_SOURCES.mkdir(parents=True, exist_ok=True)


def slug(path: Path) -> str:
    """Turn a path into a safe flat filename slug."""
    parts = list(path.parts)
    name  = "_".join(parts).replace(" ", "_").replace("/", "_")
    return name


def register_source(vault_rel: str) -> int:
    source_path = VAULT_ROOT / vault_rel

    if not source_path.exists():
        print(f"[ingest_stub] ERROR: source not found: {source_path}")
        return 1

    # ── 1. Copy into raw/chapters/ ───────────────────────────────────────────
    dest_slug  = slug(Path(vault_rel))
    dest_raw   = RAW_CHAPTERS / dest_slug
    if dest_raw.exists():
        print(f"[ingest_stub] Already registered in raw: {dest_raw.name}")
    else:
        shutil.copy2(source_path, dest_raw)
        print(f"[ingest_stub] Copied to raw/chapters/{dest_raw.name}")

    # ── 2. Create wiki/sources/ stub ─────────────────────────────────────────
    stem         = Path(vault_rel).stem
    summary_name = dest_slug.replace(source_path.suffix, "") + ".md"
    summary_path = WIKI_SOURCES / summary_name

    if summary_path.exists():
        print(f"[ingest_stub] Source summary already exists: {summary_path.name}")
    else:
        text = source_path.read_text(encoding="utf-8", errors="replace")
        line_count = len(text.splitlines())
        word_count = len(text.split())

        stub = f"""# Source Summary — {stem.replace("_", " ").title()}

Type: Source Summary
Canon State: unreviewed
Ingested: {datetime.now().strftime("%Y-%m-%d")}
Vault Path: {vault_rel}
Raw Copy: raw/chapters/{dest_raw.name}
Lines: {line_count}
Words: {word_count}

---

## What This Source Contains

<!-- MrLore: summarize what happens in this source -->

## Entities Mentioned

<!-- Characters, locations, factions, species, systems encountered -->

### Characters
-

### Locations
-

### Factions / Species
-

### Events
-

### Terms / Concepts
-

## Arc Connections

<!-- Which arcs does this source touch? -->
-

## Timeline Notes

<!-- Any dates, eras, or Enkialu references -->
-

## Contradictions Detected

<!-- Any conflicts with existing wiki pages -->
-

## Unresolved Questions Raised

<!-- New gaps or mysteries introduced -->
-

## Pages to Create or Update

<!-- List of wiki pages that should be created or updated after this ingest -->
-

## Ingest Status

- [ ] Source summary written
- [ ] Entity pages created/updated
- [ ] Arc pages updated
- [ ] Timeline pages updated
- [ ] Contradictions filed
- [ ] Unresolved questions filed
- [ ] index.md updated
- [ ] log.md appended
"""
        summary_path.write_text(stub, encoding="utf-8")
        print(f"[ingest_stub] Created wiki/sources/{summary_name}")

    # ── 3. Append to log.md ──────────────────────────────────────────────────
    log_entry = f"""
## [{datetime.now().strftime("%Y-%m-%d")}] stub | {stem.replace("_", " ").title()}

Summary:
- Source registered to raw/chapters/{dest_raw.name}
- Source summary stub created at wiki/sources/{summary_name}
- Full ingest pending

Pages changed:
- wiki/sources/{summary_name} (created)

Contradictions opened:
- none yet

Unresolved questions opened:
- none yet
"""
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(log_entry)
    print(f"[ingest_stub] Appended to wiki/log.md")

    # ── 4. Session briefing ──────────────────────────────────────────────────
    print()
    print("════════════════════════════════════")
    print(f" Source registered: {stem}")
    print("════════════════════════════════════")
    print(f"  Raw copy:     raw/chapters/{dest_raw.name}")
    print(f"  Summary stub: wiki/sources/{summary_name}")
    print()
    print("Next actions:")
    print(f"  1. Open wiki/sources/{summary_name}")
    print(f"  2. Fill in entity list, arc connections, timeline notes.")
    print(f"  3. Create/update character and arc pages.")
    print(f"  4. File any contradictions or unresolved questions.")
    print(f"  5. Check off ingest status checklist in the summary.")
    print()
    print("[ingest_stub] OK")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 ingest_source_stub.py <vault-relative-path>")
        print("Example: python3 ingest_source_stub.py book_01_book_of_genesis/001_the_ethereal_vigil.md")
        return 1
    return register_source(sys.argv[1])


if __name__ == "__main__":
    sys.exit(main())
