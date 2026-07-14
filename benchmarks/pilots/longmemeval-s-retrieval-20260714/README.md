# LongMemEval-S retrieval pilot — 2026-07-14

**Status: non-release pilot. No reader LLM was called and no QA accuracy was
measured.**

This run tests one narrow question: can a compact, query-independent session
pointer retrieve the benchmark's answer sessions? It does not test the full
Brain-AI architecture.

## Result

All 500 questions in the cleaned
[LongMemEval-S](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned)
file were evaluated. The primary metric is answer-session recall@3: for each
question, the fraction of gold answer sessions found in the top three, averaged
over questions.

![Compression versus answer-session recall on LongMemEval-S](../../../docs/assets/benchmark-compression-recall.png)

| Retrieval condition | Answer-session recall@3 | Mean indexed source text | Reduction vs. full text |
|---|---:|---:|---:|
| most recent 3 sessions | 7.5% | no search index | — |
| full-session BM25 | **86.1%** | 493,948 chars | baseline |
| 12-keyword pointer BM25 | 51.8% | 5,202 chars | 98.9% |
| 24-keyword pointer BM25 | 55.9% | 9,351 chars | 98.1% |
| 48-keyword pointer BM25 | 66.2% | 17,691 chars | 96.4% |
| 96-keyword pointer BM25 | 71.0% | 34,368 chars | 93.0% |

The negative result matters: simple term-frequency pointers compress the text
given to BM25 sharply, but even the 96-keyword version loses 15.0 percentage
points of answer-session recall relative to full-text BM25. The current pilot
therefore does **not** support a claim that compact pointers preserve retrieval
quality. It establishes a concrete target for a better semantic pointer or
routing implementation.

## Method

- Each condition sees the same timestamped histories and question.
- Pointers are generated before the question is used: date plus the session's
  12, 24, 48, or 96 most frequent non-stopword terms.
- The gold `answer_session_ids` are used only after ranking to compute recall;
  they are never indexed or shown to a retriever.
- BM25 and pointer construction use the Python standard library implementation
  in [`../../run_longmemeval_pilot.py`](../../run_longmemeval_pilot.py).
- Top-k is 3. Retrieved detail is capped at an estimated 1,000 tokens, using
  four characters per token.
- “Indexed source text” is the character count of the text supplied to BM25,
  not the serialized size of a production search index.
- Dataset SHA-256:
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.

Exact command:

    python3 benchmarks/run_longmemeval_pilot.py \
      --data /path/to/longmemeval_s_cleaned.json \
      --output benchmarks/pilots/longmemeval-s-retrieval-20260714 \
      --retrieval-only --all-items --top-k 3 \
      --retrieval-budget-tokens 1000 --context-tokens 4096 \
      --pointer-terms 12,24,48,96

The PNG can be regenerated with Matplotlib (3.10.8 was used for this copy):

    python3 benchmarks/plot_retrieval_tradeoff.py \
      --summary benchmarks/pilots/longmemeval-s-retrieval-20260714/summary.json \
      --output docs/assets/benchmark-compression-recall.png

## Artifacts and limitations

The machine-readable aggregate is [`summary.json`](summary.json). Each
condition directory contains a manifest, all 500 retrieval records, event logs,
and their SHA-256 digests.

The retrieval records contain excerpts derived from the MIT-licensed
LongMemEval dataset. See [`DATASET_NOTICE.md`](DATASET_NOTICE.md) for attribution,
the license notice, and the benchmark citation.

- This is retrieval-only; it cannot establish answer quality, abstention,
  reasoning, consolidation, or reconsolidation.
- The pointer is a deterministic keyword prototype, not the intended final
  semantic memory representation.
- Query timing is diagnostic only. This script recomputes BM25 statistics at
  query time in pure Python, so it is not a deployment latency estimate.
- The run records `repository_dirty: false`; the implementation was committed
  before execution and its SHA-256 matches every condition manifest. The
  public-claim release validator still rejects it because no reader or official
  QA scorer was used.
- The six conditions share one run, one dataset digest, one item order, and one
  retrieval budget; no cross-paper score was imported.
