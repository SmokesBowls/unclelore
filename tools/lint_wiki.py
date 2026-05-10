#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timezone
import sys

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    ROOT / "schema" / "MRLORE_SCHEMA.md",
    ROOT / "wiki" / "index.md",
    ROOT / "wiki" / "log.md",
    ROOT / "wiki" / "registry.md",
    ROOT / "raw",
    ROOT / "wiki",
    ROOT / "logs",
]

ENTITY_DIRS = [
    "characters", "factions", "species", "locations",
    "systems", "arcs", "timelines", "themes", "terms",
    "artifacts", "events",
]


def check_registry_staleness(errors: list) -> None:
    """Fail if registry.md is missing or older than any wiki entity page."""
    registry = ROOT / "wiki" / "registry.md"

    if not registry.exists():
        errors.append("registry.md missing — run: python3 tools/build_registry.py")
        return

    registry_mtime = registry.stat().st_mtime
    stale_pages = []

    for entity_dir in ENTITY_DIRS:
        dir_path = ROOT / "wiki" / entity_dir
        if not dir_path.exists():
            continue
        for page in dir_path.glob("*.md"):
            if page.stat().st_mtime > registry_mtime:
                stale_pages.append(str(page.relative_to(ROOT)))

    if stale_pages:
        errors.append(
            f"registry.md is stale — {len(stale_pages)} page(s) newer than registry. "
            f"Run: python3 tools/build_registry.py"
        )
        for p in stale_pages[:5]:
            errors.append(f"  newer than registry: {p}")
        if len(stale_pages) > 5:
            errors.append(f"  ... and {len(stale_pages) - 5} more")


def main() -> int:
    errors = []

    # Required paths
    for path in REQUIRED:
        if not path.exists():
            errors.append(f"missing required path: {path}")

    # No hidden files in raw
    if (ROOT / "raw").exists():
        for raw_file in (ROOT / "raw").rglob("*"):
            if raw_file.is_file() and raw_file.name.startswith("."):
                errors.append(f"hidden file in raw source tree: {raw_file}")

    # No empty wiki pages
    if (ROOT / "wiki").exists():
        for page in (ROOT / "wiki").rglob("*.md"):
            text = page.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                errors.append(f"empty wiki page: {page}")

    # Registry staleness
    check_registry_staleness(errors)

    if errors:
        print("[MRLORE LINT] FAILED")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("[MRLORE LINT] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
