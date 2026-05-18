#!/usr/bin/env python3
"""
TASK 6.4B: Generate wiki stubs from candidate list.
Reads latest candidates log, creates schema-compliant stub pages.
Routes phrases to terms/, single tokens via suffix heuristics.
Rebuilds registry automatically. Strictly skips existing pages.
Deterministic. --apply gated. EXIT 0/2 enforced.
"""
import os
import sys
import glob
import re
import subprocess
from datetime import date

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
LOGS_DIR = os.path.join(BASE_DIR, "logs")
BUILD_SCRIPT = os.path.join(BASE_DIR, "tools", "build_registry.py")

# Deterministic routing heuristics
LOCATION_SUFFIXES = {"kingdom", "city", "ridge", "forest", "spire", "gate", "tower", "valley", "mountain", "shore", "island", "canyon", "desert", "sea", "ocean", "realm", "zone"}
FACTION_SUFFIXES = {"keepers", "federation", "guard", "legion", "order", "circle", "brotherhood", "alliance", "guild", "council", "empire", "clan", "house", "dynasty", "cult", "syndicate", "faction"}
SYSTEM_SUFFIXES = {"pattern", "web", "field", "wave", "matrix", "grid", "array", "sequence", "network", "protocol", "resonance", "current", "pulse", "matrix", "weave"}

def find_latest_candidates():
    files = sorted(glob.glob(os.path.join(LOGS_DIR, "candidates_*.txt")))
    return files[-1] if files else None

def route_token(token, is_phrase):
    """Deterministically assign entity type and directory."""
    t = token.lower().strip()
    if is_phrase:
        return "term", "wiki/terms/"
    
    # Check suffixes
    for suf in LOCATION_SUFFIXES:
        if t.endswith(suf): return "location", "wiki/locations/"
    for suf in FACTION_SUFFIXES:
        if t.endswith(suf): return "faction", "wiki/factions/"
    for suf in SYSTEM_SUFFIXES:
        if t.endswith(suf): return "system", "wiki/systems/"
        
    return "character", "wiki/characters/"

def generate_stub(name, entity_type, freq):
    """Create a schema-compliant stub page. Returns True if written, False if skipped."""
    entity_type, rel_dir = route_token(name, " " in name)
    dir_path = os.path.join(BASE_DIR, rel_dir)
    os.makedirs(dir_path, exist_ok=True)
    
    # Sanitize filename
    filename = name.replace(" ", "_").replace("'", "").replace(",", "").replace("(", "").replace(")", "").strip(".")
    if not filename: filename = "unnamed_candidate"
    filepath = os.path.join(dir_path, f"{filename}.md")
    
    # Skip existing
    if os.path.exists(filepath):
        return False
        
    today = date.today().isoformat()
    type_display = entity_type.title()
    
    # MRLORE_SCHEMA compliant template (Section 8/9/10)
    content = f"""---
type: {entity_type}
status: candidate
canon_state: provisional
last_updated: {today}
source_count: {freq}
tags: [auto_generated, candidate_extract_6_4B]
---
# {name}

Type: {type_display}  
Status: candidate  
Canon State: provisional  
Last Updated: {today}

## Canon Summary
Stub: Auto-generated from recurring candidate extraction. Awaiting human review, arc placement, and explicit source citation.

## Identity and Nature
Stub: Pending behavioral/worldbuilding definition.

## Historical Role
Stub: Timeline and narrative function unresolved.

## Source Notes
Detected in {freq} chapter files. Exact line references and quotes are logged in the candidate extraction run.

## Unresolved Questions
- [ ] Confirm entity type and canonical status
- [ ] Verify arc placement and narrative function
- [ ] Add explicit source citations and behavioral context
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return True

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate wiki stubs from candidate list")
    parser.add_argument("--apply", action="store_true", required=True, help="Write stubs to wiki/. Rebuilds registry.")
    args = parser.parse_args()
    
    log_path = find_latest_candidates()
    if not log_path:
        print("ERROR: No candidate logs found in logs/.", file=sys.stderr)
        sys.exit(2)
        
    print(f"[INPUT] Reading candidates from: {os.path.relpath(log_path, BASE_DIR)}")
    
    created = 0
    skipped = 0
    
    # Parse candidates log
    pattern = re.compile(r'^\[(PHRASE|TOKEN)\]\s+(.+?)\s+\|\s+(\d+)\s+files')
    
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            match = pattern.match(line)
            if not match:
                continue
                
            label = match.group(1)
            name = match.group(2).strip()
            freq = int(match.group(3))
            
            is_phrase = (label == "PHRASE")
            if generate_stub(name, is_phrase, freq):
                created += 1
            else:
                skipped += 1
                
    print(f"[STUBS] {created} pages created. {skipped} skipped (already exist).")
    
    if created > 0:
        print("[REGISTRY] Rebuilding registry from updated wiki surface...")
        try:
            result = subprocess.run(
                [sys.executable, BUILD_SCRIPT],
                capture_output=True,
                text=True,
                check=True
            )
            print(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Registry rebuild failed:\n{e.stderr}", file=sys.stderr)
            sys.exit(2)
    else:
        print("[REGISTRY] No new stubs. Skipping rebuild.")
        
    print("[DONE] Stub generation complete. EXIT 0")
    sys.exit(0)

if __name__ == "__main__":
    main()