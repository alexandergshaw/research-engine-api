"""Deterministic headline tone from a small bundled lexicon — no LLM, no models.

`headline_tone` returns a float: (positive hits − negative hits) over the words in
a headline. Positive numbers lean favorable; this is the ranking key for
``company.news`` and the value the caller filters on via ``min_tone``. It is an
explicit, caller-controlled signal — not an editorial judgement.
"""

from __future__ import annotations

import re

_POSITIVE = {
    "advance", "advances", "award", "awarded", "beats", "boost", "breakthrough",
    "expands", "gain", "gains", "grew", "growth", "innovative", "launch", "launches",
    "leading", "milestone", "partnership", "praised", "profit", "profits", "raises",
    "record", "rises", "rose", "soars", "strong", "success", "surge", "surges",
    "top", "upgrade", "upgraded", "wins", "win",
}
_NEGATIVE = {
    "bankruptcy", "breach", "crisis", "cuts", "decline", "declines", "downgrade",
    "drop", "drops", "fall", "falls", "fine", "fined", "fraud", "hack", "investigation",
    "lawsuit", "layoffs", "loss", "losses", "misses", "penalty", "plunge", "plunges",
    "probe", "recall", "scandal", "slump", "sues", "sued", "warns", "weak",
}

_WORD = re.compile(r"[a-z]+")


def headline_tone(text: str | None) -> float:
    if not text:
        return 0.0
    words = _WORD.findall(text.lower())
    pos = sum(1 for w in words if w in _POSITIVE)
    neg = sum(1 for w in words if w in _NEGATIVE)
    return float(pos - neg)
