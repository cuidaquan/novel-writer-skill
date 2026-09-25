"""Reusable prose metrics for deterministic review and style-drift hints.

Every number here is defined only on observable text, so a report can be
recomputed from the same sample. These metrics never decide literary quality;
they only point a reviewer at a chapter, paragraph or line worth re-reading.
"""

from __future__ import annotations

import re


WORD_PATTERN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z]+(?:['-][A-Za-z]+)*|\d+")
SENTENCE_SPLIT = re.compile(r"[。！？!?…]+")
DIALOGUE_MARK = re.compile(r"[“”「」『』\"]")
WHITESPACE = re.compile(r"\s+")
OPENING_PREFIX = re.compile(r"^[#>\-*\s\d.、]+")
TRAILING_TERMINAL = re.compile(r"[\s。！？!?…”’」』\"'）)】\]]+$")

OPENING_LENGTH = 4
ENDING_LENGTH = 4
MIN_SIGNATURE_LENGTH = 2
REPEAT_MINIMUM = 3

# A baseline is only reported when it pools enough text to be meaningful.
MIN_BASELINE_PARAGRAPHS = 8
MIN_BASELINE_CHARACTERS = 300

# Advisory drift thresholds. Crossing one produces a hint, never a block.
SENTENCE_DRIFT = 0.30
PARAGRAPH_DRIFT = 0.40
DIALOGUE_DRIFT = 0.25


def count_words(text: str) -> int:
    """Count Chinese characters, English words and numbers; punctuation is ignored."""
    return len(WORD_PATTERN.findall(text))


def compact_length(value: str) -> int:
    return len(WHITESPACE.sub("", value))


def paragraphs(text: str) -> list[tuple[int, str]]:
    """Return (1-based line number, stripped line) for every non-empty line."""
    result: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line:
            result.append((number, line))
    return result


def sentences(text: str) -> list[tuple[int, str]]:
    """Return (1-based line number, sentence) split on terminal punctuation."""
    result: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        for part in SENTENCE_SPLIT.split(raw):
            part = part.strip()
            if part:
                result.append((number, part))
    return result


def opening_signature(line: str) -> str:
    compact = WHITESPACE.sub("", OPENING_PREFIX.sub("", line))
    return compact[:OPENING_LENGTH]


def ending_signature(line: str) -> str:
    compact = WHITESPACE.sub("", OPENING_PREFIX.sub("", line))
    compact = TRAILING_TERMINAL.sub("", compact)
    return compact[-ENDING_LENGTH:]


def repeated_signatures(items: list[tuple[int, str]], minimum: int = REPEAT_MINIMUM) -> list[tuple[str, list[int]]]:
    """Group signatures and keep those seen at least the given number of times."""
    grouped: dict[str, list[int]] = {}
    for number, signature in items:
        if len(signature) < MIN_SIGNATURE_LENGTH:
            continue
        grouped.setdefault(signature, []).append(number)
    repeats = [(signature, numbers) for signature, numbers in grouped.items() if len(numbers) >= minimum]
    return sorted(repeats, key=lambda item: (-len(item[1]), item[0]))


SENTENCE_BANDS = ((12, "short"), (22, "short-to-medium"), (32, "medium"), (float("inf"), "long"))
PARAGRAPH_BANDS = ((40, "short"), (80, "medium"), (float("inf"), "long"))
DIALOGUE_BANDS = ((0.15, "low"), (0.35, "medium"), (float("inf"), "high"))


CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
LATIN_WORD = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
PUNCTUATION_MARKS = ("，", "。", "、", "；", "：", "？", "！", "…", "—", "“", "”")
TOP_TERM_LIMIT = 10
TOP_TERM_MINIMUM = 2


def top_bigrams(text: str, limit: int = TOP_TERM_LIMIT, minimum: int = TOP_TERM_MINIMUM) -> list[tuple[str, int]]:
    """Frequent adjacent CJK character pairs, a segmentation-free word proxy."""
    counts: dict[str, int] = {}
    for run in CJK_RUN.findall(text):
        for index in range(len(run) - 1):
            bigram = run[index:index + 2]
            counts[bigram] = counts.get(bigram, 0) + 1
    ranked = sorted(((count, bigram) for bigram, count in counts.items() if count >= minimum), key=lambda item: (-item[0], item[1]))
    return [(bigram, count) for count, bigram in ranked[:limit]]


def top_latin_words(text: str, limit: int = TOP_TERM_LIMIT, minimum: int = TOP_TERM_MINIMUM) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for word in LATIN_WORD.findall(text):
        key = word.lower()
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(((count, word) for word, count in counts.items() if count >= minimum), key=lambda item: (-item[0], item[1]))
    return [(word, count) for count, word in ranked[:limit]]


def punctuation_profile(text: str, limit: int = TOP_TERM_LIMIT) -> list[tuple[str, int, float]]:
    """Punctuation counts with a per-100-character rate."""
    compact = WHITESPACE.sub("", text)
    length = len(compact) or 1
    counts = {mark: compact.count(mark) for mark in PUNCTUATION_MARKS if compact.count(mark)}
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [(mark, count, round(count * 100 / length, 2)) for mark, count in ranked[:limit]]


def lexical_diversity(text: str) -> float:
    """CJK character type-token ratio: unique characters over all CJK characters."""
    runs = CJK_RUN.findall(text)
    total = sum(len(run) for run in runs)
    if not total:
        return 0.0
    return round(len({char for run in runs for char in run}) / total, 4)


def mean(values: list[int]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def band(value: float, bands: tuple) -> str:
    for limit, label in bands:
        if value < limit:
            return label
    return bands[-1][1]


def pooled_metrics(texts: list[str]) -> dict:
    return metrics("\n\n".join(texts))


def style_proposals(value: dict) -> dict:
    """Map observed metrics to novel.yaml style bands. Judgement fields are excluded."""
    return {
        "sentence_length": band(value["avg_sentence_chars"], SENTENCE_BANDS),
        "dialogue_density": band(value["dialogue_line_ratio"], DIALOGUE_BANDS),
    }


def metrics(text: str) -> dict:
    """Observable metrics for one sample (a chapter or a pooled baseline)."""
    lines = paragraphs(text)
    sentence_items = sentences(text)
    paragraph_lengths = [compact_length(line) for _, line in lines]
    sentence_lengths = [compact_length(sentence) for _, sentence in sentence_items]
    dialogue_lines = [number for number, line in lines if DIALOGUE_MARK.search(line)]
    return {
        "characters": len(text),
        "words": count_words(text),
        "paragraphs": len(lines),
        "sentences": len(sentence_items),
        "avg_paragraph_chars": mean(paragraph_lengths),
        "avg_sentence_chars": mean(sentence_lengths),
        "dialogue_line_ratio": round(len(dialogue_lines) / len(lines), 3) if lines else 0.0,
        "repeated_openings": repeated_signatures([(number, opening_signature(line)) for number, line in lines]),
        "repeated_endings": repeated_signatures([(number, ending_signature(line)) for number, line in lines]),
        "top_bigrams": top_bigrams(text),
        "top_latin_words": top_latin_words(text),
        "punctuation_profile": punctuation_profile(text),
        "cjk_type_token_ratio": lexical_diversity(text),
    }
