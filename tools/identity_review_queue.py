#!/usr/bin/env python3
"""
MrLore v2 — Phase 6.4A Identity Review Queue Builder

Joins provisional routes, identity signal stats, and surface form stats.
Filters to review-eligible buckets. Produces JSONL + MD review queue.

Contract:
- No LLM inference. No wiki writes. No canon decisions.
- Pure deterministic join, filter, sort — same inputs → byte-identical output.
- Inputs:
    raw/math/provisional_identity_routes.jsonl
    raw/math/identity_signal_stats.jsonl
    raw/math/surface_form_stats.jsonl
- Outputs:
    review/identity_review_queue.jsonl
    review/identity_review_queue.md
- EXIT 0: queue generated, both files written, manifest logged.
- EXIT 1: structural failure — diagnostic to logs/error_6.4A.md, halt.
- EXIT 2: safety stop (zero records after filter, hash mismatch) — staged to review/pending/, halt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MRLORE_ROOT = Path(__file__).resolve().parents[1]
MATH_ROOT = MRLORE_ROOT / "raw" / "math"
REVIEW_DIR = MRLORE_ROOT / "review"
LOGS_DIR = MRLORE_ROOT / "logs"

ROUTES_FILE = MATH_ROOT / "provisional_identity_routes.jsonl"
SIGNALS_FILE = MATH_ROOT / "identity_signal_stats.jsonl"
STATS_FILE = MATH_ROOT / "surface_form_stats.jsonl"

OUTPUT_JSONL = REVIEW_DIR / "identity_review_queue.jsonl"
OUTPUT_MD = REVIEW_DIR / "identity_review_queue.md"
MANIFEST_FILE = LOGS_DIR / "manifest_6.4A.yaml"
ERROR_FILE = LOGS_DIR / "error_6.4A.md"

TOOL_VERSION = "identity_review_queue/0.1.0"

DEFAULT_INCLUDE_ROUTES: frozenset[str] = frozenset({
    "ambiguous_review_candidate",
    "bounded_actor_candidate",
    "identity_braid_candidate",
})

# Spec-mandated field order — do not reorder.
OUTPUT_FIELD_ORDER: tuple[str, ...] = (
    "surface_form",
    "primary_route",
    "matched_routes",
    "routing_reasons",
    "total_mentions",
    "chapter_count",
    "speech_ratio",
    "action_ratio",
    "monologue_viability_score",
    "collective_fragmentation_score",
    "conceptual_drift_score",
    "raw_variants",
    "top_cooccurring_tokens",
    "avg_verb_distance",
    "review_status",
    "reviewer_decision",
    "reviewer_notes",
)

_FIELD_DEFAULTS: dict[str, Any] = {
    "surface_form": "",
    "primary_route": "",
    "matched_routes": [],
    "routing_reasons": {},
    "total_mentions": 0,
    "chapter_count": 0,
    "speech_ratio": 0.0,
    "action_ratio": 0.0,
    "monologue_viability_score": 0.0,
    "collective_fragmentation_score": 0.0,
    "conceptual_drift_score": 0.0,
    "raw_variants": [],
    "top_cooccurring_tokens": [],
    "avg_verb_distance": 0.0,
    "review_status": "pending",
    "reviewer_decision": None,
    "reviewer_notes": "",
}


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
# I/O
# ──────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Load JSONL, validate `surface_form` key presence, return (records, sha256)."""
    if not path.exists():
        raise FileNotFoundError(f"Missing input: {path}")
    file_hash = sha256_of_file(path)
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line_num, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name} line {line_num}: {exc}") from exc
            if "surface_form" not in rec:
                raise ValueError(
                    f"{path.name} line {line_num}: missing required key 'surface_form'"
                )
            records.append(rec)
    return records, file_hash


def build_lookup(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["surface_form"]: r for r in records}


# ──────────────────────────────────────────────────────────────
# Config loading
# ──────────────────────────────────────────────────────────────

