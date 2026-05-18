#!/usr/bin/env python3
"""
MrLore v2 — Phase 6.0A Pass 1 Artifact Extractor

Scans raw chapters line-by-line and emits surface-token artifact records
conforming to schema/ARTIFACT_SCHEMA.md.

Contract:
- Reads schema/ARTIFACT_SCHEMA.md before any extraction.
- Pass 1 only: no classification, no confidence scoring, no entity types,
  no wiki writes, no fields beyond §2 and §3 of the schema.
- audit_only: true and provisional: true hardcoded on all outputs.
- Output: raw/artifacts/batch_<run_id>.jsonl
- Index: raw/artifacts/processed.json  (chapter source_hash → batch_id)
- EXIT 0: clean run, batch written (or previewed in --dry-run).
- EXIT 1: structural failure — missing schema, unreadable source, file error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MRLORE_ROOT = Path(__file__).resolve().parents[1]
RAW_CHAPTERS = MRLORE_ROOT / "raw" / "chapters"
SCHEMA_DIR = MRLORE_ROOT / "schema"
ARTIFACTS_ROOT = MRLORE_ROOT / "raw" / "artifacts"
LOGS_ROOT = MRLORE_ROOT / "logs"

ARTIFACT_SCHEMA = SCHEMA_DIR / "ARTIFACT_SCHEMA.md"
PROCESSED_INDEX = ARTIFACTS_ROOT / "processed.json"

SOURCE_EXTS = {".md", ".txt"}
EXTRACTOR_ID = "artifact_extractor/0.1.0"


# ──────────────────────────────────────────────────────────────
# Token extraction — Pass 1 patterns
# ──────────────────────────────────────────────────────────────

# Multi-word: 2+ consecutive words each starting with a capital letter.
# Intentionally permissive — "The Sage", "First Tongue", "Deep Grammar",
# "OPENING MOVEMENT", "Aeon Keepers", "Cosmic Infrastructure Guardians".
_MULTI_CAP_RE = re.compile(
    r'\b[A-Z][A-Za-z\'’\-]*(?:[ ]+[A-Z][A-Za-z\'’\-]*)+\b'
)

# Single-word: starts with capital, at least 2 chars total.
# Matches "Torrhen", "Zephyr", "Earth", "Sage", and ALL-CAPS like "RCS".
_SINGLE_CAP_RE = re.compile(r"\b[A-Z][A-Za-z'’\-]{1,}\b")

# Sentence-end boundary for surrounding_quote trimming.
_SENTENCE_END_RE = re.compile(r'(?<=[.!?])\s+')

# Fix 1: Expanded stop-word set.  Comparison is done on the lowercased token.
STOP_WORD_SET = frozenset({
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
    # Fix 1 additions — previously slipping through
    'across', 'almost', 'alone', 'along', 'already', 'always',
    'away', 'back', 'below', 'either', 'else',
    'herself', 'himself', 'itself', 'myself', 'ourselves', 'themselves', 'yourself',
    'however', 'let', 'like', 'made', 'many', 'near', 'never',
    'new', 'next', 'off', 'once', 'own', 're', 'same',
    'whether', 'within', 'without', 'till', 'too',
})

# Fix 1: All-caps single-word tokens are filtered unless in this whitelist.
CANON_ACRONYM_WHITELIST = frozenset({
    'RCS', 'BH', 'AH', 'TTS', 'NLP', 'AI', 'GPS',
})

# Match single-word all-caps tokens (no spaces, 2+ uppercase letters).
_ALL_CAPS_ONLY_RE = re.compile(r'^[A-Z]{2,}$')


def extract_tokens(
    line: str,
    drop_log: "list[tuple[str, str]] | None" = None,
) -> list[tuple[str, int, int]]:
    """
    Return (surface_form, char_start, char_end) tuples for all
    proper-noun candidates in one source line.

    Multi-word capitalized phrases take priority; single words are only
    extracted if they fall outside a matched phrase and are not stop words
    or unwhitelisted all-caps tokens.

    drop_log: if provided, (surface_form, reason) pairs are appended for
    every token discarded by Fix 1 filters.
    """
    tokens: list[tuple[str, int, int]] = []
    covered: set[int] = set()

    # Multi-word phrases first.
    for m in _MULTI_CAP_RE.finditer(line):
        tokens.append((m.group(0), m.start(), m.end()))
        covered.update(range(m.start(), m.end()))

    # Single-word tokens not already inside a phrase.
    for m in _SINGLE_CAP_RE.finditer(line):
        if any(i in covered for i in range(m.start(), m.end())):
            continue
        word = m.group(0)
        if word.lower() in STOP_WORD_SET:
            if drop_log is not None:
                drop_log.append((word, "stop_word"))
            continue
        if _ALL_CAPS_ONLY_RE.match(word) and word not in CANON_ACRONYM_WHITELIST:
            if drop_log is not None:
                drop_log.append((word, "all_caps_unwhitelisted"))
            continue
        tokens.append((word, m.start(), m.end()))

    return sorted(tokens, key=lambda t: t[1])


def surrounding_quote(line: str, max_sentences: int = 3) -> str:
    """
    Return up to `max_sentences` sentences from the raw line.
    Characters are taken verbatim from the source; only sentence-boundary
    truncation is applied if the line contains more sentences than the limit.
    """
    stripped = line.rstrip('\n\r')
    parts = _SENTENCE_END_RE.split(stripped)
    if len(parts) <= max_sentences:
        return stripped
    # Rejoin exactly max_sentences parts.  The separator used here is a
    # single space, matching the most common prose pattern.
    return ' '.join(parts[:max_sentences])


# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────

def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def artifact_id(source_file: str, line_num: int, char_start: int, surface: str) -> str:
    """Deterministic artifact ID per unique token occurrence."""
    key = f"{source_file}:{line_num}:{char_start}:{surface}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"art_{h}"


def make_chapter_id(stem: str) -> str:
    """
    Derive the chapter identifier in <book_id>_ch<chapter_num> format.
    E.g. 'book_04_sage_saga_021_the_first_lesson' → 'book_04_sage_saga_ch021'
    """
    m = re.search(r'^(.*?)_(\d{3})_', stem)
    if m:
        book_part = m.group(1).lower()
        chap_num = m.group(2)
        return f"{book_part}_ch{chap_num}"
    return re.sub(r'[^A-Za-z0-9_]', '_', stem).lower()


def slugify_book(stem: str) -> str:
    """Extract the book_id portion of the filename stem."""
    m = re.search(r'^(.*?)_\d{3}_', stem)
    if m:
        return m.group(1).lower()
    return re.sub(r'[^A-Za-z0-9_]', '_', stem).lower()


# ──────────────────────────────────────────────────────────────
# Chapter discovery
# ──────────────────────────────────────────────────────────────

def discover_chapters() -> list[Path]:
    if not RAW_CHAPTERS.exists():
        raise FileNotFoundError(f"Missing raw chapters directory: {RAW_CHAPTERS}")
    return sorted(
        p for p in RAW_CHAPTERS.iterdir()
        if p.is_file() and p.suffix.lower() in SOURCE_EXTS
    )


# ──────────────────────────────────────────────────────────────
# Processed-chapters index
# ──────────────────────────────────────────────────────────────

def load_processed_index() -> dict[str, str]:
    """Return {source_hash: batch_id} from the index file, or {} if absent."""
    if not PROCESSED_INDEX.exists():
        return {}
    try:
        return json.loads(PROCESSED_INDEX.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_processed_index(index: dict[str, str]) -> None:
    ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    PROCESSED_INDEX.write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ──────────────────────────────────────────────────────────────
# Core extraction
# ──────────────────────────────────────────────────────────────

def extract_chapter(
    chapter_path: Path,
    run_id: str,
    timestamp: str,
    chronological_start: int,
) -> tuple[list[dict[str, Any]], int, int]:
    """
    Extract all Pass 1 artifacts from one chapter file.
    Returns (artifacts, next_chronological_order, dropped_token_count).

    Each artifact contains exactly the fields defined in §2 and §3 of
    ARTIFACT_SCHEMA.md — no additional fields.
    """
    text = chapter_path.read_text(encoding="utf-8", errors="replace")
    source_hash = sha256_of_text(text)
    source_file = chapter_path.as_posix()
    chapter_id = make_chapter_id(chapter_path.stem)
    lines = text.splitlines()

    artifacts: list[dict[str, Any]] = []
    chron = chronological_start
    chapter_drops: list[tuple[str, int, str]] = []  # (surface_form, line_num, reason)

    for line_num_0, raw_line in enumerate(lines):
        line_num = line_num_0 + 1  # 1-indexed
        line_drop_log: list[tuple[str, str]] = []
        tokens = extract_tokens(raw_line, drop_log=line_drop_log)
        for sf, reason in line_drop_log:
            chapter_drops.append((sf, line_num, reason))
        if not tokens:
            continue

        quote = surrounding_quote(raw_line)

        for surface, char_start, char_end in tokens:
            art_id = artifact_id(source_file, line_num, char_start, surface)
            artifact: dict[str, Any] = {
                # §2 required fields
                "artifact_id": art_id,
                "surface_form": surface,
                "source_line": line_num,
                "source_span": f"{line_num}-{line_num}",
                "chapter": chapter_id,
                "chronological_order": chron,
                "surrounding_quote": quote,
                # §3 system metadata
                "extractor_id": EXTRACTOR_ID,
                "extraction_timestamp": timestamp,
                "source_file": source_file,
                "source_hash": source_hash,
                "audit_only": True,
                "provisional": True,
            }
            artifacts.append(artifact)
            chron += 1

    if chapter_drops:
        print(f"  [filter] dropped {len(chapter_drops)} token(s)")
        for sf, lnum, reason in chapter_drops[:5]:
            print(f"    L{lnum:>4}  {sf!r:25s}  ({reason})")
        if len(chapter_drops) > 5:
            print(f"    ... and {len(chapter_drops) - 5} more")

    return artifacts, chron, len(chapter_drops)


# ──────────────────────────────────────────────────────────────
# JSONL output
# ──────────────────────────────────────────────────────────────

def write_batch(batch_path: Path, artifacts: list[dict[str, Any]]) -> None:
    ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)
    with batch_path.open("w", encoding="utf-8") as fh:
        for art in artifacts:
            fh.write(json.dumps(art, ensure_ascii=False) + "\n")


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pass 1 artifact extractor — surface tokens from raw chapters."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview artifacts without writing files.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write batch JSONL to raw/artifacts/.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of chapters processed."
    )
    parser.add_argument(
        "--chapter", type=str, default=None, help="Process one chapter by filename substring."
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()

    if args.limit is not None and args.limit < 1:
        print("[error] --limit must be >= 1", file=sys.stderr)
        return 1

    # ── schema contract check ──────────────────────────────────
    if not ARTIFACT_SCHEMA.exists():
        print(f"[EXIT 1] Missing required schema: {ARTIFACT_SCHEMA}", file=sys.stderr)
        return 1

    schema_text = ARTIFACT_SCHEMA.read_text(encoding="utf-8", errors="replace")

    # ── discover chapters ──────────────────────────────────────
    try:
        chapters = discover_chapters()
    except FileNotFoundError as exc:
        print(f"[EXIT 1] {exc}", file=sys.stderr)
        return 1

    if args.chapter:
        chapters = [p for p in chapters if args.chapter in p.name]
    if args.limit is not None:
        chapters = chapters[:args.limit]
    if not chapters:
        print("[error] No chapters matched the requested input.", file=sys.stderr)
        return 1

    # ── load skip index ────────────────────────────────────────
    processed = load_processed_index()

    run_id = f"batch_{now_stamp()}"
    timestamp = now_iso()
    ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"[init] run_id={run_id}")
    print(f"[init] chapters_found={len(chapters)}")
    print(f"[init] mode={'dry-run' if args.dry_run else 'apply'}")
    print(f"[init] schema={ARTIFACT_SCHEMA.name} ({len(schema_text)} chars)")

    all_artifacts: list[dict[str, Any]] = []
    chronological_order = 1
    skipped = 0
    total_dropped = 0

    for chapter_path in chapters:
        # ── skip already-indexed chapters ──────────────────────
        try:
            text_preview = chapter_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"[EXIT 1] Cannot read {chapter_path}: {exc}", file=sys.stderr)
            return 1

        source_hash = sha256_of_text(text_preview)
        if source_hash in processed:
            batch_ref = processed[source_hash]
            print(f"[skip] {chapter_path.name} (in {batch_ref})")
            skipped += 1
            continue

        chapter_id = make_chapter_id(chapter_path.stem)
        print(f"[chapter] {chapter_path.name}  →  {chapter_id}")

        try:
            artifacts, chronological_order, ch_drops = extract_chapter(
                chapter_path, run_id, timestamp, chronological_order
            )
        except OSError as exc:
            print(f"[EXIT 1] Extraction failed for {chapter_path}: {exc}", file=sys.stderr)
            return 1

        all_artifacts.extend(artifacts)
        total_dropped += ch_drops
        print(f"  artifacts={len(artifacts)}")

    # ── summary ────────────────────────────────────────────────
    print(f"\n[complete]")
    print(f"  total_artifacts={len(all_artifacts)}")
    print(f"  total_dropped={total_dropped}")
    print(f"  chapters_skipped={skipped}")

    if not all_artifacts:
        print("[exit] EXIT 0 (nothing new to extract)")
        return 0

    if args.dry_run:
        print(f"\n[DRY-RUN] Preview (first 5 of {len(all_artifacts)} artifacts):")
        for art in all_artifacts[:5]:
            print(f"  [{art['chronological_order']:>6}]"
                  f"  {art['artifact_id']}"
                  f"  L{art['source_line']:>4}"
                  f"  {art['surface_form']!r}")
        print(f"\n[DRY-RUN] First artifact full record:")
        print(json.dumps(all_artifacts[0], indent=2, ensure_ascii=False))
        print(f"\n[exit] EXIT 0")
        return 0

    # ── --apply: write batch ───────────────────────────────────
    batch_path = ARTIFACTS_ROOT / f"{run_id}.jsonl"
    try:
        write_batch(batch_path, all_artifacts)
    except OSError as exc:
        print(f"[EXIT 1] Failed to write batch: {exc}", file=sys.stderr)
        return 1

    # ── update index ───────────────────────────────────────────
    for art in all_artifacts:
        processed[art["source_hash"]] = run_id
    try:
        save_processed_index(processed)
    except OSError as exc:
        print(f"[warn] Could not update index: {exc}")

    print(f"  batch={batch_path.relative_to(MRLORE_ROOT)}")
    print(f"  index={PROCESSED_INDEX.relative_to(MRLORE_ROOT)}")
    print("[exit] EXIT 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
