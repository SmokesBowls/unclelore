#!/usr/bin/env python3
"""
MrLore v2 — Entity Registry Builder (patched)
"""

import sys
import re
from pathlib import Path
from datetime import datetime

MRLORE_ROOT   = Path(__file__).resolve().parents[1]
WIKI_PATH     = MRLORE_ROOT / "wiki"
REGISTRY_PATH = WIKI_PATH / "registry.md"

ENTITY_DIRS = [
    "characters", "factions", "species", "locations",
    "systems", "arcs", "timelines", "themes", "terms",
    "artifacts", "events",
]


def parse_page(path: Path) -> dict:
    text  = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    entity = {
        "name":         path.stem.replace("_", " "),
        "file":         str(path.relative_to(MRLORE_ROOT)),
        "type":         path.parent.name,
        "canon_state":  "unknown",
        "status":       "unknown",
        "variants":     [],
        "first_source": "",
        "last_updated": "",
    }

    for line in lines[:30]:
        s = line.strip()
        if s.startswith("# "):
            entity["name"] = s[2:].strip()
        elif s.lower().startswith("type:"):
            entity["type"] = s.split(":", 1)[1].strip()
        elif s.lower().startswith("canon state:"):
            entity["canon_state"] = s.split(":", 1)[1].strip()
        elif s.lower().startswith("status:"):
            entity["status"] = s.split(":", 1)[1].strip()
        elif s.lower().startswith("last updated:"):
            entity["last_updated"] = s.split(":", 1)[1].strip()

    variant_section = False
    for line in lines:
        if "terminology variant" in line.lower() or "known variants" in line.lower():
            variant_section = True
            continue
        if variant_section and line.startswith("#"):
            variant_section = False
            continue
        # PATCHED: parentheses fix operator precedence
        if variant_section and (line.startswith("- ") or line.startswith("| ")):
            matches = re.findall(r"`([^`]+)`|\"([^\"]+)\"|\*\*([^*]+)\*\*", line)
            for groups in matches:
                variant = next((g for g in groups if g), None)
                if variant and variant not in entity["variants"]:
                    entity["variants"].append(variant)

    source_section = False
    for line in lines:
        if "source notes" in line.lower():
            source_section = True
            continue
        if source_section:
            if "first established" in line.lower() or "primary:" in line.lower():
                entity["first_source"] = line.split(":", 1)[-1].strip()
                break
            if line.startswith("#"):
                break

    return entity


def build_registry() -> int:
    print("[registry] Scanning wiki pages...")
    entities = []
    for entity_dir in ENTITY_DIRS:
        dir_path = WIKI_PATH / entity_dir
        if not dir_path.exists():
            continue
        for page in sorted(dir_path.glob("*.md")):
            e = parse_page(page)
            entities.append(e)
            print(f"  found: {e['type']:<15} {e['name']}")

    if not entities:
        print("[registry] No entity pages found yet.")
        return 0

    by_type = {}
    for e in entities:
        by_type.setdefault(e["type"].lower(), []).append(e)

    lines = [
        "# MrLore Entity Registry", "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Total entities: {len(entities)}", "",
        "Authoritative name map. Consult before creating new pages.", "",
        "---", "",
    ]

    for entity_type in ENTITY_DIRS:
        if entity_type not in by_type:
            continue
        group = by_type[entity_type]
        lines += [
            f"## {entity_type.title()}", "",
            "| Canonical Name | Canon State | Variants | First Source | Page |",
            "|----------------|-------------|----------|--------------|------|",
        ]
        for e in sorted(group, key=lambda x: x["name"]):
            variants = ", ".join(e["variants"]) if e["variants"] else "—"
            lines.append(f"| {e['name']} | {e['canon_state']} | {variants} | {e['first_source'] or '—'} | {e['file']} |")
        lines.append("")

    all_variants: dict = {}
    for e in entities:
        for v in e["variants"]:
            all_variants.setdefault(v.lower(), []).append(e["name"])
    collisions = {v: n for v, n in all_variants.items() if len(n) > 1}

    if collisions:
        lines += ["## Variant Collisions", "", "Variant names mapping to more than one entity:", ""]
        for v, names in sorted(collisions.items()):
            lines.append(f"- `{v}` → {', '.join(names)}")
        lines.append("")

    REGISTRY_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[registry] Written to {REGISTRY_PATH}")
    print(f"[registry] {len(entities)} entities registered")
    if collisions:
        print(f"[registry] WARNING: {len(collisions)} variant collision(s) detected")
    print("[registry] OK")
    return 0


def check_registry() -> int:
    if not REGISTRY_PATH.exists():
        print("[registry] No registry found. Run without --check to build it.")
        return 1
    registry_text = REGISTRY_PATH.read_text(encoding="utf-8")
    issues = []
    for entity_dir in ENTITY_DIRS:
        dir_path = WIKI_PATH / entity_dir
        if not dir_path.exists():
            continue
        for page in sorted(dir_path.glob("*.md")):
            rel = str(page.relative_to(MRLORE_ROOT))
            if rel not in registry_text:
                issues.append(f"page not in registry: {rel}")
    if issues:
        print("[registry] CHECK FAILED")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("[registry] CHECK OK")
    return 0


def main() -> int:
    if "--check" in sys.argv:
        return check_registry()
    return build_registry()

if __name__ == "__main__":
    sys.exit(main())
