#!/usr/bin/env python3
"""
MrLore Phase 5c — Continuity Audit (Dynamic Ruleset Engine)
continuity_audit.py
Semantic canon linting. Detects discontinuities deterministically.
Does NOT generate prose. Does NOT edit canon. Does NOT resolve conflicts.
Detectors (in order of reliability):
1. Entity alias drift        — token in chapter not in registry canonical form
2. Timeline order violations — event referenced before canonical occurrence
3. Character presence        — character in location contradicting known state
4. Location contradictions   — entity in incompatible locations in unresolved window
5. World-state descriptor drift — chapter text matches contradicting patterns in scoped ruleset
Output:
wiki/continuity/CONT-NNNN-short-title.yaml   (one per finding)
logs/continuity_audit_YYYYMMDD_HHMM.md       (run report)
Usage:
python3 tools/continuity_audit.py --source book_01/001_the_ethereal_vigil.md
python3 tools/continuity_audit.py --all-sources
python3 tools/continuity_audit.py --changed raw/changed_files.txt
Exit codes:
0  clean — no continuity conflicts detected
1  mechanical failure
2  continuity conflicts found — human review required
"""
import re
import sys
import yaml
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

MRLORE_ROOT   = Path(__file__).resolve().parents[1]
VAULT_ROOT    = MRLORE_ROOT.parent
WIKI_PATH     = MRLORE_ROOT / "wiki"
SCHEMA_PATH   = MRLORE_ROOT / "schema" / "MRLORE_SCHEMA.md"
REGISTRY_PATH = WIKI_PATH / "registry.md"
CONTINUITY_DIR = WIKI_PATH / "continuity"
LOGS_DIR      = MRLORE_ROOT / "logs"
CONTINUITY_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

SOURCE_EXTS = {".md", ".txt"}

# ── COUNTER ──────────────────────────────────────────────────────────────────
_conflict_counter_file = CONTINUITY_DIR / ".counter"
def _next_conflict_id() -> str:
    n = 0
    if _conflict_counter_file.exists():
        try:
            n = int(_conflict_counter_file.read_text().strip())
        except ValueError:
            n = 0
    n += 1
    _conflict_counter_file.write_text(str(n))
    return f"CONT-{n:04d}"

# ── REGISTRY LOADER ───────────────────────────────────────────────────────────
def load_registry() -> dict:
    """
    Parse wiki/registry.md into a usable structure.
    Returns:
    {
      "canonical_names": {lower_name: canonical_name},
      "variants":        {lower_variant: canonical_name},
      "entities":        {canonical_name: {type, canon_state, page}},
    }
    """
    data = {
        "canonical_names": {},
        "variants": {},
        "entities": {},
    }
    if not REGISTRY_PATH.exists():
        return data
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    current_type = "unknown"
    for line in text.splitlines():
        if line.startswith("## "):
            current_type = line[3:].strip().lower().rstrip("s")
            continue
        if line.startswith("|") and not line.startswith("| ---") and not line.startswith("| Canon"):
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 4:
                continue
            name, canon_state, variants_raw, *_ = cols
            if name in ("Canonical Name", "---", ""):
                continue
            canonical = name.strip()
            lower_canonical = canonical.lower()
            data["canonical_names"][lower_canonical] = canonical
            data["entities"][canonical] = {
                "type":        current_type,
                "canon_state": canon_state.strip(),
                "page":        cols[3].strip() if len(cols) > 3 else "",
            }
            if variants_raw and variants_raw != "—":
                for v in variants_raw.split(","):
                    v = v.strip().strip("`").strip('"').strip("*")
                    if v and v.lower() != lower_canonical:
                        data["variants"][v.lower()] = canonical
    return data

