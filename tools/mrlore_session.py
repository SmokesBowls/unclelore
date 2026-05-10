#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
import sys

MRLORE_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT = MRLORE_ROOT.parent

REQUIRED = [
    MRLORE_ROOT / "schema" / "MRLORE_SCHEMA.md",
    MRLORE_ROOT / "wiki" / "index.md",
    MRLORE_ROOT / "wiki" / "log.md",
    MRLORE_ROOT / "raw",
    MRLORE_ROOT / "wiki",
    MRLORE_ROOT / "tools",
]

EXCLUDED_DIRS = {
    ".git",
    ".obsidian",
    "_mrlore",
    "__pycache__",
    ".trash",
}

SOURCE_EXTS = {
    ".md",
    ".txt",
    ".zw",
    ".json",
}

def count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception:
        return 0

def iter_vault_sources():
    for path in VAULT_ROOT.rglob("*"):
        if not path.is_file():
            continue

        rel_parts = set(path.relative_to(VAULT_ROOT).parts)
        if rel_parts & EXCLUDED_DIRS:
            continue

        if path.suffix.lower() not in SOURCE_EXTS:
            continue

        yield path

def main() -> int:
    errors = []

    for path in REQUIRED:
        if not path.exists():
            errors.append(f"missing required path: {path}")

    if errors:
        print("[MrLore Session] FAILED")
        for err in errors:
            print(f"  - {err}")
        return 1

    schema = MRLORE_ROOT / "schema" / "MRLORE_SCHEMA.md"
    index = MRLORE_ROOT / "wiki" / "index.md"
    log = MRLORE_ROOT / "wiki" / "log.md"

    sources = sorted(iter_vault_sources())
    by_ext = {}
    for src in sources:
        by_ext[src.suffix.lower()] = by_ext.get(src.suffix.lower(), 0) + 1

    print("════════════════════════════════════")
    print(" MrLore v2 Session Boot")
    print("════════════════════════════════════")
    print(f"Time:        {datetime.now().isoformat(timespec='seconds')}")
    print(f"MrLore root: {MRLORE_ROOT}")
    print(f"Vault root:  {VAULT_ROOT}")
    print()
    print("Core files:")
    print(f"  schema: {schema} ({count_lines(schema)} lines)")
    print(f"  index:  {index} ({count_lines(index)} lines)")
    print(f"  log:    {log} ({count_lines(log)} lines)")
    print()
    print("Vault source scan:")
    print(f"  total candidate sources: {len(sources)}")
    for ext, count in sorted(by_ext.items()):
        print(f"  {ext or '[no ext]'}: {count}")

    print()
    print("Recent candidate sources:")
    for src in sorted(sources, key=lambda p: p.stat().st_mtime, reverse=True)[:15]:
        rel = src.relative_to(VAULT_ROOT)
        print(f"  - {rel}")

    print()
    print("[MrLore Session] OK")
    print()
    print("Next valid actions:")
    print("  1. Select one source/chapter for ingest.")
    print("  2. Create a source summary in wiki/sources/.")
    print("  3. Update affected continuity pages.")
    print("  4. Append wiki/log.md.")
    return 0

if __name__ == '__main__':
    sys.exit(main())
