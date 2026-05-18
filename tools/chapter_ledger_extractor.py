#!/usr/bin/env python3
"""
MrLore v2 — Phase 6.0A Chapter Ledger Extractor

Reads Tier 0 source chapters and emits chapter extraction ledgers conforming
to schema/CHAPTER_LEDGER_SCHEMA.md.

Contract:
- Reads schema/CHAPTER_LEDGER_SCHEMA.md before any extraction.
- Never writes to wiki/ under any circumstances.
- audit_only: true on all outputs.
- provisional: true on all outputs.
- EXIT 0 = all entries valid, confidence >= medium → ledger written to raw/ledgers/.
- EXIT 1 = structural failure (missing schema, chunk job crash, malformed envelope)
           → halt immediately, diagnostic written to logs/.
- EXIT 2 = safety stop (any low-confidence entry, unresolvable span,
           canon-breaking contradiction) → ledger staged in raw/ledgers_pending/,
           processing of remaining chapters continues.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MRLORE_ROOT = Path(__file__).resolve().parents[1]
RAW_CHAPTERS = MRLORE_ROOT / "raw" / "chapters"
SCHEMA_DIR = MRLORE_ROOT / "schema"
LEDGERS_ROOT = MRLORE_ROOT / "raw" / "ledgers"
LEDGERS_PENDING = MRLORE_ROOT / "raw" / "ledgers_pending"
LEDGER_CACHE_DIR = MRLORE_ROOT / "raw" / "ledgers_cache"
LOGS_ROOT = MRLORE_ROOT / "logs"

CHAPTER_LEDGER_SCHEMA = SCHEMA_DIR / "CHAPTER_LEDGER_SCHEMA.md"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3:latest"

SOURCE_EXTS = {".md", ".txt"}
MAX_CHARS_PER_CHUNK = 9000
EXTRACTOR_ID = "chapter_ledger_extractor/0.1.0"

VALID_OBJECT_CLASSES = {
    "character_presence",
    "location_presence",
    "faction_presence",
    "object_presence",
    "spoken_claim",
    "action_taken",
    "state_change",
    "relationship_observed",
    "world_state_descriptor",
    "timeline_marker",
    "unresolved_term",
    "contradiction_candidate",
    "group_agency_check",
}

VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_INTERACTION_TYPE = {"active", "passive", "referenced", "implied"}
VALID_SPATIAL_RELATION = {"interior", "exterior", "transit", "referenced", "unknown"}
VALID_ALIGNMENT = {"protagonist", "antagonist", "neutral", "unknown"}
VALID_MANIFESTATION = {"named_member", "banner", "decree", "rumor", "artifact"}
VALID_OBJECT_STATE = {"intact", "damaged", "hidden", "active", "inert", "unknown"}
VALID_VERACITY = {"stated", "contested", "confirmed", "refuted", "unknown"}
VALID_EVIDENCE_STRENGTH = {"explicit", "implied", "inferred"}
VALID_WORLD_DOMAIN = {
    "atmospheric", "environmental", "cosmic", "political",
    "metaphysical", "technological", "factional",
}
VALID_PRECISION = {"exact_day", "approximate", "era_only", "unordered"}
VALID_DRIFT_TYPE = {"spelling", "alias", "faction_split", "era_split", "transcription", "TTS"}
VALID_SEVERITY = {"cosmetic", "structural", "canon-breaking"}
VALID_GROUP_TYPE = {
    "faction", "collective_character", "military_unit", "crowd", "species", "unknown",
}
VALID_AGENCY_SIGNAL = {
    "shared_command", "coordinated_motion", "shared_speech",
    "collective_decision", "single_identity_reference", "unknown",
}
VALID_IDENTITY_IMPLICATION = {"individuals_only", "collective_actor", "ambiguous"}

OBJECT_CLASS_ORDER = [
    "character_presence",
    "faction_presence",
    "location_presence",
    "object_presence",
    "action_taken",
    "spoken_claim",
    "state_change",
    "relationship_observed",
    "world_state_descriptor",
    "timeline_marker",
    "group_agency_check",
    "unresolved_term",
    "contradiction_candidate",
]

_LOG_LOCK = threading.Lock()


# ──────────────────────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────────────────────

class LedgerError(Exception):
    """EXIT 1 condition: structural failure, halt immediately."""


class OllamaTimeout(Exception):
    """Ollama HTTP timeout; eligible for one retry."""


# ──────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ChapterInfo:
    path: Path
    book_id: str
    book_number: int | None
    chapter_id: str
    chapter_title: str
    source_hash: str


@dataclass
class ChunkJob:
    chapter: ChapterInfo
    chunk_index: int   # 1-based
    chunk_total: int
    chunk_text: str


@dataclass
class ChunkResult:
    job: ChunkJob
    payload: dict[str, Any] | None
    error: str | None


# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────

def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def log_line(log_path: Path, message: str) -> None:
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(message.rstrip() + "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def sha256_short(text: str) -> str:
    return sha256_text(text)[:8]


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.lower() or "unresolved"


def coerce_enum(value: Any, valid: set[str], fallback: str) -> str:
    text = str(value).strip().lower() if value is not None else ""
    return text if text in valid else fallback


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def ensure_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


# ──────────────────────────────────────────────────────────────
# Chapter parsing
# ──────────────────────────────────────────────────────────────

def parse_chapter_info(path: Path, text: str) -> ChapterInfo:
    name = path.stem
    book_match = re.search(r"(book[_-](\d+)[A-Za-z0-9_-]*)", name, re.IGNORECASE)
    if book_match:
        book_id = slugify(book_match.group(1))
        try:
            book_number = int(book_match.group(2))
        except ValueError:
            book_number = None
    else:
        book_id = "unknown_book"
        book_number = None

    chapter_match = re.search(r"_(\d{3})_([A-Za-z0-9_-]+)$", name)
    if chapter_match:
        chapter_id = f"{chapter_match.group(1)}_{slugify(chapter_match.group(2))}"
        chapter_title = chapter_match.group(2).replace("_", " ").replace("-", " ").title()
    else:
        chapter_id = slugify(name)
        chapter_title = name.replace("_", " ").replace("-", " ").title()

    return ChapterInfo(
        path=path,
        book_id=book_id,
        book_number=book_number,
        chapter_id=chapter_id,
        chapter_title=chapter_title,
        source_hash=sha256_text(text),
    )


def discover_chapters() -> list[Path]:
    if not RAW_CHAPTERS.exists():
        raise LedgerError(f"Missing raw chapters directory: {RAW_CHAPTERS}")
    chapters = [
        p for p in RAW_CHAPTERS.iterdir()
        if p.is_file() and p.suffix.lower() in SOURCE_EXTS
    ]
    return sorted(chapters)


# ──────────────────────────────────────────────────────────────
# Semantic chunking (header → paragraph → sentence)
# ──────────────────────────────────────────────────────────────

_HEADER_RE = re.compile(r"(?m)^(?=#{2,3} )")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])[ \t]+")


def _split_at_sentences(text: str, max_chars: int) -> list[str]:
    parts = _SENTENCE_END_RE.split(text)
    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = (current + " " + part).strip() if current else part
        if current and len(candidate) > max_chars:
            chunks.append(current.strip())
            current = part
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text]


def chunk_text(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> list[str]:
    sections = [s for s in _HEADER_RE.split(text) if s.strip()]
    if not sections:
        sections = [text]
    chunks: list[str] = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section.strip())
            continue
        paragraphs = [p.strip() for p in section.split("\n\n") if p.strip()]
        current = ""
        for para in paragraphs:
            if len(para) > max_chars:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(_split_at_sentences(para, max_chars))
            elif current and len(current) + 2 + len(para) > max_chars:
                chunks.append(current.strip())
                current = para
            else:
                current = (current + "\n\n" + para).lstrip("\n") if current else para
        if current.strip():
            chunks.append(current.strip())
    return [c for c in chunks if c]


# ──────────────────────────────────────────────────────────────
# Chunk-level cache
# ──────────────────────────────────────────────────────────────

def cache_path_for(chapter: ChapterInfo, chunk_index: int) -> Path:
    return LEDGER_CACHE_DIR / f"{chapter.source_hash}_{chunk_index}.json"


def read_chunk_cache(chapter: ChapterInfo, chunk_index: int) -> dict[str, Any] | None:
    path = cache_path_for(chapter, chunk_index)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("ledger_entries"), list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def write_chunk_cache(chapter: ChapterInfo, chunk_index: int, payload: dict[str, Any]) -> None:
    if not isinstance(payload.get("ledger_entries"), list):
        return
    try:
        LEDGER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path_for(chapter, chunk_index).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def clear_chapter_cache(chapter: ChapterInfo) -> None:
    if not LEDGER_CACHE_DIR.exists():
        return
    for path in LEDGER_CACHE_DIR.glob(f"{chapter.source_hash}_*.json"):
        try:
            path.unlink()
        except OSError:
            pass


# ──────────────────────────────────────────────────────────────
# JSON truncation recovery
# ──────────────────────────────────────────────────────────────

def repair_truncated_ledger_json(raw: str) -> dict[str, Any] | None:
    """Recover ledger_entries from a truncated Ollama JSON response."""
    start = raw.find('"ledger_entries"')
    if start == -1:
        return None
    bracket = raw.find('[', start)
    if bracket == -1:
        return None

    entries: list[Any] = []
    pos = bracket + 1
    depth = 0
    in_string = False
    escape_next = False
    obj_start: int | None = None

    while pos < len(raw):
        ch = raw[pos]
        if escape_next:
            escape_next = False
            pos += 1
            continue
        if ch == '\\' and in_string:
            escape_next = True
            pos += 1
            continue
        if ch == '"':
            in_string = not in_string
            pos += 1
            continue
        if in_string:
            pos += 1
            continue
        if ch == '{':
            if depth == 0:
                obj_start = pos
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and obj_start is not None:
                try:
                    obj = json.loads(raw[obj_start:pos + 1])
                    if isinstance(obj, dict):
                        entries.append(obj)
                except json.JSONDecodeError:
                    pass
                obj_start = None
        elif ch == ']' and depth == 0:
            break
        pos += 1

    if not entries:
        return None
    return {"ledger_entries": entries}


# ──────────────────────────────────────────────────────────────
# Ollama
# ──────────────────────────────────────────────────────────────

def ollama_json(prompt: str, timeout_sec: int = 300) -> dict[str, Any]:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "num_predict": -1,
        },
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise OllamaTimeout(f"Ollama timed out: {exc}") from exc
        raise LedgerError(f"Ollama request failed: {exc}") from exc

    try:
        envelope = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LedgerError(f"Ollama returned non-JSON envelope: {exc}") from exc

    raw_response = envelope.get("response", "")
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise LedgerError("Ollama returned an empty response.")

    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError:
        recovered = repair_truncated_ledger_json(raw_response)
        if recovered and recovered.get("ledger_entries"):
            return recovered
        raise LedgerError(
            f"Ollama response could not be parsed as JSON: {raw_response[:200]!r}"
        )

    if not isinstance(parsed, dict):
        raise LedgerError("Ollama response was not a JSON object.")

    if "ledger_entries" not in parsed:
        recovered = repair_truncated_ledger_json(raw_response)
        if recovered and recovered.get("ledger_entries"):
            return recovered
        raise LedgerError("Ollama response missing 'ledger_entries' key.")

    return parsed


# ──────────────────────────────────────────────────────────────
# Extraction prompt
# ──────────────────────────────────────────────────────────────

def build_ledger_prompt(
    chapter: ChapterInfo,
    chunk: str,
    chunk_index: int,
    chunk_total: int,
) -> str:
    return f"""You are a structured extraction engine for a fantasy fiction corpus.
