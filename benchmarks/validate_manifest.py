#!/usr/bin/env python3
"""Validate benchmark run metadata and the public-claim release gate.

Uses only the Python standard library. This validates reporting completeness,
not whether a memory method is scientifically sound.

Run:
    python3 benchmarks/validate_manifest.py RUN/manifest.json
    python3 benchmarks/validate_manifest.py RUN/manifest.json --release
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


PLACEHOLDER = re.compile(r"replace-me|^$|^0+$", re.IGNORECASE)
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
GIT_COMMIT = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


def get(data, dotted):
    value = data
    for key in dotted.split("."):
        if not isinstance(value, dict) or key not in value:
            raise KeyError(dotted)
        value = value[key]
    return value


def is_placeholder(value):
    return value is None or (
        isinstance(value, str) and bool(PLACEHOLDER.search(value.strip()))
    )


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(data, manifest_path, release=False):
    errors = []
    required = [
        "schema_version",
        "comparison_id",
        "run_id",
        "status",
        "benchmark.name",
        "benchmark.version",
        "benchmark.split",
        "benchmark.expected_cases",
        "benchmark.dataset_sha256",
        "repository_commit",
        "repository_dirty",
        "started_at",
        "completed_at",
        "reader.provider",
        "reader.model",
        "reader.revision",
        "reader.temperature",
        "reader.max_output_tokens",
        "condition.name",
        "condition.implementation",
        "condition.implementation_sha256",
        "controls.prompt_sha256",
        "controls.context_budget_tokens",
        "controls.retrieval_budget_tokens",
        "controls.retrieval_top_k",
        "controls.seed",
        "controls.online_ingestion",
        "controls.oracle_evidence",
        "scoring.name",
        "scoring.revision",
        "scoring.official",
        "scoring.prompt_sha256",
        "metrics.cases_total",
        "metrics.cases_scored",
        "artifacts.predictions_jsonl",
        "artifacts.retrieval_jsonl",
        "artifacts.events_jsonl",
        "artifacts.stdout_log",
        "artifacts.stderr_log",
        "artifact_sha256.predictions_jsonl",
        "artifact_sha256.retrieval_jsonl",
        "artifact_sha256.events_jsonl",
        "artifact_sha256.stdout_log",
        "artifact_sha256.stderr_log",
    ]
    for field in required:
        try:
            get(data, field)
        except KeyError:
            errors.append(f"missing required field: {field}")

    if errors:
        return errors

    if data["schema_version"] != 1:
        errors.append("schema_version must be 1")

    if data["status"] not in {"planned", "running", "complete", "failed"}:
        errors.append("status must be planned, running, complete, or failed")

    for field in (
        "reader.temperature",
    ):
        value = get(data, field)
        if not is_number(value):
            errors.append(f"{field} must be numeric")
        elif value < 0:
            errors.append(f"{field} must be non-negative")

    for field in (
        "reader.max_output_tokens",
        "controls.context_budget_tokens",
        "controls.retrieval_budget_tokens",
        "controls.retrieval_top_k",
        "controls.seed",
        "metrics.cases_total",
        "metrics.cases_scored",
        "benchmark.expected_cases",
    ):
        value = get(data, field)
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{field} must be an integer")
        elif value < 0:
            errors.append(f"{field} must be non-negative")

    for field in (
        "repository_dirty",
        "controls.online_ingestion",
        "controls.oracle_evidence",
        "scoring.official",
    ):
        if not isinstance(get(data, field), bool):
            errors.append(f"{field} must be boolean")

    total = data["metrics"]["cases_total"]
    scored = data["metrics"]["cases_scored"]
    if isinstance(total, int) and isinstance(scored, int) and scored > total:
        errors.append("metrics.cases_scored cannot exceed metrics.cases_total")

    if release:
        if data["status"] != "complete":
            errors.append("release gate: status must be complete")
        if data["repository_dirty"] is not False:
            errors.append("release gate: repository_dirty must be false")
        if data["controls"]["oracle_evidence"] is not False:
            errors.append("release gate: oracle_evidence must be false")
        if data["controls"]["online_ingestion"] is not True:
            errors.append("release gate: online_ingestion must be true")
        if not (isinstance(total, int) and isinstance(scored, int)) or total <= 0 or scored != total:
            errors.append("release gate: every case must be scored")
        expected = data["benchmark"]["expected_cases"]
        if not isinstance(expected, int) or isinstance(expected, bool) or expected <= 0:
            errors.append("release gate: benchmark.expected_cases must be a positive integer")
        elif total != expected:
            errors.append("release gate: cases_total must equal benchmark.expected_cases")
        if data["scoring"]["official"] is not True:
            errors.append("release gate: scoring.official must be true")
        if not is_number(data["reader"]["max_output_tokens"]) or data["reader"]["max_output_tokens"] <= 0:
            errors.append("release gate: reader.max_output_tokens must be positive")
        if not is_number(data["controls"]["context_budget_tokens"]) or data["controls"]["context_budget_tokens"] <= 0:
            errors.append("release gate: controls.context_budget_tokens must be positive")
        if not is_number(data["controls"]["retrieval_budget_tokens"]) or data["controls"]["retrieval_budget_tokens"] <= 0:
            errors.append("release gate: controls.retrieval_budget_tokens must be positive")
        if not is_number(data["controls"]["retrieval_top_k"]) or data["controls"]["retrieval_top_k"] <= 0:
            errors.append("release gate: controls.retrieval_top_k must be positive")

        identity_fields = [
            "comparison_id",
            "run_id",
            "benchmark.version",
            "benchmark.split",
            "started_at",
            "completed_at",
            "reader.provider",
            "reader.model",
            "reader.revision",
            "condition.name",
            "condition.implementation",
            "scoring.name",
            "scoring.revision",
        ]
        for field in identity_fields:
            if is_placeholder(get(data, field)):
                errors.append(f"release gate: {field} is missing or a placeholder")
        if not HEX64.fullmatch(str(data["benchmark"]["dataset_sha256"])):
            errors.append("release gate: dataset_sha256 must be a 64-character hex digest")
        if not HEX64.fullmatch(str(data["controls"]["prompt_sha256"])):
            errors.append("release gate: prompt_sha256 must be a 64-character hex digest")
        if not HEX64.fullmatch(str(data["scoring"]["prompt_sha256"])):
            errors.append("release gate: scoring.prompt_sha256 must be a 64-character hex digest")
        if not HEX64.fullmatch(str(data["condition"]["implementation_sha256"])):
            errors.append("release gate: implementation_sha256 must be a 64-character hex digest")
        if not GIT_COMMIT.fullmatch(str(data["repository_commit"])):
            errors.append("release gate: repository_commit must be a git commit hash")

        required_metrics = [
            "answer_accuracy",
            "answer_accuracy_ci95_low",
            "answer_accuracy_ci95_high",
            "mean_retrieved_tokens",
            "mean_query_latency_ms",
            "p95_query_latency_ms",
            "mean_ingest_tokens_per_event",
        ]
        for metric in required_metrics:
            value = data["metrics"].get(metric)
            if value is None or not is_number(value):
                errors.append(f"release gate: metrics.{metric} must be numeric")

        for metric in (
            "answer_accuracy",
            "answer_accuracy_ci95_low",
            "answer_accuracy_ci95_high",
            "retrieval_recall_at_k",
            "abstention_accuracy",
        ):
            value = data["metrics"].get(metric)
            if value is not None and (not is_number(value) or not 0 <= value <= 1):
                errors.append(f"release gate: metrics.{metric} must be between 0 and 1")

        low = data["metrics"].get("answer_accuracy_ci95_low")
        point = data["metrics"].get("answer_accuracy")
        high = data["metrics"].get("answer_accuracy_ci95_high")
        if all(is_number(value) for value in (low, point, high)):
            if not low <= point <= high:
                errors.append("release gate: answer accuracy must lie inside its CI")

        base = manifest_path.parent.resolve()
        for name, relative in data["artifacts"].items():
            if not isinstance(relative, str) or is_placeholder(relative):
                errors.append(f"release gate: artifacts.{name} is a placeholder")
                continue
            relative_path = Path(relative)
            path = (base / relative_path).resolve()
            if relative_path.is_absolute() or base not in path.parents:
                errors.append(f"release gate: artifact must stay inside run directory: {name}")
                continue
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"release gate: missing or empty artifact {name}: {relative}")
                continue
            expected = data["artifact_sha256"].get(name)
            if not isinstance(expected, str) or not HEX64.fullmatch(expected):
                errors.append(f"release gate: artifact_sha256.{name} must be a hex digest")
            elif sha256_file(path) != expected.lower():
                errors.append(f"release gate: artifact_sha256.{name} does not match {relative}")

    return errors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args(argv)

    try:
        raw = args.manifest.read_bytes()
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid manifest: {exc}", file=sys.stderr)
        return 2

    errors = validate(data, args.manifest, release=args.release)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    digest = hashlib.sha256(raw).hexdigest()
    mode = "release" if args.release else "structure"
    print(f"PASS: {mode} validation; manifest_sha256={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