def load_include_routes(config_path: Path | None) -> frozenset[str]:
    """Return the include-routes set — from config if provided, else defaults."""
    if config_path is None:
        return DEFAULT_INCLUDE_ROUTES
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    suffix = config_path.suffix.lower()
    if suffix == ".json":
        with config_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml as _yaml
        except ImportError:
            raise ImportError(
                "pyyaml not installed — required for YAML config.\n"
                f"  Install: pip install pyyaml\n"
                f"  Or use JSON: {config_path.with_suffix('.json')}"
            )
        with config_path.open(encoding="utf-8") as fh:
            data = _yaml.safe_load(fh)
    else:
        raise ValueError(f"Unsupported config format '{suffix}'. Use .json, .yaml, or .yml")
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping")
    if "include_routes" not in data:
        raise ValueError("Config missing 'include_routes' key")
    routes = data["include_routes"]
    if not isinstance(routes, list) or not all(isinstance(r, str) for r in routes):
        raise ValueError("'include_routes' must be a list of strings")
    return frozenset(routes)


# ──────────────────────────────────────────────────────────────
# Join and merge
# ──────────────────────────────────────────────────────────────

def merge_record(
    sf: str,
    route_r: dict[str, Any],
    signal_r: dict[str, Any] | None,
    stats_r: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Priority merge: routes → signals → stats → type defaults.
    Field aliases: matched_rules → matched_routes, proximity_cooccurrence → top_cooccurring_tokens.
    """
    sig = signal_r or {}
    sta = stats_r or {}

    def route_signal_default(field: str) -> Any:
        """For fields present in both routes and signals, routes wins."""
        if field in route_r:
            return route_r[field]
        if field in sig:
            return sig[field]
        return _FIELD_DEFAULTS[field]

    return {
        "surface_form": sf,
        "primary_route": route_r.get("primary_route", ""),
        "matched_routes": route_r.get("matched_rules", []),
        "routing_reasons": route_r.get("routing_reasons", {}),
        "total_mentions": route_signal_default("total_mentions"),
        "chapter_count": route_signal_default("chapter_count"),
        "speech_ratio": sig.get("speech_ratio", 0.0),
        "action_ratio": sig.get("action_ratio", 0.0),
        "monologue_viability_score": sig.get("monologue_viability_score", 0.0),
        "collective_fragmentation_score": sig.get("collective_fragmentation_score", 0.0),
        "conceptual_drift_score": sig.get("conceptual_drift_score", 0.0),
        "raw_variants": sta.get("raw_variants", []),
        "top_cooccurring_tokens": sig.get("proximity_cooccurrence", []),
        "avg_verb_distance": sig.get("avg_verb_distance", 0.0),
        "review_status": "pending",
        "reviewer_decision": None,
        "reviewer_notes": "",
    }


def ordered_record(rec: dict[str, Any]) -> dict[str, Any]:
    return {k: rec[k] for k in OUTPUT_FIELD_ORDER}


# ──────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────

def validate_output_record(rec: dict[str, Any], sf: str) -> list[str]:
    errors: list[str] = []
    missing = set(OUTPUT_FIELD_ORDER) - set(rec)
    for field in sorted(missing):
        errors.append(f"'{sf}': missing field '{field}'")

    _float_fields = {
        "speech_ratio", "action_ratio", "monologue_viability_score",
        "collective_fragmentation_score", "conceptual_drift_score", "avg_verb_distance",
    }
    _int_fields = {"total_mentions", "chapter_count"}
    _list_fields = {"matched_routes", "raw_variants", "top_cooccurring_tokens"}

    for field in _float_fields:
        if field in rec and not isinstance(rec[field], (int, float)):
            errors.append(f"'{sf}': '{field}' expected float, got {type(rec[field]).__name__}")
    for field in _int_fields:
        if field in rec and not isinstance(rec[field], int):
            errors.append(f"'{sf}': '{field}' expected int, got {type(rec[field]).__name__}")
    for field in _list_fields:
        if field in rec and not isinstance(rec[field], list):
            errors.append(f"'{sf}': '{field}' expected list, got {type(rec[field]).__name__}")
    if "routing_reasons" in rec and not isinstance(rec["routing_reasons"], dict):
        errors.append(f"'{sf}': 'routing_reasons' expected dict, got {type(rec['routing_reasons']).__name__}")
    return errors


# ──────────────────────────────────────────────────────────────
# Markdown generation
# ──────────────────────────────────────────────────────────────

def _cell(val: Any) -> str:
    if isinstance(val, (list, dict)):
        s = json.dumps(val, ensure_ascii=False, separators=(",", ":"))
    elif val is None:
        s = "null"
    else:
        s = str(val)
    return s.replace("|", "\\|").replace("\n", " ")


def build_markdown(
    records: list[dict[str, Any]],
    meta: dict[str, Any],
    include_routes: frozenset[str],
) -> str:
    lines: list[str] = []

    lines.append("# MrLore Identity Review Queue")
    lines.append("")
    lines.append(f"**Generated:** {meta['timestamp']}  ")
    lines.append(f"**Tool:** {TOOL_VERSION}  ")
    lines.append(f"**Total records:** {meta['total_records']}  ")
    lines.append("")
    lines.append("## Filter")
    lines.append("")
    for route in sorted(include_routes):
        lines.append(f"- `{route}`")
    lines.append("")
    lines.append("## Input Hashes")
    lines.append("")
    lines.append("| File | SHA-256 (first 32) |")
    lines.append("|---|---|")
    lines.append(f"| `provisional_identity_routes.jsonl` | `{meta['routes_hash'][:32]}` |")
    lines.append(f"| `identity_signal_stats.jsonl` | `{meta['signals_hash'][:32]}` |")
    lines.append(f"| `surface_form_stats.jsonl` | `{meta['stats_hash'][:32]}` |")
    lines.append("")
    lines.append("## Bucket Distribution")
    lines.append("")
    lines.append("| Bucket | Count |")
    lines.append("|---|---|")
    for bucket in sorted(meta["bucket_counts"].keys()):
        lines.append(f"| `{bucket}` | {meta['bucket_counts'][bucket]} |")
    lines.append("")
    lines.append("## Review Queue")
    lines.append("")
    lines.append("| " + " | ".join(OUTPUT_FIELD_ORDER) + " |")
    lines.append("| " + " | ".join("---" for _ in OUTPUT_FIELD_ORDER) + " |")
    for rec in records:
        cells = [_cell(rec.get(field)) for field in OUTPUT_FIELD_ORDER]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        f"*{meta['total_records']} records — awaiting reviewer decisions "
        f"before Pass 5 promotion logic.*"
    )
    lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Side-effect helpers
# ──────────────────────────────────────────────────────────────

def write_error_log(message: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    content = (
        f"# Error Log — {TOOL_VERSION} — {now_iso()}\n\n"
        f"## Error\n\n```\n{message}\n```\n\n"
    )
    try:
        with ERROR_FILE.open("a", encoding="utf-8") as fh:
            fh.write(content)
    except OSError:
        pass


def stage_pending(reason: str, meta: dict[str, Any]) -> None:
    """Write a diagnostic JSON to review/pending/ for EXIT 2 conditions."""
    pending_dir = REVIEW_DIR / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    ts = meta.get("timestamp", now_iso()).replace(":", "").replace("-", "")
    fname = f"staged_{ts}.json"
    content = json.dumps(
        {
            "reason": reason,
            "timestamp": meta.get("timestamp"),
            "tool": TOOL_VERSION,
            "routes_hash": meta.get("routes_hash"),
            "signals_hash": meta.get("signals_hash"),
            "stats_hash": meta.get("stats_hash"),
        },
        indent=2,
    ) + "\n"
    try:
        write_atomic(pending_dir / fname, content)
        print(f"[staged] diagnostic → review/pending/{fname}")
    except OSError as exc:
        print(f"[warn] could not write staging diagnostic: {exc}")


def append_manifest(meta: dict[str, Any]) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f"tool: {TOOL_VERSION}",
        f"timestamp: {meta['run_timestamp']}",
        f"routes_input_timestamp: {meta['timestamp']}",
        f"total_records: {meta['total_records']}",
        f"routes_hash: {meta['routes_hash']}",
        f"signals_hash: {meta['signals_hash']}",
        f"stats_hash: {meta['stats_hash']}",
        "bucket_counts:",
    ]
    for bucket in sorted(meta["bucket_counts"].keys()):
        lines.append(f"  {bucket}: {meta['bucket_counts'][bucket]}")
    lines.append(f"output_jsonl: {OUTPUT_JSONL.relative_to(MRLORE_ROOT)}")
    lines.append(f"output_md: {OUTPUT_MD.relative_to(MRLORE_ROOT)}")
    lines.append("")
    with MANIFEST_FILE.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Identity review queue builder — deterministic join, filter, and sort.\n"
            "Produces review/identity_review_queue.jsonl and .md."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs, compute join, print sample. Exit 0 without writing.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Write review/identity_review_queue.jsonl and .md (EXIT 0).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Optional config (.json/.yaml) with 'include_routes' list override.",
    )
    return parser.parse_args()


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    print(f"[init] tool: {TOOL_VERSION}")

    # ── Config ────────────────────────────────────────────────────────────────
    try:
        include_routes = load_include_routes(args.config)
    except (FileNotFoundError, ValueError, ImportError, OSError) as exc:
        msg = f"Config error: {exc}"
        print(f"[EXIT 1] {msg}", file=sys.stderr)
        write_error_log(msg)
        return 1

    if args.config:
        print(f"[config] include_routes loaded from {args.config}: {sorted(include_routes)}")
    else:
        print(f"[config] include_routes (default): {sorted(include_routes)}")

    # ── Load inputs ───────────────────────────────────────────────────────────
    print(f"[load] {ROUTES_FILE.name} ...", end=" ", flush=True)
    try:
        routes_records, routes_hash = load_jsonl(ROUTES_FILE)
    except (FileNotFoundError, ValueError, OSError) as exc:
        msg = str(exc)
        print(f"\n[EXIT 1] {msg}", file=sys.stderr)
        write_error_log(msg)
        return 1
    print(f"{len(routes_records):,}")

    print(f"[load] {SIGNALS_FILE.name} ...", end=" ", flush=True)
    try:
        signals_records, signals_hash = load_jsonl(SIGNALS_FILE)
    except (FileNotFoundError, ValueError, OSError) as exc:
        msg = str(exc)
        print(f"\n[EXIT 1] {msg}", file=sys.stderr)
        write_error_log(msg)
        return 1
    print(f"{len(signals_records):,}")

    print(f"[load] {STATS_FILE.name} ...", end=" ", flush=True)
    try:
        stats_records, stats_hash = load_jsonl(STATS_FILE)
    except (FileNotFoundError, ValueError, OSError) as exc:
        msg = str(exc)
        print(f"\n[EXIT 1] {msg}", file=sys.stderr)
        write_error_log(msg)
        return 1
    print(f"{len(stats_records):,}")

    timestamp = now_iso()

    # ── Cross-file hash validation ────────────────────────────────────────────
    # Routes embed input_stats_hash — the identity_signal_stats hash at routing time.
    # Mismatched hash means the signals file changed after the router ran.
    embedded_signals_hash = routes_records[0].get("input_stats_hash", "") if routes_records else ""
    if embedded_signals_hash and embedded_signals_hash != signals_hash:
        msg = (
            f"Hash mismatch: routes were generated against signals "
            f"{embedded_signals_hash[:16]}... "
            f"but current signals file hashes to {signals_hash[:16]}..."
        )
        print(f"[EXIT 2] {msg}", file=sys.stderr)
        stage_pending(
            msg,
            {"timestamp": timestamp, "routes_hash": routes_hash,
             "signals_hash": signals_hash, "stats_hash": stats_hash},
        )
        return 2

    print(f"[validate] cross-file hash: OK")
    print(f"[hash] routes:  {routes_hash[:16]}...")
    print(f"[hash] signals: {signals_hash[:16]}...")
    print(f"[hash] stats:   {stats_hash[:16]}...")

    # ── Build lookup tables ───────────────────────────────────────────────────
    routes_by_sf = build_lookup(routes_records)
    signals_by_sf = build_lookup(signals_records)
    stats_by_sf = build_lookup(stats_records)

    # Coverage gap warnings
    all_included_sfs_raw = {
        sf for sf, r in routes_by_sf.items()
        if r.get("primary_route") in include_routes
    }
    missing_signals = all_included_sfs_raw - set(signals_by_sf)
    missing_stats = all_included_sfs_raw - set(stats_by_sf)
    if missing_signals:
        print(f"[warn] {len(missing_signals)} included surface_form(s) absent from signals — defaulting fields")
    if missing_stats:
        print(f"[warn] {len(missing_stats)} included surface_form(s) absent from stats — defaulting fields")

    # ── Filter and sort ───────────────────────────────────────────────────────
    included_sfs: list[str] = sorted(
        sf for sf, r in routes_by_sf.items()
        if r.get("primary_route") in include_routes
    )
    total_in = len(routes_records)
    total_included = len(included_sfs)
    print(f"[filter] {total_included} of {total_in} surface_forms match include filter")

    if total_included == 0:
        msg = "Zero records match the include filter after join."
        print(f"[EXIT 2] {msg}", file=sys.stderr)
        stage_pending(
            msg,
            {"timestamp": timestamp, "routes_hash": routes_hash,
             "signals_hash": signals_hash, "stats_hash": stats_hash},
        )
        return 2

    # ── Build and validate output records ─────────────────────────────────────
    output_records: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    bucket_counts: dict[str, int] = defaultdict(int)

    for sf in included_sfs:
        route_r = routes_by_sf[sf]
        signal_r = signals_by_sf.get(sf)
        stats_r = stats_by_sf.get(sf)
        merged = merge_record(sf, route_r, signal_r, stats_r)
        errs = validate_output_record(merged, sf)
        if errs:
            validation_errors.extend(errs)
        ordered = ordered_record(merged)
        output_records.append(ordered)
        bucket_counts[ordered["primary_route"]] += 1

    if validation_errors:
        msg = "Output field validation errors:\n" + "\n".join(validation_errors[:20])
        if len(validation_errors) > 20:
            msg += f"\n... and {len(validation_errors) - 20} more"
        print(f"[EXIT 1] {msg}", file=sys.stderr)
        write_error_log(msg)
        return 1

    # ── Assemble metadata ─────────────────────────────────────────────────────
    # MD header uses the routes-file's own computation_timestamp so the markdown
    # is byte-identical on re-run. The manifest uses the live timestamp.
    routes_timestamp = (
        routes_records[0].get("computation_timestamp", timestamp)
        if routes_records else timestamp
    )
    meta: dict[str, Any] = {
        "timestamp": routes_timestamp,
        "run_timestamp": timestamp,
        "total_records": len(output_records),
        "routes_hash": routes_hash,
        "signals_hash": signals_hash,
        "stats_hash": stats_hash,
        "bucket_counts": dict(bucket_counts),
    }

    # ── Dry-run ───────────────────────────────────────────────────────────────
    if args.dry_run:
        print(f"\n[DRY-RUN] {len(output_records)} records would be written.")
        print(f"[DRY-RUN] Bucket distribution:")
        for bucket in sorted(bucket_counts.keys()):
            print(f"  {bucket:<42s} {bucket_counts[bucket]:>5}")
        print(f"\n[DRY-RUN] Field validation: PASS (all {len(output_records)} records valid)")
        sample = min(3, len(output_records))
        print(f"\n[DRY-RUN] Sample ({sample} records):")
        for rec in output_records[:sample]:
            print(json.dumps(rec, ensure_ascii=False, indent=2))
        print(f"\n[exit] EXIT 0 (dry-run — no output written)")
        return 0

    # ── Write JSONL atomically ────────────────────────────────────────────────
    jsonl_content = "".join(
        json.dumps(rec, ensure_ascii=False) + "\n" for rec in output_records
    )
    try:
        write_atomic(OUTPUT_JSONL, jsonl_content)
    except OSError as exc:
        msg = f"JSONL write failed: {exc}"
        print(f"[EXIT 1] {msg}", file=sys.stderr)
        write_error_log(msg)
        return 1

    # ── Write markdown atomically ─────────────────────────────────────────────
    md_content = build_markdown(output_records, meta, include_routes)
    try:
        write_atomic(OUTPUT_MD, md_content)
    except OSError as exc:
        msg = f"Markdown write failed: {exc}"
        print(f"[EXIT 1] {msg}", file=sys.stderr)
        write_error_log(msg)
        return 1

    # ── Append manifest ───────────────────────────────────────────────────────
    try:
        append_manifest(meta)
    except OSError as exc:
        print(f"[warn] could not write manifest: {exc}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n[complete]")
    print(f"  output JSONL: {OUTPUT_JSONL.relative_to(MRLORE_ROOT)}")
    print(f"  output MD:    {OUTPUT_MD.relative_to(MRLORE_ROOT)}")
    print(f"  manifest:     {MANIFEST_FILE.relative_to(MRLORE_ROOT)}")
    print(f"  records:      {len(output_records):,}")
    print(f"  buckets:")
    for bucket in sorted(bucket_counts.keys()):
        print(f"    {bucket:<42s} {bucket_counts[bucket]:>5}")
    print("[exit] EXIT 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
