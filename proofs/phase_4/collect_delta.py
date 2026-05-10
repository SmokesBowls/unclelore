#!/usr/bin/env python3
"""
MrLore Phase 4 — Delta Collector
collect_delta.py

Purpose:
    Read all .flag files emitted by coco_flow.py.
    Write one atomic delta manifest: raw/cocoindex_delta.txt
    Clear processed flags (optional --keep-flags to preserve).

Usage:
    python3 cocowatch/collect_delta.py
    python3 cocowatch/collect_delta.py --keep-flags
    python3 cocowatch/collect_delta.py --dry-run

After this runs:
    python3 tools/write_changed_manifest.py --from-file raw/cocoindex_delta.txt
    python3 tools/mrlore_run_changed.py --changed raw/changed_files.txt
"""

import sys
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

_HERE       = Path(__file__).resolve().parent
MRLORE_ROOT = _HERE.parent
FLAG_DIR    = _HERE / "output" / "changed"
DELTA_OUT   = MRLORE_ROOT / "raw" / "cocoindex_delta.txt"
LOGS_DIR    = MRLORE_ROOT / "logs"

LOGS_DIR.mkdir(exist_ok=True)


def collect_flags() -> list[str]:
    """Read all .flag files and return sorted list of vault-relative paths."""
    if not FLAG_DIR.exists():
        return []

    paths = []
    for flag_file in sorted(FLAG_DIR.glob("*.flag")):
        content = flag_file.read_text(encoding="utf-8").strip()
        if content:
            paths.append(content)

    return sorted(set(paths))  # dedupe + stable sort


def write_delta_atomic(paths: list[str], source: str) -> None:
    """Write delta manifest atomically via temp file + rename."""
    lines = [
        f"# MrLore CocoIndex Delta Manifest",
        f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Source: {source}",
        f"# Count: {len(paths)}",
        f"# Feed to: write_changed_manifest.py --from-file {DELTA_OUT}",
        "",
    ] + paths + [""]

    tmp = DELTA_OUT.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    shutil.move(str(tmp), str(DELTA_OUT))


def clear_flags() -> int:
    """Remove all processed flag files. Returns count removed."""
    if not FLAG_DIR.exists():
        return 0
    flags = list(FLAG_DIR.glob("*.flag"))
    for f in flags:
        f.unlink()
    return len(flags)


def log_collection(count: int, cleared: int, source: str) -> None:
    log_file = LOGS_DIR / "manifest_events.log"
    entry = (
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        f"action=collect count={count} cleared={cleared} source={source}\n"
    )
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)


def main() -> int:
    args = sys.argv[1:]
    dry_run    = "--dry-run" in args
    keep_flags = "--keep-flags" in args

    print(f"[collect_delta] Scanning: {FLAG_DIR}")
    paths = collect_flags()

    if not paths:
        print("[collect_delta] No changed files detected.")
        print("[collect_delta] Either vault has not changed or coco_flow.py has not run yet.")
        return 0

    print(f"[collect_delta] {len(paths)} changed file(s) detected:")
    for p in paths:
        print(f"  {p}")

    if dry_run:
        print(f"\n[collect_delta] DRY RUN — would write to {DELTA_OUT}")
        return 0

    # Write atomic delta manifest
    DELTA_OUT.parent.mkdir(parents=True, exist_ok=True)
    write_delta_atomic(paths, source="cocoindex_flags")
    print(f"\n[collect_delta] Written: {DELTA_OUT}")

    # Clear flags unless --keep-flags
    cleared = 0
    if not keep_flags:
        cleared = clear_flags()
        print(f"[collect_delta] Cleared {cleared} flag file(s)")
    else:
        print(f"[collect_delta] Flags preserved (--keep-flags)")

    log_collection(len(paths), cleared, "cocoindex_flags")

    print(f"\n[collect_delta] Next steps:")
    print(f"  python3 tools/write_changed_manifest.py --from-file {DELTA_OUT}")
    print(f"  python3 tools/mrlore_run_changed.py --changed raw/changed_files.txt")

    return 0


if __name__ == "__main__":
    sys.exit(main())
