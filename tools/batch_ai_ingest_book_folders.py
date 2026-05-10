#!/usr/bin/env python3
"""
MrLore v2 — Batch AI Ingest for Book Folders Only (JSON mode)
- Scans top-level book directories
- Processes only files directly inside (no recursion)
- Uses Ollama with JSON format for structured extraction
- Saves raw JSON to _mrlore/wiki/json/
- Renders markdown summary from template
- Creates entity stubs filtering invalid names
- Handles JSON failures with debug output
"""

import sys
import os
import re
import json
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# === CONFIGURATION ===========================================
MRLORE_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT = MRLORE_ROOT.parent

RAW_CHAPTERS = MRLORE_ROOT / "raw" / "chapters"
WIKI_SOURCES = MRLORE_ROOT / "wiki" / "sources"
WIKI_JSON = MRLORE_ROOT / "wiki" / "json"          # NEW: store raw JSON per chapter
LOG_PATH = MRLORE_ROOT / "wiki" / "log.md"

# Entity directories (same as original MrLore)
ENTITY_DIRS = {
    "characters": "Characters",
    "locations": "Locations",
    "factions": "Factions",
    "species": "Species",
    "terms": "Terms",
    "arcs": "Arcs",
    "events": "Events",
    "artifacts": "Artifacts",
    "systems": "Systems",
    "timelines": "Timelines",
}

# LLM backend: only Ollama for local JSON mode
OLLAMA_MODEL = "qwen2.5:7b-instruct"
OLLAMA_URL = "http://localhost:11434/api/generate"

SOURCE_EXTS = {".md", ".txt"}

# === HELPER FUNCTIONS ========================================

def slug_path(file_path: Path, vault_root: Path) -> str:
    """Create a unique slug from the relative path."""
    rel = file_path.relative_to(vault_root)
    return str(rel).replace("/", "_").replace(" ", "_")

def is_invalid_entity_name(name: str) -> bool:
    """Filter out generic placeholders and obviously invalid names."""
    name_lower = name.lower().strip()
    invalid = {
        "", "list", "none", "n/a", "unknown", "no_data",
        "to be determined", "tbd", "?", "??", "...", "—",
        "characters", "locations", "factions", "species", "terms",
        "events", "arcs", "timelines"
    }
    if name_lower in invalid:
        return True
    if len(name) < 2:
        return True
    if name_lower.startswith("[") and name_lower.endswith("]"):
        return True
    return False

def call_ollama_json(prompt: str, timeout_sec: int = 600) -> dict:
    """Send prompt to Ollama with JSON format. Return parsed dict or raise."""
    import requests
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",          # force JSON output
        "temperature": 0.2,
        "options": {
            "num_predict": 4096    # enough for a full chapter summary
        }
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=timeout_sec)
    if response.status_code != 200:
        raise Exception(f"Ollama HTTP {response.status_code}: {response.text}")
    data = response.json()
    raw_output = data.get("response", "")
    # Attempt to parse JSON
    try:
        parsed = json.loads(raw_output)
        return parsed
    except json.JSONDecodeError as e:
        # Save raw output for debugging
        raise Exception(f"JSON parse error: {e}\nRaw output:\n{raw_output}")