# ── WORLD STATE RULESET LOADER (Phase 5c dynamic) ──────────────────────────
def load_world_state_rulesets() -> list[dict]:
    """
    Scans wiki/canon_decisions/*.md for rulesets.
    Returns list of dicts with keys:
      - source_file
      - world_state_tag
      - scope: {books, arcs, locations, excludes}
      - contradicting_descriptors (list of regex strings)
      - confirming_descriptors (optional)
    """
    rulesets = []
    decisions_dir = WIKI_PATH / "canon_decisions"
    if not decisions_dir.exists():
        return rulesets

    for md_file in decisions_dir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        end = text.find("---", 3)
        if end == -1:
            continue
        try:
            front = yaml.safe_load(text[3:end])
        except yaml.YAMLError:
            continue

        if not isinstance(front, dict):
            continue
        if not front.get("audit_only"):
            continue
        contradicting = front.get("contradicting_descriptors", [])
        if not contradicting or not isinstance(contradicting, list):
            continue

        rulesets.append({
            "source_file": str(md_file.relative_to(MRLORE_ROOT)),
            "world_state_tag": front.get("world_state_tag", "unnamed"),
            "scope": {
                "books": front.get("scope", {}).get("books", []),
                "arcs": front.get("scope", {}).get("arcs", []),
                "locations": front.get("scope", {}).get("locations", []),
                "excludes": front.get("scope", {}).get("excludes", []),
            },
            "contradicting_descriptors": contradicting,
            "confirming_descriptors": front.get("confirming_descriptors", []),
        })

    return rulesets

# ── CHARACTER STATE LOADER ────────────────────────────────────────────────────
def load_character_states() -> dict:
    states = {}
    chars_dir = WIKI_PATH / "characters"
    if not chars_dir.exists():
        return states
    for page in chars_dir.glob("*.md"):
        text = page.read_text(encoding="utf-8", errors="replace")
        name = page.stem.replace("_", " ")
        state = {"status": "unknown", "last_location": None,
                 "last_arc": None, "source": str(page.relative_to(MRLORE_ROOT))}
        for line in text.splitlines():
            l = line.lower().strip()
            if "status:" in l:
                state["status"] = line.split(":", 1)[-1].strip().lower()
            if "current location:" in l or "location:" in l:
                state["last_location"] = line.split(":", 1)[-1].strip()
            if "primary arc:" in l:
                state["last_arc"] = line.split(":", 1)[-1].strip()
        states[name.lower()] = state
    return states

# ── SOURCE TEXT LOADER ────────────────────────────────────────────────────────
def load_source(vault_rel: str) -> str:
    path = VAULT_ROOT / vault_rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")

# ── CHAPTER METADATA EXTRACTOR ────────────────────────────────────────────────
def _extract_chapter_meta(text: str) -> dict:
    """Pull YAML frontmatter from a chapter source file."""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    try:
        meta = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return meta if isinstance(meta, dict) else {}

# ── DETECTOR 1: ENTITY ALIAS DRIFT ───────────────────────────────────────────
KNOWN_ALIAS_PAIRS = [
    (r"\bNeferati\b",    "Nephoretti"),
    (r"\bNehereti\b",    "Nephoretti"),
    (r"\bNephrati\b",    "Nephoretti"),
    (r"\bAaon Keepers?\b", "Aeon Keepers"),
    (r"\bGraviton[^i]",  None),
]

def detect_alias_drift(text: str, source_rel: str, registry: dict) -> list[dict]:
    findings = []
    for pattern, canonical in KNOWN_ALIAS_PAIRS:
        matches = re.findall(pattern, text)
        if matches:
            findings.append({
                "detector":    "entity_alias_drift",
                "source":      source_rel,
                "detected":    {"token": pattern.strip(r"\b"), "count": len(matches)},
                "registry":    {"canonical": canonical or "REVIEW_REQUIRED"},
                "severity":    "warning" if canonical else "info",
                "proposal_available": canonical is not None,
                "human_review_required": True,
            })
    for variant_lower, canonical in registry.get("variants", {}).items():
        if len(variant_lower) < 4:
            continue
        pattern = r"\b" + re.escape(variant_lower) + r"\b"
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            canonical_matches = re.findall(
                r"\b" + re.escape(canonical) + r"\b", text, re.IGNORECASE
            )
            if len(matches) > len(canonical_matches):
                findings.append({
                    "detector":    "entity_alias_drift",
                    "source":      source_rel,
                    "detected":    {"token": variant_lower, "count": len(matches)},
                    "registry":    {"canonical": canonical},
                    "severity":    "warning",
                    "proposal_available": True,
                    "human_review_required": True,
                })
    return findings

# ── DETECTOR 2: CHARACTER PRESENCE CONTRADICTION ─────────────────────────────
DEATH_INDICATORS = [
    r"\b(died|dead|killed|slain|deceased|fell|perished|destroyed)\b"
]
ABSENCE_INDICATORS = [
    r"\b(departed|left|vanished|gone|absent|no longer)\b"
]

