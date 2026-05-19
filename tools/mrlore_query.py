#!/usr/bin/env python3
"""mrlore_query.py — read-only MrLore registry query interface.

Usage:
    python3 tools/mrlore_query.py "Geralt"
    python3 tools/mrlore_query.py --incarnation "Geralt"
    python3 tools/mrlore_query.py --appearances "Vale"
    python3 tools/mrlore_query.py --cooccurs "Geralt"
    python3 tools/mrlore_query.py --id CHR-0017-geralt
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("[error] PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

BASE_DIR     = Path(__file__).resolve().parent.parent
ENTITIES_YAML = BASE_DIR / "wiki/registry/entities.yaml"
SIGNAL_STATS  = BASE_DIR / "raw/math/identity_signal_stats.jsonl"
ARTIFACTS_DIR = BASE_DIR / "raw/artifacts"

_SEP_RE = re.compile(r"^  # ── .+ ──\s*$", re.MULTILINE)

# ── loaders ──────────────────────────────────────────────────────────────────

def load_entities() -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    """Parse entities.yaml and return (by_name, by_id, by_alias) indexes."""
    text = ENTITIES_YAML.read_text(encoding="utf-8")
    segments = _SEP_RE.split(text)
    # segments[0] is the file header; [1:] are entity content blocks

    by_name:  dict[str, dict] = {}
    by_id:    dict[str, dict] = {}
    by_alias: dict[str, dict] = {}

    for seg in segments[1:]:
        # strip 2-space indent added by entity_to_yaml
        lines = []
        for line in seg.split("\n"):
            if line.startswith("  "):
                lines.append(line[2:])
            else:
                lines.append(line)
        block = "\n".join(lines)
        try:
            ent = yaml.safe_load(block)
        except yaml.YAMLError:
            continue
        if not isinstance(ent, dict):
            continue

        name = ent.get("display_name", "")
        eid  = ent.get("entity_id", "")
        if name:
            by_name[name.lower()] = ent
        if eid:
            by_id[eid.lower()] = ent

        for alias in ent.get("aliases") or []:
            aname = alias.get("name", "") if isinstance(alias, dict) else str(alias)
            if aname:
                by_alias[aname.lower()] = ent

    return by_name, by_id, by_alias


def load_signal_stats() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not SIGNAL_STATS.exists():
        return out
    with SIGNAL_STATS.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
                sf = rec.get("surface_form", "")
                if sf:
                    out[sf] = rec
            except json.JSONDecodeError:
                pass
    return out


def load_artifacts() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for batch in sorted(ARTIFACTS_DIR.glob("batch_*.jsonl")):
        with batch.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                    sf = rec.get("surface_form", "")
                    if sf:
                        out.setdefault(sf, []).append(rec)
                except json.JSONDecodeError:
                    pass
    return out


# ── lookup ───────────────────────────────────────────────────────────────────

def find_entity(
    name: str,
    by_name: dict[str, dict],
    by_id:   dict[str, dict],
    by_alias: dict[str, dict],
) -> dict | None:
    key = name.lower()
    return by_name.get(key) or by_id.get(key) or by_alias.get(key)


# ── display helpers ───────────────────────────────────────────────────────────

_BAR = "─" * 50

def hdr(label: str) -> str:
    return f"\n── {label} {_BAR[len(label)+4:]}"


def _cooc_list(ent: dict, signal: dict | None) -> list[str]:
    ss = ent.get("signal_stats") or {}
    coocs = [c for c in (ss.get("top_cooccurrences") or []) if c]
    if not coocs and signal:
        coocs = [c for c in (signal.get("proximity_cooccurrence") or []) if c]
    return coocs


# ── display modes ─────────────────────────────────────────────────────────────

def display_summary(ent: dict, signal: dict | None, artifacts: list[dict]) -> None:
    name  = ent.get("display_name", "?")
    eid   = ent.get("entity_id", "?")
    etype = ent.get("entity_type", "?")
    ss    = ent.get("signal_stats") or {}

    mentions = ss.get("total_mentions") or (signal.get("total_mentions", 0) if signal else 0)
    chapters = ss.get("chapter_count")  or (signal.get("chapter_count",  0) if signal else 0)
    books    = ss.get("book_count", 0)
    route    = ss.get("primary_route", "?")

    print(hdr(f"ENTITY: {name}"))
    print(f"  id       : {eid}")
    print(f"  type     : {etype}   status: {ent.get('status','?')} / {ent.get('canon_state','?')}")
    print(f"  route    : {route}")
    print(f"  mentions : {mentions}   chapters: {chapters}   books: {books}")

    if signal:
        sr = signal.get("speech_ratio", 0) or 0
        ar = signal.get("action_ratio", 0) or 0
        print(f"  speech   : {sr:.3f}   action: {ar:.3f}")

    aliases = ent.get("aliases") or []
    if aliases:
        names = []
        for a in aliases:
            n = a.get("name", "") if isinstance(a, dict) else str(a)
            if n:
                names.append(n)
        if names:
            print(f"  aliases  : {', '.join(names)}")

    # incarnation chain (compact)
    chain = ent.get("incarnation_chain")
    if chain and isinstance(chain, dict):
        seq = sorted(chain.get("sequence") or [], key=lambda s: s.get("order", 0))
        if seq:
            steps = " → ".join(s["identity"] for s in seq)
            print(f"\n  incarnation chain ({len(seq)}):")
            print(f"    {steps}")

    # accessories (compact)
    accs = ent.get("accessories") or []
    if accs:
        acc_names = []
        for a in accs:
            ref = f"[{a['entity_ref']}]" if a.get("entity_ref") else ""
            acc_names.append(f"{a['name']}{' ' + ref if ref else ''}")
        print(f"\n  accessories ({len(accs)}): {', '.join(acc_names)}")

    # cooccurrences
    coocs = _cooc_list(ent, signal)
    if coocs:
        print(f"\n  cooccurrences: {', '.join(coocs[:5])}")

    # snippets — deterministic random sample
    if artifacts:
        n = min(3, len(artifacts))
        sample = random.Random(name).sample(artifacts, n)
        print(f"\n  snippets ({n} of {len(artifacts)}):")
        for art in sample:
            ch = art.get("chapter", "?")
            q  = (art.get("surrounding_quote") or "").strip()
            if len(q) > 120:
                q = q[:117] + "..."
            print(f"    [{ch}]")
            print(f"    {q}")
            print()
    else:
        print()


def display_incarnation(ent: dict) -> None:
    name  = ent.get("display_name", "?")
    chain = ent.get("incarnation_chain")
    if not chain:
        print(f"\n  {name}: no incarnation chain recorded.")
        return

    print(hdr(f"INCARNATION CHAIN: {name}"))
    print(f"  authority : {chain.get('authority', '?')}")
    print(f"  status    : {chain.get('status', '?')}")
    print()
    seq = sorted(chain.get("sequence") or [], key=lambda s: s.get("order", 0))
    for step in seq:
        ref   = f"  [{step['entity_ref']}]" if step.get("entity_ref") else ""
        notes = f"  # {step['notes']}"       if step.get("notes")      else ""
        print(f"  {step['order']:>2}.  {step['identity']}{ref}{notes}")
    print()


def display_appearances(ent: dict) -> None:
    name     = ent.get("display_name", "?")
    books    = ent.get("book_appearances") or []
    chapters = ent.get("chapter_appearances") or []

    print(hdr(f"APPEARANCES: {name}"))

    if not books and not chapters:
        print("  (no appearance data recorded)")
        return

    if books:
        print(f"\n  books ({len(books)}):")
        for b in books:
            bnum = b.get("book_number", "?")
            bid  = b.get("book_id", "?")
            conf = b.get("confidence", "?")
            print(f"    book {bnum:>2}: {bid}  [{conf}]")

    if chapters:
        print(f"\n  chapters ({len(chapters)}):")
        for c in chapters:
            cid   = c.get("chapter_id", "?")
            ptype = c.get("presence_type", "?")
            conf  = c.get("confidence", "?")
            print(f"    {cid}  ({ptype}, {conf})")
    print()


def display_cooccurs(ent: dict, signal: dict | None) -> None:
    name = ent.get("display_name", "?")
    print(hdr(f"CO-OCCURRENCES: {name}"))

    ss    = ent.get("signal_stats") or {}
    reg   = [c for c in (ss.get("top_cooccurrences") or []) if c]
    prox  = [c for c in (signal.get("proximity_cooccurrence") or []) if c] if signal else []

    if reg:
        print(f"\n  registry top cooccurrences:")
        for i, c in enumerate(reg, 1):
            print(f"    {i:>2}. {c}")

    if prox and prox != reg[:len(prox)]:
        print(f"\n  signal proximity cooccurrences:")
        for i, c in enumerate(prox, 1):
            print(f"    {i:>2}. {c}")

    if not reg and not prox:
        print("  (no co-occurrence data)")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="mrlore_query.py",
        description="Read-only MrLore registry query interface.",
    )
    p.add_argument("name",          nargs="?", help="Entity name (default: full summary)")
    p.add_argument("--incarnation", metavar="NAME", help="Show incarnation chain")
    p.add_argument("--appearances", metavar="NAME", help="Show book/chapter appearances")
    p.add_argument("--cooccurs",    metavar="NAME", help="Show top co-occurrences")
    p.add_argument("--id",          metavar="ENTITY_ID", help="Look up by entity_id")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    query = args.incarnation or args.appearances or args.cooccurs or args.id or args.name

    if not query:
        print("Usage: mrlore_query.py NAME")
        print("       mrlore_query.py --incarnation NAME")
        print("       mrlore_query.py --appearances NAME")
        print("       mrlore_query.py --cooccurs NAME")
        print("       mrlore_query.py --id ENTITY_ID")
        return 1

    by_name, by_id, by_alias = load_entities()
    signal_index   = load_signal_stats()
    artifact_index = load_artifacts()

    ent = find_entity(query, by_name, by_id, by_alias)
    if not ent:
        print(f"[not found] {query!r}")
        print(f"  searched: {len(by_name)} entities, {len(by_alias)} aliases")
        return 1

    display_name = ent.get("display_name", query)
    signal = signal_index.get(display_name)
    arts   = artifact_index.get(display_name, [])

    if args.incarnation:
        display_incarnation(ent)
    elif args.appearances:
        display_appearances(ent)
    elif args.cooccurs:
        display_cooccurs(ent, signal)
    else:
        display_summary(ent, signal, arts)

    return 0


if __name__ == "__main__":
    sys.exit(main())
