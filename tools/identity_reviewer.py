#!/usr/bin/env python3
"""
MrLore v2 — Phase 6.5A Identity Reviewer

Interactive terminal reviewer for identity routing decisions.

Reads:  raw/math/provisional_identity_routes.jsonl
        raw/math/identity_signal_stats.jsonl
        raw/artifacts/batch_*.jsonl  (snippet lookup)
Writes: review/human_identity_reviews.jsonl  (append-only, decisions only)

Contract:
- Never modifies upstream files (routes, artifacts, stats).
- Decisions are append-only; last entry per surface_form wins on resume.
- --dry-run shows first record without writing.
- --resume skips already-reviewed surface_forms.
- EXIT 0: clean exit (q pressed, or queue exhausted).
- EXIT 1: structural failure (missing input, corrupt JSONL).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import textwrap
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MRLORE_ROOT = Path(__file__).resolve().parents[1]
MATH_ROOT   = MRLORE_ROOT / "raw" / "math"
ARTIFACTS_ROOT = MRLORE_ROOT / "raw" / "artifacts"
REVIEW_DIR  = MRLORE_ROOT / "review"

ROUTES_FILE  = MATH_ROOT / "provisional_identity_routes.jsonl"
SIGNALS_FILE = MATH_ROOT / "identity_signal_stats.jsonl"
OUTPUT_FILE  = REVIEW_DIR / "human_identity_reviews.jsonl"

TOOL_VERSION = "identity_reviewer/0.1.0"

DEFAULT_BUCKET = "bounded_actor_candidate"

VALID_BUCKETS: frozenset[str] = frozenset({
    "bounded_actor_candidate",
    "identity_braid_candidate",
    "ambiguous_review_candidate",
    "collective_or_species_candidate",
    "concept_field_candidate",
    "sparse_reference_candidate",
    "noise_or_header_candidate",
})

DECISION_KEYS: dict[str, str] = {
    "a": "approved",
    "r": "rejected",
    "s": "skipped",
    "m": "merge_review",
}

SNIPPET_COUNT = 3


# ──────────────────────────────────────────────────────────────
# Terminal helpers
# ──────────────────────────────────────────────────────────────

_IS_TTY = sys.stdout.isatty() and sys.stdin.isatty()

_R  = "\033[0m"
_B  = "\033[1m"
_DM = "\033[2m"
_YL = "\033[33m"
_CY = "\033[36m"
_GR = "\033[32m"
_RD = "\033[31m"
_MG = "\033[35m"

_DEC_COLOR = {
    "approved":    _GR,
    "rejected":    _RD,
    "skipped":     _YL,
    "merge_review": _MG,
}


def _c(text: str, *codes: str) -> str:
    """Apply ANSI codes only when stdout is a tty."""
    if not _IS_TTY:
        return text
    return "".join(codes) + text + _R


def _clear() -> None:
    if _IS_TTY:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def _tw() -> int:
    try:
        import shutil
        return min(shutil.get_terminal_size().columns, 100)
    except Exception:
        return 80


def getch() -> str:
    """Read one keypress without requiring Enter. Falls back to readline."""
    if not _IS_TTY:
        line = sys.stdin.readline()
        return line.strip()[:1].lower() if line.strip() else "q"
    import termios
    import tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch.lower()


# ──────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────

def load_routes(bucket: str) -> list[dict[str, Any]]:
    if not ROUTES_FILE.exists():
        raise FileNotFoundError(f"Missing routes file: {ROUTES_FILE}")
    records: list[dict[str, Any]] = []
    with ROUTES_FILE.open(encoding="utf-8") as fh:
        for line_num, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                r = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Routes line {line_num}: {exc}") from exc
            if r.get("primary_route") == bucket:
                records.append(r)
    return sorted(records, key=lambda r: r["surface_form"])


def load_signals() -> dict[str, dict[str, Any]]:
    if not SIGNALS_FILE.exists():
        return {}
    signals: dict[str, dict[str, Any]] = {}
    with SIGNALS_FILE.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            r = json.loads(raw)
            signals[r["surface_form"]] = r
    return signals


def load_artifacts() -> dict[str, list[dict[str, Any]]]:
    """Index all batch artifacts by surface_form."""
    arts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for batch in sorted(ARTIFACTS_ROOT.glob("batch_*.jsonl")):
        with batch.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                r = json.loads(raw)
                arts[r["surface_form"]].append(r)
    return dict(arts)


def load_existing_reviews() -> dict[str, dict[str, Any]]:
    """Return {surface_form: last_decision_record} from output file."""
    if not OUTPUT_FILE.exists():
        return {}
    decisions: dict[str, dict[str, Any]] = {}
    with OUTPUT_FILE.open(encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                r = json.loads(raw)
                if "surface_form" in r:
                    decisions[r["surface_form"]] = r
            except json.JSONDecodeError:
                pass
    return decisions


def pick_snippets(
    sf: str,
    arts_by_sf: dict[str, list[dict[str, Any]]],
    n: int = SNIPPET_COUNT,
) -> list[dict[str, Any]]:
    """Return up to n snippets, deterministically sampled by surface_form seed."""
    arts = arts_by_sf.get(sf, [])
    if len(arts) <= n:
        return arts
    return random.Random(sf).sample(arts, n)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ──────────────────────────────────────────────────────────────
# Display
# ──────────────────────────────────────────────────────────────

def render(
    route:    dict[str, Any],
    signal:   dict[str, Any],
    snippets: list[dict[str, Any]],
    idx:      int,
    total:    int,
    decided:  int,
    prior:    dict[str, Any] | None,
) -> None:
    tw = _tw()
    sep  = "═" * tw
    thin = "─" * tw

    sf     = route["surface_form"]
    bucket = route["primary_route"]

    # ── header ───────────────────────────────────────────────────
    _clear()
    info = f" IDENTITY REVIEWER  │  {bucket}  │  {idx+1}/{total}  │  {decided} decided "
    print(_c(sep, _B))
    print(_c(info[:tw], _B))
    print(_c(sep, _B))
    print()

    # ── surface form (prominent) ──────────────────────────────────
    sf_label = f"  ▶  {sf}  ◀  "
    print(_c(sf_label.center(min(tw, 60)), _B, _CY))

    mentions = route.get("total_mentions") or signal.get("total_mentions", 0)
    chapters = route.get("chapter_count")  or signal.get("chapter_count", 0)
    print(_c(f"  mentions: {mentions}   chapters: {chapters}".center(min(tw, 60)), _B))
    print()

    # ── signal fields ─────────────────────────────────────────────
    rr  = route.get("routing_reasons", {})
    sr  = signal.get("speech_ratio",               rr.get("speech_ratio", 0.0))
    ar  = signal.get("action_ratio",                rr.get("action_ratio", 0.0))
    mvs = signal.get("monologue_viability_score",   rr.get("monologue_viability_score", 0.0))
    cfs = signal.get("collective_fragmentation_score", 0.0)
    cds = signal.get("conceptual_drift_score",      0.0)
    avd = signal.get("avg_verb_distance",           0.0)

    print(f"  speech: {sr:.3f}   action: {ar:.3f}   mvs: {mvs:.3f}")
    print(f"  cfs:    {cfs:.3f}   cds:    {cds:.3f}   avd: {avd:.3f}")

    cooc = [t for t in signal.get("proximity_cooccurrence", []) if t]
    if cooc:
        print(f"  near:   {_c('  ·  '.join(cooc), _YL)}")

    matched = route.get("matched_rules", [bucket])
    if len(matched) > 1:
        extra = ", ".join(matched[1:])
        print(f"  also:   {_c(extra, _DM)}")

    # prior decision badge
    if prior:
        dec = prior["decision"]
        col = _DEC_COLOR.get(dec, "")
        print(f"\n  {_c(f'[ prior decision: {dec} ]', col, _B)}")

    print()
    print(_c(thin, _DM))

    # ── snippets ──────────────────────────────────────────────────
    if snippets:
        print(_c(f"  SNIPPETS  ({len(snippets)} of {mentions} shown)", _DM))
        print()
        qw = max(tw - 8, 40)
        for snip in snippets:
            chap = snip.get("chapter", "?")
            lnum = snip.get("source_line", "?")
            quote = snip.get("surrounding_quote", "").strip()
            # Shorten chapter id: keep book_XX and chapter number
            parts = chap.split("_ch")
            chap_disp = f"ch{parts[-1]}" if len(parts) > 1 else chap[-10:]
            print(f"  {_c(f'[{chap_disp} L{lnum}]', _DM)}")
            lines = textwrap.wrap(f'"{quote}"', width=qw)
            for ln in lines[:2]:                # max 2 lines of quote
                print(f"    {ln}")
            print()
    else:
        print(_c("  (no artifact snippets found)", _DM))
        print()

    print(_c(thin, _DM))

    # ── keymap ────────────────────────────────────────────────────
    print(
        f"  {_c('[a]', _GR)}pprove  "
        f"{_c('[r]', _RD)}eject  "
        f"{_c('[s]', _YL)}kip  "
        f"{_c('[m]', _MG)}erge  "
        f"{_c('[n]', _B)}ext  "
        f"{_c('[b]', _B)}ack  "
        f"{_c('[q]', _DM)}uit"
    )


# ──────────────────────────────────────────────────────────────
# Decision I/O
# ──────────────────────────────────────────────────────────────

def append_decision(rec: dict[str, Any]) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def make_decision_record(
    route:    dict[str, Any],
    decision: str,
    notes:    str = "",
) -> dict[str, Any]:
    return {
        "surface_form":   route["surface_form"],
        "primary_route":  route["primary_route"],
        "decision":       decision,
        "reviewer_notes": notes,
        "timestamp":      now_iso(),
        "audit_only":     True,
        "provisional":    True,
    }


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Interactive terminal reviewer for MrLore identity routing decisions.\n"
            f"Default bucket: {DEFAULT_BUCKET}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--bucket",
        default=DEFAULT_BUCKET,
        metavar="BUCKET",
        help=(
            f"Review bucket to load (default: {DEFAULT_BUCKET}).\n"
            f"Options: {', '.join(sorted(VALID_BUCKETS))}"
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip surface_forms that already have a decision in the output file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display first record without writing any decisions. EXIT 0.",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()

    if args.bucket not in VALID_BUCKETS:
        print(
            f"[error] Unknown bucket: {args.bucket!r}\n"
            f"  Valid: {', '.join(sorted(VALID_BUCKETS))}",
            file=sys.stderr,
        )
        return 1

    # ── Load data ─────────────────────────────────────────────────
    print(f"[init] {TOOL_VERSION}")
    print(f"[load] routes ...", end=" ", flush=True)
    try:
        all_routes = load_routes(args.bucket)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"\n[EXIT 1] {exc}", file=sys.stderr)
        return 1
    print(f"{len(all_routes)} records in '{args.bucket}'")

    print(f"[load] signals ...", end=" ", flush=True)
    try:
        signals = load_signals()
    except (OSError, ValueError) as exc:
        print(f"\n[EXIT 1] {exc}", file=sys.stderr)
        return 1
    print(f"{len(signals)} signal records")

    print(f"[load] artifacts ...", end=" ", flush=True)
    try:
        arts_by_sf = load_artifacts()
    except (OSError, ValueError) as exc:
        print(f"\n[EXIT 1] {exc}", file=sys.stderr)
        return 1
    print(f"{len(arts_by_sf)} surface_forms indexed")

    # ── Existing reviews ──────────────────────────────────────────
    existing = load_existing_reviews()
    print(f"[load] existing decisions: {len(existing)}")

    # ── Build queue ───────────────────────────────────────────────
    if args.resume:
        queue = [r for r in all_routes if r["surface_form"] not in existing]
        skipped_count = len(all_routes) - len(queue)
        if skipped_count:
            print(f"[resume] skipped {skipped_count} already-reviewed records")
    else:
        queue = all_routes

    if not queue:
        print(f"[done] No records to review in '{args.bucket}'.")
        return 0

    # ── Dry-run ───────────────────────────────────────────────────
    if args.dry_run:
        r   = queue[0]
        sig = signals.get(r["surface_form"], {})
        snp = pick_snippets(r["surface_form"], arts_by_sf)
        render(r, sig, snp, idx=0, total=len(queue), decided=0, prior=None)
        print(f"\n[dry-run] {len(queue)} records in queue. No output written.")
        return 0

    print(f"[ready] {len(queue)} records to review. Starting...")
    if _IS_TTY:
        print("  Press any key to begin...")
        getch()

    # ── Review loop ───────────────────────────────────────────────
    # decisions: in-memory copy of what we've decided this session
    session_decisions: dict[str, dict[str, Any]] = {}
    cursor = 0

    while 0 <= cursor < len(queue):
        route = queue[cursor]
        sf    = route["surface_form"]
        sig   = signals.get(sf, {})
        snips = pick_snippets(sf, arts_by_sf)

        # Prior decision = either this session's or a loaded existing one
        prior = session_decisions.get(sf) or existing.get(sf)

        decided_count = len(session_decisions)
        render(route, sig, snips, cursor, len(queue), decided_count, prior)

        try:
            key = getch()
        except (KeyboardInterrupt, EOFError):
            key = "q"

        if key in DECISION_KEYS:
            decision = DECISION_KEYS[key]
            rec = make_decision_record(route, decision)
            session_decisions[sf] = rec
            append_decision(rec)
            cursor += 1

        elif key == "n":
            # Advance without recording a decision
            cursor += 1

        elif key == "b":
            # Back — view previous record (does not undo decisions)
            if cursor > 0:
                cursor -= 1

        elif key == "q":
            _clear()
            print(f"\n[quit] Session complete.")
            print(f"  Reviewed this session: {len(session_decisions)}")
            print(f"  Total decisions on file: {len(existing) + len(session_decisions)}")
            print(f"  Output: {OUTPUT_FILE.relative_to(MRLORE_ROOT)}")
            return 0

        elif key == "\x03":  # Ctrl-C
            _clear()
            print(f"\n[interrupted] {len(session_decisions)} decisions saved.")
            return 0

        # Any other key: re-render (ignore)

    # Queue exhausted
    _clear()
    print(f"\n[complete] All {len(queue)} records in '{args.bucket}' reviewed.")
    print(f"  Decisions this session: {len(session_decisions)}")
    print(f"  Output: {OUTPUT_FILE.relative_to(MRLORE_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
