#!/usr/bin/env python3
"""Aggregate the read-only stage reports into one review.

Runs the existing progress, handoff, promise and style-profile commands and
concatenates their sections with the source command named. It adds no state
logic and creates no truth file; advisory child exits never fail the review.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SECTIONS = (
    ("Progress", "progress_report.py"),
    ("Handoff", "handoff_report.py"),
    ("Promises", "promise_report.py"),
    ("Style profile", "style_profile.py"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the progress, handoff, promise and style-profile reports and print them as one "
            "stage review. Read-only; each section names the script that produced it."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--stale", type=int, default=5, help="Passed to handoff_report.py (default: 5)")
    parser.add_argument("--deferred-streak", type=int, default=3, help="Passed to promise_report.py (default: 3)")
    parser.add_argument("--recent", type=int, default=5, help="Passed to style_profile.py (default: 5)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    extras = {
        "handoff_report.py": ("--stale", str(args.stale)),
        "promise_report.py": ("--deferred-streak", str(args.deferred_streak)),
        "style_profile.py": ("--recent", str(args.recent)),
    }
    print("# Stage Review")
    print()
    print(f"- Project: {project}")
    print(f"- Sources: {', '.join(f'scripts/{script}' for _, script in SECTIONS)}")
    print()
    input_error = False
    for title, script in SECTIONS:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / script), str(project), *extras.get(script, ())],
            capture_output=True,
            text=True,
        )
        print(f"## {title} (scripts/{script})")
        print()
        print(result.stdout.rstrip() if result.stdout.strip() else "(no output)")
        if result.returncode == 2:
            input_error = True
            print(f"ERROR: {script} reported an input error: {result.stderr.strip() or result.stdout.strip()}")
        elif result.returncode != 0:
            print(f"(advisory exit code {result.returncode}; not a stage failure)")
        print()
    print("## Notes")
    print("- Each section comes from the named read-only script; this aggregator adds no state logic.")
    print("- Advisory exits, such as an insufficient style sample, do not fail the stage review.")
    return 2 if input_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
