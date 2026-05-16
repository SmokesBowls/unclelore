#!/usr/bin/env python3
"""
TASK 7.5A-R1: Registry context contains noise entities.
Filters LLM anchor context to exclude common words, metadata artifacts,
and non-structural registry entries. Only passes canonical entities from
core wiki directories (characters, factions, species, locations, systems).
Dry-run and apply modes preserved. EXIT 0/2 enforced.
"""
import argparse
import json
import os
import re
import sys
import time
import glob
import subprocess
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install via: pip install requests", file=sys.stderr)
    sys.exit(1)

BASE_DIR = "/home/mytruelove/Downloads/obsidianburdenNov25/_mrlore"
REGISTRY_PATH = os.path.join(BASE_DIR, "wiki/registry.md")
SCHEMA_PATH = os.path.join(BASE_DIR, "MRLORE_SCHEMA.md")
CHAPTERS_DIR = os.path.join(BASE_DIR, "raw/chapters")
OLLAMA_URL = "http://localhost:11434/api/generate"

# R1 FIX: Context filtering sets
CONTEXT_EXCLUSIONS = {
    "The", "A", "An", "And", "Or", "But", "In", "On", "At", "To", "For", "With", "By", "From", "Up",
    "About", "Into", "Over", "After", "I", "Me", "My", "We", "Us", "Our", "You", "Your", "He", "Him",
    "His", "She", "Her", "It", "Its", "They", "Them", "Their", "What", "Which", "Who", "Whom", "This",
    "That", "These", "Those", "Is", "Are", "Was", "Were", "Be", "Been", "Being", "Have", "Has", "Had",
    "Do", "Does", "Did", "Will", "Would", "Could", "Should", "May", "Might", "Must", "Shall", "Can",
    "Need", "Dare", "Ought", "Used", "Of", "If", "So", "As", "No", "Not", "Of",
    "Red", "Blue", "Green", "White", "Crimson", "Violet", "Golden", "Silver", "Black", "Purple", "Dark",
    "Light", "First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth",
    "ACT", "ARC", "STATUS", "TIME", "FOCUS", "THREADS", "POV", "PERIOD", "REGION", "MOVEMENT", "NOTE",
    "CHAPTER", "BOOK", "PART", "SECTION", "VOLUME", "PAGE", "FILE", "Day", "Year", "Month", "Night",
    "Morning", "Dawn", "Above", "Below", "Across", "Against", "Along", "Around", "Behind", "Before",
    "Between", "Beyond", "Down", "During", "Else", "Even", "Every", "Few", "Here", "How", "Just", "Last",
    "Let", "Like", "More", "Most", "Much", "Never", "None", "Only", "Other", "Part", "Place", "Point",
    "Rather", "Same", "Since", "Some", "Such", "Than", "There", "Think", "Through", "Under", "Until",
    "Use", "Used", "Using", "Very", "Way", "Well", "When", "Where", "While", "Why", "Without", "Yet",
    "Acknowledged", "Activation", "Agricultural", "Aetheric", "Agreed", "Aftermath", "Alignment",
    "Almost", "Already", "Although", "Always", "Amidst", "Among", "Amount", "Ancient", "Another",
    "Anytime", "Anything", "Anyway", "Anywhere", "Approaching", "Around", "Arrival", "Arrived",
    "Ascend", "Ascendant", "Ascension", "Assembly", "Assigned", "Assignment", "Assistance", "Attain",
    "Attained", "Attaining", "Attempt", "Attempted", "Attention", "Attuned", "Attribute", "Attributes"
}
ALLOWED_CONTEXT_DIRS = {"/characters/", "/factions/", "/species/", "/locations/", "/systems/"}

VALID_ENTITY_TYPES = {"character", "faction", "species", "location", "system", "artifact", "event", "arc", "term", "timeline"}