def render_markdown_summary(meta: dict, json_data: dict, vault_rel: str, raw_slug: str) -> str:
    """Render the final source summary markdown from the JSON data."""
    today = datetime.now().strftime("%Y-%m-%d")
    title = json_data.get("title", meta.get("stem", "Untitled"))
    # Build sections
    lines = [
        f"# Source Summary — {title}",
        "",
        f"Type: Source Summary",
        f"Canon State: unreviewed",
        f"Ingested: {today}",
        f"Vault Path: {vault_rel}",
        f"Raw Copy: raw/chapters/{raw_slug}",
        "",
        "## What This Source Contains",
        "",
        json_data.get("summary", "No summary provided."),
        "",
        "## Entities Mentioned",
        ""
    ]
    for category, display_name in [
        ("characters", "Characters"),
        ("locations", "Locations"),
        ("factions", "Factions / Species"),
        ("events", "Events"),
        ("terms", "Terms / Concepts"),
    ]:
        items = json_data.get("entities", {}).get(category, [])
        if items:
            lines.append(f"### {display_name}")
            lines.append("")
            for item in items:
                if not is_invalid_entity_name(item):
                    lines.append(f"- {item}")
            lines.append("")
    # Arc connections
    lines.append("## Arc Connections")
    lines.append("")
    arcs = json_data.get("arc_connections", [])
    if arcs:
        for arc in arcs:
            lines.append(f"- {arc}")
    else:
        lines.append("- None yet")
    lines.append("")
    # Timeline notes
    lines.append("## Timeline Notes")
    lines.append("")
    notes = json_data.get("timeline_notes", [])
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- None")
    lines.append("")
    # Contradictions
    lines.append("## Contradictions Detected")
    lines.append("")
    contr = json_data.get("contradictions", [])
    if contr:
        for c in contr:
            lines.append(f"- {c}")
    else:
        lines.append("- None yet")
    lines.append("")
    # Unresolved questions
    lines.append("## Unresolved Questions Raised")
    lines.append("")
    quest = json_data.get("unresolved_questions", [])
    if quest:
        for q in quest:
            lines.append(f"- {q}")
    else:
        lines.append("- None")
    lines.append("")
    # Pages to create
    lines.append("## Pages to Create or Update")
    lines.append("")
    pages = json_data.get("pages_to_create", [])
    if pages:
        for p in pages:
            lines.append(f"- {p}")
    else:
        lines.append("- None")
    lines.append("")
    # Ingest status checklist
    lines.append("## Ingest Status")
    lines.append("")
    lines.append("- [x] Source summary written")
    lines.append("- [ ] Entity pages created/updated")
    lines.append("- [ ] Arc pages updated")
    lines.append("- [ ] Timeline pages updated")
    lines.append("- [ ] Contradictions filed")
    lines.append("- [ ] Unresolved questions filed")
    lines.append("- [ ] index.md updated")
    lines.append("- [x] log.md appended")
    lines.append("")
    return "\n".join(lines)

def create_entity_stub(entity_type: str, name: str, source_summary_path: str):
    """Create a wiki stub only if name is valid and page doesn't exist."""
    if is_invalid_entity_name(name):
        return
    dir_path = MRLORE_ROOT / "wiki" / entity_type
    dir_path.mkdir(parents=True, exist_ok=True)
    safe_name = name.replace(" ", "_")
    page_path = dir_path / f"{safe_name}.md"
    if page_path.exists():
        return
    stub = f"""# {name}

Type: {entity_type.title()}
Canon State: provisional
First Source: {source_summary_path}
Last Updated: {datetime.now().strftime("%Y-%m-%d")}

---

## Current Continuity State

<!-- Fill manually after review -->

## Canon Summary

<!-- To be written -->

## Source Notes

- Established in {source_summary_path}
"""
    page_path.write_text(stub, encoding="utf-8")
    print(f"    Created stub: {page_path.relative_to(MRLORE_ROOT)}")

def process_source_file(source_path: Path):
    """Copy source, call Ollama JSON, save outputs, create stubs."""
    print(f"\nProcessing: {source_path.relative_to(VAULT_ROOT)}")

    # 1. Copy to raw/chapters/
    dest_slug = slug_path(source_path, VAULT_ROOT)
    dest_raw = RAW_CHAPTERS / dest_slug
    if not dest_raw.exists():
        shutil.copy2(source_path, dest_raw)
        print(f"  Copied to raw/chapters/{dest_slug}")
    else:
        print(f"  Already in raw/chapters/{dest_slug}")

    # 2. Read source text
    text = source_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print("  WARNING: empty file, skipping.")
        return

    # 3. Build JSON prompt
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""You are MrLore, a lore extraction system. Given the chapter text below, output a JSON object with the following fields:

{{
  "title": "brief title of the chapter (use the filename if unclear)",
  "summary": "detailed paragraph summary of the chapter's events and lore",
  "entities": {{
    "characters": ["list of character names"],
    "locations": ["list of locations"],
    "factions": ["list of factions or species"],
    "events": ["list of major events"],
    "terms": ["list of important terms/concepts"]
  }},
  "arc_connections": ["list of arcs this chapter touches"],
  "timeline_notes": ["any dates, eras, or timeline references"],
  "contradictions": ["any conflicts with established lore", "or empty array"],
  "unresolved_questions": ["new mysteries or gaps"],
  "pages_to_create": ["wiki/... paths for new entity pages"]
}}

Do not add any extra text outside the JSON. Use empty arrays if nothing found. Keep entity names short (no markdown links).

