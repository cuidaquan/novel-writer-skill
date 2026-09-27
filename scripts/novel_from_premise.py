#!/usr/bin/env python3
"""Regenerate novel.yaml from the project's premise without touching anything else.

A premise round can change the shape of the book (chapter count, genre, tone,
forbidden rules). The config has to follow, but `init_novel.py` is an
initializer: it re-scaffolds state and the outline, so using it on a live
project would throw away work. This script writes only novel.yaml, and it asks
before discarding config edits that did not come from the premise.

Exit codes: 0 written, 1 refused, 2 usage error.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from brief_check import check_against_novel, check_consistency, check_recorded, check_required
from init_novel import render_novel_yaml
from premise import field_value, is_unset, load_premise, premise_path
from project_yaml import ProjectYAMLError, read_yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rewrite novel.yaml from the project's premise.yaml (nothing else is touched)."
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite novel.yaml even when it carries edits that the premise does not explain")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    return parser.parse_args()


COMPARED = (
    ("title", ("title",)),
    ("audience", ("audience",)),
    ("genre.primary", ("genre", "primary")),
    ("length.target_chapters", ("length", "target_chapters")),
    ("length.target_words", ("length", "target_words")),
    ("narration.pov", ("narration", "pov")),
    ("style.tone", ("style", "tone")),
    ("style.ending_mode", ("style", "ending_mode")),
)


def changed_fields(before: dict, after_text: str) -> list[str]:
    """Report the top-level decisions this regeneration moves, for the author."""
    from tempfile import NamedTemporaryFile

    import os

    handle = NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    try:
        handle.write(after_text)
        handle.close()
        after = read_yaml(Path(handle.name))
    finally:
        os.unlink(handle.name)
    if not isinstance(after, dict):
        return []
    moved = []
    for label, path in COMPARED:
        old_value = field_value(before, ".".join(path))
        new_value = field_value(after, ".".join(path))
        if not is_unset(old_value) or not is_unset(new_value):
            if str(old_value) != str(new_value):
                moved.append(f"{label}: {old_value!r} → {new_value!r}")
    return moved


def main() -> int:
    args = parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2

    premise = load_premise(project)
    if premise is None:
        print(f"ERROR: {premise_path(project)} not found; the config is generated from the premise")
        return 2
    if not premise:
        print(f"ERROR: {premise_path(project)} is empty")
        return 2

    findings: list[tuple[str, str, str]] = []
    check_required(premise, findings)
    check_consistency(premise, findings)
    check_recorded(project, premise, findings)
    blocking = [f"{label}: {message}" for level, label, message in findings if level == "BLOCK"]
    # novel-drift is what this script exists to fix, so it is deliberately not a
    # precondition here; every other blocking finding still stops the rewrite.
    blocking = [item for item in blocking if not item.startswith("novel-drift")]
    if blocking:
        print("ERROR: the premise is not settled; fix these first (python3 scripts/brief_check.py .):")
        for item in blocking:
            print(f"  - {item}")
        return 1

    target = project / "novel.yaml"
    rendered = render_novel_yaml(premise)
    before: dict = {}
    if target.is_file():
        try:
            loaded = read_yaml(target)
            before = loaded if isinstance(loaded, dict) else {}
        except ProjectYAMLError as error:
            print(f"ERROR: existing novel.yaml does not parse: {error}")
            return 2
        if target.read_text(encoding="utf-8") == rendered:
            print("novel.yaml already matches the premise; nothing to do")
            return 0

    moved = changed_fields(before, rendered) if before else []
    if args.dry_run:
        print("# dry run: would rewrite novel.yaml")
        for item in moved:
            print(f"- {item}")
        return 0

    if before and not moved and target.is_file() and not args.force:
        # The premise agrees on every compared field, so the difference is an
        # author edit somewhere else in the file.
        print("ERROR: novel.yaml differs from the premise in fields the premise does not decide; "
              "pass --force to overwrite your edits")
        return 1

    target.write_text(rendered, encoding="utf-8")
    print("novel.yaml regenerated from premise.yaml")
    for item in moved:
        print(f"- {item}")
    if not moved:
        print("- (no decision-level change)")
    print("\nnext: python3 scripts/brief_check.py .")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
