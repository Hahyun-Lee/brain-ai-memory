#!/usr/bin/env python3
"""Run an explicitly non-release LongMemEval retrieval or reader pilot.

This is a feasibility pilot for retrieval conditions:

1. recency: the most recent sessions;
2. flat_bm25: BM25 over full session text; and
3. pointer_bm25_tN: BM25 over compact, query-independent session pointers with
   N keywords, followed by detail fetch.

Retrieval-only mode can evaluate the full cleaned set without a reader LLM.
Reader mode uses a deterministic stratified subset and a simple
answer-containment proxy because the official evaluator requires a separate
judge model. Neither mode tests consolidation, reconsolidation, rule gating, or
the full architecture.

Example:
    python3 benchmarks/run_longmemeval_pilot.py \
      --data /path/to/longmemeval_s_cleaned.json \
      --output benchmarks/pilots/my-run \
      --model qwen2.5:7b --per-type 2
"""

import argparse
import hashlib
import json
import math
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


BASE_CONDITIONS = ("recency", "flat_bm25")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.IGNORECASE)
NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
STOPWORDS = {
    "a", "about", "after", "again", "all", "also", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "but",
    "by", "can", "could", "did", "do", "does", "for", "from", "had",
    "has", "have", "he", "her", "here", "hers", "him", "his", "how",
    "i", "if", "in", "into", "is", "it", "its", "just", "me", "more",
    "my", "no", "not", "of", "on", "or", "our", "out", "she", "so",
    "some", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "those", "to", "too", "up", "us", "was",
    "we", "were", "what", "when", "where", "which", "who", "why", "will",
    "with", "would", "you", "your", "assistant", "user",
}
PROMPT_TEMPLATE = """You answer a question about the user's past conversations.
Use only the retrieved history below. If the answer is not supported, answer
"I don't know." Give only the concise answer, without explaining your process.

Question date: {question_date}

Retrieved history:
{history}

Question: {question}
Answer:"""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_fact(args, default):
    try:
        result = subprocess.run(
            ["git", *args], check=True, capture_output=True, text=True
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return default


def tokenize(text):
    return TOKEN_RE.findall(text.lower())


def normalize_answer(value):
    return NORMALIZE_RE.sub(" ", str(value).lower()).strip()


def answer_match(prediction, reference):
    pred = normalize_answer(prediction)
    ref = normalize_answer(reference)
    return bool(pred and ref and (pred == ref or ref in pred))


def wilson_interval(successes, total, z=1.96):
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    margin /= denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


def percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def select_items(data, seed, per_type, all_items=False):
    if all_items:
        return sorted(data, key=lambda item: item["question_id"])
    grouped = defaultdict(list)
    for item in data:
        grouped[item["question_type"]].append(item)

    selected = []
    for question_type in sorted(grouped):
        ranked = sorted(
            grouped[question_type],
            key=lambda item: sha256_bytes(
                f"{seed}:{item['question_id']}".encode("utf-8")
            ),
        )
        selected.extend(ranked[:per_type])
    return sorted(selected, key=lambda item: (item["question_type"], item["question_id"]))


def session_text(turns):
    return "\n".join(
        f"{turn.get('role', 'unknown')}: {turn.get('content', '')}" for turn in turns
    )


def build_sessions(item, max_pointer_terms):
    sessions = []
    for position, (session_id, date, turns) in enumerate(
        zip(
            item["haystack_session_ids"],
            item["haystack_dates"],
            item["haystack_sessions"],
        )
    ):
        text = session_text(turns)
        terms = [
            token for token in tokenize(text)
            if token not in STOPWORDS and len(token) > 2
        ]
        keywords = [
            token for token, _ in Counter(terms).most_common(max_pointer_terms)
        ]
        sessions.append(
            {
                "position": position,
                "session_id": session_id,
                "date": date,
                "text": text,
                "pointer_keywords": keywords,
            }
        )
    return sessions


def bm25_scores(documents, query, k1=1.5, b=0.75):
    tokenized = [tokenize(document) for document in documents]
    query_tokens = tokenize(query)
    n_docs = len(tokenized)
    if n_docs == 0:
        return []
    avg_length = sum(map(len, tokenized)) / n_docs or 1.0
    document_frequency = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))

    scores = []
    for tokens in tokenized:
        counts = Counter(tokens)
        length = len(tokens)
        score = 0.0
        for term in query_tokens:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            df = document_frequency[term]
            inverse_frequency = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1 - b + b * length / avg_length)
            score += inverse_frequency * frequency * (k1 + 1) / denominator
        scores.append(score)
    return scores


