#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
import re
import sys

MRLORE_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT = MRLORE_ROOT.parent
REPORT_DIR = MRLORE_ROOT / "logs"

EXCLUDED_DIRS = {
    ".git",
    ".obsidian",
    "_mrlore",
    "__pycache__",
    ".trash",
}

SOURCE_EXTS = {".md", ".txt", ".zw", ".json"}

WATCH_TERMS = [
    "Nephoretti",
    "Neferati",
    "Nephrati",
    "Nehereti",
    "Aaon Keepers",
    "Aeon Keepers",
    "Vrill",
    "Tiamat",
    "Nibiru",
    "Anunnaki",
    "Graviton",
    "Gravitons",
    "Void Spire",
    "Zaryonic",
    "Vale",
    "Zephyr",
    "Torrhen",
    "Tran",
    "Keen",
    "Thang",
    "Rongtai",
    "Geralt",
    "Mr GPT",
    "Enkialu",
    "Dingirash",
    "Viên",
]

def is_excluded(path: Path) -> bool:
    try:
        rel_parts = set(path.relative_to(VAULT_ROOT).parts)
    except ValueError:
        return True
    return bool(rel_parts & EXCLUDED_DIRS)

def classify(path: Path) -> str:
    rel = str(path.relative_to(VAULT_ROOT)).lower()
    name = path.name.lower()

    if path.suffix == ".json":
        return "json_data"
    if path.suffix == ".zw":
        return "zw_source"
    if "book_" in rel and re.search(r"/\d{3,4}[_-]", rel):
        return "chapter"
    if "chapter" in name:
        return "chapter_candidate"
    if "canon" in name:
        return "canon_reference"
    if "timeline" in name:
        return "timeline_reference"
    if "lore" in name:
        return "lore_reference"
    if "manifest" in name:
        return "manifest"
    return "loose_note"

def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    sources = []
    for path in VAULT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if is_excluded(path):
            continue
        if path.suffix.lower() not in SOURCE_EXTS:
            continue
        sources.append(path)

    by_ext = Counter(p.suffix.lower() for p in sources)
    by_class = Counter(classify(p) for p in sources)

    huge = []
    empty = []
    duplicates_by_name = defaultdict(list)
    watch_hits = defaultdict(list)

    for path in sources:
        rel = str(path.relative_to(VAULT_ROOT))
        duplicates_by_name[path.name.lower()].append(rel)

        text = read_text(path)
        words = len(text.split())

        if words == 0:
            empty.append(rel)
        if words > 12000:
            huge.append((rel, words))

        for term in WATCH_TERMS:
            if term.lower() in text.lower():
                watch_hits[term].append(rel)

    duplicate_names = {
        name: paths for name, paths in duplicates_by_name.items()
        if len(paths) > 1
    }

    now = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = REPORT_DIR / f"vault_audit_{now}.md"

    lines = []
    lines.append("# MrLore Vault Audit")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Vault Root: `{VAULT_ROOT}`")
    lines.append(f"MrLore Root: `{MRLORE_ROOT}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total candidate sources: {len(sources)}")
    lines.append(f"- Empty files: {len(empty)}")
    lines.append(f"- Huge files over 12,000 words: {len(huge)}")
    lines.append(f"- Duplicate basenames: {len(duplicate_names)}")
    lines.append("")
    lines.append("## By Extension")
    lines.append("")
    for ext, count in sorted(by_ext.items()):
        lines.append(f"- `{ext}`: {count}")
    lines.append("")
    lines.append("## By Classification")
    lines.append("")
    for cls, count in sorted(by_class.items()):
        lines.append(f"- `{cls}`: {count}")
    lines.append("")
    lines.append("## Likely Chapters")
    lines.append("")
    for path in sorted(sources):
        if classify(path) in {"chapter", "chapter_candidate"}:
            lines.append(f"- `{path.relative_to(VAULT_ROOT)}`")
    lines.append("")
    lines.append("## Canon / Lore References")
    lines.append("")
    for path in sorted(sources):
        if classify(path) in {"canon_reference", "lore_reference", "timeline_reference"}:
            lines.append(f"- `{path.relative_to(VAULT_ROOT)}`")
    lines.append("")
    lines.append("## ZW Sources")
    lines.append("")
    for path in sorted(sources):
        if classify(path) == "zw_source":
            lines.append(f"- `{path.relative_to(VAULT_ROOT)}`")
    lines.append("")
    lines.append("## Huge Files")
    lines.append("")
    if huge:
        for rel, words in sorted(huge, key=lambda x: x[1], reverse=True):
            lines.append(f"- `{rel}` — {words} words")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Empty Files")
    lines.append("")
    if empty:
        for rel in sorted(empty):
            lines.append(f"- `{rel}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Duplicate Basenames")
    lines.append("")
    if duplicate_names:
        for name, paths in sorted(duplicate_names.items()):
            lines.append(f"### `{name}`")
            for rel in sorted(paths):
                lines.append(f"- `{rel}`")
            lines.append("")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Watch Term Hits")
    lines.append("")
    for term in WATCH_TERMS:
        paths = watch_hits.get(term, [])
        lines.append(f"### {term}")
        lines.append(f"Hits: {len(paths)}")
        for rel in sorted(paths)[:40]:
            lines.append(f"- `{rel}`")
        if len(paths) > 40:
            lines.append(f"- ... {len(paths) - 40} more")
        lines.append("")
    lines.append("## Stress Test Conclusion")
    lines.append("")
    lines.append("This audit does not ingest or modify continuity pages. It maps the vault so MrLore can decide safe ingest order.")
    lines.append("")
    lines.append("Recommended next step:")
    lines.append("1. Ingest canonical Book 1 chapters in order.")
    lines.append("2. Ingest canon/reference files separately.")
    lines.append("3. Do not batch-ingest all loose notes until duplicate and terminology drift is reviewed.")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("[vault_audit] OK")
    print(f"[vault_audit] Sources scanned: {len(sources)}")
    print(f"[vault_audit] Report: {report_path}")
    print()
    print("Top classifications:")
    for cls, count in by_class.most_common():
        print(f"  {cls}: {count}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