Extract all observable tokens from the chapter chunk into a JSON ledger.

CHAPTER: {chapter.chapter_title}
BOOK: {chapter.book_id}
CHUNK: {chunk_index} of {chunk_total}

EXTRACT ALL 13 OBJECT CLASSES (omit only if the class has zero evidence in this chunk):

1. character_presence — named or implied characters present or referenced
2. location_presence — named or implied locations
3. faction_presence — named factions, groups, organizations
4. object_presence — named or significant objects, artifacts, items
5. spoken_claim — dialogue, direct speech, stated claims
6. action_taken — actions performed by characters or entities
7. state_change — observable changes in character, location, or world state
8. relationship_observed — observed relationships between entities
9. world_state_descriptor — world-building descriptors (atmospheric, political, cosmic, etc.)
10. timeline_marker — temporal markers, dates, sequence anchors
11. unresolved_term — ambiguous, variant, or unknown terms and names
12. contradiction_candidate — claims that visibly conflict with each other inside this chunk
13. group_agency_check — groups acting with unified will or collective agency

BASE FIELDS (every entry must have all of these):
  object_class: one of the 13 class names above
  extracted_value: the raw claim or token from the prose
  context_quote: exact verbatim 1-3 sentence window from the text — must not be paraphrased
  confidence: "high" (explicit, unambiguous), "medium" (strong context, minor ambiguity), "low" (inferred, fragmented)