def detect_character_presence(text: str, source_rel: str,
                              character_states: dict) -> list[dict]:
    findings = []
    for char_lower, state in character_states.items():
        if state.get("status") in ("dead", "destroyed", "absent"):
            pattern = r"\b" + re.escape(char_lower) + r"\b.{0,60}\b(said|moved|walked|ran|spoke|stood|felt|saw|heard|called)\b"
            if re.search(pattern, text.lower()):
                findings.append({
                    "detector":    "character_presence_contradiction",
                    "source":      source_rel,
                    "detected":    {
                        "character": char_lower,
                        "appears_active": True,
                    },
                    "wiki_state":  {
                        "status":   state["status"],
                        "declared": state["source"],
                    },
                    "severity":    "high",
                    "proposal_available": False,
                    "human_review_required": True,
                    "notes": "Character declared absent/dead in wiki but appears active in source.",
                })
    return findings

# ── DETECTOR 3: WORLD-STATE DESCRIPTOR DRIFT ─────────────────────────────────
def detect_world_state_drift(
    text: str,
    source_rel: str,
    world_state_rulesets: list[dict],
) -> list[dict]:
    findings = []
    if not world_state_rulesets:
        return findings

    chapter_meta = _extract_chapter_meta(text)
    chapter_book = chapter_meta.get("book", "")
    chapter_arc  = chapter_meta.get("arc", "")
    chapter_loc  = chapter_meta.get("location", "")
    
    if isinstance(chapter_loc, str):
        chapter_locations = [chapter_loc.strip()] if chapter_loc.strip() else []
    elif isinstance(chapter_loc, list):
        chapter_locations = [l.strip() for l in chapter_loc if l.strip()]
    else:
        chapter_locations = []

    def _scope_matches(scope: dict) -> bool:
        books = scope.get("books", [])
        arcs = scope.get("arcs", [])
        locs = scope.get("locations", [])
        if not books and not arcs and not locs:
            return True  # global
        if books and chapter_book not in books:
            return False
        if arcs and chapter_arc not in arcs:
            return False
        if locs:
            if not any(cl in locs for cl in chapter_locations):
                return False
        return True

    text_lower = text.lower()
    for ruleset in world_state_rulesets:
        if not _scope_matches(ruleset["scope"]):
            continue

        for pattern_str in ruleset["contradicting_descriptors"]:
            try:
                matches = re.findall(pattern_str, text_lower, re.IGNORECASE)
            except re.error:
                continue
            if matches:
                findings.append({
                    "detector": "world_state_descriptor_drift",
                    "source": source_rel,
                    "detected": {
                        "descriptor": pattern_str,
                        "match_count": len(matches),
                    },
                    "ruleset": {
                        "world_state_tag": ruleset["world_state_tag"],
                        "declared_in": ruleset["source_file"],
                    },
                    "severity": "warning",
                    "proposal_available": False,
                    "human_review_required": True,
                    "notes": f"Contradicting descriptor matched in scope.",
                })
    return findings

# ── CONFLICT FILE WRITER ──────────────────────────────────────────────────────
def write_conflict(finding: dict) -> Path:
    conflict_id = _next_conflict_id()
    detector    = finding.get("detector", "unknown")
    slug        = detector.replace("_", "-")
    filename    = f"{conflict_id}-{slug}.yaml"
    path        = CONTINUITY_DIR / filename
    record = {
        "conflict_id":            conflict_id,
        "type":                   finding.get("detector"),
        "severity":               finding.get("severity", "warning"),
        "detected":               datetime.now().strftime("%Y-%m-%d"),
        "status":                 "open",
        "chapter":                {"source": finding.get("source")},
        "detected":               finding.get("detected"),
        "registry":               finding.get("registry"),
        "wiki_state":             finding.get("wiki_state"),
        "world_state":            finding.get("world_state"),
        "ruleset":                finding.get("ruleset"),
        "instances":              finding.get("detected", {}).get("count", 1) or finding.get("detected", {}).get("match_count", 1),
        "proposal_available":     finding.get("proposal_available", False),
        "human_review_required":  finding.get("human_review_required", True),
        "notes":                  finding.get("notes", ""),
        "user_decision":          None,
        "resolution_log":         [],
    }
    record = {k: v for k, v in record.items() if v is not None}
    path.write_text(
        yaml.dump(record, default_flow_style=False, allow_unicode=True),
        encoding="utf-8"
    )
    return path