def load_registry_entities(limit=None):
    """Load filtered canonical names from registry.md for LLM context anchoring."""
    entities = []
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[WARN] Registry load failed: {e}", file=sys.stderr)
        return entities

    header_found = False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"): continue
        parts = [p.strip() for p in stripped.strip("|").split("|")]
        if "Canonical Name" in parts:
            header_found = True; continue
        if not header_found: continue
        if not parts or "---" in parts[0]: continue
        
        canon = parts[0].strip()
        if not canon: continue
            
        # R1 Filter 1: Minimum length
        if len(canon) < 3: continue
        
        # R1 Filter 2: Exclude common/metadata noise
        canon_lower = canon.lower()
        if canon_lower in {e.lower() for e in CONTEXT_EXCLUSIONS} or canon.upper() in {e.upper() for e in CONTEXT_EXCLUSIONS}:
            continue
            
        # R1 Filter 3: Only core ontology directories (exclude terms/arcs/timelines for context)
        page_col = parts[4].strip().lower() if len(parts) > 4 else ""
        if not any(d in page_col for d in ALLOWED_CONTEXT_DIRS):
            continue
            
        # Deduplicate & append
        if canon_lower not in [e.lower() for e in entities]:
            entities.append(canon)
            
        if limit and len(entities) >= limit:
            break
            
    return entities

def load_schema_contracts():
    """Extract required frontmatter fields from MRLORE_SCHEMA.md."""
    required = {
        "frontmatter": ["type", "status", "canon_state", "last_updated", "audit_only"],
        "sections": ["Canon Summary", "Identity and Nature", "Historical Role", "Source Notes", "Unresolved Questions"]
    }
    return required

def build_prompt(chunk_text, entity_context, schema_contracts):
    """Construct deterministic, schema-enforcing prompt for one text chunk."""
    entity_list = "\n".join(f"- {e}" for e in entity_context)

    return f"""You are MrLore, a governed narrative co-author for the Chronicles universe.
Your task: Read the chapter excerpt and extract structured entity data that conforms to MRLORE_SCHEMA.

KNOWN ENTITIES (anchor your extraction to these; do not invent new ones unless they recur 3+ times):
{entity_list}

REQUIRED OUTPUT FORMAT (strict JSON, no markdown):
{{
  "entities": [
    {{
      "name": "Canonical entity name (use registry form if known)",
      "type": "character|faction|species|location|system|artifact|event|arc|term|timeline",
      "first_appearance": "relative chapter reference",
      "summary": "One-sentence canon-aligned description",
      "brief_description": "2-3 sentences describing this entity from the excerpt. Include physical traits, affiliation, or defining behaviour visible in the text.",
      "role": "What function this entity serves in this chapter (protagonist, antagonist, mentor, setting, MacGuffin, etc.).",
      "confidence": "high|medium|low — how clearly is this entity identified in the excerpt?",
      "raw_quote": "Shortest verbatim sentence or phrase from the excerpt that best supports this entity's presence.",
      "summary_observation": "1-2 sentences of provisional lore about this entity derived directly from the excerpt.",
      "relationship_observations": ["Free-text observations about how this entity relates to others in the excerpt, e.g. 'Lyaris coordinates with Theron on temporal strategy'."],
      "timeline_observation": "Any temporal anchor visible in the excerpt for this entity, e.g. '3,417 years after Marduk-Tiamat collision'. Empty string if none.",
      "relationships_mentioned": ["Other entity names that appear alongside this entity in meaningful context."],
      "relationships": [
        {{"predicate": "member_of|allied_with|opposes|located_in", "target": "EntityName"}}
      ],
      "source_citations": ["file:line references"]
    }}
  ],
  "world_state_updates": [
    {{
      "descriptor": "state change description",
      "scope": "global|factional|personal",
      "temporal_anchor": "chapter reference or timeline marker"
    }}
  ]
}}

CONSTRAINTS:
- Use ONLY entity names from the known list above, or propose new ones ONLY if they appear 3+ times in the excerpt.
- Never output markdown, commentary, or non-JSON text.
- If no entities are found, return {{"entities": [], "world_state_updates": []}}.
- All observations must be grounded in the excerpt text; do not speculate beyond what is written.
- raw_quote must be a verbatim substring of the excerpt (max 120 characters).
- confidence must reflect how unambiguously the entity is named or described in the excerpt.

CHAPTER EXCERPT:
{chunk_text}

Respond with valid JSON only:"""