CLASS-SPECIFIC FIELDS:
character_presence: entity_name (name as used in prose), arc_context (short tag: north/south/cosmic/mentor/unknown), interaction_type (active|passive|referenced|implied)
location_presence: location_name (name as used in prose), spatial_relation (interior|exterior|transit|referenced|unknown), environmental_state (brief description or empty)
faction_presence: faction_name (name as used in prose), alignment_indicator (protagonist|antagonist|neutral|unknown), manifestation (named_member|banner|decree|rumor|artifact)
object_presence: object_type (category of object), object_name (name or "unnamed"), ownership_or_access (who has it or empty), state (intact|damaged|hidden|active|inert|unknown)
spoken_claim: speaker (who said it), claim_text (what was said), claim_target (who/what it is about), veracity_status (stated|contested|confirmed|refuted|unknown)
action_taken: actor (who acts), action_verb (short verb phrase), target (recipient or empty), outcome_state (observable result or empty)
state_change: subject (what changed), previous_state (before), new_state (after), trigger (what caused it)
relationship_observed: entity_a (first party), entity_b (second party), relation_type (allied|hostile|familial|hierarchical|transactional or other), evidence_strength (explicit|implied|inferred)
world_state_descriptor: domain (atmospheric|environmental|cosmic|political|metaphysical|technological|factional), descriptor_value (brief description), contradicts_existing (true|false), matches_existing (true|false)
timeline_marker: era_label (RCS|BH|AH|relative|unknown), sequence_anchor (e.g. "two years after X"), precision (exact_day|approximate|era_only|unordered)
unresolved_term: term_variant (spelling or name variant as found), canonical_candidate (best guess at canonical form or empty), drift_type (spelling|alias|faction_split|era_split|transcription|TTS), requires_resolution (always true)
contradiction_candidate: conflict_axis (what conflicts: character_behavior|location_state|timeline|terminology|faction_allegiance), claim_a_span (short verbatim quote), claim_b_span (conflicting short verbatim quote), severity_estimate (cosmetic|structural|canon-breaking)
group_agency_check: group_name (name as used), group_type (faction|collective_character|military_unit|crowd|species|unknown), exhibits_unified_action (true|false), unified_action_evidence (quoted or described evidence), agency_signal (shared_command|coordinated_motion|shared_speech|collective_decision|single_identity_reference|unknown), identity_implication (individuals_only|collective_actor|ambiguous)