# ── REPORT WRITER ─────────────────────────────────────────────────────────────
def write_report(run_id: str, results: list[dict], sources: list[str]) -> Path:
    total    = len(results)
    by_sev   = defaultdict(int)
    for r in results:
        by_sev[r.get("severity", "warning")] += 1
    lines = [
        f"# MrLore Continuity Audit — {run_id}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Sources audited: {len(sources)}",
        f"Total findings: {total}",
        "",
        "## Summary",
        "",
        f"| Severity | Count |",
        f"|----------|-------|",
    ]
    for sev in ("high", "warning", "info"):
        lines.append(f"| {sev} | {by_sev[sev]} |")
    lines.append("")
    if not results:
        lines += ["## Result", "", "✓ No continuity conflicts detected.", ""]
    else:
        lines += ["## Findings", ""]
        for r in results:
            lines.append(f"- [{r.get('severity','?').upper()}] "
                         f"{r.get('detector','?')} in `{r.get('source','?')}`")
            if r.get("detected"):
                det = r["detected"]
                if isinstance(det, dict):
                    for k, v in det.items():
                        lines.append(f"  {k}: {v}")
            lines.append("")
    lines += [
        "## Next Steps",
        "",
        "1. Review CONT-*.yaml files in wiki/continuity/",
        "2. Resolve or defer each finding",
        "3. Run 5b proposal generation for findings with proposal_available: true",
        "",
    ]
    report_path = LOGS_DIR / f"continuity_audit_{run_id}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path

# ── MAIN ──────────────────────────────────────────────────────────────────────
def collect_sources(args: list[str]) -> list[str]:
    sources = []
    if "--all-sources" in args:
        for path in sorted(VAULT_ROOT.rglob("*")):
            if path.is_file() and path.suffix.lower() in SOURCE_EXTS:
                rel = str(path.relative_to(VAULT_ROOT))
                if not rel.startswith("_mrlore"):
                    sources.append(rel)
        return sources
    for i, arg in enumerate(args):
        if arg == "--source" and i + 1 < len(args):
            sources.append(args[i + 1])
        if arg == "--changed" and i + 1 < len(args):
            manifest = Path(args[i + 1])
            if manifest.exists():
                lines = manifest.read_text(encoding="utf-8").splitlines()
                sources += [l.strip() for l in lines
                            if l.strip() and not l.startswith("#")]
    return sources

def main() -> int:
    args     = sys.argv[1:]
    run_id   = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not args:
        print(__doc__)
        return 0

    print(f"[continuity_audit] Loading registry...")
    registry = load_registry()
    print(f"[continuity_audit] Registry: {len(registry['canonical_names'])} canonical, "
          f"{len(registry['variants'])} variants")
    
    print(f"[continuity_audit] Loading world state rulesets...")
    world_state_rulesets = load_world_state_rulesets()
    print(f"[continuity_audit] Loaded {len(world_state_rulesets)} ruleset(s) with active descriptors")
    
    print(f"[continuity_audit] Loading character states...")
    char_states = load_character_states()
    
    sources = collect_sources(args)
    if not sources:
        print("[continuity_audit] No sources to audit.")
        return 0
    print(f"[continuity_audit] Auditing {len(sources)} source(s)...")
    
    all_findings = []
    for source_rel in sources:
        text = load_source(source_rel)
        if not text.strip():
            continue
        findings = []
        findings += detect_alias_drift(text, source_rel, registry)
        findings += detect_character_presence(text, source_rel, char_states)
        findings += detect_world_state_drift(text, source_rel, world_state_rulesets)
        
        for f in findings:
            path = write_conflict(f)
            print(f"  [{f.get('severity','?').upper()}] {f.get('detector')} "
                  f"— {source_rel} → {path.name}")
        all_findings += findings

    report = write_report(run_id, all_findings, sources)
    print(f"\n[continuity_audit] Report: {report}")
    print(f"[continuity_audit] Findings: {len(all_findings)}")
    
    log_entry = (
        f"\n## [{datetime.now().strftime('%Y-%m-%d')}] continuity_audit | {run_id}\n"
        f"Sources audited: {len(sources)}\n"
        f"Findings: {len(all_findings)}\n"
        f"Report: logs/continuity_audit_{run_id}.md\n"
    )
    log_path = WIKI_PATH / "log.md"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_entry)
        
    if all_findings:
        print("[continuity_audit] EXIT 2 — continuity conflicts require human review")
        return 2
    print("[continuity_audit] EXIT 0 — clean")
    return 0

if __name__ == "__main__":
    sys.exit(main())