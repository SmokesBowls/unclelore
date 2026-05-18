#!/usr/bin/env python3
"""
MrLore v2 — Phase 6.2A Identity Signal Math

Joins Pass 1 artifacts with Pass 2 surface-form stats and computes
10 deterministic signal fields per unique surface_form.

Contract:
- Reads schema/PASS2_MATH_SCHEMA.md first.
- No LLM inference. No wiki writes. No canon decisions. No entity type labels.
- Pure deterministic math — same inputs → byte-identical output.
- Input: raw/artifacts/batch_*.jsonl + raw/math/surface_form_stats.jsonl
- Output: raw/math/identity_signal_stats.jsonl  (atomic write)
- EXIT 0: all surface_forms processed, output written (or previewed in --dry-run).
- EXIT 1: structural failure — missing input, missing schema, crash.
- EXIT 2: safety stop — batch hash mismatch or input incoherence detected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MRLORE_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = MRLORE_ROOT / "raw" / "artifacts"
MATH_ROOT = MRLORE_ROOT / "raw" / "math"
SCHEMA_DIR = MRLORE_ROOT / "schema"

PASS2_SCHEMA = SCHEMA_DIR / "PASS2_MATH_SCHEMA.md"
PASS2_STATS = MATH_ROOT / "surface_form_stats.jsonl"
OUTPUT_FILENAME = "identity_signal_stats.jsonl"

EXTRACTOR_ID = "identity_signal_math/0.1.0"

# Heuristic: capitalized noun phrases following location prepositions.
_LOCATION_PREP_RE = re.compile(
    r"\b(?:in|at|near|from|to|through|into|toward|across|by|around)\s+"
    r"([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+)*)\b"
)

# ── Fix 3: Proximity metrics ───────────────────────────────────

STATIC_VERB_SET: frozenset[str] = frozenset({
    "said", "asked", "replied", "continued", "went", "took", "saw", "held",
    "moved", "struck", "opened", "closed", "walked", "ran", "spoke", "looked",
    "turned", "raised", "fell", "stood", "sat", "whispered", "shouted", "murmured",
})

# Stop words for proximity co-occurrence filtering (mirrors artifact_extractor.py STOP_WORD_SET).
_PROXIMITY_STOP_WORDS: frozenset[str] = frozenset({
    'a', 'an', 'the', 'this', 'that', 'these', 'those',
    'it', 'its', 'he', 'him', 'she', 'her', 'they', 'them',
    'we', 'us', 'i', 'me', 'you', 'my', 'your',
    'his', 'our', 'their', 'theirs', 'hers', 'ours', 'yours',
    'and', 'but', 'or', 'nor', 'so', 'yet', 'for',
    'in', 'on', 'at', 'by', 'to', 'of', 'with', 'from',
    'into', 'onto', 'upon', 'out', 'up', 'down',
    'over', 'under', 'between', 'through', 'about',
    'after', 'before', 'during', 'since', 'until', 'while',
    'when', 'where', 'why', 'how', 'what', 'which', 'who', 'whom',
    'if', 'as', 'than', 'though', 'although', 'because',
    'then', 'thus', 'also', 'just', 'even', 'only', 'still',
    'here', 'there', 'now', 'not', 'yes', 'no',
    'was', 'were', 'is', 'are', 'be', 'been', 'being',
    'had', 'has', 'have', 'do', 'did', 'done', 'does', 'doing', 'having',
    'will', 'would', 'could', 'should', 'may', 'might',
    'shall', 'can', 'cannot', 'must',
    'each', 'every', 'all', 'both', 'few', 'more', 'most',
    'other', 'some', 'any', 'such',
    'across', 'almost', 'alone', 'along', 'already', 'always',
    'away', 'back', 'below', 'either', 'else',
    'herself', 'himself', 'itself', 'myself', 'ourselves', 'themselves', 'yourself',
    'however', 'let', 'like', 'made', 'many', 'near', 'never',
    'new', 'next', 'off', 'once', 'own', 're', 'same',
    'whether', 'within', 'without', 'till', 'too',
})

# Mirrors PLURAL_SINGULAR_MAP from pass2_math.py for cross-tool artifact indexing.
_PASS2_PLURAL_MAP: dict[str, str] = {
    "Keepers":      "Keeper",
    "Giants":       "Giant",
    "Students":     "Student",
    "Aeon Keepers": "Aeon Keepers",
    "Shadows":      "Shadow",
    "Factions":     "Faction",
}
_PASS2_POSSESSIVE_RE = re.compile(r"(?i)([a-zA-Z]+)'s(?=\s+[a-z])")


def _normalize_for_index(sf: str) -> str:
    """Lightweight mirror of pass2_math.normalize_surface_form for index alignment."""
    stripped = _PASS2_POSSESSIVE_RE.sub(r"\1", sf)
    return _PASS2_PLURAL_MAP.get(stripped, stripped)


_WORD_TOKEN_RE = re.compile(r"[A-Za-z''\-]+")


def _tokenize(text: str) -> list[str]:
    """Extract word tokens (preserving case, stripping punctuation)."""
    return _WORD_TOKEN_RE.findall(text)


def _find_form_positions(sf_tokens: list[str], all_tokens: list[str]) -> list[int]:
    """
    Return 0-based start indices where sf_tokens appears as a contiguous
    subsequence in all_tokens (case-insensitive).
    """
    sf_len = len(sf_tokens)
    if sf_len == 0:
        return []
    sf_lower = [t.lower() for t in sf_tokens]
    return [
        i for i in range(len(all_tokens) - sf_len + 1)
        if [all_tokens[i + j].lower() for j in range(sf_len)] == sf_lower
    ]


def compute_proximity_cooccurrence(
    arts: list[dict], sf: str
) -> list[str]:
    """
    Top-3 capitalized co-occurring tokens in a ±10-word window around each
    mention of sf across all artifacts.  Stop words and sf itself excluded.
    Ties broken lexicographically; padded with '' if fewer than 3 found.
    """
    from collections import Counter
    counts: Counter[str] = Counter()
    sf_tokens = _tokenize(sf)
    sf_len = len(sf_tokens)
    sf_lower = sf.lower()

    for art in arts:
        quote = art.get("surrounding_quote", "")
        tokens = _tokenize(quote)
        positions = _find_form_positions(sf_tokens, tokens)
        for start in positions:
            lo = max(0, start - 10)
            hi = min(len(tokens), start + sf_len + 10)
            for idx in range(lo, hi):
                if start <= idx < start + sf_len:
                    continue  # skip the surface_form span itself
                tok = tokens[idx]
                if tok and tok[0].isupper() and tok.lower() not in _PROXIMITY_STOP_WORDS and tok.lower() != sf_lower:
                    counts[tok] += 1

    top = sorted(counts, key=lambda t: (-counts[t], t))[:3]
    while len(top) < 3:
        top.append("")
    return top


def compute_avg_verb_distance(
    arts: list[dict], sf: str
) -> float:
    """
    Average word distance from the first occurrence of sf to the nearest
    verb in STATIC_VERB_SET within each artifact's surrounding_quote.
    Distance = 0.0 when no verb is found in the quote.
    """
    sf_tokens = _tokenize(sf)
    distances: list[float] = []

    for art in arts:
        quote = art.get("surrounding_quote", "")
        tokens = _tokenize(quote)
        positions = _find_form_positions(sf_tokens, tokens)

        if not positions:
            distances.append(0.0)
            continue

        start = positions[0]
        min_dist: int | None = None
        for idx, tok in enumerate(tokens):
            if tok.lower() in STATIC_VERB_SET:
                d = abs(idx - start)
                if min_dist is None or d < min_dist:
                    min_dist = d

        distances.append(0.0 if min_dist is None else float(min_dist))

    if not distances:
        return 0.0
    return round(sum(distances) / len(distances), 6)


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


def write_atomic(path: Path, content: str) -> None:
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
# Data loading
# ──────────────────────────────────────────────────────────────

def load_pass2_stats() -> list[dict[str, Any]]:
    if not PASS2_STATS.exists():
        raise FileNotFoundError(f"Missing Pass 2 stats: {PASS2_STATS}")
    records: list[dict[str, Any]] = []
    with PASS2_STATS.open(encoding="utf-8") as fh:
        for line_num, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"surface_form_stats.jsonl line {line_num}: {exc}"
                ) from exc
    return records


def load_artifacts() -> tuple[list[dict[str, Any]], list[str]]:
    """Load all Pass 1 artifacts. Returns (artifacts, batch_file_hashes)."""
    if not ARTIFACTS_ROOT.exists():
        raise FileNotFoundError(f"Missing artifacts directory: {ARTIFACTS_ROOT}")
    batches = sorted(ARTIFACTS_ROOT.glob("batch_*.jsonl"))
    if not batches:
        raise FileNotFoundError(f"No batch_*.jsonl files in {ARTIFACTS_ROOT}")

    artifacts: list[dict[str, Any]] = []
    hashes: list[str] = []

    for bp in batches:
        print(f"  {bp.name} ...", end=" ", flush=True)
        file_hash = sha256_of_file(bp)
        hashes.append(file_hash)
        count_before = len(artifacts)
        with bp.open(encoding="utf-8") as fh:
            for line_num, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    artifacts.append(json.loads(raw))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{bp.name} line {line_num}: {exc}") from exc
        print(f"{len(artifacts) - count_before} artifacts")

    return artifacts, hashes


# ──────────────────────────────────────────────────────────────
# Signal computation helpers
# ──────────────────────────────────────────────────────────────

def extract_location_entities(quote: str, exclude_sf: str) -> set[str]:
    """
    Heuristic: capitalized phrases immediately following location prepositions.
    Excludes the surface_form itself to prevent self-reference inflation.
    """
    entities: set[str] = set()
    exclude_lower = exclude_sf.lower()
    for m in _LOCATION_PREP_RE.finditer(quote):
        loc = m.group(1).strip()
        if loc.lower() != exclude_lower:
            entities.add(loc)
    return entities


def compute_signals(
    pass2_records: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    batch_hashes: list[str],
    pass2_hash: str,
    timestamp: str,
) -> list[dict[str, Any]]:
    """Compute 10 signal fields for each surface_form in pass2_records."""

    total_artifacts = len(artifacts)

    # Index artifacts by surface_form — O(N).
    # Pass 2 stats use normalized keys (Fix 2); index under both original and
    # normalized forms so lookup always succeeds for merged plural variants.
    print("[compute] indexing artifacts by surface_form ...", end=" ", flush=True)
    arts_by_sf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_chapters: set[str] = set()
    sf_set_in_pass2 = {r["surface_form"] for r in pass2_records}
    for art in artifacts:
        sf_orig = art["surface_form"]
        # Always index under the original form.
        arts_by_sf[sf_orig].append(art)
        # Also index under the normalized form if it differs and is in pass2.
        sf_norm = _normalize_for_index(sf_orig)
        if sf_norm != sf_orig and sf_norm in sf_set_in_pass2:
            arts_by_sf[sf_norm].append(art)
        all_chapters.add(art["chapter"])
    print(f"{len(arts_by_sf)} forms indexed")

    # Sorted chapter index for chapter_distribution (deterministic)
    sorted_chapters = sorted(all_chapters)
    chapter_to_idx: dict[str, int] = {ch: i for i, ch in enumerate(sorted_chapters)}
    total_chapters = len(sorted_chapters)

    print(
        f"[compute] corpus: {total_artifacts:,} artifacts, "
        f"{total_chapters} chapters, {len(pass2_records):,} surface_forms"
    )
    print("[compute] computing signals ...", end=" ", flush=True)

    records: list[dict[str, Any]] = []

    for p2 in pass2_records:
        sf: str = p2["surface_form"]
        arts = arts_by_sf.get(sf, [])

        total_mentions: int = p2["total_mentions"]
        chapter_count: int = p2["chapter_count"]
        speech_count: int = p2["speech_count"]
        action_count: int = p2["action_count"]
        first_seen: str = p2["first_seen_chapter"]
        last_seen: str = p2["last_seen_chapter"]

        # ── 1. mention_density ────────────────────────────────
        mention_density = round(total_mentions / max(1, total_artifacts), 8)

        # ── 2. chapter_distribution ───────────────────────────
        min_chapter_idx = chapter_to_idx.get(first_seen, 0)
        max_chapter_idx = chapter_to_idx.get(last_seen, total_chapters - 1)
        spread_ratio = round(
            (max_chapter_idx - min_chapter_idx) / max(1, total_chapters - 1), 6
        )
        art_chapter_idxs = [chapter_to_idx.get(a["chapter"], 0) for a in arts]
        if art_chapter_idxs:
            mean_idx = sum(art_chapter_idxs) / len(art_chapter_idxs)
            chapter_variance = round(
                sum((idx - mean_idx) ** 2 for idx in art_chapter_idxs)
                / len(art_chapter_idxs),
                6,
            )
        else:
            chapter_variance = 0.0
        chapter_distribution = {
            "min_chapter_idx": min_chapter_idx,
            "max_chapter_idx": max_chapter_idx,
            "spread_ratio": spread_ratio,
            "chapter_variance": chapter_variance,
        }

        # ── 3. speech_ratio ───────────────────────────────────
        speech_ratio = round(speech_count / max(1, total_mentions), 6)

        # ── 4. action_ratio ───────────────────────────────────
        action_ratio = round(action_count / max(1, total_mentions), 6)

        # ── 5. quote_context_count ────────────────────────────
        unique_quotes: set[str] = {a["surrounding_quote"] for a in arts}
        quote_context_count = len(unique_quotes)

        # ── 6. monologue_viability_score ──────────────────────
        # speech_ratio * log2(total_mentions) / chapter_count, capped at 1.0
        raw_mvs = (
            speech_ratio
            * math.log2(max(1, total_mentions))
            / max(1, chapter_count)
        )
        monologue_viability_score = round(min(1.0, raw_mvs), 6)

        # ── 7. collective_fragmentation_score ─────────────────
        chapter_counts = Counter(a["chapter"] for a in arts)
        max_in_single = max(chapter_counts.values()) if chapter_counts else 0
        collective_fragmentation_score = round(
            1.0 - (max_in_single / max(1, total_mentions)), 6
        )

        # ── 8. conceptual_drift_score ─────────────────────────
        # Proportion of mentions with a unique surrounding_quote context.
        conceptual_drift_score = round(
            min(1.0, len(unique_quotes) / max(1, total_mentions)), 6
        )

        # ── 9. sparse_reference_score ─────────────────────────
        sparse_reference_score = round(1.0 / (chapter_count + 1), 6)

        # ── 10. location_drift_score ──────────────────────────
        # Distinct location entities found in surrounding_quotes / total_mentions.
        all_locs: set[str] = set()
        for a in arts:
            all_locs.update(extract_location_entities(a["surrounding_quote"], sf))
        location_drift_score = round(
            min(1.0, len(all_locs) / max(1, total_mentions)), 6
        )

        # ── Fix 3: Proximity metrics ──────────────────────────
        proximity_cooccurrence = compute_proximity_cooccurrence(arts, sf)
        avg_verb_distance = compute_avg_verb_distance(arts, sf)

        records.append({
            "surface_form": sf,
            "total_mentions": total_mentions,
            "chapter_count": chapter_count,
            "mention_density": mention_density,
            "chapter_distribution": chapter_distribution,
            "speech_ratio": speech_ratio,
            "action_ratio": action_ratio,
            "quote_context_count": quote_context_count,
            "monologue_viability_score": monologue_viability_score,
            "collective_fragmentation_score": collective_fragmentation_score,
            "conceptual_drift_score": conceptual_drift_score,
            "sparse_reference_score": sparse_reference_score,
            "location_drift_score": location_drift_score,
            "proximity_cooccurrence": proximity_cooccurrence,
            "avg_verb_distance": avg_verb_distance,
            "provisional": True,
            "audit_only": True,
            "heuristic_approximation": True,
            "computation_timestamp": timestamp,
            "input_batch_hashes": batch_hashes,
            "pass2_stats_hash": pass2_hash,
        })

    print(f"{len(records)} records computed")

    # Deterministic sort: lexicographic by surface_form
    records.sort(key=lambda r: r["surface_form"])
    return records


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Identity signal math — 10 deterministic signal fields per surface_form."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and preview sample records without writing.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Compute and write raw/math/identity_signal_stats.jsonl.",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()

    # Schema contract check
    if not PASS2_SCHEMA.exists():
        print(f"[EXIT 1] Missing required schema: {PASS2_SCHEMA}", file=sys.stderr)
        return 1
    print(f"[init] schema: {PASS2_SCHEMA.name}")

    # Load Pass 2 stats
    print(f"[load] {PASS2_STATS.name} ...", end=" ", flush=True)
    try:
        pass2_records = load_pass2_stats()
    except (FileNotFoundError, ValueError) as exc:
        print(f"\n[EXIT 1] {exc}", file=sys.stderr)
        return 1
    print(f"{len(pass2_records)} surface_forms")

    pass2_hash = sha256_of_file(PASS2_STATS)

    # Extract expected batch hashes from Pass 2 stats for coherence check
    expected_hashes: list[str] | None = None
    if pass2_records and "input_batch_hashes" in pass2_records[0]:
        expected_hashes = pass2_records[0]["input_batch_hashes"]

    # Load Pass 1 artifacts
    print("[load] Pass 1 artifacts:")
    try:
        artifacts, batch_hashes = load_artifacts()
    except (FileNotFoundError, ValueError) as exc:
        print(f"[EXIT 1] {exc}", file=sys.stderr)
        return 1
    print(f"[load] total: {len(artifacts):,} artifacts, {len(batch_hashes)} batches")

    # Validate batch hashes against those consumed by Pass 2
    if expected_hashes is not None and sorted(batch_hashes) != sorted(expected_hashes):
        print("[EXIT 2] Batch hash mismatch: Pass 1 batches differ from those "
              "consumed by Pass 2. Re-run pass2_math.py --apply first.")
        print(f"  pass2 expected: {expected_hashes}")
        print(f"  found now:      {batch_hashes}")
        return 2

    # Coherence check: every pass2 surface_form must be reachable from artifacts.
    # Compare against normalized artifact forms because pass2 uses normalized keys.
    sf_in_artifacts_norm: set[str] = {_normalize_for_index(a["surface_form"]) for a in artifacts}
    sf_in_pass2: set[str] = {r["surface_form"] for r in pass2_records}
    ghost_forms = sf_in_pass2 - sf_in_artifacts_norm
    if ghost_forms:
        sample = sorted(ghost_forms)[:5]
        print(f"[EXIT 2] Input incoherence: {len(ghost_forms)} surface_form(s) "
              f"in Pass 2 stats have no reachable Pass 1 artifacts. Sample: {sample}")
        return 2

    # Compute signals
    timestamp = now_iso()
    records = compute_signals(
        pass2_records, artifacts, batch_hashes, pass2_hash, timestamp
    )

    # Verify record count matches pass2
    if len(records) != len(pass2_records):
        print(
            f"[EXIT 1] Record count mismatch: computed {len(records)} "
            f"but expected {len(pass2_records)}",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        sample_count = min(5, len(records))
        print(f"\n[DRY-RUN] Sample ({sample_count} of {len(records)} records):")
        for r in records[:sample_count]:
            display = dict(r)
            display["input_batch_hashes"] = (
                display["input_batch_hashes"][:1] + ["..."]
                if len(display.get("input_batch_hashes", [])) > 1
                else display.get("input_batch_hashes", [])
            )
            print(json.dumps(display, ensure_ascii=False, indent=2))
        print(f"\n[exit] EXIT 0")
        return 0

    # Write output atomically
    output_path = MATH_ROOT / OUTPUT_FILENAME
    content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    try:
        write_atomic(output_path, content)
    except OSError as exc:
        print(f"[EXIT 1] Failed to write output: {exc}", file=sys.stderr)
        return 1

    print(f"\n[complete]")
    print(f"  output: {output_path.relative_to(MRLORE_ROOT)}")
    print(f"  records: {len(records):,}")
    print(f"  total_size: {len(content):,} bytes")
    print("[exit] EXIT 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