def chunk_text(text, max_words=2000):
    """Split text into chunks of at most max_words words, breaking on blank lines.

    Paragraph-boundary splitting keeps sentences intact and avoids sending
    mid-sentence context to the model. If a single paragraph exceeds max_words
    it is emitted as its own chunk.
    """
    paragraphs = re.split(r'\n{2,}', text.strip())
    chunks = []
    current_words = []
    current_count = 0

    for para in paragraphs:
        para_words = para.split()
        if not para_words:
            continue
        if current_count + len(para_words) > max_words and current_words:
            chunks.append(" ".join(current_words))
            current_words = para_words
            current_count = len(para_words)
        else:
            current_words.extend(para_words)
            current_count += len(para_words)

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks if chunks else [text]


def call_ollama(prompt, model, timeout, max_retries=3):
    """Robust Ollama client with exponential backoff and JSON validation."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "top_p": 0.9}
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
            response.raise_for_status()
            result = response.json()
            content = result.get("response", "")
            
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                parsed = json.loads(json_match.group())
                return parsed
            else:
                print(f"[WARN] Attempt {attempt+1}: No JSON found in response", file=sys.stderr)
                
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Attempt {attempt+1}: Ollama request failed: {e}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"[WARN] Attempt {attempt+1}: JSON parse failed: {e}", file=sys.stderr)
            
        if attempt < max_retries - 1:
            wait = 2 ** attempt
            print(f"[RETRY] Waiting {wait}s before next attempt...", file=sys.stderr)
            time.sleep(wait)
            
    return None

def validate_entity_record(rec, schema_contracts):
    """Check entity record against MRLORE_SCHEMA requirements."""
    errors = []
    if "name" not in rec or not rec["name"].strip():
        errors.append("Missing or empty 'name'")
    if "type" not in rec or rec["type"] not in VALID_ENTITY_TYPES:
        errors.append(f"Invalid type: '{rec.get('type')}'")
    if "summary" not in rec or len(rec["summary"]) < 10:
        errors.append("Summary too short or missing")
    return errors

def generate_stub(entity_rec, source_file, schema_contracts):
    """Generate schema-compliant stub page content, populated with LLM-extracted lore."""
    name = entity_rec["name"]
    entity_type = entity_rec["type"]
    today = date.today().isoformat()

    filename = re.sub(r'[^a-zA-Z0-9_\-]', '_', name).strip("_")
    if not filename:
        filename = "unnamed_entity"

    dir_map = {
        "character": "wiki/characters/", "faction": "wiki/factions/", "species": "wiki/species/",
        "location": "wiki/locations/", "system": "wiki/systems/", "artifact": "wiki/artifacts/",
        "event": "wiki/events/", "arc": "wiki/arcs/", "term": "wiki/terms/", "timeline": "wiki/timelines/"
    }
    rel_dir = dir_map.get(entity_type, "wiki/terms/")

    # ── Identity and Nature: prefer brief_description / summary_observation ──
    brief_description = entity_rec.get("brief_description", "").strip()
    summary_obs = entity_rec.get("summary_observation", "").strip()
    identity_text = brief_description or summary_obs or "Stub: Pending behavioral/worldbuilding definition."

    # ── Relationships: structured predicates + free-text observations ─────────
    relationships = entity_rec.get("relationships", [])
    rel_lines_parts = []
    if relationships:
        rel_lines_parts.extend(f"- {r['predicate']}: {r['target']}" for r in relationships)
    rel_obs = entity_rec.get("relationship_observations", [])
    if rel_obs:
        rel_lines_parts.extend(f"- (provisional) {obs}" for obs in rel_obs)
    mentioned = entity_rec.get("relationships_mentioned", [])
    if mentioned:
        structured_targets = {r["target"].lower() for r in relationships}
        for m in mentioned:
            if m.lower() not in structured_targets:
                rel_lines_parts.append(f"- mentioned_alongside: {m}")
    rel_lines = "\n".join(rel_lines_parts) if rel_lines_parts else "Stub: Pending relationship extraction."

    # ── Historical Role: use role + timeline_observation ──────────────────────
    role = entity_rec.get("role", "").strip()
    tl_obs = entity_rec.get("timeline_observation", "").strip()
    role_parts = []
    if role:
        role_parts.append(role)
    if tl_obs:
        role_parts.append(f"Timeline anchor (provisional): {tl_obs}")
    historical_role_section = "\n".join(role_parts) if role_parts else "Stub: Timeline and narrative function unresolved."

    citations = entity_rec.get("source_citations", [])
    raw_quote = entity_rec.get("raw_quote", "").strip()
    cite_lines_parts = [f"- {c}" for c in citations] if citations else [f"- Auto-detected in {source_file}"]
    if raw_quote:
        cite_lines_parts.append(f'- Raw quote (provisional): "{raw_quote}"')
    cite_lines = "\n".join(cite_lines_parts)

    content = f"""---