def pointer_term_count(condition):
    match = re.fullmatch(r"pointer_bm25_t([1-9][0-9]*)", condition)
    return int(match.group(1)) if match else None


def pointer_text(session, term_count):
    return f"{session['date']} {' '.join(session['pointer_keywords'][:term_count])}"


def rank_sessions(condition, sessions, question):
    if condition == "recency":
        return [(index, float(len(sessions) - index)) for index in reversed(range(len(sessions)))]
    if condition == "flat_bm25":
        documents = [session["text"] for session in sessions]
    else:
        term_count = pointer_term_count(condition)
        if term_count is None:
            raise ValueError(f"unknown retrieval condition: {condition}")
        documents = [pointer_text(session, term_count) for session in sessions]
    scores = bm25_scores(documents, question)
    return sorted(enumerate(scores), key=lambda pair: (-pair[1], pair[0]))


def clip_middle(text, limit):
    if len(text) <= limit:
        return text
    if limit < 80:
        return text[:limit]
    head = (limit - 24) // 2
    tail = limit - 24 - head
    return f"{text[:head]}\n...[truncated]...\n{text[-tail:]}"


def retrieve(condition, sessions, question, top_k, retrieval_budget_chars):
    ranked = rank_sessions(condition, sessions, question)
    selected = ranked[:top_k]
    per_session = max(1, retrieval_budget_chars // max(1, len(selected)))
    blocks = []
    records = []
    for rank, (index, score) in enumerate(selected, start=1):
        session = sessions[index]
        block = f"[Conversation {session['position'] + 1}; {session['date']}]\n{session['text']}"
        clipped = clip_middle(block, per_session)
        blocks.append((session["position"], clipped))
        records.append(
            {
                "rank": rank,
                "session_id": session["session_id"],
                "position": session["position"],
                "score": score,
                "source_chars": len(block),
                "retrieved_chars": len(clipped),
            }
        )
    history = "\n\n".join(block for _, block in sorted(blocks))
    return history, records


def ollama_generate(host, model, prompt, max_output_tokens, context_tokens, timeout):
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0,
                "num_predict": max_output_tokens,
                "num_ctx": context_tokens,
                "seed": 0,
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read())
        error = None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        result = {}
        error = str(exc)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "prediction": result.get("response", ""),
        "error": error,
        "elapsed_ms": elapsed_ms,
        "prompt_tokens": result.get("prompt_eval_count", 0),
        "output_tokens": result.get("eval_count", 0),
        "ollama_total_ns": result.get("total_duration", 0),
    }


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build_manifest(
    *, args, condition, condition_dir, comparison_id, dataset_sha256,
    repository_commit, repository_dirty, started_at, completed_at, records,
    retrieval_records, event_records, expected_cases, reader_prompt,
):
    successes = sum(record["answer_containment"] is True for record in records)
    total = len(records)
    low, high = wilson_interval(successes, total) if not args.retrieval_only else (None, None)
    query_latencies = [event["query_latency_ms"] for event in event_records]
    artifact_paths = {
        "predictions_jsonl": "predictions.jsonl",
        "retrieval_jsonl": "retrieval.jsonl",
        "events_jsonl": "events.jsonl",
        "stdout_log": "stdout.log",
        "stderr_log": "stderr.log",
        "prompt_txt": "prompt.txt",
    }
    artifact_hashes = {
        name: sha256_file(condition_dir / relative)
        for name, relative in artifact_paths.items()
    }
    retrieval_recalls = [record["answer_session_recall"] for record in retrieval_records]
    retrieved_chars = [record["retrieved_chars"] for record in retrieval_records]
    index_chars = [record["index_chars"] for record in retrieval_records]
    by_type = defaultdict(list)
    for record in retrieval_records:
        by_type[record["question_type"]].append(record["answer_session_recall"])

    return {
        "schema_version": 1,
        "comparison_id": comparison_id,
        "run_id": f"{comparison_id}-{condition}",
        "status": "complete",
        "benchmark": {
            "name": "LongMemEval",
            "version": "longmemeval_s_cleaned.json",
            "split": (
                "all-items" if args.all_items
                else f"deterministic-stratified-{args.per_type}-per-type"
            ),
            "expected_cases": expected_cases,
            "dataset_sha256": dataset_sha256,
        },
        "repository_commit": repository_commit,
        "repository_dirty": repository_dirty,
        "started_at": started_at,
        "completed_at": completed_at,
        "reader": {
            "provider": "none-retrieval-only" if args.retrieval_only else "ollama-local",
            "model": "none" if args.retrieval_only else args.model,
            "revision": "not-applicable" if args.retrieval_only else args.model_revision,
            "quantization": "not-applicable" if args.retrieval_only else "as-installed",
            "temperature": 0,
            "max_output_tokens": 0 if args.retrieval_only else args.max_output_tokens,
        },
        "condition": {
            "name": condition,
            "implementation": "benchmarks/run_longmemeval_pilot.py",
            "implementation_sha256": sha256_file(Path(__file__)),
            "pointer_terms": pointer_term_count(condition),
        },
        "controls": {
            "prompt_sha256": sha256_bytes(reader_prompt.encode("utf-8")),
            "context_budget_tokens": args.context_tokens,
            "retrieval_budget_tokens": args.retrieval_budget_tokens,
            "retrieval_top_k": args.top_k,
            "seed": args.seed,
            "online_ingestion": True,
            "oracle_evidence": False,
        },
        "scoring": {
            "name": (
                "answer-session-recall-at-k"
                if args.retrieval_only else "normalized-reference-containment-proxy"
            ),
            "revision": "pilot-v1",
            "official": False,
            "prompt_sha256": sha256_bytes(b"no-judge-prompt-used"),
        },
        "metrics": {
            "cases_total": total,
            "cases_scored": total,
            "answer_accuracy": (
                None if args.retrieval_only
                else successes / total if total else 0.0
            ),
            "answer_accuracy_ci95_low": low,
            "answer_accuracy_ci95_high": high,
            "retrieval_recall_at_k": (
                sum(retrieval_recalls) / len(retrieval_recalls)
                if retrieval_recalls else 0.0
            ),
            "retrieval_recall_at_k_by_type": {
                question_type: sum(values) / len(values)
                for question_type, values in sorted(by_type.items())
            },
            "abstention_accuracy": None,
            "mean_retrieved_tokens": (
                sum(retrieved_chars) / len(retrieved_chars) / 4
                if retrieved_chars else 0.0
            ),
            "mean_query_latency_ms": (
                sum(query_latencies) / len(query_latencies)
                if query_latencies else 0.0
            ),
            "p95_query_latency_ms": percentile(query_latencies, 0.95),
            "mean_ingest_tokens_per_event": 0.0,
            "mean_index_chars": (
                sum(index_chars) / len(index_chars) if index_chars else 0.0
            ),
        },
        "artifacts": artifact_paths,
        "artifact_sha256": artifact_hashes,
        "notes": (
            "NON-RELEASE PILOT. "
            + (
                "No reader model was called and answer_accuracy is intentionally null. "
                if args.retrieval_only else
                "answer_accuracy is normalized reference-string containment, not the "
                "official LongMemEval judge score. "
            )
            + "Retrieved tokens are estimated as characters/4. The pointer condition "
            "is a deterministic keyword prototype and does not implement consolidation "
            "or reconsolidation."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="qwen2.5:7b")
    parser.add_argument("--model-revision", default="local-ollama-tag")
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--per-type", type=int, default=2)
    parser.add_argument("--all-items", action="store_true")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--seed", type=int, default=20260714)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--pointer-terms",
        default="12,24,48,96",
        help="comma-separated keyword counts for pointer ablations",
    )
    parser.add_argument("--retrieval-budget-tokens", type=int, default=5000)
    parser.add_argument("--context-tokens", type=int, default=8192)
    parser.add_argument("--max-output-tokens", type=int, default=96)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    if (not args.all_items and args.per_type < 1) or args.top_k < 1 or args.retrieval_budget_tokens < 1:
        parser.error("per-type, top-k, and retrieval-budget-tokens must be positive")
    if not args.data.is_file():
        parser.error(f"data file does not exist: {args.data}")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error(f"output directory is not empty: {args.output}")

    args.output.mkdir(parents=True, exist_ok=True)
    try:
        pointer_counts = sorted({int(value) for value in args.pointer_terms.split(",")})
    except ValueError:
        parser.error("pointer-terms must be comma-separated positive integers")
    if not pointer_counts or any(value < 1 for value in pointer_counts):
        parser.error("pointer-terms must be comma-separated positive integers")
    conditions = (*BASE_CONDITIONS, *(f"pointer_bm25_t{value}" for value in pointer_counts))
    started_at = utc_now()
    mode = "retrieval" if args.retrieval_only else "qa"
    comparison_id = f"longmemeval-{mode}-pilot-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    dataset_sha256 = sha256_file(args.data)
    repository_commit = git_fact(["rev-parse", "HEAD"], "unknown")
    repository_dirty = bool(git_fact(["status", "--porcelain"], "dirty"))

    with args.data.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    expected_cases = len(data)
    items = select_items(data, args.seed, args.per_type, args.all_items)
    del data

    condition_state = {
        condition: {"predictions": [], "retrieval": [], "events": [], "stdout": []}
        for condition in conditions
    }
    retrieval_budget_chars = args.retrieval_budget_tokens * 4

    print(
        f"NON-RELEASE PILOT: {len(items)} items, {len(conditions)} conditions, "
        f"mode={mode}" + ("" if args.retrieval_only else f", model={args.model}")
    )
    for item_number, item in enumerate(items, start=1):
        ingest_started = time.perf_counter()
        sessions = build_sessions(item, max(pointer_counts))
        ingest_ms = (time.perf_counter() - ingest_started) * 1000
        answer_ids = set(item.get("answer_session_ids", []))

        for condition in conditions:
            retrieval_started = time.perf_counter()
            history, retrieved = retrieve(
                condition,
                sessions,
                item["question"],
                args.top_k,
                retrieval_budget_chars,
            )
            retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
            if args.retrieval_only:
                result = {
                    "prediction": "",
                    "error": None,
                    "elapsed_ms": retrieval_ms,
                    "prompt_tokens": 0,
                    "output_tokens": 0,
                    "ollama_total_ns": 0,
                }
                match = None
            else:
                prompt = PROMPT_TEMPLATE.format(
                    question_date=item["question_date"],
                    history=history,
                    question=item["question"],
                )
                result = ollama_generate(
                    args.ollama_host,
                    args.model,
                    prompt,
                    args.max_output_tokens,
                    args.context_tokens,
                    args.timeout,
                )
                result["elapsed_ms"] += retrieval_ms
                match = answer_match(result["prediction"], item["answer"])
            selected_ids = {record["session_id"] for record in retrieved}
            answer_recall = (
                len(answer_ids & selected_ids) / len(answer_ids) if answer_ids else 0.0
            )
            if condition == "recency":
                index_chars = 0
            elif condition == "flat_bm25":
                index_chars = sum(len(session["text"]) for session in sessions)
            else:
                term_count = pointer_term_count(condition)
                index_chars = sum(
                    len(pointer_text(session, term_count)) for session in sessions
                )
            state = condition_state[condition]
            prediction_record = {
                "question_id": item["question_id"],
                "question_type": item["question_type"],
                "hypothesis": result["prediction"],
                "answer_containment": match,
                "error": result["error"],
            }
            if not args.retrieval_only:
                prediction_record.update(
                    {"question": item["question"], "reference": item["answer"]}
                )
            state["predictions"].append(prediction_record)
            state["retrieval"].append(
                {
                    "question_id": item["question_id"],
                    "question_type": item["question_type"],
                    "answer_session_ids": sorted(answer_ids),
                    "answer_session_recall": answer_recall,
                    "retrieved_chars": sum(record["retrieved_chars"] for record in retrieved),
                    "index_chars": index_chars,
                    "ranked_sessions": retrieved,
                }
            )
            state["events"].append(
                {
                    "question_id": item["question_id"],
                    "ingestion_latency_ms": ingest_ms,
                    "query_latency_ms": result["elapsed_ms"],
                    "prompt_tokens": result["prompt_tokens"],
                    "output_tokens": result["output_tokens"],
                    "ollama_total_ns": result["ollama_total_ns"],
                }
            )
            match_display = "NA" if match is None else str(int(match))
            line = (
                f"{item_number:02d}/{len(items)} {item['question_type']:<27} "
                f"{condition:<18} match={match_display} retrieval={answer_recall:.2f} "
                f"latency={result['elapsed_ms']:.0f}ms"
            )
            state["stdout"].append(line)
            if (
                not args.retrieval_only
                or item_number == 1
                or item_number % 25 == 0
                or item_number == len(items)
            ):
                print(line, flush=True)

    completed_at = utc_now()
    summary = {
        "status": "non-release-pilot",
        "comparison_id": comparison_id,
        "dataset_sha256": dataset_sha256,
        "model": "none-retrieval-only" if args.retrieval_only else args.model,
        "selected_question_ids": [item["question_id"] for item in items],
        "pointer_term_grid": pointer_counts,
        "conditions": {},
        "limitations": [
            *([] if args.all_items else ["deterministic stratified subset rather than all questions"]),
            *(
                ["retrieval-only: no reader model and no QA accuracy"]
                if args.retrieval_only else
                ["normalized answer-containment proxy rather than official judge scoring",
                 "one local reader model and one seed"]
            ),
            "pointer keyword prototype only; no consolidation or reconsolidation",
            "retrieval token counts estimated from character counts",
        ],
    }

    for condition, state in condition_state.items():
        condition_dir = args.output / condition
        condition_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(condition_dir / "predictions.jsonl", state["predictions"])
        write_jsonl(condition_dir / "retrieval.jsonl", state["retrieval"])
        write_jsonl(condition_dir / "events.jsonl", state["events"])
        (condition_dir / "stdout.log").write_text(
            "NON-RELEASE PILOT\n" + "\n".join(state["stdout"]) + "\n",
            encoding="utf-8",
        )
        (condition_dir / "stderr.log").write_text("No errors captured.\n", encoding="utf-8")
        reader_prompt = (
            "No reader prompt used: retrieval-only pilot.\n"
            if args.retrieval_only else PROMPT_TEMPLATE + "\n"
        )
        (condition_dir / "prompt.txt").write_text(reader_prompt, encoding="utf-8")
        manifest = build_manifest(
            args=args,
            condition=condition,
            condition_dir=condition_dir,
            comparison_id=comparison_id,
            dataset_sha256=dataset_sha256,
            repository_commit=repository_commit,
            repository_dirty=repository_dirty,
            started_at=started_at,
            completed_at=completed_at,
            records=state["predictions"],
            retrieval_records=state["retrieval"],
            event_records=state["events"],
            expected_cases=expected_cases,
            reader_prompt=reader_prompt,
        )
        (condition_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        summary["conditions"][condition] = manifest["metrics"]

    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote pilot artifacts to {args.output}")
    print("These results are not release-grade and must not support a README claim.")


if __name__ == "__main__":
    main()
