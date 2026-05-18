#!/usr/bin/env python3
"""
MrLore v2 — Layer 2 Entity State Compiler

Reads Tier 0 source chapters and emits chapter-local entity state YAML records.

Contract:
- Reads schema/ENTITY_STATE_SCHEMA.md first.
- Reads schema/ENTITY_COMPILER_SCHEMA.md for pipeline context.
- Reads schema/REGISTRY_SYMBOL_TABLE_SCHEMA.md for registry context.
- Never writes to wiki/characters/.
- Never creates global profiles.
- Writes only to wiki/entity_states/<book_id>/<chapter_id>/<entity_slug>.yaml when --apply is used.
- Dry-run previews records without writing files.
- EXIT 0 = all jobs completed or skipped cleanly.
- EXIT 1 = one or more chunk jobs failed; run continued with partial results.
- EXIT 2 = schema/safety stop / unrecoverable error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


MRLORE_ROOT = Path(__file__).resolve().parents[1]
RAW_CHAPTERS = MRLORE_ROOT / "raw" / "chapters"
SCHEMA_DIR = MRLORE_ROOT / "schema"
REGISTRY_PATH = MRLORE_ROOT / "wiki" / "registry.md"
ENTITY_STATES_ROOT = MRLORE_ROOT / "wiki" / "entity_states"
LOGS_ROOT = MRLORE_ROOT / "logs"
CHUNK_CACHE_DIR = MRLORE_ROOT / ".cache" / "chunks"

ENTITY_STATE_SCHEMA = SCHEMA_DIR / "ENTITY_STATE_SCHEMA.md"
ENTITY_COMPILER_SCHEMA = SCHEMA_DIR / "ENTITY_COMPILER_SCHEMA.md"
REGISTRY_SYMBOL_TABLE_SCHEMA = SCHEMA_DIR / "REGISTRY_SYMBOL_TABLE_SCHEMA.md"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3:latest"

SOURCE_EXTS = {".md", ".txt"}
MAX_CHARS_PER_CHUNK = 9000

VALID_ENTITY_TYPES = {
    "character",
    "faction",
    "species",
    "location",
    "system",
    "artifact",
    "event",
    "concept",
    "group",
    "relationship_label",
    "unknown",
}

VALID_STATUS = {"captured", "compiled", "needs_review", "rejected", "superseded"}
VALID_CANON_STATE = {"evidence_only", "provisional", "reviewed", "approved"}
VALID_CONFIDENCE = {"low", "medium", "high"}

IDENTITY_SIGNAL_KEYS = [
    "named_directly",
    "speaks",
    "performs_actions",
    "receives_description",
    "has_internal_state",
    "appears_as_label_only",
    "exhibits_unified_action",
]

_LOG_LOCK = threading.Lock()


class SafetyStop(Exception):
    """Raised when the compiler must stop with EXIT 2."""


class OllamaTimeout(Exception):
    """Raised when an Ollama HTTP request times out (eligible for retry)."""


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
    chapter_index: int  # position in the chapters list; preserves ordering across threads
    chunk_index: int    # 1-based
    chunk_total: int
    chunk_text: str


@dataclass
class ChunkResult:
    job: ChunkJob
    payload: dict[str, Any] | None  # None when the job failed
    error: str | None               # non-None when the job failed


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def log_line(log_path: Path, message: str) -> None:
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK:
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")


def require_file(path: Path, label: str) -> str:
    if not path.exists():
        raise SafetyStop(f"Missing required {label}: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_required_contracts(log_path: Path) -> dict[str, str]:
    contracts = {
        "ENTITY_STATE_SCHEMA": require_file(ENTITY_STATE_SCHEMA, "schema"),
        "ENTITY_COMPILER_SCHEMA": require_file(ENTITY_COMPILER_SCHEMA, "schema"),
        "REGISTRY_SYMBOL_TABLE_SCHEMA": require_file(REGISTRY_SYMBOL_TABLE_SCHEMA, "schema"),
    }
    for name, text in contracts.items():
        log_line(log_path, f"[schema] read {name}: {len(text)} chars")
    return contracts


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def slugify(value: str) -> str:
    cleaned = value.strip()
    cleaned = cleaned.replace("’", "'")
    cleaned = re.sub(r"'s\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.lower() or "unresolved"


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
        raise SafetyStop(f"Missing raw chapters directory: {RAW_CHAPTERS}")

    chapters = [
        path for path in RAW_CHAPTERS.iterdir()
        if path.is_file() and path.suffix.lower() in SOURCE_EXTS
    ]
    return sorted(chapters)


_HEADER_RE = re.compile(r"(?m)^(?=#{2,3} )")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])[ \t]+")


def _split_at_sentences(text: str, max_chars: int) -> list[str]:
    """Split at sentence boundaries; keeps oversized single sentences intact rather than cutting mid-sentence."""
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
    # Step 1: split on ## / ### header lines; each section travels with its header
    sections = [s for s in _HEADER_RE.split(text) if s.strip()]
    if not sections:
        sections = [text]

    chunks: list[str] = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section.strip())
            continue

        # Step 2: oversized section — split at paragraph boundaries
        paragraphs = [p.strip() for p in section.split("\n\n") if p.strip()]
        current = ""
        for para in paragraphs:
            if len(para) > max_chars:
                if current:
                    chunks.append(current.strip())
                    current = ""
                # Step 3: oversized paragraph — split at sentence boundaries
                chunks.extend(_split_at_sentences(para, max_chars))
            elif current and len(current) + 2 + len(para) > max_chars:
                chunks.append(current.strip())
                current = para
            else:
                current = (current + "\n\n" + para).lstrip("\n") if current else para
        if current.strip():
            chunks.append(current.strip())

    return [c for c in chunks if c]


def load_registry_names() -> dict[str, str]:
    if not REGISTRY_PATH.exists():
        return {}

    text = REGISTRY_PATH.read_text(encoding="utf-8", errors="replace")
    names: dict[str, str] = {}

    id_pattern = re.compile(r"\b([A-Z]{3}-\d{4,}-[a-z0-9_-]+)\b")
    heading_pattern = re.compile(r"^#+\s+(.+?)\s*$", re.MULTILINE)

    for match in id_pattern.finditer(text):
        entity_id = match.group(1)
        slug = entity_id.split("-", 2)[-1]
        names[slug.replace("_", " ").lower()] = entity_id

    for heading in heading_pattern.finditer(text):
        label = heading.group(1).strip()
        if label:
            names.setdefault(label.lower(), f"candidate:{slugify(label)}")

    return names


def resolve_entity_ref(display_name: str, registry_names: dict[str, str]) -> str:
    direct = registry_names.get(display_name.lower())
    if direct:
        return direct

    slug = slugify(display_name)
    slug_key = slug.replace("_", " ")
    direct = registry_names.get(slug_key)
    if direct:
        return direct

    return f"candidate:{slug}"


def cache_path_for(chapter: ChapterInfo, chunk_index: int) -> Path:
    return CHUNK_CACHE_DIR / f"{chapter.source_hash}_{chunk_index}.json"


def read_chunk_cache(chapter: ChapterInfo, chunk_index: int) -> dict[str, Any] | None:
    path = cache_path_for(chapter, chunk_index)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("entity_states"), list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def write_chunk_cache(chapter: ChapterInfo, chunk_index: int, payload: dict[str, Any]) -> None:
    if not isinstance(payload.get("entity_states"), list):
        return
    try:
        CHUNK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path_for(chapter, chunk_index).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def clear_chapter_cache(chapter: ChapterInfo) -> None:
    if not CHUNK_CACHE_DIR.exists():
        return
    for path in CHUNK_CACHE_DIR.glob(f"{chapter.source_hash}_*.json"):
        try:
            path.unlink()
        except OSError:
            pass


def repair_truncated_json(raw: str) -> dict[str, Any] | None:
    """
    Recover entity_states from a truncated Ollama JSON response.

    Walks the raw string character-by-character, correctly tracking string
    boundaries and escape sequences, and collects every fully-closed top-level
    object inside the entity_states array.  Returns None if nothing usable
    is found.
    """
    start = raw.find('"entity_states"')
    if start == -1:
        return None
    bracket = raw.find('[', start)
    if bracket == -1:
        return None

    entities: list[Any] = []
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
                        entities.append(obj)
                except json.JSONDecodeError:
                    pass
                obj_start = None
        elif ch == ']' and depth == 0:
            break

        pos += 1

    if not entities:
        return None
    return {"entity_states": entities}


def ollama_json(prompt: str, timeout_sec: int = 120) -> dict[str, Any]:
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
            raise OllamaTimeout(f"Ollama request timed out: {exc}") from exc
        raise SafetyStop(f"Ollama request failed: {exc}") from exc

    try:
        envelope = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SafetyStop(f"Ollama returned non-JSON envelope: {exc}") from exc

    raw_response = envelope.get("response", "")
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise SafetyStop("Ollama returned an empty response.")

    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        recovered = repair_truncated_json(raw_response)
        if recovered and recovered.get("entity_states"):
            return recovered
        raise SafetyStop(
            f"Ollama response was not valid JSON and recovery found no complete"
            f" entities: {exc}\nRaw response:\n{raw_response[:2000]}"
        ) from exc

    if not isinstance(parsed, dict):
        raise SafetyStop("Ollama JSON root must be an object.")

    return parsed


def ollama_ping() -> None:
    """Send a minimal request to keep the model resident after the run."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": "{}",
        "stream": False,
        "format": "json",
        "options": {"num_predict": 1},
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except Exception:
        pass


