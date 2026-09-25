#!/usr/bin/env python3
"""Read-only review of one drafted chapter before its state transaction.

Exits 1 when a BLOCK finding is reported, 0 when only advisory NOTE findings
remain, and 2 for usage or input errors. Nothing on disk is modified.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import review


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Review one drafted chapter without changing the body, state or transactions. "
            "BLOCK findings are reproducible structural problems that must be cleared before "
            "commit; NOTE findings are evidence for author judgement and never block commit."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--chapter", type=int, help="Chapter number; defaults to current_chapter + 1")
    parser.add_argument("--style", action="store_true", help="Append the advisory style-drift report")
    parser.add_argument(
        "--baseline",
        type=int,
        default=3,
        help="Number of recent finalized chapters pooled as the style baseline (default: 3)",
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

    findings = review.chapter_findings(chapter)
    print(review.render_report(chapter, findings))

    if args.style:
        baseline = review.baseline_chapters(project, chapter.state, chapter.number, args.baseline)
        style_findings = review.style_findings(chapter, baseline)
        print()
        print(review.render_style_report(chapter, baseline, style_findings))

    return 1 if any(finding.level == "BLOCK" for finding in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
