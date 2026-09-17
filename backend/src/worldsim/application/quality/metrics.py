"""Deterministic narration quality metrics (owned by S3-QUAL-001).

Every metric computes from committed rows only: no model calls, no
thresholds, no judges. Definitions are frozen here and in
backend/README.md:

- repetition: one minus distinct over total word bigrams across the
  phase's beats (n=2 fixed). Text is lowercased, punctuation
  stripped, whitespace split. Zero or one bigram total scores 0.
- diversity: distinct cited fact keys across the phase's beats over
  the phase's scene count. Beats without citations dilute it.
- fallback: fallback-narration scenes over scenes.
- quiet: quiet phases over phases (aggregate only).
- director: hooks plus arcs created in the phase over phases, and
  the no-op norm (phases without creations over phases).
"""

from __future__ import annotations

import re
import string

_WORD = re.compile(r"\S+")

#: Fixed n-gram width for the repetition metric.
NGRAM_N = 2


def _words(text: str) -> list[str]:
    lowered = text.lower().translate(str.maketrans("", "", string.punctuation))
    return [word for word in _WORD.findall(lowered) if word]


def bigrams(text: str) -> list[tuple[str, str]]:
    words = _words(text)
    return list(zip(words, words[1:], strict=False))


def repetition(beat_texts: list[str]) -> float:
    """Duplicate-bigram ratio over one phase's beats, 0 when too thin."""
    grams: list[tuple[str, str]] = []
    for text in beat_texts:
        grams.extend(bigrams(text))
    if len(grams) < 2:
        return 0.0
    return 1.0 - len(set(grams)) / len(grams)


def diversity(cited_keys: list[str], scene_count: int) -> float:
    """Distinct cited keys over scenes; citation-free phases score 0."""
    if scene_count <= 0 or not cited_keys:
        return 0.0
    return len(set(cited_keys)) / scene_count


def phase_metrics(
    beat_texts: list[str],
    cited_keys: list[str],
    scene_count: int,
    fallback_scenes: int,
    hooks_created: int,
    arcs_created: int,
) -> dict[str, float]:
    """All per-phase metrics with frozen denominators."""
    scenes = max(1, scene_count)
    return {
        "repetition": round(repetition(beat_texts), 4),
        "diversity": round(diversity(cited_keys, scene_count), 4),
        "fallback_rate": round(fallback_scenes / scenes, 4),
        "director_creations": hooks_created + arcs_created,
    }