def run_chunk_job(job: ChunkJob, log_path: Path, timeout_sec: int = 120) -> ChunkResult:
    """
    Call Ollama for one chunk.  Retries once on timeout; other errors are final.
    Thread-safe: log_line is locked; cache paths are unique per (chapter, chunk).
    """
    cached = read_chunk_cache(job.chapter, job.chunk_index)
    if cached is not None:
        log_line(log_path, f"[cache-hit] {job.chapter.path.name} chunk {job.chunk_index}")
        return ChunkResult(job=job, payload=cached, error=None)

    prompt = build_prompt(job.chapter, job.chunk_text, job.chunk_index, job.chunk_total)
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
            # natural loop continuation retries on attempt 1; exits on attempt 2
        except Exception as exc:
            last_error = str(exc)
            break
    return ChunkResult(job=job, payload=None, error=last_error or "unknown error")


def write_failure_records(failures: list[dict[str, Any]], log_path: Path) -> Path:
    """Write a structured YAML failure report alongside the run log."""
    failure_path = log_path.with_name(log_path.stem + "_failures.yaml")
    lines = ["schema: chunk_failure_report", "failures:"]
    for f in failures:
        lines.append("  -")
        for key, val in f.items():
            lines.append(f"    {key}: {yaml_scalar(val)}")
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    failure_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return failure_path