type: {entity_type}
status: candidate
canon_state: provisional
last_updated: {today}
audit_only: true
tags: [auto_ingested, ollama_cockpit_7_5A]
---
# {name}

Type: {entity_type.title()}  
Status: candidate  
Canon State: provisional  
Last Updated: {today}

## Canon Summary
{entity_rec.get("summary", "Stub: Awaiting human review and explicit source citation.")}

## Core Identity
{identity_text}

## Behavioral Pattern
Stub: Under-pressure choices and recurring tendencies unverified.

## Emotional Trajectory
Stub: State changes across chapters unlogged.

## Relationships
{rel_lines}

## Timeline Position
{historical_role_section}

## Major Events
Stub: None cataloged.

## Contradictions / Drift
None detected.

## Source Notes
{cite_lines}

## Unresolved Questions
- [ ] Confirm canonical status and arc placement
- [ ] Verify behavioral context and relationship predicates
- [ ] Add explicit line-level citations from source chapters
"""
    return rel_dir, filename, content


# ── Section names used in Vale-style character wiki pages ────────────────────
_ENRICHABLE_SECTIONS = [
    "Current Continuity State",
    "Core Identity",
    "Behavioral Pattern",
    "Emotional Trajectory",
    "Relationships",
    "Timeline Position",
    "Major Events",
    "Source Notes",
    "Unresolved Questions",
    # cockpit-generated aliases
    "Canon Summary",
    "Identity and Nature",
    "Historical Role",
]


def enrich_existing_stub(filepath, entity_rec, source_file):
    """Surgically patch an existing wiki page with LLM-extracted lore.

    Rules:
    - Never touch Tier-0 prose (raw/chapters/).  filepath is always under wiki/.
    - Lines that begin with 'Stub:' are replaced when a matching observation exists.
    - Sections that already have real content get a provisional bullet appended.
    - Every appended line includes a source reference.
    - Nothing is marked canon-confirmed.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            original = f.read()
    except Exception as e:
        print(f"[WARN] Cannot read {filepath} for enrichment: {e}", file=sys.stderr)
        return False

    today = date.today().isoformat()
    source_ref = f"{source_file}"
    raw_quote   = entity_rec.get("raw_quote", "").strip()
    conf        = entity_rec.get("confidence", "low")
    summary_obs = entity_rec.get("summary_observation", "").strip()
    brief_desc  = entity_rec.get("brief_description", "").strip()
    role        = entity_rec.get("role", "").strip()
    tl_obs      = entity_rec.get("timeline_observation", "").strip()
    rel_obs     = entity_rec.get("relationship_observations", [])
    relationships = entity_rec.get("relationships", [])
    mentioned   = entity_rec.get("relationships_mentioned", [])

    # Build per-section injection content
    identity_text = brief_desc or summary_obs
    rel_bullets   = []
    if relationships:
        rel_bullets.extend(f"- (provisional, {conf}) {r['predicate']}: {r['target']} — source: {source_ref}" for r in relationships)
    if rel_obs:
        rel_bullets.extend(f"- (provisional, {conf}) {obs} — source: {source_ref}" for obs in rel_obs)
    if mentioned:
        existing_targets = {r["target"].lower() for r in relationships}
        for m in mentioned:
            if m.lower() not in existing_targets:
                rel_bullets.append(f"- (provisional, {conf}) mentioned_alongside: {m} — source: {source_ref}")

    cite_bullet_parts = [f"- (auto-ingest, {conf}) {source_ref}"]
    if raw_quote:
        cite_bullet_parts.append(f'  - Raw quote: "{raw_quote}"')
    cite_bullet = "\n".join(cite_bullet_parts)

    # Map section heading → what to inject
    section_injections = {
        "Current Continuity State": summary_obs or identity_text,
        "Core Identity":            identity_text,
        "Behavioral Pattern":       role,
        "Emotional Trajectory":     "",
        "Timeline Position":        tl_obs,
        "Major Events":             "",
        "Source Notes":             cite_bullet,
        # cockpit-generated aliases
        "Canon Summary":            entity_rec.get("summary", "").strip(),
        "Identity and Nature":      identity_text,
        "Historical Role":          (f"{role}\nTimeline anchor (provisional): {tl_obs}" if tl_obs else role),
        "Relationships":            "\n".join(rel_bullets) if rel_bullets else "",
    }

    lines = original.splitlines(keepends=True)
    out   = []
    i     = 0
    current_section = None
    changed = False

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n")

        # Detect ## section heading
        heading_match = re.match(r'^## (.+)$', stripped)
        if heading_match:
            current_section = heading_match.group(1).strip()
            out.append(line)
            i += 1
            continue

        # Check for bare Stub: line
        if stripped.startswith("Stub:") and current_section in section_injections:
            injection = section_injections[current_section]
            if injection:
                # Replace the stub line with the LLM observation
                out.append(f"{injection} *(provisional — {today})*\n")
                changed = True
                i += 1
                continue
            # No injection available — keep stub as-is

        # Append-mode: for Source Notes, always add our citation at end of section
        # This is handled below after section detection.
        out.append(line)
        i += 1

    # Second pass: append relationship bullets to Relationships section if it has real content
    # and didn't get stub-replaced above; similarly append cite to Source Notes.
    if rel_bullets or cite_bullet:
        out2  = []
        j     = 0
        cur_sec = None
        rel_appended  = False
        cite_appended = False

        while j < len(out):
            line2 = out[j]
            stripped2 = line2.rstrip("\n")
            hm = re.match(r'^## (.+)$', stripped2)
            if hm:
                # Before switching sections, decide if we need to append to the section
                # we're leaving
                if cur_sec == "Relationships" and rel_bullets and not rel_appended:
                    out2.append("\n".join(rel_bullets) + "\n")
                    rel_appended = True
                    changed = True
                if cur_sec == "Source Notes" and not cite_appended:
                    out2.append(cite_bullet + "\n")
                    cite_appended = True
                    changed = True
                cur_sec = hm.group(1).strip()

            out2.append(line2)
            j += 1

        # Handle case where Relationships / Source Notes is the last section
        if cur_sec == "Relationships" and rel_bullets and not rel_appended:
            out2.append("\n".join(rel_bullets) + "\n")
            changed = True
        if cur_sec == "Source Notes" and not cite_appended:
            out2.append(cite_bullet + "\n")
            changed = True

        out = out2

    if not changed:
        print(f"  [ENRICH] No applicable observations for {os.path.basename(filepath)}", file=sys.stderr)
        return False

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("".join(out))
        print(f"  [ENRICH] Updated {os.path.basename(filepath)}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"[WARN] Failed to write enriched stub {filepath}: {e}", file=sys.stderr)
        return False

def run_validation_tools():
    """Post-ingest: rebuild registry and lint STB."""
    print("[VALIDATION] Running build_registry.py...", file=sys.stderr)
    try:
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "tools", "build_registry.py")], check=True, capture_output=True)
        print("[VALIDATION] Registry rebuild complete.", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Registry rebuild failed: {e.stderr.decode()}", file=sys.stderr)
        return False
        
    print("[VALIDATION] Running stb_lint.py --dir stb/...", file=sys.stderr)
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(BASE_DIR, "tools", "stb_lint.py"), "--dir", "stb/"],
            capture_output=True, text=True
        )
        print(result.stdout, file=sys.stderr)
        if result.returncode != 0:
            print(f"[WARN] Lint reported issues (EXIT {result.returncode})", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] Lint execution failed: {e}", file=sys.stderr)
        
    return True