RULES:
- Extract only from the chunk below. Do not infer from outside knowledge.
- context_quote must be verbatim text — no paraphrasing, no normalization.
- Use confidence "low" only when evidence is genuinely ambiguous or fragmented.
- contradiction_candidate: only flag contradictions visible within this chunk.
- Omit entries for classes with zero evidence.

Respond with JSON only:
{{
  "ledger_entries": [
    {{"object_class": "...", "extracted_value": "...", "context_quote": "...", "confidence": "...", ...class fields...}},
    ...
  ]
}}

CHAPTER CHUNK TEXT:
---
{chunk}
---""".strip()


# ──────────────────────────────────────────────────────────────
# Entry validation and normalisation
# ──────────────────────────────────────────────────────────────

def make_source_span(chapter: ChapterInfo, chunk_index: int, context_quote: str) -> str:
    if context_quote.strip():
        h = sha256_short(context_quote)
        return f"quote_id:{h}_c{chunk_index}"
    return f"{chapter.book_id}_ch{chapter.chapter_id}:unresolvable"


def validate_entry(
    raw: dict[str, Any],
    chapter: ChapterInfo,
    chunk_index: int,
    extraction_timestamp: str,
) -> tuple[dict[str, Any], list[str]]:
    """
    Validate and normalise one raw Ollama-extracted ledger entry.
    Returns (normalised_entry, error_list).
    Errors are collected rather than raised; caller decides exit code.
    """
    errors: list[str] = []

    object_class = str(raw.get("object_class", "")).strip().lower()
    if object_class not in VALID_OBJECT_CLASSES:
        errors.append(f"invalid object_class: {object_class!r}")
        object_class = "unknown"

    extracted_value = str(raw.get("extracted_value", "")).strip()
    if not extracted_value:
        errors.append("missing extracted_value")

    context_quote = str(raw.get("context_quote", "")).strip()
    confidence = coerce_enum(raw.get("confidence"), VALID_CONFIDENCE, "low")

    if not context_quote:
        confidence = "low"
        errors.append("empty context_quote: span unresolvable, confidence forced to low")

    source_span = make_source_span(chapter, chunk_index, context_quote)

    entry: dict[str, Any] = {
        "object_class": object_class,
        "source_span": source_span,
        "confidence": confidence,
        "provisional": True,
        "audit_only": True,
        "extracted_value": extracted_value,
        "context_quote": context_quote,
        "extraction_timestamp": extraction_timestamp,
        "extractor_id": EXTRACTOR_ID,
    }

    if object_class == "character_presence":
        entry["entity_name"] = str(raw.get("entity_name", "")).strip() or "unknown"
        entry["arc_context"] = str(raw.get("arc_context", "")).strip()
        entry["interaction_type"] = coerce_enum(
            raw.get("interaction_type"), VALID_INTERACTION_TYPE, "implied"
        )

    elif object_class == "location_presence":
        entry["location_name"] = str(raw.get("location_name", "")).strip() or "unknown"
        entry["spatial_relation"] = coerce_enum(
            raw.get("spatial_relation"), VALID_SPATIAL_RELATION, "unknown"
        )
        entry["environmental_state"] = str(raw.get("environmental_state", "")).strip()

    elif object_class == "faction_presence":
        entry["faction_name"] = str(raw.get("faction_name", "")).strip() or "unknown"
        entry["alignment_indicator"] = coerce_enum(
            raw.get("alignment_indicator"), VALID_ALIGNMENT, "unknown"
        )
        entry["manifestation"] = coerce_enum(
            raw.get("manifestation"), VALID_MANIFESTATION, "named_member"
        )

    elif object_class == "object_presence":
        entry["object_type"] = str(raw.get("object_type", "")).strip() or "unknown"
        entry["object_name"] = str(raw.get("object_name", "")).strip() or "unnamed"
        entry["ownership_or_access"] = str(raw.get("ownership_or_access", "")).strip()
        entry["state"] = coerce_enum(raw.get("state"), VALID_OBJECT_STATE, "unknown")

    elif object_class == "spoken_claim":
        entry["speaker"] = str(raw.get("speaker", "")).strip() or "unknown"
        entry["claim_text"] = str(raw.get("claim_text", "")).strip()
        entry["claim_target"] = str(raw.get("claim_target", "")).strip()
        entry["veracity_status"] = coerce_enum(
            raw.get("veracity_status"), VALID_VERACITY, "stated"
        )

    elif object_class == "action_taken":
        entry["actor"] = str(raw.get("actor", "")).strip() or "unknown"
        entry["action_verb"] = str(raw.get("action_verb", "")).strip()
        entry["target"] = str(raw.get("target", "")).strip()
        entry["outcome_state"] = str(raw.get("outcome_state", "")).strip()

    elif object_class == "state_change":
        entry["subject"] = str(raw.get("subject", "")).strip() or "unknown"
        entry["previous_state"] = str(raw.get("previous_state", "")).strip()
        entry["new_state"] = str(raw.get("new_state", "")).strip()
        entry["trigger"] = str(raw.get("trigger", "")).strip()

    elif object_class == "relationship_observed":
        entry["entity_a"] = str(raw.get("entity_a", "")).strip() or "unknown"
        entry["entity_b"] = str(raw.get("entity_b", "")).strip() or "unknown"
        entry["relation_type"] = str(raw.get("relation_type", "")).strip()
        entry["evidence_strength"] = coerce_enum(
            raw.get("evidence_strength"), VALID_EVIDENCE_STRENGTH, "implied"
        )

    elif object_class == "world_state_descriptor":
        entry["domain"] = coerce_enum(raw.get("domain"), VALID_WORLD_DOMAIN, "atmospheric")
        entry["descriptor_value"] = str(raw.get("descriptor_value", "")).strip()
        entry["contradicts_existing"] = coerce_bool(raw.get("contradicts_existing", False))
        entry["matches_existing"] = coerce_bool(raw.get("matches_existing", False))

    elif object_class == "timeline_marker":
        entry["era_label"] = str(raw.get("era_label", "unknown")).strip()
        entry["sequence_anchor"] = str(raw.get("sequence_anchor", "")).strip()
        entry["precision"] = coerce_enum(raw.get("precision"), VALID_PRECISION, "unordered")

    elif object_class == "unresolved_term":
        entry["term_variant"] = str(raw.get("term_variant", "")).strip()
        entry["canonical_candidate"] = str(raw.get("canonical_candidate", "")).strip()
        entry["drift_type"] = coerce_enum(
            raw.get("drift_type"), VALID_DRIFT_TYPE, "alias"
        )
        entry["requires_resolution"] = True

    elif object_class == "contradiction_candidate":
        entry["conflict_axis"] = str(raw.get("conflict_axis", "")).strip()
        entry["claim_a_span"] = str(raw.get("claim_a_span", "")).strip()
        entry["claim_b_span"] = str(raw.get("claim_b_span", "")).strip()
        entry["severity_estimate"] = coerce_enum(
            raw.get("severity_estimate"), VALID_SEVERITY, "cosmetic"
        )

    elif object_class == "group_agency_check":
        entry["group_name"] = str(raw.get("group_name", "")).strip() or "unknown"
        entry["group_type"] = coerce_enum(raw.get("group_type"), VALID_GROUP_TYPE, "unknown")
        entry["exhibits_unified_action"] = coerce_bool(
            raw.get("exhibits_unified_action", False)
        )
        entry["unified_action_evidence"] = str(raw.get("unified_action_evidence", "")).strip()
        entry["agency_signal"] = coerce_enum(
            raw.get("agency_signal"), VALID_AGENCY_SIGNAL, "unknown"
        )
        entry["identity_implication"] = coerce_enum(
            raw.get("identity_implication"), VALID_IDENTITY_IMPLICATION, "ambiguous"
        )

    # hard invariants — must never be violated
    entry["audit_only"] = True
    entry["provisional"] = True

    return entry, errors


def check_exit2(entries: list[dict[str, Any]]) -> tuple[bool, str]:
    """
    Return (True, reason) if any EXIT 2 condition is present.

    Exemptions:
    - unresolved_term entries with low confidence are expected and explicitly
      handled via requires_resolution: true (schema §5 "explicitly handled").
    - contradiction_candidate entries only trigger EXIT 2 at canon-breaking severity.
    """
    for e in entries:
        cls = e.get("object_class", "")
        # unresolved_term: low confidence is expected; requires_resolution=true is its explicit handler.
        # contradiction_candidate: EXIT 2 only at canon-breaking severity, not on confidence level.
        EXEMPT_FROM_LOW_CONF = {"unresolved_term", "contradiction_candidate"}
        if e.get("confidence") == "low" and cls not in EXEMPT_FROM_LOW_CONF:
            return True, (
                f"low-confidence entry: {cls} — "
                f"{str(e.get('extracted_value', ''))[:80]}"
            )
        if cls == "contradiction_candidate":
            if e.get("severity_estimate") == "canon-breaking":
                return True, f"canon-breaking contradiction: {e.get('conflict_axis', '')}"
        if "unresolvable" in str(e.get("source_span", "")) and cls not in EXEMPT_FROM_LOW_CONF:
            return True, (
                f"unresolvable span: {cls} — "
                f"{str(e.get('extracted_value', ''))[:80]}"
            )
    return False, ""


# ──────────────────────────────────────────────────────────────
# Ledger assembly
# ──────────────────────────────────────────────────────────────

def sort_key_for_entry(entry: dict[str, Any]) -> tuple[int, str]:
    cls = entry.get("object_class", "")
    idx = OBJECT_CLASS_ORDER.index(cls) if cls in OBJECT_CLASS_ORDER else 99
    return (idx, str(entry.get("source_span", "")))


def assemble_ledger(
    chapter: ChapterInfo,
    entries: list[dict[str, Any]],
    run_id: str,
    exit_code: int,
) -> dict[str, Any]:
    sorted_entries = sorted(entries, key=sort_key_for_entry)
    return {
        "schema": "chapter_ledger",
        "schema_version": "0.1.1-candidate",
        "ledger_id": f"{chapter.book_id}__{chapter.chapter_id}__{run_id}",
        "book_id": chapter.book_id,
        "book_number": chapter.book_number,
        "chapter_id": chapter.chapter_id,
        "chapter_title": chapter.chapter_title,
        "source_file": chapter.path.as_posix(),
        "source_hash": chapter.source_hash,
        "created_at": today(),
        "updated_at": today(),
        "extractor_run_id": run_id,
        "audit_only": True,
        "provisional": True,
        "exit_code_at_extraction": exit_code,
        "entry_count": len(sorted_entries),
        "entries": sorted_entries,
    }


# ──────────────────────────────────────────────────────────────
# YAML serialisation
# ──────────────────────────────────────────────────────────────

def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_./:-]+", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def to_yaml(value: Any, indent: int = 0) -> str:
    space = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{space}{key}: {yaml_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return f"{space}[]"
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{space}- {yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{space}{yaml_scalar(value)}"


# ──────────────────────────────────────────────────────────────
# Output paths
# ──────────────────────────────────────────────────────────────

def ledger_path_for(chapter: ChapterInfo, pending: bool = False) -> Path:
    root = LEDGERS_PENDING if pending else LEDGERS_ROOT
    return root / chapter.book_id / f"{chapter.chapter_id}.ledger.yaml"


# ──────────────────────────────────────────────────────────────
# Atomic write
# ──────────────────────────────────────────────────────────────

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
# Chunk job runner
# ──────────────────────────────────────────────────────────────

def run_chunk_job(job: ChunkJob, log_path: Path, timeout_sec: int = 300) -> ChunkResult:
    cached = read_chunk_cache(job.chapter, job.chunk_index)
    if cached is not None:
        log_line(log_path, f"[cache-hit] {job.chapter.path.name} chunk {job.chunk_index}")
        return ChunkResult(job=job, payload=cached, error=None)

    prompt = build_ledger_prompt(job.chapter, job.chunk_text, job.chunk_index, job.chunk_total)
    last_error = ""
    for attempt in range(1, 3):
        try:
            payload = ollama_json(prompt, timeout_sec=timeout_sec)
            write_chunk_cache(job.chapter, job.chunk_index, payload)
            return ChunkResult(job=job, payload=payload, error=None)
        except OllamaTimeout as exc:
            last_error = str(exc)
            log_line(
                log_path,
                f"[retry] {job.chapter.path.name} chunk {job.chunk_index}"
                f" attempt {attempt} timed out",
            )
        except LedgerError as exc:
            last_error = str(exc)
            break
        except Exception as exc:
            last_error = str(exc)
            break
    return ChunkResult(job=job, payload=None, error=last_error or "unknown error")


# ──────────────────────────────────────────────────────────────
# Failure diagnostic writer
# ──────────────────────────────────────────────────────────────

def write_failure_diagnostic(
    failed: list[ChunkResult],
    chapter: ChapterInfo,
    run_id: str,
) -> Path:
    diag_path = LOGS_ROOT / f"{run_id}_failures.yaml"
    records = [
        {
            "extractor_run_id": run_id,
            "chapter_id": chapter.chapter_id,
            "chapter_path": chapter.path.as_posix(),
            "chunk_index": r.job.chunk_index,
            "chunk_total": r.job.chunk_total,
            "error": r.error or "unknown",
            "timestamp": today(),
        }
        for r in failed
    ]
    content = "schema: chunk_failure_report\nfailures:\n"
    for rec in records:
        content += "  -\n" + to_yaml(rec, 4) + "\n"
    try:
        LOGS_ROOT.mkdir(parents=True, exist_ok=True)
        diag_path.write_text(content, encoding="utf-8")
    except OSError:
        pass
    return diag_path


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract chapter ledgers from raw chapters (Phase 6.0A)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview ledger without writing files.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write ledgers to raw/ledgers/ or raw/ledgers_pending/.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of chapters processed."
    )
    parser.add_argument(
        "--chapter", type=str, default=None, help="Process one chapter by filename substring."
    )
    parser.add_argument(
        "--workers", type=int, default=1, help="Concurrent Ollama workers (default: 1)."
    )
    parser.add_argument(
        "--timeout", type=int, default=300, help="Per-chunk Ollama timeout in seconds (default: 300)."
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

    run_id = f"chapter_ledger_{now_stamp()}"
    log_path = LOGS_ROOT / f"{run_id}.txt"

    # ── contract check ─────────────────────────────────────────
    if not CHAPTER_LEDGER_SCHEMA.exists():
        msg = f"[EXIT 1] Missing required schema: {CHAPTER_LEDGER_SCHEMA}"
        print(msg, file=sys.stderr)
        log_line(log_path, msg)
        return 1

    schema_text = CHAPTER_LEDGER_SCHEMA.read_text(encoding="utf-8", errors="replace")
    log_line(log_path, f"[schema] read CHAPTER_LEDGER_SCHEMA: {len(schema_text)} chars")

    # ── discover chapters ──────────────────────────────────────
    try:
        chapters = discover_chapters()
    except LedgerError as exc:
        print(f"[EXIT 1] {exc}", file=sys.stderr)
        log_line(log_path, f"[EXIT 1] {exc}")
        return 1

    if args.chapter:
        chapters = [p for p in chapters if args.chapter in p.name]
    if args.limit is not None:
        chapters = chapters[:args.limit]
    if not chapters:
        print("[error] No chapters matched the requested input.", file=sys.stderr)
        return 1

    # ── required output directories (§6.1) ────────────────────
    for d in (LEDGERS_ROOT, LEDGERS_PENDING, LEDGER_CACHE_DIR, LOGS_ROOT):
        d.mkdir(parents=True, exist_ok=True)

    print(f"[init] extractor_run_id={run_id}")
    print(f"[init] chapters={len(chapters)}")
    print(f"[init] mode={'dry-run' if args.dry_run else 'apply'}")
    print(f"[init] workers={args.workers}")
    print(f"[init] timeout={args.timeout}s")
    print(f"[init] log={log_path}")

    overall_exit = 0
    total_entries = 0
    extraction_timestamp = now_iso()

    for chapter_path in chapters:
        text = chapter_path.read_text(encoding="utf-8", errors="replace")
        chapter = parse_chapter_info(chapter_path, text)

        # ── skip already-processed ────────────────────────────
        if ledger_path_for(chapter, pending=False).exists():
            print(f"[skip] {chapter.path.name} (ledger exists)")
            log_line(log_path, f"[skip] {chapter.path.name} ledger exists")
            continue
        if ledger_path_for(chapter, pending=True).exists():
            print(f"[skip] {chapter.path.name} (pending review)")
            log_line(log_path, f"[skip] {chapter.path.name} pending exists")
            continue

        chunks = chunk_text(text)
        log_line(log_path, f"[chapter] {chapter.path.name} chunks={len(chunks)}")
        print(f"[chapter] {chapter.path.name} ({len(chunks)} chunks)")

        jobs = [
            ChunkJob(
                chapter=chapter,
                chunk_index=i,
                chunk_total=len(chunks),
                chunk_text=chunk,
            )
            for i, chunk in enumerate(chunks, 1)
        ]

        # ── concurrent chunk jobs ──────────────────────────────
        results_by_index: dict[int, ChunkResult] = {}
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_job = {
                executor.submit(run_chunk_job, job, log_path, args.timeout): job
                for job in jobs
            }
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = ChunkResult(job=job, payload=None, error=f"unexpected: {exc}")
                results_by_index[job.chunk_index] = result
                tag = "ok" if result.error is None else "FAILED"
                print(
                    f"[job] {chapter.path.name}"
                    f" chunk {job.chunk_index}/{job.chunk_total}: {tag}"
                )
                log_line(
                    log_path,
                    f"[job] {chapter.path.name}"
                    f" chunk {job.chunk_index}/{job.chunk_total}: {tag}",
                )

        # ── EXIT 1 check: chunk failures ──────────────────────
        results_ordered = [results_by_index[i] for i in sorted(results_by_index)]
        failed = [r for r in results_ordered if r.error is not None]

        if failed:
            diag_path = write_failure_diagnostic(failed, chapter, run_id)
            print(
                f"\n[failures] {len(failed)} chunk(s) failed"
                f" — see {diag_path}"
            )
            log_line(log_path, f"[EXIT 1] {chapter.path.name}: {len(failed)} chunk(s) failed")
            print("[exit] EXIT 1")
            return 1

        # ── collect and validate entries ───────────────────────
        all_entries: list[dict[str, Any]] = []
        validation_warnings: list[str] = []

        for result in results_ordered:
            raw_list = ensure_list(
                result.payload.get("ledger_entries") if result.payload else []
            )
            for raw in raw_list:
                if not isinstance(raw, dict):
                    continue
                entry, errs = validate_entry(
                    raw, chapter, result.job.chunk_index, extraction_timestamp
                )
                if entry.get("object_class") in VALID_OBJECT_CLASSES:
                    all_entries.append(entry)
                validation_warnings.extend(errs)

        # ── EXIT 2 check ───────────────────────────────────────
        is_exit2, exit2_reason = check_exit2(all_entries)
        chapter_exit = 2 if is_exit2 else 0

        ledger = assemble_ledger(chapter, all_entries, run_id, chapter_exit)
        ledger_yaml = to_yaml(ledger) + "\n"
        total_entries += len(all_entries)

        # ── print chapter summary ──────────────────────────────
        print(f"\n=== {chapter.path.name} ===")
        print(f"Book: {chapter.book_id}")
        print(f"Chapter: {chapter.chapter_id}")
        print(f"Entries: {len(all_entries)}")

        by_class: dict[str, int] = {}
        for e in all_entries:
            cls = e.get("object_class", "unknown")
            by_class[cls] = by_class.get(cls, 0) + 1
        for cls, count in sorted(by_class.items()):
            print(f"  {cls}: {count}")

        if chapter_exit == 2:
            print(f"[EXIT 2] Safety stop — {exit2_reason}")
            log_line(log_path, f"[EXIT 2] {chapter.path.name}: {exit2_reason}")
            overall_exit = max(overall_exit, 2)
        if validation_warnings:
            print(f"[warn] {len(validation_warnings)} validation warning(s)")
            for w in validation_warnings[:3]:
                print(f"  - {w}")

        if args.dry_run:
            if all_entries:
                print(f"\n[DRY-RUN] Preview of first entry:")
                print(to_yaml(all_entries[0], 0))
            else:
                print("[DRY-RUN] No entries extracted from this chapter.")
        else:
            pending = chapter_exit == 2
            out_path = ledger_path_for(chapter, pending=pending)
            write_atomic(out_path, ledger_yaml)
            dest = "raw/ledgers_pending" if pending else "raw/ledgers"
            print(
                f"[APPLY] Wrote {len(all_entries)} entries"
                f" → {dest}/{chapter.book_id}/{chapter.chapter_id}.ledger.yaml"
            )
            log_line(log_path, f"[write] {out_path.relative_to(MRLORE_ROOT)}")
            clear_chapter_cache(chapter)

    print(f"\n[complete] total_entries={total_entries}")
    if overall_exit == 0:
        print("[exit] EXIT 0")
    else:
        print("[exit] EXIT 2 — one or more chapters staged in raw/ledgers_pending/")
    return overall_exit


if __name__ == "__main__":
    sys.exit(main())
