#!/usr/bin/env python3
"""
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
"""

import sys
import os
import re
import tempfile
import shutil
from pathlib import Path, PurePosixPath
from datetime import datetime

MRLORE_ROOT   = Path(__file__).resolve().parents[1]
VAULT_ROOT    = MRLORE_ROOT.parent
MANIFEST_PATH = MRLORE_ROOT / "raw" / "changed_files.txt"
LOGS_DIR      = MRLORE_ROOT / "logs"

LOGS_DIR.mkdir(exist_ok=True)
MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

SOURCE_EXTS = {".md", ".txt", ".zw"}


# ── TIER CLASSIFIER (inline) ─────────────────────────────────────────────────

def _is_chapter_file(path: Path) -> bool:
    return bool(re.match(r"^\d+[_\-]", path.name))

def _is_book_dir(path: Path) -> bool:
    parent = path.parent.name.lower()
    return parent.startswith("book") or parent.startswith("book_")

def _in_southern_arc(path: Path) -> bool:
    parts = [p.lower() for p in path.parts]
    return "southern arc" in parts or "southern_arc" in parts

def classify_tier(path: Path) -> int:
    if path.suffix.lower() == ".json":             return 4
    if path.suffix in {".sh", ".py", ".pyc"}:      return 4
    if any(x in path.name for x in ["(1)","(2)","(3)"]): return 4
    if "fairy_tale" in path.parent.name.lower():   return 3
    if path.parent.name.lower() in {"extra","extras","ongoing","solid"} \
            or path.parent.name.lower().startswith("extra"): return 3
    if path.parent == VAULT_ROOT:                  return 3
    if "canon" in path.name.lower():               return 1
    if "unresolved" in path.name.lower():          return 1
    if any(k in path.name.lower() for k in
           ["lore","profile","magic","graviton","nephoretti",
            "igigi","vale","zephyr","keeper"]): return 1
    if _is_chapter_file(path) and (_is_book_dir(path) or _in_southern_arc(path)):
        return 0
    if _is_chapter_file(path): return 0
    return 3


# ── VALIDATION ───────────────────────────────────────────────────────────────

class ValidationError(Exception):
    pass


def normalize_path(raw: str) -> str:
    """
    Normalize a path string to a safe vault-relative forward-slash path.
    Raises ValidationError on any violation.
    """
    raw = raw.strip()
    if not raw:
        raise ValidationError("empty path")

    # Reject absolute paths
    if os.path.isabs(raw):
        raise ValidationError(f"absolute path rejected: {raw}")

    # Normalize separators to forward slash
    normalized = raw.replace("\\", "/")

    # Reject traversal
    if ".." in normalized.split("/"):
        raise ValidationError(f"path traversal rejected: {raw}")

    # Reject hidden files / dirs
    parts = normalized.split("/")
    if any(p.startswith(".") for p in parts):
        raise ValidationError(f"hidden path rejected: {raw}")

    # Reject _mrlore self-reference
    if parts[0] == "_mrlore":
        raise ValidationError(f"_mrlore internal path rejected: {raw}")

    # Canonical: no trailing slash, no leading slash
    normalized = normalized.strip("/")

    return normalized


def validate_vault_path(normalized: str, require_exists: bool = True,
                         allowed_tiers: set = None) -> tuple[str, int]:
    """
    Validate a normalized path against the vault.
    Returns (normalized_path, tier).
    Raises ValidationError on failure.
    """
    full_path = VAULT_ROOT / normalized

    if require_exists and not full_path.exists():
        raise ValidationError(f"not found in vault: {normalized}")

    if full_path.is_dir():
        raise ValidationError(f"path is a directory: {normalized}")

    if full_path.suffix.lower() not in SOURCE_EXTS:
        raise ValidationError(
            f"unsupported extension '{full_path.suffix}': {normalized}"
        )

    tier = classify_tier(full_path)

    if allowed_tiers is not None and tier not in allowed_tiers:
        raise ValidationError(
            f"tier {tier} not allowed (allowed: {sorted(allowed_tiers)}): {normalized}"
        )

    return normalized, tier


def process_raw_paths(
    raw_paths: list[str],
    require_exists: bool = True,
    allowed_tiers: set = None,
) -> tuple[list[tuple[str, int]], list[tuple[str, str]]]:
    """
    Process a list of raw path strings.
    Returns (valid_list, error_list).
    valid_list:  [(normalized_path, tier), ...]
    error_list:  [(original_raw, error_message), ...]
    """
    valid, errors = [], []
    seen = set()

    for raw in raw_paths:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        try:
            norm = normalize_path(raw)
            norm, tier = validate_vault_path(norm, require_exists, allowed_tiers)
            if norm in seen:
                continue  # dedupe silently
            seen.add(norm)
            valid.append((norm, tier))
        except ValidationError as e:
            errors.append((raw.strip(), str(e)))

    # Stable sort: by path string
    valid.sort(key=lambda x: x[0])
    return valid, errors


# ── MANIFEST I/O ─────────────────────────────────────────────────────────────

def read_manifest() -> list[str]:
    """Read current manifest. Returns list of paths (comments stripped)."""
    if not MANIFEST_PATH.exists():
        return []
    lines = MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines
            if l.strip() and not l.strip().startswith("#")]


