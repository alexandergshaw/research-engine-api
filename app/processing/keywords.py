"""RAKE-style keyword extraction — deterministic, stdlib-only (no LLM, no models).

Splits text into candidate phrases at punctuation and stopwords, then scores each
phrase by the sum of its words' degree/frequency ratios (Rapid Automatic Keyword
Extraction). Good enough to surface "key terms" for slide outlines.
"""

from __future__ import annotations

import re
from collections import Counter

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could",
    "do", "does", "for", "from", "had", "has", "have", "if", "in", "into", "is", "it",
    "its", "may", "might", "no", "non", "not", "of", "on", "or", "other", "over",
    "such", "than", "that", "the", "their", "them", "then", "there", "these", "they",
    "this", "to", "use", "used", "uses", "using", "was", "were", "which", "while",
    "who", "whom", "will", "with", "within", "without", "would", "you", "your",
}

# Word chars keep intra-word -, +, # (so "public-key", "c++", "c#" survive); everything
# else (incl. "." and whitespace runs) is a clause/phrase boundary.
_CLAUSE = re.compile(r"[^A-Za-z0-9+#\- ]+")


def extract_keywords(text: str | None, limit: int = 8) -> list[str]:
    if not text:
        return []

    phrases = _phrases(text)
    if not phrases:
        return []

    freq: Counter[str] = Counter()
    degree: Counter[str] = Counter()
    for phrase in phrases:
        span = len(phrase) - 1
        for word in phrase:
            freq[word] += 1
            degree[word] += span
    for word in freq:
        degree[word] += freq[word]

    word_score = {word: degree[word] / freq[word] for word in freq}

    best: dict[str, float] = {}
    for phrase in phrases:
        text_phrase = " ".join(phrase)
        score = sum(word_score[word] for word in phrase)
        if score > best.get(text_phrase, -1.0):
            best[text_phrase] = score

    ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
    return [phrase for phrase, _ in ranked[:limit]]


def _phrases(text: str) -> list[list[str]]:
    phrases: list[list[str]] = []
    for clause in _CLAUSE.split(text):
        current: list[str] = []
        for raw in clause.split():
            word = raw.lower().strip("-")
            if not word or word in _STOPWORDS or len(word) <= 2:
                if current:
                    phrases.append(current)
                    current = []
                continue
            current.append(word)
        if current:
            phrases.append(current)
    return phrases
