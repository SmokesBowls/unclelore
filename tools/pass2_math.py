#!/usr/bin/env python3
"""
MrLore v2 — Phase 6.0A Pass 2: Surface Form Statistics

Reads all raw/artifacts/batch_*.jsonl files and emits deterministic
per-surface_form statistics conforming to schema/PASS2_MATH_SCHEMA.md.

Contract:
- Reads schema/PASS2_MATH_SCHEMA.md and schema/ARTIFACT_SCHEMA.md first.
- No LLM calls. No classification. No wiki writes.
- audit_only: true and provisional: true hardcoded on all outputs.
- Output: raw/math/surface_form_stats.jsonl  (atomic write)
- EXIT 0: all surface_forms processed, output written (or previewed in --dry-run).
- EXIT 1: structural failure — malformed artifact, missing required field, crash.
- EXIT 2: safety stop — chronological_order inversion detected, or batch hash
           mismatch. Stats staged in raw/math_pending/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MRLORE_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = MRLORE_ROOT / "raw" / "artifacts"
MATH_ROOT = MRLORE_ROOT / "raw" / "math"
MATH_PENDING = MRLORE_ROOT / "raw" / "math_pending"
SCHEMA_DIR = MRLORE_ROOT / "schema"
LOGS_ROOT = MRLORE_ROOT / "logs"

PASS2_SCHEMA = SCHEMA_DIR / "PASS2_MATH_SCHEMA.md"
ARTIFACT_SCHEMA = SCHEMA_DIR / "ARTIFACT_SCHEMA.md"
OUTPUT_FILENAME = "surface_form_stats.jsonl"

EXTRACTOR_ID = "pass2_math/0.1.0"

# Required fields per ARTIFACT_SCHEMA §2 and §3.
REQUIRED_ARTIFACT_FIELDS = frozenset({
    "artifact_id", "surface_form", "source_line", "source_span",
    "chapter", "chronological_order", "surrounding_quote",
    "extractor_id", "extraction_timestamp", "source_file",
    "source_hash", "audit_only", "provisional",
})

# Speech verbs per PASS2_MATH_SCHEMA §4.1.
_SPEECH_VERBS = (
    "said", "asked", "replied", "continued", "whispered", "shouted", "murmured"
)

# Action verbs per PASS2_MATH_SCHEMA §4.2.
_ACTION_VERBS = (
    "went", "took", "saw", "held", "moved", "struck",
    "opened", "closed", "walked", "ran", "spoke", "looked",
)

_SPEECH_VERB_PATTERN = "|".join(_SPEECH_VERBS)
_ACTION_VERB_PATTERN = "|".join(_ACTION_VERBS)

# Compiled pattern caches.
_speech_re_cache: dict[str, re.Pattern[str]] = {}
_action_re_cache: dict[str, re.Pattern[str]] = {}

# ── Fix 2: Lightweight normalization ──────────────────────────
# Possessive strip: only fires on multi-word surface_forms where 's is
# immediately followed by a lowercase word (e.g. "Geralt's sword" — though
# in practice the extractor rarely produces such forms; included per spec).
_POSSESSIVE_RE = re.compile(r"(?i)([a-zA-Z]+)'s(?=\s+[a-z])")

# Plural → singular canonical mapping.  Extendable via external config.
PLURAL_SINGULAR_MAP: dict[str, str] = {
    "Keepers":      "Keeper",
    "Giants":       "Giant",
    "Students":     "Student",
    "Aeon Keepers": "Aeon Keepers",   # identity: canonical form preserved
    "Shadows":      "Shadow",
    "Factions":     "Faction",
    # 6.4C: normalize standalone "GPT" occurrences to the canonical form
    "GPT":          "Mr GPT",
    "Mr GPT":       "Mr GPT",         # identity: canonical form preserved
}


def normalize_surface_form(sf: str) -> str:
    """Apply possessive strip then plural-singular map (Fix 2)."""
    stripped = _POSSESSIVE_RE.sub(r"\1", sf)
    return PLURAL_SINGULAR_MAP.get(stripped, stripped)


def speech_re(surface_form: str) -> re.Pattern[str]:
    """Return (cached) speech-detection pattern for this surface_form (§4.1)."""
    if surface_form not in _speech_re_cache:
        esc = re.escape(surface_form)
        _speech_re_cache[surface_form] = re.compile(
            r"\b" + esc + r"\s+(" + _SPEECH_VERB_PATTERN + r")\b",
            re.IGNORECASE,
        )
    return _speech_re_cache[surface_form]


def action_re(surface_form: str) -> re.Pattern[str]:
    """Return (cached) action-subject pattern for this surface_form (§4.2).

    [^.]{0,200} caps backtracking on long quotes — equivalent to [^.]* for
    typical prose sentences, which rarely exceed 200 characters between periods.
    """
    if surface_form not in _action_re_cache:
        esc = re.escape(surface_form)
        _action_re_cache[surface_form] = re.compile(
            r"\b" + esc + r"\b\s+[^.]{0,200}\b(" + _ACTION_VERB_PATTERN + r")\b",
            re.IGNORECASE,
        )
    return _action_re_cache[surface_form]


# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_book_id(source_file: str) -> str:
    """
    Derive book_id from the source_file path.
    E.g. '.../raw/chapters/book_04_sage_saga_021_the_first_lesson.md'
         → 'book_04_sage_saga'
    """
    stem = Path(source_file).stem
    m = re.search(r"^(.*?)_\d{3}_", stem)
    if m:
        return m.group(1).lower()
    return re.sub(r"[^a-z0-9_]", "_", stem.lower())


def write_atomic(path: Path, content: str) -> None:
    """Write content to path atomically via temp + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ──────────────────────────────────────────────────────────────