def write_manifest_atomic(paths: list[str], metadata: dict) -> None:
    """Write manifest atomically via temp file + rename."""
    lines = [
        f"# MrLore Changed Files Manifest",
        f"# Written: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Source:  {metadata.get('source', 'unknown')}",
        f"# Count:   {len(paths)}",
        f"#",
        f"# All paths are vault-relative, forward-slash normalized.",
        f"# Do not edit manually. Use write_changed_manifest.py.",
        "",
    ] + sorted(set(paths)) + [""]

    tmp = MANIFEST_PATH.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    shutil.move(str(tmp), str(MANIFEST_PATH))


def append_to_manifest(new_paths: list[str], metadata: dict) -> list[str]:
    """Merge new paths into existing manifest, dedupe, sort, rewrite."""
    existing = read_manifest()
    merged   = sorted(set(existing) | set(new_paths))
    write_manifest_atomic(merged, metadata)
    return merged


# ── DISCOVERY ────────────────────────────────────────────────────────────────

EXCLUDED_DIRS = {
    "_mrlore", ".git", ".obsidian", ".engain", "__pycache__", ".trash",
}

def discover_tier0() -> list[str]:
    sources = []
    for path in sorted(VAULT_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SOURCE_EXTS:
            continue
        rel_parts = set(path.relative_to(VAULT_ROOT).parts)
        if rel_parts & EXCLUDED_DIRS:
            continue
        if classify_tier(path) == 0:
            sources.append(str(path.relative_to(VAULT_ROOT)))
    return sources


# ── LOGGING ──────────────────────────────────────────────────────────────────

def log_manifest_event(action: str, count: int, errors: int, source: str) -> None:
    log_file = LOGS_DIR / "manifest_events.log"
    entry = (
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
        f"action={action} count={count} errors={errors} source={source}\n"
    )
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> int:
    args = sys.argv[1:]

    dry_run       = "--dry-run" in args
    use_stdin     = "--stdin" in args
    tier0_all     = "--tier0" in args
    show_manifest = "--show" in args
    clear         = "--clear" in args
    from_file     = None
    allow_tier1   = "--allow-tier1" in args

    for i, arg in enumerate(args):
        if arg == "--from-file" and i + 1 < len(args):
            from_file = Path(args[i + 1])

    allowed_tiers = {0}
    if allow_tier1:
        allowed_tiers.add(1)

    # ── show ────────────────────────────────────────────────────────────────
    if show_manifest:
        if not MANIFEST_PATH.exists():
            print("[manifest] No manifest exists yet.")
            return 0
        paths = read_manifest()
        print(f"[manifest] Current manifest ({len(paths)} entries):")
        for p in paths:
            print(f"  {p}")
        return 0

    # ── clear ────────────────────────────────────────────────────────────────
    if clear:
        if dry_run:
            print("[manifest] DRY RUN: would clear manifest")
            return 0
        write_manifest_atomic([], {"source": "clear"})
        print("[manifest] Manifest cleared.")
        log_manifest_event("clear", 0, 0, "manual")
        return 0

    # ── collect raw input ────────────────────────────────────────────────────
    raw_inputs: list[str] = []

    if tier0_all:
        raw_inputs = discover_tier0()
        source_label = "tier0-discovery"
        print(f"[manifest] --tier0: discovered {len(raw_inputs)} Tier 0 sources")
    elif use_stdin:
        raw_inputs = [l.rstrip() for l in sys.stdin]
        source_label = "stdin"
    elif from_file:
        if not from_file.exists():
            print(f"[manifest] ERROR: --from-file not found: {from_file}")
            return 1
        raw_inputs = from_file.read_text(encoding="utf-8").splitlines()
        source_label = str(from_file)
    else:
        # Positional args = individual paths
        raw_inputs = [a for a in args if not a.startswith("-")]
        source_label = "cli"

    if not raw_inputs:
        print(__doc__)
        return 0

    # ── validate ─────────────────────────────────────────────────────────────
    valid, errors = process_raw_paths(
        raw_inputs,
        require_exists=True,
        allowed_tiers=allowed_tiers,
    )

    print(f"[manifest] Input: {len(raw_inputs)}  Valid: {len(valid)}  Errors: {len(errors)}")

    for raw, err in errors:
        print(f"  REJECTED: {raw!r} — {err}")

    if not valid:
        print("[manifest] No valid paths. Manifest not written.")
        log_manifest_event("rejected", 0, len(errors), source_label)
        return 2

    # ── dry run ──────────────────────────────────────────────────────────────
    if dry_run:
        print(f"[manifest] DRY RUN — would write {len(valid)} path(s):")
        for path, tier in valid:
            print(f"  [Tier {tier}] {path}")
        return 0

    # ── write ─────────────────────────────────────────────────────────────────
    merged = append_to_manifest(
        [p for p, _ in valid],
        {"source": source_label}
    )

    print(f"[manifest] Written: {MANIFEST_PATH}")
    print(f"[manifest] Total entries in manifest: {len(merged)}")
    for path, tier in valid:
        print(f"  [Tier {tier}] {path}")

    log_manifest_event("write", len(valid), len(errors), source_label)

    if errors:
        print(f"[manifest] WARNING: {len(errors)} path(s) rejected during validation")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
