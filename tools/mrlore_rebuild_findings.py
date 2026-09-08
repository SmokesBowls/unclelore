#!/usr/bin/env python3
"""
MrLore v2 — Rebuild Findings Tool
Purpose: Atomically clear generated continuity tickets and counter, then run a fresh audit.
Rule: CONT-*.yaml and .counter are generated output, not canon.
Exit Codes: Propagates exit code from mrlore_run_changed.py (0=clean, 1=failure, 2=review).
"""

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path

# Resolve project root (assumes this script is in tools/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
CONTINUITY_DIR = PROJECT_ROOT / "wiki" / "continuity"

def main():
    parser = argparse.ArgumentParser(description="MrLore: Rebuild continuity findings from scratch.")
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="List files to be deleted without modifying the filesystem."
    )
    args = parser.parse_args()

    print(f"[MrLore] Project Root: {PROJECT_ROOT}")

    # 1. Identify target generated files
    files_to_delete = []
    
    # Match CONT-*.yaml
    cont_files = glob.glob(str(CONTINUITY_DIR / "CONT-*.yaml"))
    files_to_delete.extend(cont_files)
    
    # Match .counter
    counter_file = CONTINUITY_DIR / ".counter"
    if counter_file.exists():
        files_to_delete.append(str(counter_file))

    # Sort for deterministic ordering
    files_to_delete = sorted(list(set(files_to_delete)))

    if not files_to_delete:
        print("[MrLore] No generated CONT files or .counter found to clear.")
    else:
        print(f"[MrLore] Identified {len(files_to_delete)} generated artifact(s) for removal.")
        for f in files_to_delete:
            if args.dry_run:
                print(f"  [DRY-RUN] Would delete: {f}")
            else:
                try:
                    os.remove(f)
                    print(f"  [DELETED] {f}")
                except Exception as e:
                    print(f"[ERROR] Failed to delete {f}: {e}", file=sys.stderr)
                    sys.exit(1)

    if args.dry_run:
        print("[MrLore] Dry run complete. No audit executed.")
        sys.exit(0)

    # 2. Execute fresh continuity audit sequence
    print("[MrLore] Executing fresh continuity audit sequence...")
    
    # Step A: write_changed_manifest.py --tier0
    manifest_script = TOOLS_DIR / "write_changed_manifest.py"
    print(f"[MrLore] Running: python3 {manifest_script} --tier0")
    result_manifest = subprocess.run(
        [sys.executable, str(manifest_script), "--tier0"],
        cwd=PROJECT_ROOT,
        capture_output=False
    )
    if result_manifest.returncode != 0:
        print(f"[ERROR] Manifest generation failed (EXIT {result_manifest.returncode}).", file=sys.stderr)
        sys.exit(1)

    # Step B: mrlore_run_changed.py --changed raw/changed_files.txt
    audit_script = TOOLS_DIR / "mrlore_run_changed.py"
    changed_files = PROJECT_ROOT / "raw" / "changed_files.txt"
    
    print(f"[MrLore] Running: python3 {audit_script} --changed {changed_files}")
    result_audit = subprocess.run(
        [sys.executable, str(audit_script), "--changed", str(changed_files)],
        cwd=PROJECT_ROOT,
        capture_output=False
    )

    # 3. Propagate exit code
    print(f"[MrLore] Audit completed with EXIT {result_audit.returncode}.")
    sys.exit(result_audit.returncode)

if __name__ == "__main__":
    main()