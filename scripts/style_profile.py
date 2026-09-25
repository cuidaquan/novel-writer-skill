#!/usr/bin/env python3
"""Build a reviewable style profile from finalized chapters or supplied samples.

The profile only reports observable metrics and proposes novel.yaml style bands.
It never stores original sentences and never treats a band as a rule until the
author confirms it. Judgement fields are explicitly left to the author.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import prose_metrics
from planning import numbered_path
from project_yaml import ProjectYAMLError, read_yaml
from state_model import read_json, validate_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract an observable style profile from recent finalized chapters or from "
            "--sample files, and propose novel.yaml style bands. The report is advisory: it "
            "does not store source sentences and leaves judgement fields to the author."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument(
        "--sample",
        action="append",
        default=[],
        metavar="PATH",
        help="Sample chapter file to read instead of finalized chapters; repeat as needed",
    )
    parser.add_argument(
        "--recent",
        type=int,
        default=5,
        help="Finalized chapters to pool when no --sample is given (default: 5)",
    )
    return parser.parse_args()


def display(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path)


def collect_samples(project: Path, state: dict, requested: list[str], recent: int) -> tuple[list[Path], list[str]]:
    if requested:
        sources: list[Path] = []
        for name in requested:
            path = Path(name).expanduser().resolve()
            if not path.is_file():
                raise SystemExit(f"sample file not found: {path}")
            sources.append(path)
        return sources, [display(project, path) for path in sources]
    current = state["project"]["current_chapter"]
    sources = []
    for number in range(max(1, current - recent + 1), current + 1):
        path = numbered_path(project / "chapters", "chapter", number, ("md", "txt"))
        if path is not None:
            sources.append(path)
    return sources, [display(project, path) for path in sources]


def repeat_line(label: str, repeats: list[tuple[str, list[int]]]) -> str:
    if not repeats:
        return f"- {label}: none"
    parts = [f"'{signature}' (lines {', '.join(map(str, numbers))})" for signature, numbers in repeats]
    return f"- {label}: " + "; ".join(parts)


def main() -> int:
    args = parse_args()
    if args.recent < 1:
        print("ERROR: --recent must be a positive integer")
        return 2
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    try:
        novel = read_yaml(project / "novel.yaml")
        state = read_json(project / "state" / "state.json")
    except (OSError, ValueError, ProjectYAMLError) as exc:
        print(f"ERROR: {exc}")
        return 2
    if not isinstance(novel, dict):
        print("ERROR: novel.yaml must be a mapping")
        return 2
    errors = validate_state(state)
    if errors:
        print("ERROR: invalid state: " + "; ".join(errors))
        return 2

    try:
        sources, labels = collect_samples(project, state, args.sample, args.recent)
    except SystemExit as exc:
        print(f"ERROR: {exc}")
        return 2
    texts: list[str] = []
    for path in sources:
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"ERROR: cannot read sample {path}: {exc}")
            return 2
    pooled = prose_metrics.pooled_metrics(texts)

    print("# Style Profile")
    print()
    print(f"- Sample sources: {len(sources)} file(s)")
    for label in labels:
        print(f"  - {label}")
    print(f"- Sample size: {pooled['paragraphs']} paragraphs, {pooled['characters']} characters")
    print()
    if not sources or pooled["paragraphs"] < prose_metrics.MIN_BASELINE_PARAGRAPHS or pooled["characters"] < prose_metrics.MIN_BASELINE_CHARACTERS:
        print("## Result")
        print(
            f"INSUFFICIENT: need at least {prose_metrics.MIN_BASELINE_PARAGRAPHS} paragraphs and "
            f"{prose_metrics.MIN_BASELINE_CHARACTERS} characters; no style bands proposed."
        )
        return 1

    proposals = prose_metrics.style_proposals(pooled)
    print("## Observed")
    print(f"- sentences: {pooled['sentences']}")
    print(f"- avg_sentence_chars: {pooled['avg_sentence_chars']}")
    print(f"- avg_paragraph_chars: {pooled['avg_paragraph_chars']}")
    print(f"- dialogue_line_ratio: {pooled['dialogue_line_ratio']}")
    print(repeat_line("repeated openings (>=3)", pooled["repeated_openings"]))
    print(repeat_line("repeated endings (>=3)", pooled["repeated_endings"]))
    print()
    print("## Proposed novel.yaml style (confirm before writing)")
    print("style:")
    print(f"  sentence_length: {proposals['sentence_length']}")
    print(f"  dialogue_density: {proposals['dialogue_density']}")
    print()
    print("## Basis")
    print(
        f"- sentence_length {proposals['sentence_length']}: avg_sentence_chars "
        f"{pooled['avg_sentence_chars']} in " + _band_range(pooled["avg_sentence_chars"], prose_metrics.SENTENCE_BANDS)
    )
    print(
        f"- dialogue_density {proposals['dialogue_density']}: dialogue_line_ratio "
        f"{pooled['dialogue_line_ratio']} in " + _band_range(pooled["dialogue_line_ratio"], prose_metrics.DIALOGUE_BANDS)
    )
    print()
    print("## Not inferred")
    print("- tone, pov_distance, interiority, metaphor_density, humor and violence need an author read; the profile leaves them unchanged.")
    print("- Only aggregate numbers are stored; no source sentence becomes an imitation template.")
    return 0


def _band_range(value: float, bands: tuple) -> str:
    lower = 0.0
    for limit, label in bands:
        if value < limit:
            upper = "inf" if limit == float("inf") else str(limit)
            return f"[{lower}, {upper})"
        lower = limit
    return "[0, inf)"


if __name__ == "__main__":
    raise SystemExit(main())
