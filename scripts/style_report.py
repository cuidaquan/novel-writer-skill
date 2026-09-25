#!/usr/bin/env python3
"""Advisory style metrics and drift hints for one drafted chapter.

The report is always advisory: drift never changes the exit code. Exit code 2
is reserved for usage or input errors.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import review


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare one chapter's observable prose metrics against the recent finalized "
            "chapters. The output is advisory and never blocks a commit; when the sample is "
            "too small the report says there is no baseline instead of inventing one."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--chapter", type=int, help="Chapter number; defaults to current_chapter + 1")
    parser.add_argument(
        "--baseline",
        type=int,
        default=3,
        help="Number of recent finalized chapters pooled as the baseline (default: 3)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    try:
        chapter = review.load_chapter(project, args.chapter)
    except review.ReviewInputError as exc:
        print(f"ERROR: {exc}")
        return 2

    baseline = review.baseline_chapters(project, chapter.state, chapter.number, args.baseline)
    findings = review.style_findings(chapter, baseline)
    cross = review.cross_chapter_findings(chapter, baseline)
    print(review.render_style_report(chapter, baseline, findings, cross))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
