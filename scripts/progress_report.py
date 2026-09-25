#!/usr/bin/env python3
"""Read-only progress and budget dashboard for a novel project.

Shows planned versus written chapters and words, the remaining work, the words
projected at the current pace, and the currently unsettled continuity items.
It never changes state and never creates a new source of truth.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from planning import numbered_path, payoff_groups
from prose_metrics import count_words
from project_yaml import ProjectYAMLError, read_yaml
from state_model import integer, read_json, validate_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Show planned versus written chapters and words, remaining length, the projection "
            "at the current pace, and unsettled threads, clues, revelations and promises. "
            "Read-only; it does not modify state or add a truth file."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    return parser.parse_args()


def chapter_target_words(project: Path, number: int) -> int | None:
    card = numbered_path(project / "control-cards", "chapter", number, ("yaml", "yml"))
    if card is None:
        return None
    try:
        data = read_yaml(card)
    except (OSError, ProjectYAMLError):
        return None
    if isinstance(data, dict) and integer(data.get("target_words"), 1):
        return data["target_words"]
    return None


def main() -> int:
    args = parse_args()
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
    state_errors = validate_state(state)
    if state_errors:
        print("ERROR: invalid state: " + "; ".join(state_errors))
        return 2

    current = state["project"]["current_chapter"]
    length = novel.get("length") if isinstance(novel.get("length"), dict) else {}
    target_chapters = length.get("target_chapters") if integer(length.get("target_chapters"), 1) else None
    target_words = length.get("target_words") if integer(length.get("target_words"), 1) else None

    rows: list[tuple[int, int, int | None]] = []
    total_words = 0
    for number in range(1, current + 1):
        body = numbered_path(project / "chapters", "chapter", number, ("md", "txt"))
        words = count_words(body.read_text(encoding="utf-8")) if body is not None else 0
        total_words += words
        rows.append((number, words, chapter_target_words(project, number)))
    average = round(total_words / current, 1) if current else 0.0

    print(f"# Progress Report: {state['project'].get('title', '')}".rstrip())
    print()
    print(f"- Committed chapters: {current}" + (f" / {target_chapters}" if target_chapters else " (no target_chapters)"))
    if target_words:
        print(f"- Written words: {total_words} / {target_words} ({total_words * 100 / target_words:.1f}%)")
    else:
        print(f"- Written words: {total_words} (no target_words)")
    print(f"- Average per committed chapter: {average}")
    if target_chapters:
        remaining = max(0, target_chapters - current)
        projected = round(average * target_chapters)
        verdict = "meets the target" if target_words and projected >= target_words else "below the target"
        print(f"- Remaining chapters: {remaining}")
        if target_words:
            print(f"- Projected words at the current pace: {projected} ({verdict})")
        else:
            print(f"- Projected words at the current pace: {projected}")
    below = [(number, words, target) for number, words, target in rows if target and words < target * 0.8]
    print(f"- Committed chapters below 80% of their target: {len(below)}")
    print()

    print("## Per chapter (committed)")
    if rows:
        for number, words, target in rows:
            print(f"- chapter {number}: {words} words" + (f" / target {target}" if target else " (no target_words)"))
    else:
        print("(none)")
    print()

    threads = state.get("plot_threads") if isinstance(state.get("plot_threads"), dict) else {}
    open_threads = sorted(key for key, value in threads.items() if isinstance(value, dict) and value.get("status", "open") in {"open", "paused"})
    clues = state.get("foreshadowing") if isinstance(state.get("foreshadowing"), dict) else {}
    open_clues = sorted(key for key, value in clues.items() if isinstance(value, dict) and value.get("status", "planted") in {"planted", "active"})
    secrets = state.get("revelations") if isinstance(state.get("revelations"), dict) else {}
    unrevealed = sorted(key for key, value in secrets.items() if isinstance(value, dict) and value.get("reader_known") is not True)
    deferred = [key for key, entries in payoff_groups(project, current) if entries[-1][1].get("status") == "deferred"]

    print("## Unsettled items")
    print(f"- Open or paused plot threads: {len(open_threads)}" + (f" ({', '.join(open_threads)})" if open_threads else ""))
    print(f"- Unresolved foreshadowing: {len(open_clues)}" + (f" ({', '.join(open_clues)})" if open_clues else ""))
    print(f"- Reader-unknown revelations: {len(unrevealed)}" + (f" ({', '.join(unrevealed)})" if unrevealed else ""))
    print(f"- Deferred promises: {len(deferred)}" + (f" ({', '.join(deferred)})" if deferred else ""))
    print()
    print("This report is derived from state, cards and bodies; it never changes them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
