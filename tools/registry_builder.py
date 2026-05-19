#!/usr/bin/env python3
"""
registry_builder.py — Phase 6.6

Reads human review decisions and signal stats, builds the MrLore symbol-table registry.

Inputs:
  review/human_identity_reviews.jsonl   — per-entity human decisions
  raw/math/surface_form_stats.jsonl     — book/chapter appearance data
  review/identity_review_queue.jsonl    — variants and co-occurrence hints

Outputs:
  wiki/registry/entities.yaml           — full symbol table (approved entries)
  wiki/registry/pending_merges.yaml     — merge_review entries awaiting parent resolution
  wiki/registry.md                      — human-readable index rebuilt from entities

Run from _mrlore/ root or via absolute path.
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = str(date.today())

REVIEWS_PATH       = os.path.join(BASE_DIR, "review/human_identity_reviews.jsonl")
STATS_PATH         = os.path.join(BASE_DIR, "raw/math/surface_form_stats.jsonl")
QUEUE_PATH         = os.path.join(BASE_DIR, "review/identity_review_queue.jsonl")
OUT_ENTITIES       = os.path.join(BASE_DIR, "wiki/registry/entities.yaml")
OUT_MERGES         = os.path.join(BASE_DIR, "wiki/registry/pending_merges.yaml")
OUT_REGISTRY_MD    = os.path.join(BASE_DIR, "wiki/registry.md")

WIKI_DIR_TO_TYPE = {
    "characters": "character",
    "factions":   "faction",
    "species":    "species",
    "locations":  "location",
    "artifacts":  "artifact",
    "systems":    "system",
    "events":     "event",
    "terms":      "concept",
    "arcs":       "concept",
    "themes":     "concept",
}

TYPE_TO_PREFIX = {
    "character":        "CHR",
    "faction":          "FAC",
    "species":          "SPE",
    "location":         "LOC",
    "artifact":         "ART",
    "system":           "SYS",
    "event":            "EVT",
    "concept":          "CON",
    "group":            "GRP",
    "relationship_label": "REL",
    "unknown":          "UNK",
}

ROUTE_DEFAULT_TYPE = {
    "bounded_actor_candidate":    "character",
    "identity_braid_candidate":   "unknown",
    "ambiguous_review_candidate":  "unknown",
}


# ── loaders ──────────────────────────────────────────────────────────────────

def load_reviews(path):
    """Deduplicate by taking the last (most recent) decision per surface_form."""
    by_sf = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            sf = r["surface_form"]
            if sf not in by_sf or r["timestamp"] > by_sf[sf]["timestamp"]:
                by_sf[sf] = r
    return by_sf


def load_surface_stats(path):
    stats = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            stats[r["surface_form"]] = r
    return stats


def load_queue(path):
    queue = {}
    if not os.path.exists(path):
        return queue
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            queue[r["surface_form"]] = r
    return queue


# ── entity type detection ─────────────────────────────────────────────────────

def _build_wiki_type_index():
    """Return {lowered_stem: (entity_type, wiki_path)} for all wiki md files."""
    index = {}
    wiki_base = os.path.join(BASE_DIR, "wiki")
    for dir_name, entity_type in WIKI_DIR_TO_TYPE.items():
        dir_path = os.path.join(wiki_base, dir_name)
        if not os.path.isdir(dir_path):
            continue
        for fn in os.listdir(dir_path):
            if not fn.endswith(".md"):
                continue
            stem = os.path.splitext(fn)[0]
            key = stem.replace("_", " ").lower()
            rel_path = f"wiki/{dir_name}/{fn}"
            index[key] = (entity_type, rel_path)
    return index


WIKI_TYPE_INDEX = _build_wiki_type_index()


def detect_entity_type(surface_form, primary_route):
    key = surface_form.lower()
    if key in WIKI_TYPE_INDEX:
        return WIKI_TYPE_INDEX[key]
    # Possessive drift: "Name's" → treat as character
    if surface_form.endswith("’s") or surface_form.endswith("'s"):
        return "character", None
    return ROUTE_DEFAULT_TYPE.get(primary_route, "unknown"), None


# ── ID / slug generation ──────────────────────────────────────────────────────

def make_slug(name):
    slug = name.lower()
    slug = re.sub(r"[‘’'\"]", "", slug)   # strip quotes/apostrophes
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def assign_entity_ids(approved_items):
    """Return {surface_form: entity_id}, numbering sequentially per prefix."""
    counters = defaultdict(int)
    result = {}
    for sf, entity_type, _ in sorted(approved_items, key=lambda x: x[0].lower()):
        prefix = TYPE_TO_PREFIX.get(entity_type, "UNK")
        counters[prefix] += 1
        slug = make_slug(sf)
        result[sf] = f"{prefix}-{counters[prefix]:04d}-{slug}"
    return result


# ── appearance parsing ────────────────────────────────────────────────────────

def parse_chapter_ref(chapter_id):
    """Parse 'book_05_the_nameless_one_ch028' into structured dict."""
    if not chapter_id:
        return None
    m = re.match(r"(book_(\d+)_.+)_ch(\d+)$", chapter_id)
    if m:
        return {
            "chapter_id": chapter_id,
            "book_id": m.group(1),
            "book_number": int(m.group(2)),
            "chapter_number": int(m.group(3)),
        }
    return {"chapter_id": chapter_id, "book_id": chapter_id, "book_number": None, "chapter_number": None}


def build_appearances(sf_stat):
    """Build book_appearances and chapter_appearances from surface_form_stats entry."""
    first_ref = parse_chapter_ref(sf_stat.get("first_seen_chapter"))
    last_ref  = parse_chapter_ref(sf_stat.get("last_seen_chapter"))

    # Deduplicate if first == last
    chapter_refs = [first_ref] if first_ref else []
    if last_ref and (not first_ref or last_ref["chapter_id"] != first_ref["chapter_id"]):
        chapter_refs.append(last_ref)

    # Collect unique books
    seen_books = {}
    for ref in chapter_refs:
        bid = ref["book_id"]
        if bid not in seen_books:
            seen_books[bid] = ref

    book_appearances = []
    for bid, ref in seen_books.items():
        book_appearances.append({
            "book_id": bid,
            "book_number": ref["book_number"],
            "profile_path": None,
            "confidence": "low",
        })

    chapter_appearances = []
    for ref in chapter_refs:
        chapter_appearances.append({
            "chapter_id": ref["chapter_id"],
            "state_id": None,
            "source_file": None,
            "presence_type": "direct",
            "confidence": "low",
        })

    return book_appearances, chapter_appearances


# ── YAML serialization ────────────────────────────────────────────────────────

def _yaml_str(val):
    """Quote a string value if needed for YAML safety."""
    if val is None:
        return "null"
    s = str(val)
    # needs quoting if it starts with special chars or contains ':'
    need_quote = (
        not s
        or s[0] in "#:&*!|>'\"%@`,"
        or ":" in s
        or s in ("null", "true", "false")
        or s.startswith("-")
    )
    if need_quote:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def _yaml_val(val, indent=0):
    pad = "  " * indent
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(val)
    if isinstance(val, str):
        return _yaml_str(val)
    if isinstance(val, list):
        if not val:
            return "[]"
        lines = []
        for item in val:
            if isinstance(item, dict):
                first = True
                for k, v in item.items():
                    prefix = f"{pad}- " if first else f"{pad}  "
                    lines.append(f"{prefix}{k}: {_yaml_val(v, indent+1)}")
                    first = False
            else:
                lines.append(f"{pad}- {_yaml_val(item, indent)}")
        return "\n" + "\n".join(lines)
    if isinstance(val, dict):
        if not val:
            return "{}"
        lines = []
        for k, v in val.items():
            rendered = _yaml_val(v, indent + 1)
            if rendered.startswith("\n"):
                lines.append(f"{pad}{k}:{rendered}")
            else:
                lines.append(f"{pad}{k}: {rendered}")
        return "\n" + "\n".join(lines)
    return _yaml_str(str(val))


def entity_to_yaml(entity, indent=0):
    """Serialize a single entity dict to YAML block, 2-space indented."""
    lines = []
    pad = "  " * indent
    for key, val in entity.items():
        if isinstance(val, list):
            if not val:
                lines.append(f"{pad}{key}: []")
            else:
                lines.append(f"{pad}{key}:")
                for item in val:
                    if isinstance(item, dict):
                        first = True
                        for k, v in item.items():
                            prefix = f"{pad}  - " if first else f"{pad}    "
                            lines.append(f"{prefix}{k}: {_yaml_val(v, indent+2)}")
                            first = False
                    else:
                        lines.append(f"{pad}  - {_yaml_val(item, indent+1)}")
        elif isinstance(val, dict):
            lines.append(f"{pad}{key}:")
            for k, v in val.items():
                rendered = _yaml_val(v, indent + 2)
                if rendered.startswith("\n"):
                    lines.append(f"{pad}  {k}:{rendered}")
                else:
                    lines.append(f"{pad}  {k}: {rendered}")
        else:
            lines.append(f"{pad}{key}: {_yaml_val(val)}")
    return "\n".join(lines)


# ── registry symbol builder ───────────────────────────────────────────────────

def build_entity_symbol(sf, entity_id, entity_type, wiki_path, sf_stat, queue_entry):
    raw_variants = sf_stat.get("raw_variants", [])
    aliases = []
    for v in raw_variants:
        if v != sf:
            aliases.append({
                "name": v,
                "alias_type": "uncertain",
                "status": "candidate",
                "first_seen": sf_stat.get("first_seen_chapter"),
            })
    # Mark possessive-drift forms
    if sf.endswith("’s") or sf.endswith("'s"):
        aliases.append({
            "name": sf,
            "alias_type": "possessive_drift",
            "status": "needs_review",
            "first_seen": sf_stat.get("first_seen_chapter"),
        })

    book_appearances, chapter_appearances = build_appearances(sf_stat)

    primary_sources = []
    if wiki_path:
        primary_sources.append(wiki_path)

    cooccurrences = []
    if queue_entry:
        cooccurrences = [t for t in queue_entry.get("top_cooccurring_tokens", []) if t]

    symbol = {
        "schema": "registry_symbol",
        "schema_version": 1,
        "entity_id": entity_id,
        "display_name": sf,
        "canonical_name": sf,
        "entity_type": entity_type,
        "status": "candidate",
        "canon_state": "provisional",
        "authority_level": "human_review",
        "aliases": aliases,
        "book_appearances": book_appearances,
        "chapter_appearances": chapter_appearances,
        "identity_states": [
            {"state_name": "baseline", "scope": None, "status": "provisional"}
        ],
        "merge_split": {
            "merge_status": "none",
            "split_status": "none",
            "related_symbols": [],
        },
        "evidence": {
            "primary_sources": primary_sources,
            "entity_states": [],
            "book_profiles": [],
            "canon_decisions": [],
        },
        "review": {
            "needs_review": False,
            "review_reason": None,
            "last_reviewed": TODAY,
            "reviewed_by": "human",
        },
        "signal_stats": {
            "total_mentions": sf_stat.get("total_mentions", 0),
            "chapter_count": sf_stat.get("chapter_count", 0),
            "book_count": sf_stat.get("book_count", 0),
            "primary_route": sf_stat.get("primary_route") or (
                queue_entry.get("primary_route") if queue_entry else None
            ),
            "top_cooccurrences": cooccurrences,
        },
        "timestamps": {
            "created_at": TODAY,
            "updated_at": TODAY,
        },
    }
    return symbol


def build_pending_merge(sf, review, sf_stat, queue_entry):
    cooccurrences = []
    if queue_entry:
        cooccurrences = [t for t in queue_entry.get("top_cooccurring_tokens", []) if t]

    return {
        "surface_form": sf,
        "primary_route": review.get("primary_route"),
        "reviewer_notes": review.get("reviewer_notes") or None,
        "total_mentions": sf_stat.get("total_mentions", 0),
        "chapter_count": sf_stat.get("chapter_count", 0),
        "book_count": sf_stat.get("book_count", 0),
        "first_seen_chapter": sf_stat.get("first_seen_chapter"),
        "last_seen_chapter": sf_stat.get("last_seen_chapter"),
        "raw_variants": sf_stat.get("raw_variants", []),
        "top_cooccurrences": cooccurrences,
        "merge_parent": None,
        "merge_status": "pending_human_review",
        "created_at": TODAY,
    }


# ── markdown registry ─────────────────────────────────────────────────────────

def build_registry_md(entities, pending_merges):
    lines = [
        "# MrLore Registry — Symbol Table",
        "",
        f"Generated: {TODAY}  ",
        f"Tool: `tools/registry_builder.py`  ",
        f"Machine-readable: `wiki/registry/entities.yaml`",
        "",
        "---",
        "",
        f"## Approved Entities ({len(entities)})",
        "",
        "Status: `candidate` | Canon state: `provisional` | Authority: `human_review`",
        "",
        "| Entity ID | Display Name | Type | Books | Chapters | Route |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for sym in sorted(entities, key=lambda e: e["entity_id"]):
        eid   = sym["entity_id"]
        name  = sym["display_name"]
        etype = sym["entity_type"]
        stats = sym.get("signal_stats", {})
        books = stats.get("book_count", len(sym.get("book_appearances", [])))
        chaps = stats.get("chapter_count", len(sym.get("chapter_appearances", [])))
        route = stats.get("primary_route") or ""
        lines.append(f"| {eid} | {name} | {etype} | {books} | {chaps} | {route} |")

    lines += [
        "",
        "---",
        "",
        f"## Pending Merges ({len(pending_merges)})",
        "",
        "These entities were flagged `merge_review`. No standalone registry entry created.",
        "Parent resolution requires human or canon decision.",
        "",
        "| Surface Form | Route | Mentions | Books | Top Co-occurrences |",
        "| --- | --- | --- | --- | --- |",
    ]

    for pm in sorted(pending_merges, key=lambda x: x["surface_form"].lower()):
        sf    = pm["surface_form"]
        route = pm.get("primary_route") or ""
        ment  = pm.get("total_mentions", 0)
        books = pm.get("book_count", 0)
        coocc = ", ".join(pm.get("top_cooccurrences", [])[:3]) or "—"
        lines.append(f"| {sf} | {route} | {ment} | {books} | {coocc} |")

    lines += [
        "",
        "---",
        "",
        "## Legacy Wiki-Only Entries",
        "",
        "The previous flat-table registry (wiki-scan entries) is superseded by this symbol table.",
        "To regenerate the legacy table, run `tools/build_registry.py`.",
        "",
    ]

    return "\n".join(lines) + "\n"


# ── YAML file writers ─────────────────────────────────────────────────────────

def write_entities_yaml(entities, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# MrLore Registry — Entity Symbol Table\n")
        f.write(f"# Generated: {TODAY}\n")
        f.write(f"# Tool: tools/registry_builder.py\n")
        f.write(f"# schema: registry_symbol v1\n")
        f.write(f"# entity_count: {len(entities)}\n\n")
        f.write("entities:\n\n")
        for sym in sorted(entities, key=lambda e: e["entity_id"]):
            f.write(f"  # ── {sym['entity_id']} ──\n")
            f.write(entity_to_yaml(sym, indent=1))
            f.write("\n\n")


def write_merges_yaml(pending_merges, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# MrLore Registry — Pending Merges\n")
        f.write(f"# Generated: {TODAY}\n")
        f.write(f"# Tool: tools/registry_builder.py\n")
        f.write(f"# merge_count: {len(pending_merges)}\n")
        f.write("# Each entry requires human resolution before a standalone entity is created.\n\n")
        f.write("pending_merges:\n\n")
        for pm in sorted(pending_merges, key=lambda x: x["surface_form"].lower()):
            f.write(f"  # ── {pm['surface_form']} ──\n")
            f.write(entity_to_yaml(pm, indent=1))
            f.write("\n\n")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("[registry_builder] Loading inputs...")
    reviews    = load_reviews(REVIEWS_PATH)
    sf_stats   = load_surface_stats(STATS_PATH)
    queue      = load_queue(QUEUE_PATH)

    approved     = {sf: r for sf, r in reviews.items() if r["decision"] == "approved"}
    merge_review = {sf: r for sf, r in reviews.items() if r["decision"] == "merge_review"}
    rejected     = {sf: r for sf, r in reviews.items() if r["decision"] == "rejected"}

    print(f"  approved={len(approved)}  merge_review={len(merge_review)}  rejected={len(rejected)}")

    # Collect (surface_form, entity_type, wiki_path) for ID assignment
    type_lookup = {}
    for sf in approved:
        route = approved[sf].get("primary_route", "")
        etype, wpath = detect_entity_type(sf, route)
        type_lookup[sf] = (etype, wpath)

    approved_items = [(sf, type_lookup[sf][0], type_lookup[sf][1]) for sf in approved]
    entity_ids = assign_entity_ids(approved_items)

    # Build entity symbols
    entities = []
    missing_stats = []
    for sf in approved:
        stat = sf_stats.get(sf)
        if not stat:
            missing_stats.append(sf)
            continue
        eid   = entity_ids[sf]
        etype, wpath = type_lookup[sf]
        qentry = queue.get(sf)
        sym = build_entity_symbol(sf, eid, etype, wpath, stat, qentry)
        entities.append(sym)

    if missing_stats:
        print(f"  [WARN] {len(missing_stats)} approved entities missing from surface_form_stats: {missing_stats}")

    # Build pending merges
    pending_merges = []
    for sf in merge_review:
        stat   = sf_stats.get(sf, {})
        qentry = queue.get(sf)
        pm = build_pending_merge(sf, merge_review[sf], stat, qentry)
        pending_merges.append(pm)

    # Write outputs
    print(f"[registry_builder] Writing {OUT_ENTITIES}...")
    write_entities_yaml(entities, OUT_ENTITIES)

    print(f"[registry_builder] Writing {OUT_MERGES}...")
    write_merges_yaml(pending_merges, OUT_MERGES)

    print(f"[registry_builder] Writing {OUT_REGISTRY_MD}...")
    md = build_registry_md(entities, pending_merges)
    with open(OUT_REGISTRY_MD, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"[registry_builder] Done.")
    print(f"  entities.yaml   : {len(entities)} symbols")
    print(f"  pending_merges  : {len(pending_merges)} entries")
    print(f"  registry.md     : rebuilt")


if __name__ == "__main__":
    main()