def build_prompt(chapter: ChapterInfo, chunk: str, chunk_index: int, chunk_total: int) -> str:
    return f"""
You are MrLore v2 Layer 2 Entity State Extractor.

You must extract chapter-local entity states only.
Do not create global profiles.
Do not infer canon.
Do not write wiki pages.
Do not promote relationship labels to characters.

Source:
- book_id: {chapter.book_id}
- book_number: {chapter.book_number}
- chapter_id: {chapter.chapter_id}
- chapter_title: {chapter.chapter_title}
- source_file: {chapter.path.as_posix()}
- chunk: {chunk_index} of {chunk_total}

Return JSON only.

Required JSON shape:

{{
  "entity_states": [
    {{
      "display_name": "short entity name as used in this chapter",
      "entity_type": "character | faction | species | location | system | artifact | event | concept | group | relationship_label | unknown",
      "chapter_role": "what this entity does or means in this chapter only",
      "identity_evidence": {{
        "named_directly": true,
        "speaks": false,
        "performs_actions": true,
        "receives_description": true,
        "has_internal_state": false,
        "appears_as_label_only": false,
        "exhibits_unified_action": false,
        "identity_confidence": "low | medium | high"
      }},
      "timeline_events": [
        {{
          "event_type": "state_change | location_move | physical_alteration | relationship_change | knowledge_gain | identity_reveal",
          "description": "what changed and when within the chapter",
          "confidence": "low | medium | high",
          "source_quote_id": "Q-0001 or null"
        }}
      ],
      "relationships": [
        {{
          "predicate": "relationship predicate",
          "subject": "name or UNRESOLVED",
          "target": "name or UNRESOLVED",
          "evidence": "direct | inferred | unresolved",
          "confidence": "low | medium | high",
          "notes": "short note"
        }}
      ],
      "actions": [
        {{
          "action": "short action",
          "target": "name or null",
          "consequence": "short consequence or null",
          "confidence": "low | medium | high"
        }}
      ],
      "dialogue": [
        {{
          "speaker": "name",
          "addressee": "name or unknown",
          "quote_excerpt": "short exact excerpt",
          "voice_note": "short note or null"
        }}
      ],
      "presence": {{
        "direct_presence": true,
        "mentioned_only": false,
        "locations": [
          {{
            "name": "location name",
            "confidence": "low | medium | high"
          }}
        ]
      }},
      "arc_position": {{
        "arc_name": "unknown",
        "role_in_arc": "setup | escalation | revelation | reversal | resolution | aftermath | unknown",
        "chapter_function": "short note"
      }},
      "changes": [
        {{
          "change_type": "relationship_change | identity_reveal | location_change | status_change | knowledge_gain | transformation | contradiction | none",
          "before": "unknown",
          "after": "unknown",
          "confidence": "low | medium | high"
        }}
      ],
      "evidence": [
        {{
          "excerpt": "short exact quote from chapter",
          "supports": ["identity:character"]
        }}
      ],
      "classification_notes": "why this type was chosen",
      "continuity_flags": [
        {{
          "flag_type": "alias_drift | identity_merge_possible | identity_split_possible | relationship_conflict | location_conflict | timeline_conflict | type_conflict | none",
          "severity": "info | warning | conflict",
          "note": "short note"
        }}
      ],
      "compiler_notes": {{
        "eligible_for_book_profile": true,
        "eligible_for_global_profile": false,
        "requires_registry_resolution": true,
        "suggested_registry_action": "create_candidate | link_existing | merge_candidate | reject_candidate | review"
      }}
    }}
  ]
}}

Character eligibility:
A character must have at least two identity signals among:
named_directly, speaks, performs_actions, receives_description,
has_internal_state, exhibits_unified_action, relationship to resolved entity.

If a term is only a relationship label such as Brothers, Sisters, Companions,
Survivors, Freed Slaves, or Five Mikas, classify it as relationship_label or group,
not character.

Group agency rule:
If a group term exhibits a unified action verb (chose, marched, defended,
integrated, built, or similar collective agency), set exhibits_unified_action
to true and classify the entity as faction, not relationship_label.

Chapter text:

{chunk}
""".strip()