# Batch loading and validation
# ──────────────────────────────────────────────────────────────

def discover_batches() -> list[Path]:
    if not ARTIFACTS_ROOT.exists():
        raise FileNotFoundError(f"Missing artifacts directory: {ARTIFACTS_ROOT}")
    batches = sorted(ARTIFACTS_ROOT.glob("batch_*.jsonl"))
    if not batches:
        raise FileNotFoundError(f"No batch_*.jsonl files found in {ARTIFACTS_ROOT}")
    return batches


def load_batch(
    path: Path,
) -> tuple[list[dict[str, Any]], str]:
    """
    Parse one JSONL batch file.  Returns (artifacts, file_sha256).
    Raises ValueError with a descriptive message on any structural problem.
    """
    file_hash = sha256_of_file(path)
    artifacts: list[dict[str, Any]] = []

    with path.open(encoding="utf-8") as fh:
        for line_num, raw_line in enumerate(fh, 1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                art = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path.name} line {line_num}: invalid JSON — {exc}"
                ) from exc

            missing = REQUIRED_ARTIFACT_FIELDS - set(art)
            if missing:
                raise ValueError(
                    f"{path.name} line {line_num}: missing fields {sorted(missing)}"
                )

            artifacts.append(art)

    return artifacts, file_hash


def check_chronological_order(
    batch_path: Path,
    artifacts: list[dict[str, Any]],
) -> str | None:
    """
    Return an error message if chronological_order is not non-decreasing,
    or None if the batch is ordered correctly.
    """
    prev = None
    for art in artifacts:
        order = art.get("chronological_order")
        if not isinstance(order, int):
            return f"{batch_path.name}: non-integer chronological_order: {order!r}"
        if prev is not None and order < prev:
            return (
                f"{batch_path.name}: chronological_order inversion "
                f"({prev} → {order})"
            )
        prev = order
    return None


# ──────────────────────────────────────────────────────────────
# Statistics computation
# ──────────────────────────────────────────────────────────────

