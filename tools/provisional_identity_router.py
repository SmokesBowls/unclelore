#!/usr/bin/env python3
"""
MrLore v2 — Phase 6.3A Provisional Identity Router

Reads identity signal stats and assigns each surface_form to a deterministic
review bucket via configurable numeric thresholds.

Contract:
- No LLM inference. No wiki writes. No canon decisions. No entity type labels.
- Pure threshold evaluation — same inputs → byte-identical output.
- Input: raw/math/identity_signal_stats.jsonl
- Output: raw/math/provisional_identity_routes.jsonl  (atomic write)
- EXIT 0: all surface_forms routed, output written.
- EXIT 1: structural failure (malformed JSONL, missing required fields, crash).
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

try:
    import yaml as _yaml_mod
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


MRLORE_ROOT = Path(__file__).resolve().parents[1]
MATH_ROOT = MRLORE_ROOT / "raw" / "math"
SCHEMA_DIR = MRLORE_ROOT / "schema"

PASS2_SCHEMA = SCHEMA_DIR / "PASS2_MATH_SCHEMA.md"
INPUT_STATS = MATH_ROOT / "identity_signal_stats.jsonl"
OUTPUT_FILENAME = "provisional_identity_routes.jsonl"
MANIFEST_FILENAME = "provisional_identity_routes.manifest.json"

TOOL_VERSION = "provisional_identity_router/0.1.0"

REQUIRED_INPUT_FIELDS = frozenset({
    "surface_form", "total_mentions", "chapter_count",
    "speech_ratio", "action_ratio", "monologue_viability_score",
    "collective_fragmentation_score", "conceptual_drift_score",
})

REQUIRED_OUTPUT_FIELDS = frozenset({
    "surface_form", "primary_route", "matched_rules",
    "routing_reasons", "provisional", "audit_only",
})

# Evaluation priority order (highest = first = wins as primary_route).
PRIORITY_ORDER = (
    "noise_or_header_candidate",
    "concept_field_candidate",
    "bounded_actor_candidate",
    "collective_or_species_candidate",
    "identity_braid_candidate",
    "sparse_reference_candidate",
    "ambiguous_review_candidate",
)

# ──────────────────────────────────────────────────────────────
# Embedded default thresholds
# ──────────────────────────────────────────────────────────────

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "bounded_actor_candidate": {
        "speech_ratio_min": 0.05,
        "action_ratio_min": 0.05,
        "monologue_viability_score_min": 0.01,
    },
    "identity_braid_candidate": {
        "speech_or_action_ratio_min": 0.05,
        "chapter_count_min": 10,
        "collective_fragmentation_score_min": 0.75,
    },
    "collective_or_species_candidate": {
        "speech_ratio_eq": 0.0,
        "action_ratio_max": 0.05,
        "chapter_count_min": 5,
        "collective_fragmentation_score_min": 0.5,
    },
    "concept_field_candidate": {
        "speech_ratio_eq": 0.0,
        "action_ratio_eq": 0.0,
        "conceptual_drift_score_min": 0.8,
    },
    "sparse_reference_candidate": {
        "chapter_count_max": 2,
        "total_mentions_max": 20,
    },
    "noise_or_header_candidate": {
        "total_mentions_max": 3,
    },
}

_REQUIRED_THRESHOLD_KEYS: dict[str, frozenset[str]] = {
    "bounded_actor_candidate": frozenset({
        "speech_ratio_min", "action_ratio_min", "monologue_viability_score_min",
    }),
    "identity_braid_candidate": frozenset({
        "speech_or_action_ratio_min", "chapter_count_min",
        "collective_fragmentation_score_min",
    }),
    "collective_or_species_candidate": frozenset({
        "speech_ratio_eq", "action_ratio_max",
        "chapter_count_min", "collective_fragmentation_score_min",
    }),
    "concept_field_candidate": frozenset({
        "speech_ratio_eq", "action_ratio_eq", "conceptual_drift_score_min",
    }),
    "sparse_reference_candidate": frozenset({
        "chapter_count_max", "total_mentions_max",
    }),
    "noise_or_header_candidate": frozenset({
        "total_mentions_max",
    }),
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


def sha256_of_dict(d: dict) -> str:
    canonical = json.dumps(d, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def feq(a: float, b: float, eps: float = 1e-9) -> bool:
    """Float equality with epsilon guard for division-derived values."""
    return abs(a - b) <= eps


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


def write_atomic_validated(path: Path, records: list[dict]) -> None:
    """Write records to JSONL atomically; validates structure before rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    tmp_path = Path(tmp)
    try:
        content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        with tmp_path.open(encoding="utf-8") as fh:
            for line_num, raw in enumerate(fh, 1):
                raw = raw.strip()
                if not raw:
                    continue
                parsed = json.loads(raw)
                missing = REQUIRED_OUTPUT_FIELDS - set(parsed)
                if missing:
                    raise ValueError(
                        f"Temp file line {line_num}: missing {sorted(missing)}"
                    )
        os.replace(tmp, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ──────────────────────────────────────────────────────────────
# Config loading and validation
# ──────────────────────────────────────────────────────────────

def load_config(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        if not _YAML_AVAILABLE:
            raise ValueError(
                "pyyaml not installed — required for YAML config.\n"
                "  Install: pip install pyyaml\n"
                f"  Or use JSON: {path.with_suffix('.json')}"
            )
        with path.open(encoding="utf-8") as fh:
            data = _yaml_mod.safe_load(fh)
    elif suffix == ".json":
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        raise ValueError(
            f"Unsupported config format '{suffix}'. Use .yaml, .yml, or .json"
        )
    if not data:
        raise ValueError("Config file is empty or null")
    if "thresholds" in data:
        data = data["thresholds"]
    return data


def validate_thresholds(t: dict[str, Any]) -> list[str]:
    """Return list of validation errors, or [] if valid."""
    errors: list[str] = []
    for rule, required_keys in _REQUIRED_THRESHOLD_KEYS.items():
        if rule not in t:
            errors.append(f"Missing threshold block: '{rule}'")
            continue
        block = t[rule]
        if not isinstance(block, dict):
            errors.append(f"'{rule}' must be a mapping, got {type(block).__name__}")
            continue
        missing = required_keys - set(block)
        if missing:
            errors.append(f"'{rule}' missing keys: {sorted(missing)}")
    return errors


# ──────────────────────────────────────────────────────────────
# Rule evaluators — each returns (matched: bool, reasons: dict)
# ──────────────────────────────────────────────────────────────

def eval_noise_or_header(
    r: dict[str, Any], t: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    th = t["noise_or_header_candidate"]
    tm = r["total_mentions"]
    return tm <= th["total_mentions_max"], {"total_mentions": tm}


def eval_concept_field(
    r: dict[str, Any], t: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    th = t["concept_field_candidate"]
    sr = r["speech_ratio"]
    ar = r["action_ratio"]
    cds = r["conceptual_drift_score"]
    matched = (
        feq(sr, th["speech_ratio_eq"])
        and feq(ar, th["action_ratio_eq"])
        and cds >= th["conceptual_drift_score_min"]
    )
    return matched, {"speech_ratio": sr, "action_ratio": ar, "conceptual_drift_score": cds}


def eval_bounded_actor(
    r: dict[str, Any], t: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    th = t["bounded_actor_candidate"]
    sr = r["speech_ratio"]
    ar = r["action_ratio"]
    mvs = r["monologue_viability_score"]
    matched = (
        sr >= th["speech_ratio_min"]
        and ar >= th["action_ratio_min"]
        and mvs >= th["monologue_viability_score_min"]
    )
    return matched, {
        "speech_ratio": sr,
        "action_ratio": ar,
        "monologue_viability_score": mvs,
    }


def eval_collective_or_species(
    r: dict[str, Any], t: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    th = t["collective_or_species_candidate"]
    sr = r["speech_ratio"]
    ar = r["action_ratio"]
    cc = r["chapter_count"]
    cfs = r["collective_fragmentation_score"]
    matched = (
        feq(sr, th["speech_ratio_eq"])
        and ar <= th["action_ratio_max"]
        and cc >= th["chapter_count_min"]
        and cfs >= th["collective_fragmentation_score_min"]
    )
    return matched, {
        "speech_ratio": sr,
        "action_ratio": ar,
        "chapter_count": cc,
        "collective_fragmentation_score": cfs,
    }


def eval_identity_braid(
    r: dict[str, Any], t: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    th = t["identity_braid_candidate"]
    sr = r["speech_ratio"]
    ar = r["action_ratio"]
    cc = r["chapter_count"]
    cfs = r["collective_fragmentation_score"]
    min_ratio = th["speech_or_action_ratio_min"]
    matched = (
        (sr >= min_ratio or ar >= min_ratio)
        and cc >= th["chapter_count_min"]
        and cfs >= th["collective_fragmentation_score_min"]
    )
    return matched, {
        "speech_ratio": sr,
        "action_ratio": ar,
        "chapter_count": cc,
        "collective_fragmentation_score": cfs,
    }


def eval_sparse_reference(
    r: dict[str, Any], t: dict[str, Any]
) -> tuple[bool, dict[str, Any]]:
    th = t["sparse_reference_candidate"]
    cc = r["chapter_count"]
    tm = r["total_mentions"]
    matched = cc <= th["chapter_count_max"] and tm <= th["total_mentions_max"]
    return matched, {"chapter_count": cc, "total_mentions": tm}


_EVALUATORS: dict[str, Any] = {
    "noise_or_header_candidate": eval_noise_or_header,
    "concept_field_candidate": eval_concept_field,
    "bounded_actor_candidate": eval_bounded_actor,
    "collective_or_species_candidate": eval_collective_or_species,
    "identity_braid_candidate": eval_identity_braid,
    "sparse_reference_candidate": eval_sparse_reference,
}


def route_record(
    r: dict[str, Any], thresholds: dict[str, Any]
) -> tuple[str, list[str], dict[str, Any]]:
    """
    Evaluate all threshold rules in priority order.
    Returns (primary_route, all_matched_rules, routing_reasons_for_primary).
    ambiguous_review_candidate is the fallback when nothing else matches.
    """
    matched: list[str] = []
    reasons_by_rule: dict[str, dict[str, Any]] = {}

    for rule_name in PRIORITY_ORDER:
        if rule_name == "ambiguous_review_candidate":
            continue
        evaluator = _EVALUATORS[rule_name]
        is_match, rule_reasons = evaluator(r, thresholds)
        if is_match:
            matched.append(rule_name)
            reasons_by_rule[rule_name] = rule_reasons

    if matched:
        primary = matched[0]  # highest priority by iteration order
        return primary, matched, reasons_by_rule[primary]
    else:
        return "ambiguous_review_candidate", ["ambiguous_review_candidate"], {}


# ──────────────────────────────────────────────────────────────
# Data loading
# ──────────────────────────────────────────────────────────────

def load_signal_stats() -> tuple[list[dict[str, Any]], str]:
    if not INPUT_STATS.exists():
        raise FileNotFoundError(f"Missing identity signal stats: {INPUT_STATS}")
    file_hash = sha256_of_file(INPUT_STATS)
    records: list[dict[str, Any]] = []
    with INPUT_STATS.open(encoding="utf-8") as fh:
        for line_num, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"identity_signal_stats.jsonl line {line_num}: {exc}"
                ) from exc
            missing = REQUIRED_INPUT_FIELDS - set(rec)
            if missing:
                raise ValueError(
                    f"identity_signal_stats.jsonl line {line_num}: "
                    f"missing fields {sorted(missing)}"
                )
            records.append(rec)
    return records, file_hash


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Provisional identity router — deterministic threshold-based review bucket assignment.\n"
            "Note: --dry-run exits with code 2 per pipeline safety convention."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute routes and preview sample without writing (EXIT 0).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Compute and write raw/math/provisional_identity_routes.jsonl (EXIT 0).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Threshold config (.yaml, .yml, or .json). Uses embedded defaults if omitted.",
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
    print(f"[init] tool: {TOOL_VERSION}")

    # Load threshold config
    if args.config:
        print(f"[config] loading: {args.config}")
        try:
            raw_config = load_config(args.config)
        except (FileNotFoundError, ValueError, OSError) as exc:
            print(f"[EXIT 2] Threshold config error: {exc}", file=sys.stderr)
            return 2
        errors = validate_thresholds(raw_config)
        if errors:
            print("[EXIT 2] Invalid threshold config:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 2
        thresholds = raw_config
        config_source = str(args.config)
    else:
        thresholds = DEFAULT_THRESHOLDS
        config_source = "embedded_defaults"
        print("[config] using embedded defaults")

    threshold_config_hash = sha256_of_dict(thresholds)
    print(f"[config] hash: {threshold_config_hash[:16]}...")

    # Load and validate signal stats
    print(f"[load] {INPUT_STATS.name} ...", end=" ", flush=True)
    try:
        signal_records, stats_hash = load_signal_stats()
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"\n[EXIT 1] {exc}", file=sys.stderr)
        return 1
    print(f"{len(signal_records):,} surface_forms")
    print(f"[load] input hash: {stats_hash[:16]}...")

    # Sort for deterministic processing (input is already sorted, but enforce it)
    signal_records.sort(key=lambda r: r["surface_form"])

    # Route all records
    timestamp = now_iso()
    print(f"[route] evaluating {len(signal_records):,} surface_forms ...", end=" ", flush=True)

    output_records: list[dict[str, Any]] = []
    bucket_counts: dict[str, int] = defaultdict(int)

    for rec in signal_records:
        primary_route, matched_rules, routing_reasons = route_record(rec, thresholds)
        bucket_counts[primary_route] += 1
        output_records.append({
            "surface_form": rec["surface_form"],
            "total_mentions": rec["total_mentions"],
            "chapter_count": rec["chapter_count"],
            "primary_route": primary_route,
            "matched_rules": matched_rules,
            "routing_reasons": routing_reasons,
            "provisional": True,
            "audit_only": True,
            "computation_timestamp": timestamp,
            "input_stats_hash": stats_hash,
            "threshold_config_hash": threshold_config_hash,
        })

    print(f"done")

    # Bucket distribution summary
    total = len(output_records)
    print("[route] bucket distribution:")
    for bucket in PRIORITY_ORDER:
        count = bucket_counts.get(bucket, 0)
        bar = "#" * max(1, round(30 * count / max(1, total)))
        print(f"  {bucket:<42s} {count:>5}  {100 * count / max(1, total):5.1f}%  {bar}")

    # Sanity check: same number of outputs as inputs
    if len(output_records) != len(signal_records):
        print(
            f"[EXIT 1] Record count mismatch: {len(output_records)} out vs "
            f"{len(signal_records)} in",
            file=sys.stderr,
        )
        return 1

    # Dry-run: print sample without writing
    if args.dry_run:
        sample_count = min(5, len(output_records))
        print(f"\n[DRY-RUN] Sample ({sample_count} of {total} records):")
        for r in output_records[:sample_count]:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        print(f"\n[exit] EXIT 0 (dry-run — no output written)")
        return 0

    # Write output atomically with JSONL structure validation
    output_path = MATH_ROOT / OUTPUT_FILENAME
    try:
        write_atomic_validated(output_path, output_records)
    except (OSError, ValueError) as exc:
        print(f"[EXIT 1] Output write failed: {exc}", file=sys.stderr)
        return 1

    # Write manifest sidecar
    manifest = {
        "tool": TOOL_VERSION,
        "timestamp": timestamp,
        "input_stats": str(INPUT_STATS.relative_to(MRLORE_ROOT)),
        "input_stats_hash": stats_hash,
        "threshold_config_source": config_source,
        "threshold_config_hash": threshold_config_hash,
        "thresholds": thresholds,
        "total_records": total,
        "bucket_counts": {
            bucket: bucket_counts.get(bucket, 0) for bucket in PRIORITY_ORDER
        },
    }
    manifest_path = MATH_ROOT / MANIFEST_FILENAME
    try:
        write_atomic(
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
    except OSError as exc:
        print(f"[warn] Could not write manifest sidecar: {exc}")

    print(f"\n[complete]")
    print(f"  output:   {output_path.relative_to(MRLORE_ROOT)}")
    print(f"  manifest: {manifest_path.relative_to(MRLORE_ROOT)}")
    print(f"  records:  {total:,}")
    print("[exit] EXIT 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