def normalize_bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def normalize_confidence(value: Any) -> str:
    text = str(value).strip().lower()
    return text if text in VALID_CONFIDENCE else "low"


def identity_signal_count(identity: dict[str, Any], relationships: list[Any]) -> int:
    count = 0
    for key in ["named_directly", "speaks", "performs_actions", "receives_description",
                "has_internal_state", "exhibits_unified_action"]:
        if normalize_bool(identity.get(key)):
            count += 1
    if relationships:
        count += 1
    return count


def sanitize_entity_type(entity_type: Any) -> str:
    text = str(entity_type).strip().lower()
    return text if text in VALID_ENTITY_TYPES else "unknown"


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def ensure_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def merge_entity_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}

    for payload in payloads:
        for item in ensure_list(payload.get("entity_states")):
            if not isinstance(item, dict):
                continue

            name = str(item.get("display_name", "")).strip()
            if not name:
                continue

            etype = sanitize_entity_type(item.get("entity_type", "unknown"))
            key = (slugify(name), etype)

            if key not in merged:
                merged[key] = item
                continue

            existing = merged[key]

            for list_key in ["relationships", "actions", "dialogue", "timeline_events", "changes", "evidence", "continuity_flags"]:
                existing.setdefault(list_key, [])
                existing[list_key].extend(ensure_list(item.get(list_key)))

            if not existing.get("chapter_role") and item.get("chapter_role"):
                existing["chapter_role"] = item["chapter_role"]

    return list(merged.values())


def next_est_number() -> int:
    max_seen = 0
    if ENTITY_STATES_ROOT.exists():
        for path in ENTITY_STATES_ROOT.rglob("*.yaml"):
            text = path.read_text(encoding="utf-8", errors="replace")[:500]
            match = re.search(r"state_id:\s*EST-(\d+)", text)
            if match:
                max_seen = max(max_seen, int(match.group(1)))
    return max_seen + 1