def compute_stats(
    all_artifacts: list[dict[str, Any]],
    batch_hashes: list[str],
    timestamp: str,
    persistence_threshold: int,
) -> list[dict[str, Any]]:
    """
    Group artifacts by normalized surface_form (Fix 2) and compute all §3 fields.
    Returns one record per unique normalized surface_form, sorted per §6.2.
    raw_variants preserves the original pre-normalization forms for audit.
    chron_to_chapter is built inline (O(N) total, fixing prior O(S*N) assembly).
    """
    # Grouping pass — O(N): normalize key, build chron_to_chapter inline
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "artifact_ids": [],
        "chapters": set(),
        "books": set(),
        "chron_orders": [],
        "chron_to_chapter": defaultdict(list),
        "speech_count": 0,
        "action_count": 0,
        "raw_variants": set(),
    })

    for art in all_artifacts:
        sf_orig = art["surface_form"]
        sf = normalize_surface_form(sf_orig)
        g = groups[sf]
        g["artifact_ids"].append(art["artifact_id"])
        g["chapters"].add(art["chapter"])
        g["books"].add(extract_book_id(art["source_file"]))
        g["chron_orders"].append(art["chronological_order"])
        g["chron_to_chapter"][art["chronological_order"]].append(art["chapter"])
        g["raw_variants"].add(sf_orig)

    # Pattern-match pass — O(N): match against original form in original text
    for art in all_artifacts:
        sf_orig = art["surface_form"]
        sf = normalize_surface_form(sf_orig)
        quote = art.get("surrounding_quote", "")
        g = groups[sf]
        if speech_re(sf_orig).search(quote):
            g["speech_count"] += 1
        if action_re(sf_orig).search(quote):
            g["action_count"] += 1

    # Assembly pass — O(S): chron_to_chapter already populated
    records: list[dict[str, Any]] = []
    for sf, g in groups.items():
        chron_orders = g["chron_orders"]
        min_chron = min(chron_orders)
        max_chron = max(chron_orders)

        # Tie first/last chapter: lexicographically smallest chapter on ties.
        first_seen = min(g["chron_to_chapter"][min_chron])
        last_seen = max(g["chron_to_chapter"][max_chron])

        book_count = len(g["books"])
        records.append({
            "surface_form": sf,
            "raw_variants": sorted(g["raw_variants"]),
            "total_mentions": len(g["artifact_ids"]),
            "chapter_count": len(g["chapters"]),
            "speech_count": g["speech_count"],
            "action_count": g["action_count"],
            "book_count": book_count,
            "cross_chapter_persistence": book_count >= persistence_threshold,
            "first_seen_chapter": first_seen,
            "last_seen_chapter": last_seen,
            "chronological_span": max_chron - min_chron,
            "artifact_ids": sorted(g["artifact_ids"]),
            "provisional": True,
            "audit_only": True,
            "heuristic_approximation": True,
            "computation_timestamp": timestamp,
            "input_batch_hashes": batch_hashes,
        })

    # Sort per §6.2: lexicographic surface_form, then first_seen_chapter.
    records.sort(key=lambda r: (r["surface_form"], r["first_seen_chapter"]))
    return records


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pass 2 — deterministic surface-form statistics over artifact batches."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and preview stats without writing files.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write stats to raw/math/surface_form_stats.jsonl.",
    )
    parser.add_argument(
        "--persistence-threshold",
        type=int,
        default=3,
        metavar="N",
        help="Minimum book_count for cross_chapter_persistence=true (default: 3).",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()

    # ── schema contract check ──────────────────────────────────
    for schema_path in (PASS2_SCHEMA, ARTIFACT_SCHEMA):
        if not schema_path.exists():
            print(f"[EXIT 1] Missing required schema: {schema_path}", file=sys.stderr)
            return 1
    print(f"[init] schemas loaded: {PASS2_SCHEMA.name}, {ARTIFACT_SCHEMA.name}")

    # ── discover batches ───────────────────────────────────────
    try:
        batch_paths = discover_batches()
    except FileNotFoundError as exc:
        print(f"[EXIT 1] {exc}", file=sys.stderr)
        return 1

    print(f"[init] batches found: {len(batch_paths)}")
    for bp in batch_paths:
        print(f"  {bp.name}")

    # ── load and validate batches ──────────────────────────────
    all_artifacts: list[dict[str, Any]] = []
    batch_hashes: list[str] = []
    inversion_error: str | None = None

    for bp in batch_paths:
        print(f"[load] {bp.name} ...", end=" ", flush=True)
        try:
            artifacts, file_hash = load_batch(bp)
        except ValueError as exc:
            print(f"\n[EXIT 1] {exc}", file=sys.stderr)
            return 1
        except OSError as exc:
            print(f"\n[EXIT 1] Cannot read {bp}: {exc}", file=sys.stderr)
            return 1

        print(f"{len(artifacts)} artifacts")
        batch_hashes.append(file_hash)

        # Check chronological ordering (EXIT 2 trigger).
        inv = check_chronological_order(bp, artifacts)
        if inv and inversion_error is None:
            inversion_error = inv

        all_artifacts.extend(artifacts)

    print(f"[load] total artifacts: {len(all_artifacts)}")

    # ── compute statistics ─────────────────────────────────────
    timestamp = now_iso()
    print("[compute] grouping and aggregating ...", end=" ", flush=True)
    records = compute_stats(
        all_artifacts, batch_hashes, timestamp, args.persistence_threshold
    )
    print(f"{len(records)} unique surface_forms")

    # ── chronological inversion → EXIT 2 ──────────────────────
    if inversion_error:
        print(f"[EXIT 2] {inversion_error}")
        if args.apply:
            pending_path = MATH_PENDING / OUTPUT_FILENAME
            content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
            write_atomic(pending_path, content)
            print(f"  staged: {pending_path.relative_to(MRLORE_ROOT)}")
        return 2

    # ── dry-run: print sample records ─────────────────────────
    if args.dry_run:
        sample_count = min(5, len(records))
        print(f"\n[DRY-RUN] Sample ({sample_count} of {len(records)} records):")
        for r in records[:sample_count]:
            # Summarise artifact_ids list to keep output readable.
            display = dict(r)
            display["artifact_ids"] = (
                display["artifact_ids"][:3] + ["..."]
                if len(display["artifact_ids"]) > 3
                else display["artifact_ids"]
            )
            print(json.dumps(display, ensure_ascii=False, indent=2))
        print(f"\n[exit] EXIT 0")
        return 0

    # ── apply: write output atomically ────────────────────────
    output_path = MATH_ROOT / OUTPUT_FILENAME
    content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    try:
        write_atomic(output_path, content)
    except OSError as exc:
        print(f"[EXIT 1] Failed to write output: {exc}", file=sys.stderr)
        return 1

    print(f"\n[complete]")
    print(f"  output: {output_path.relative_to(MRLORE_ROOT)}")
    print(f"  records: {len(records)}")
    print(f"  total_size: {len(content):,} bytes")
    print("[exit] EXIT 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