def main():
    parser = argparse.ArgumentParser(description="Governed Ollama Ingestion Cockpit")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Print prompts & predicted outputs. No Ollama calls, no writes.")
    group.add_argument("--apply", action="store_true", help="Execute ingestion with Ollama and write stubs.")
    parser.add_argument("--limit", type=int, default=None, help="Process only first N chapter files.")
    parser.add_argument("--model", type=str, default="qwen2.5:7b-instruct", help="Ollama model name.")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds.")
    parser.add_argument("--pacing", type=float, default=2.0, help="Seconds to wait between chapter processing.")
    args = parser.parse_args()
    
    if not os.path.exists(CHAPTERS_DIR):
        print("ERROR: raw/chapters/ directory not found.", file=sys.stderr)
        sys.exit(2)
        
    entities = load_registry_entities(limit=200)
    schema = load_schema_contracts()
    print(f"[INIT] Loaded {len(entities)} filtered registry entities for context anchoring.", file=sys.stderr)
    
    chapter_files = sorted(
        glob.glob(os.path.join(CHAPTERS_DIR, "*.md")) +
        glob.glob(os.path.join(CHAPTERS_DIR, "*.txt"))
    )
    if args.limit:
        chapter_files = chapter_files[:args.limit]
        print(f"[LIMIT] Processing {len(chapter_files)} chapter(s) only.", file=sys.stderr)
        
    print(f"[SCAN] Found {len(chapter_files)} total chapter files.", file=sys.stderr)
    
    total_extracted = 0
    total_written = 0
    
    for i, chap_path in enumerate(chapter_files):
        rel_path = os.path.relpath(chap_path, BASE_DIR)
        print(f"[{i+1}/{len(chapter_files)}] Processing {rel_path}", file=sys.stderr)
        
        try:
            with open(chap_path, "r", encoding="utf-8") as f:
                chapter_text = f.read()
        except Exception as e:
            print(f"[WARN] Failed to read {chap_path}: {e}", file=sys.stderr)
            continue
            
        # ── Chunk the chapter and query each chunk separately ────────────────
        chunks = chunk_text(chapter_text, max_words=400)
        print(f"  [CHUNK] {len(chunks)} chunk(s) for {rel_path}", file=sys.stderr)

        # Collect and deduplicate entities across all chunks
        seen_names: dict[str, dict] = {}   # lower(name) -> entity record
        world_state_updates = []

        for c_idx, chunk in enumerate(chunks, 1):
            print(f"  [CHUNK {c_idx}/{len(chunks)}] ~{len(chunk.split())} words", file=sys.stderr)
            prompt = build_prompt(chunk, entities, schema)

            if args.dry_run:
                print(f"[DRY-RUN] Chunk {c_idx} preview (first 300 chars): {chunk[:300]}...", file=sys.stderr)
                continue

            result = call_ollama(prompt, args.model, args.timeout)
            if not result:
                print(f"  [WARN] Chunk {c_idx}: no valid JSON from Ollama", file=sys.stderr)
                continue

            for ent in result.get("entities", []):
                key = ent.get("name", "").strip().lower()
                if not key:
                    continue
                if key not in seen_names:
                    seen_names[key] = ent   # first occurrence wins

            world_state_updates.extend(result.get("world_state_updates", []))

        if args.dry_run:
            print(f"[DRY-RUN] Would call Ollama with model={args.model}, timeout={args.timeout}s per chunk", file=sys.stderr)
            continue

        # ── Write stubs / enrich existing pages ───────────────────────────────
        for ent in seen_names.values():
            errors = validate_entity_record(ent, schema)
            if errors:
                print(f"[WARN] Skipping invalid entity '{ent.get('name')}': {errors}", file=sys.stderr)
                continue

            rel_dir, filename, content = generate_stub(ent, rel_path, schema)
            dir_path = os.path.join(BASE_DIR, rel_dir)
            os.makedirs(dir_path, exist_ok=True)
            filepath = os.path.join(dir_path, f"{filename}.md")

            if os.path.exists(filepath):
                # Enrich the existing page instead of skipping it
                enriched = enrich_existing_stub(filepath, ent, rel_path)
                if enriched:
                    total_extracted += 1
            else:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                total_written += 1
                total_extracted += 1

        time.sleep(args.pacing)
        
    print(f"\n[RESULTS] Extracted {total_extracted} entities. Wrote {total_written} new stubs.", file=sys.stderr)
    
    if args.apply and total_written > 0:
        if not run_validation_tools():
            print("[ERROR] Post-ingest validation failed. Review logs before proceeding.", file=sys.stderr)
            sys.exit(2)
            
    print("[DONE] Ingestion complete. EXIT 0", file=sys.stderr)
    sys.exit(0)

if __name__ == "__main__":
    main()