Now here is the chapter text:

{text}
"""
    # 4. Call Ollama with JSON mode
    try:
        json_data = call_ollama_json(prompt, timeout_sec=600)
    except Exception as e:
        print(f"  ❌ LLM JSON error: {e}")
        # Save raw error response for debugging
        debug_dir = MRLORE_ROOT / "logs" / "failed_ingest"
        debug_dir.mkdir(parents=True, exist_ok=True)
        debug_file = debug_dir / f"{dest_slug}_error.txt"
        debug_file.write_text(f"Error: {e}\n\nPrompt:\n{prompt}", encoding="utf-8")
        print(f"  Debug info saved to {debug_file}")
        return

    # 5. Save raw JSON to wiki/json/
    WIKI_JSON.mkdir(parents=True, exist_ok=True)
    json_path = WIKI_JSON / f"{dest_slug.replace(source_path.suffix, '')}.json"
    json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    print(f"  Saved JSON to {json_path.relative_to(MRLORE_ROOT)}")

    # 6. Render markdown summary from template
    vault_rel = str(source_path.relative_to(VAULT_ROOT))
    summary_text = render_markdown_summary(
        meta={"stem": source_path.stem},
        json_data=json_data,
        vault_rel=vault_rel,
        raw_slug=dest_slug
    )
    summary_path = WIKI_SOURCES / f"{dest_slug.replace(source_path.suffix, '')}.md"
    summary_path.write_text(summary_text, encoding="utf-8")
    print(f"  Created summary: {summary_path.relative_to(MRLORE_ROOT)}")

    # 7. Create entity stubs from JSON (skip invalid names)
    total_stubs = 0
    entities_dict = json_data.get("entities", {})
    for etype, names in entities_dict.items():
        if etype not in ENTITY_DIRS:
            continue
        for name in names:
            if not is_invalid_entity_name(name):
                create_entity_stub(etype, name, str(summary_path.relative_to(MRLORE_ROOT)))
                total_stubs += 1
    print(f"  Extracted entities: {total_stubs} stubs created (or already existed)")

    # 8. Append to log.md
    log_entry = f"""
## [{datetime.now().strftime("%Y-%m-%d")}] AI ingest | {source_path.stem}

Source: {vault_rel}
Summary: {summary_path.relative_to(MRLORE_ROOT)}
JSON: {json_path.relative_to(MRLORE_ROOT)}
Entities stubbed: {total_stubs}
"""
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(log_entry)

def discover_book_sources():
    """Return list of source files from any 'book*' directory anywhere under VAULT_ROOT.

    Uses rglob so nested book dirs (e.g. 'Southern arc/Book 25 .../') are found.
    Only looks one level inside each matched book directory (not recursive within it).
    """
    sources = []
    seen_dirs: set = set()
    for item in VAULT_ROOT.rglob("*"):
        if not item.is_dir():
            continue
        if not item.name.lower().startswith("book"):
            continue
        if item in seen_dirs:
            continue
        seen_dirs.add(item)
        for file in item.iterdir():
            if file.is_file() and file.suffix.lower() in SOURCE_EXTS:
                sources.append(file)
    return sources

def main():
    # Ensure directories exist
    RAW_CHAPTERS.mkdir(parents=True, exist_ok=True)
    WIKI_SOURCES.mkdir(parents=True, exist_ok=True)
    WIKI_JSON.mkdir(parents=True, exist_ok=True)

    sources = discover_book_sources()
    if not sources:
        print("No source files found in any top-level 'book*' directory.")
        print("Checked in:", VAULT_ROOT)
        return 1

    print(f"Found {len(sources)} source files in book directories.\n")
    # Confirm continuation
    # input("Press Enter to start processing (or Ctrl+C to cancel)...")

    for idx, src in enumerate(sources, 1):
        print(f"\n=== [{idx}/{len(sources)}] ===")
        process_source_file(src)
        time.sleep(10)   # generous delay between chapters

    # Rebuild registry
    print("\nRebuilding entity registry...")
    subprocess.run([sys.executable, str(MRLORE_ROOT / "tools" / "build_registry.py")], check=True)

    print("\n✅ Batch AI ingest complete.")
    print("Next: Review auto-generated summaries and entity stubs.")
    print("Run 'python3 tools/lint_wiki.py' to catch any issues.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
