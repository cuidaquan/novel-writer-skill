#!/usr/bin/env python3
"""Advisory cross-chapter duplicate scan for a novel project.

Copy-paste accidents survive a per-chapter read: a duplicated paragraph looks
fine in isolation and only shows up when the whole book is compared with
itself. This report is always advisory — repeated lines can be deliberate
motifs or a frame — so it never changes the exit code. Exit code 2 is reserved
for usage or input errors.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from planning import numbered_path

CJK = re.compile(r"[\u4e00-\u9fff]")
SENTENCE_SPLIT = re.compile(r"[。！？…；]+")
# Decoration removed before comparison so quoted and unquoted variants match.
NOISE = "“”‘’\"'「」『』（）()《》〈〉—…·、，。；：？！,.;:?! 　\t"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare every committed chapter with itself and report duplicated paragraphs, "
            "duplicated sentences, near-duplicate sentences and repeated short phrases. "
            "Advisory only: a repeated frame or motif is a craft choice, not a defect."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--min-chars", type=int, default=10, help="Shortest unit to compare (default: 10)")
    parser.add_argument("--window", type=int, default=8, help="Phrase window in characters (default: 8)")
    parser.add_argument("--min-count", type=int, default=3, help="Report phrases seen at least this often (default: 3)")
    parser.add_argument("--similarity", type=float, default=0.88, help="Near-duplicate threshold (default: 0.88)")
    parser.add_argument("--limit", type=int, default=20, help="Maximum rows per section (default: 20)")
    return parser.parse_args()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(char for char in text if char not in NOISE)


def load_units(project: Path, minimum: int) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
    """Return (paragraphs, sentences) as (chapter, line, text) with their normalized form."""
    paragraphs: list[tuple[int, int, str]] = []
    sentences: list[tuple[int, int, str]] = []
    number = 1
    while (path := numbered_path(project / "chapters", "chapter", number, ("md", "txt"))) is not None:
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line == "—" or line.startswith("#"):
                continue
            paragraphs.append((number, line_number, line))
            for sentence in SENTENCE_SPLIT.split(line):
                sentence = sentence.strip()
                if len(normalize(sentence)) >= minimum:
                    sentences.append((number, line_number, sentence))
        number += 1
    return paragraphs, sentences


def duplicates(units: list[tuple[int, int, str]], minimum: int) -> dict[str, list[tuple[int, int, str]]]:
    buckets: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for chapter, line, text in units:
        key = normalize(text)
        if len(key) >= minimum:
            buckets[key].append((chapter, line, text))
    return {key: value for key, value in buckets.items() if len(value) > 1}


def near_duplicates(
    sentences: list[tuple[int, int, str]], excluded: set[str], threshold: float
) -> list[tuple[float, tuple[int, int, str], tuple[int, int, str]]]:
    pool = [
        (chapter, line, text, normalize(text))
        for chapter, line, text in sentences
        if normalize(text) not in excluded
    ]
    by_length: dict[int, list[tuple[int, int, str, str]]] = defaultdict(list)
    for item in pool:
        by_length[len(item[3])].append(item)
    found = []
    lengths = sorted(by_length)
    for index, length in enumerate(lengths):
        for other in lengths[index:]:
            if other > length * 1.25:
                break
            for left in by_length[length]:
                for right in by_length[other]:
                    if left[:2] >= right[:2] or left[3] == right[3]:
                        continue
                    ratio = SequenceMatcher(None, left[3], right[3]).ratio()
                    if ratio >= threshold:
                        found.append((ratio, left, right))
    return sorted(found, key=lambda item: -item[0])


def repeated_phrases(
    paragraphs: list[tuple[int, int, str]], window: int, minimum: int
) -> dict[str, list[tuple[int, int]]]:
    hits: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for chapter, line, text in paragraphs:
        compact = normalize(text)
        for start in range(max(0, len(compact) - window + 1)):
            hits[compact[start : start + window]].append((chapter, line))
    return {phrase: sorted(set(places)) for phrase, places in hits.items() if len(set(places)) >= minimum}


def render(
    project: Path,
    paragraphs: list[tuple[int, int, str]],
    sentences: list[tuple[int, int, str]],
    args: argparse.Namespace,
) -> str:
    lines = [
        "# Duplicate Scan",
        "",
        f"- Project: {project}",
        f"- Compared: {len(paragraphs)} paragraphs, {len(sentences)} sentences",
        f"- Paragraph/sentence minimum: {args.min_chars} characters (punctuation and quotes ignored)",
        f"- Phrase window: {args.window} characters, reported at {args.min_count}+ occurrences",
        f"- Near-duplicate threshold: {args.similarity}",
        "",
        "A repeated frame or motif is a craft choice; this report never blocks a commit.",
    ]

    paragraph_hits = duplicates(paragraphs, args.min_chars)
    lines += ["", f"## Duplicated paragraphs ({len(paragraph_hits)})"]
    if paragraph_hits:
        for key, places in sorted(paragraph_hits.items(), key=lambda item: -len(item[0]))[: args.limit]:
            lines.append(f"- [{len(places)}x] {places[0][2][:60]}")
            lines.extend(f"    chapter {chapter}:{line}" for chapter, line, _ in places)
    else:
        lines.append("(none)")

    sentence_hits = duplicates(sentences, args.min_chars)
    lines += ["", f"## Duplicated sentences ({len(sentence_hits)})"]
    if sentence_hits:
        for key, places in sorted(sentence_hits.items(), key=lambda item: -len(item[0]))[: args.limit]:
            where = " ".join(f"chapter {chapter}:{line}" for chapter, line, _ in places)
            lines.append(f"- [{len(places)}x] {places[0][2][:56]}   {where}")
    else:
        lines.append("(none)")

    near = near_duplicates(sentences, set(sentence_hits), args.similarity)
    lines += ["", f"## Near-duplicate sentences ({len(near)})"]
    if near:
        for ratio, left, right in near[: args.limit]:
            lines.append(f"- {ratio:.2f} chapter {left[0]}:{left[1]} {left[2][:40]}")
            lines.append(f"        chapter {right[0]}:{right[1]} {right[2][:40]}")
        lines.append("- Check each pair: a frame or callback is intentional, a paraphrase of the same beat is not.")
    else:
        lines.append("(none)")

    phrases = repeated_phrases(paragraphs, args.window, args.min_count)
    lines += ["", f"## Repeated {args.window}-character phrases ({len(phrases)})"]
    if phrases:
        for phrase, places in sorted(phrases.items(), key=lambda item: -len(item[1]))[: args.limit]:
            where = " ".join(f"chapter {chapter}:{line}" for chapter, line in places)
            lines.append(f"- [{len(places)}x] {phrase}   {where}")
        lines.append("- Motifs and object names repeat on purpose; look for narration formulas instead.")
    else:
        lines.append("(none)")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    for name, value, minimum in (("--min-chars", args.min_chars, 2), ("--window", args.window, 2), ("--min-count", args.min_count, 2), ("--limit", args.limit, 1)):
        if value < minimum:
            print(f"ERROR: {name} must be at least {minimum}")
            return 2
    if not 0.5 <= args.similarity <= 1.0:
        print("ERROR: --similarity must be between 0.5 and 1.0")
        return 2
    chapters = sorted((project / "chapters").glob("chapter-*"))
    if not chapters:
        print(f"ERROR: no chapter files found under {project / 'chapters'}")
        return 2
    paragraphs, sentences = load_units(project, args.min_chars)
    if not paragraphs:
        print("ERROR: chapter files contain no drafted prose")
        return 2
    print(render(project, paragraphs, sentences, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
