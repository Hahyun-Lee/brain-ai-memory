"""Dependency-free multilingual tokenization and BM25 ranking."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable


TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?|[가-힣]+", re.IGNORECASE)
KOREAN_RE = re.compile(r"^[가-힣]+$")


def tokenize(text: str) -> list[str]:
    """Tokenize Latin text and add Korean character n-grams.

    Korean words are not reliably space-delimited, so retaining the full token
    while adding bigrams gives the local fallback useful recall without a model
    download. It is a lexical fallback, not an embedding substitute.
    """

    tokens: list[str] = []
    for raw in TOKEN_RE.findall(str(text).lower()):
        tokens.append(raw)
        if KOREAN_RE.fullmatch(raw) and len(raw) > 1:
            tokens.extend(f"ko:{raw[i:i + 2]}" for i in range(len(raw) - 1))
    return tokens


def bm25_scores(documents: Iterable[str], query: str, k1: float = 1.5, b: float = 0.75) -> list[float]:
    docs = [tokenize(document) for document in documents]
    query_tokens = tokenize(query)
    if not docs:
        return []
    avg_length = sum(map(len, docs)) / len(docs) or 1.0
    document_frequency: Counter[str] = Counter()
    for tokens in docs:
        document_frequency.update(set(tokens))

    scores: list[float] = []
    for tokens in docs:
        counts = Counter(tokens)
        length = len(tokens)
        score = 0.0
        for term in query_tokens:
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            df = document_frequency[term]
            inverse_frequency = math.log(1 + (len(docs) - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1 - b + b * length / avg_length)
            score += inverse_frequency * frequency * (k1 + 1) / denominator
        scores.append(score)
    return scores


def ranked(documents: list[dict], query: str, text_key: str = "text", limit: int = 5) -> list[dict]:
    scores = bm25_scores([str(item.get(text_key, "")) for item in documents], query)
    pairs = sorted(zip(documents, scores), key=lambda pair: (-pair[1], str(pair[0].get("id", ""))))
    output = []
    for item, score in pairs:
        if score <= 0:
            continue
        result = dict(item)
        result["score"] = round(score, 6)
        output.append(result)
        if len(output) >= limit:
            break
    return output