def build_state_record(
    raw: dict[str, Any],
    chapter: ChapterInfo,
    registry_names: dict[str, str],
    state_number: int,
    compiler_run_id: str,
) -> dict[str, Any]:
    display_name = str(raw.get("display_name", "")).strip()
    if not display_name:
        raise ValueError("entity state missing display_name")

    entity_type = sanitize_entity_type(raw.get("entity_type", "unknown"))
    relationships = ensure_list(raw.get("relationships"))
    identity = ensure_dict(raw.get("identity_evidence"))

    exhibits_unified_action = normalize_bool(identity.get("exhibits_unified_action"))
    signal_count = identity_signal_count(identity, relationships)
    status = "captured"
    canon_state = "evidence_only"

    classification_notes = str(raw.get("classification_notes", "")).strip()

    if entity_type in ("relationship_label", "group") and exhibits_unified_action:
        entity_type = "faction"
        classification_notes = (
            classification_notes
            + " Elevated to faction: exhibits_unified_action detected."
        ).strip()

    if entity_type == "character" and signal_count < 2:
        entity_type = "unknown"
        status = "needs_review"
        classification_notes = (
            classification_notes
            + " Character classification downgraded: fewer than two identity signals."
        ).strip()

    if entity_type == "relationship_label":
        status = "captured"

    entity_ref = resolve_entity_ref(display_name, registry_names)

    evidence_items = []
    for idx, evidence in enumerate(ensure_list(raw.get("evidence")), 1):
        if not isinstance(evidence, dict):
            continue
        evidence_items.append({
            "quote_id": f"Q-{idx:04d}",
            "source_file": chapter.path.as_posix(),
            "line_start": None,
            "line_end": None,
            "excerpt": str(evidence.get("excerpt", "")).strip()[:500],
            "supports": ensure_list(evidence.get("supports")),
        })

    record = {
        "schema": "entity_state",
        "schema_version": 1,
        "state_id": f"EST-{state_number:06d}",
        "entity_ref": entity_ref,
        "display_name": display_name,
        "entity_type": entity_type,
        "status": status,
        "canon_state": canon_state,
        "audit_only": True,
        "book_id": chapter.book_id,
        "book_number": chapter.book_number,
        "chapter_id": chapter.chapter_id,
        "chapter_title": chapter.chapter_title,
        "source_file": chapter.path.as_posix(),
        "source_hash": chapter.source_hash,
        "created_at": today(),
        "updated_at": today(),
        "compiler_run_id": compiler_run_id,
        "chapter_role": str(raw.get("chapter_role", "")).strip(),
        "identity_evidence": {
            "named_directly": normalize_bool(identity.get("named_directly")),
            "speaks": normalize_bool(identity.get("speaks")),
            "performs_actions": normalize_bool(identity.get("performs_actions")),
            "receives_description": normalize_bool(identity.get("receives_description")),
            "has_internal_state": normalize_bool(identity.get("has_internal_state")),
            "appears_as_label_only": normalize_bool(identity.get("appears_as_label_only")),
            "exhibits_unified_action": exhibits_unified_action,
            "identity_confidence": normalize_confidence(identity.get("identity_confidence")),
            "identity_signal_count": signal_count,
        },
        "timeline_events": ensure_list(raw.get("timeline_events")),
        "relationships": relationships,
        "actions": ensure_list(raw.get("actions")),
        "dialogue": ensure_list(raw.get("dialogue")),
        "presence": ensure_dict(raw.get("presence")),
        "arc_position": ensure_dict(raw.get("arc_position")),
        "changes": ensure_list(raw.get("changes")),
        "evidence": evidence_items,
        "classification_notes": classification_notes,
        "continuity_flags": ensure_list(raw.get("continuity_flags")),
        "compiler_notes": ensure_dict(raw.get("compiler_notes")),
    }

    if record["audit_only"] is not True:
        raise ValueError("audit_only enforcement failed")

    if record["status"] not in VALID_STATUS:
        raise ValueError(f"invalid status: {record['status']}")

    if record["canon_state"] not in VALID_CANON_STATE:
        raise ValueError(f"invalid canon_state: {record['canon_state']}")

    if record["entity_type"] not in VALID_ENTITY_TYPES:
        raise ValueError(f"invalid entity_type: {record['entity_type']}")

    return record


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int | float):
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
            if isinstance(item, dict):
                lines.append(f"{space}-")
                lines.append(to_yaml(item, indent + 2))
            elif isinstance(item, list):
                lines.append(f"{space}-")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{space}- {yaml_scalar(item)}")
        return "\n".join(lines)

    return f"{space}{yaml_scalar(value)}"


def output_path_for(record: dict[str, Any]) -> Path:
    book_id = slugify(str(record["book_id"]))
    chapter_id = slugify(str(record["chapter_id"]))
    entity_slug = slugify(str(record["display_name"]))
    return ENTITY_STATES_ROOT / book_id / chapter_id / f"{entity_slug}.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile chapter-local entity states from raw chapters."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview records without writing files.")
    mode.add_argument("--apply", action="store_true", help="Write records to wiki/entity_states/.")

    parser.add_argument("--limit", type=int, default=None, help="Limit number of chapters processed.")
    parser.add_argument("--chapter", type=str, default=None, help="Process one chapter filename substring.")
    parser.add_argument("--workers", type=int, default=2, help="Concurrent Ollama workers (default: 2).")
    parser.add_argument("--timeout", type=int, default=300, help="Per-chunk Ollama timeout in seconds (default: 300).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.limit is not None and args.limit < 1:
        print("[error] --limit must be >= 1", file=sys.stderr)
        return 2

    compiler_run_id = f"compile_entity_states_{now_stamp()}"
    log_path = LOGS_ROOT / f"{compiler_run_id}.txt"

    try:
        read_required_contracts(log_path)
        registry_names = load_registry_names()

        chapters = discover_chapters()
        if args.chapter:
            chapters = [path for path in chapters if args.chapter in path.name]
        if args.limit is not None:
            chapters = chapters[:args.limit]
        if not chapters:
            raise SafetyStop("No chapters matched the requested input.")

        print(f"[init] compiler_run_id={compiler_run_id}")
        print(f"[init] chapters={len(chapters)}")
        print(f"[init] mode={'dry-run' if args.dry_run else 'apply'}")
        print(f"[init] workers={args.workers}")
        print(f"[init] timeout={args.timeout}s")
        print(f"[init] registry symbols loaded={len(registry_names)}")
        print(f"[init] log={log_path}")

        # Phase 1: scan chapters, skip completed, build job manifest
        all_jobs: list[ChunkJob] = []
        chapter_manifest: list[tuple[int, ChapterInfo]] = []

        for chapter_index, chapter_path in enumerate(chapters):
            text = chapter_path.read_text(encoding="utf-8", errors="replace")
            chapter = parse_chapter_info(chapter_path, text)

            chapter_state_dir = ENTITY_STATES_ROOT / chapter.book_id / chapter.chapter_id
            if chapter_state_dir.is_dir() and any(chapter_state_dir.glob("*.yaml")):
                print(f"[skip] {chapter.path.name} already processed")
                log_line(log_path, f"[skip] {chapter.path.name} already processed")
                continue

            chunks = chunk_text(text)
            log_line(log_path, f"[chapter] {chapter.path.name} chunks={len(chunks)}")
            chapter_manifest.append((chapter_index, chapter))
            for i, chunk in enumerate(chunks, 1):
                all_jobs.append(ChunkJob(
                    chapter=chapter,
                    chapter_index=chapter_index,
                    chunk_index=i,
                    chunk_total=len(chunks),
                    chunk_text=chunk,
                ))

        print(f"[init] pending_jobs={len(all_jobs)}")

        if not all_jobs:
            print("\n[complete] all chapters already processed")
            print("[exit] EXIT 0")
            return 0

        # Phase 2: run all jobs concurrently
        results_map: dict[tuple[int, int], ChunkResult] = {}

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_job = {
                executor.submit(run_chunk_job, job, log_path, args.timeout): job
                for job in all_jobs
            }
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = ChunkResult(job=job, payload=None, error=f"unexpected: {exc}")
                results_map[(job.chapter_index, job.chunk_index)] = result
                tag = "ok" if result.error is None else "FAILED"
                print(
                    f"[job] {job.chapter.path.name}"
                    f" chunk {job.chunk_index}/{job.chunk_total}: {tag}"
                )
                log_line(
                    log_path,
                    f"[job] {job.chapter.path.name}"
                    f" chunk {job.chunk_index}/{job.chunk_total}: {tag}",
                )

        # Phase 3: assemble per-chapter records in manifest order
        failures: list[dict[str, Any]] = []
        est_number = next_est_number()
        total_records = 0

        for chapter_index, chapter in chapter_manifest:
            chapter_results = sorted(
                [r for (ci, _), r in results_map.items() if ci == chapter_index],
                key=lambda r: r.job.chunk_index,
            )

            failed_results = [r for r in chapter_results if r.error is not None]
            succeeded_results = [r for r in chapter_results if r.error is None]

            for r in failed_results:
                failures.append({
                    "compiler_run_id": compiler_run_id,
                    "chapter_id": chapter.chapter_id,
                    "chapter_path": chapter.path.as_posix(),
                    "chunk_index": r.job.chunk_index,
                    "chunk_total": r.job.chunk_total,
                    "error": r.error or "unknown",
                    "timestamp": today(),
                })
                log_line(
                    log_path,
                    f"[failure] {chapter.path.name} chunk {r.job.chunk_index}: {r.error}",
                )

            if not succeeded_results:
                print(f"\n=== {chapter.path.name} === all chunks failed, skipping assembly")
                continue

            payloads = [r.payload for r in succeeded_results if r.payload is not None]
            merged = merge_entity_payloads(payloads)

            records: list[dict[str, Any]] = []
            for item in merged:
                try:
                    record = build_state_record(
                        item, chapter, registry_names, est_number, compiler_run_id
                    )
                except ValueError as exc:
                    log_line(log_path, f"[skip] invalid entity state in {chapter.path.name}: {exc}")
                    continue
                records.append(record)
                est_number += 1

            if not records:
                log_line(log_path, f"[warn] no valid entity states from {chapter.path.name}")
                print(f"\n=== {chapter.path.name} === WARNING: no valid entity states extracted")
                continue

            print(f"\n=== {chapter.path.name} ===")
            print(f"Book: {chapter.book_id}")
            print(f"Chapter: {chapter.chapter_id}")
            print(f"Entity states: {len(records)}")
            for record in records[:10]:
                print(
                    f"- {record['state_id']} | {record['entity_type']} | "
                    f"{record['display_name']} | {record['status']} | {record['entity_ref']}"
                )
            if len(records) > 10:
                print(f"... {len(records) - 10} more records")

            if args.dry_run:
                print("\n[DRY-RUN] Preview of first record:")
                print(to_yaml(records[0])[:4000])

            elif args.apply:
                if failed_results:
                    # Partial chapter: withhold entity YAMLs so skip-check doesn't
                    # fire on the next run and the chapter is retried in full.
                    print(
                        f"[PARTIAL] {chapter.path.name}: {len(failed_results)} chunk(s) failed,"
                        " entity states not written — chapter will be retried next run"
                    )
                else:
                    for record in records:
                        path = output_path_for(record)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(to_yaml(record) + "\n", encoding="utf-8")
                        log_line(log_path, f"[write] {path.relative_to(MRLORE_ROOT)}")
                    clear_chapter_cache(chapter)
                    print(f"[APPLY] Wrote {len(records)} entity state record(s).")

            total_records += len(records)

        if failures:
            failure_path = write_failure_records(failures, log_path)
            print(f"\n[failures] {len(failures)} chunk(s) failed — see {failure_path}")

        ollama_ping()

        print(f"\n[complete] entity state records={total_records}")

        if failures:
            print("[exit] EXIT 1")
            return 1

        print("[exit] EXIT 0")
        return 0

    except SafetyStop as exc:
        log_line(log_path, f"[EXIT 2] {exc}")
        print(f"[safety-stop] {exc}", file=sys.stderr)
        print("[exit] EXIT 2", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        log_line(log_path, "[EXIT 2] interrupted")
        print("[safety-stop] interrupted", file=sys.stderr)
        print("[exit] EXIT 2", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
