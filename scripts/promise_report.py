#!/usr/bin/env python3
"""Track genre promises across chapters: expected payoffs and deferrals.

Read-only and advisory. It reads the optional card payoff record, the genre
declared in novel.yaml, and the replayed state to show whether mystery
information and romance relationships keep moving. It never imposes one rhythm
formula and never changes state.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from planning import numbered_path
from project_yaml import ProjectYAMLError, read_yaml
from state_model import last_touched_chapters, read_json, validate_state
from state_rebuild import transaction_paths


DEFAULT_DEFERRED = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List each chapter's declared genre payoff and flag consecutive deferrals. "
            "For mystery and romance it adds information-control and relationship-movement "
            "hints; other genres use the same generic deferral path. Read-only and advisory."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument(
        "--deferred-streak",
        type=int,
        default=DEFAULT_DEFERRED,
        help="Consecutive deferred chapters before a hint (default: 3)",
    )
    return parser.parse_args()


def genre_ids(novel: dict) -> tuple[str, list[str]]:
    genre = novel.get("genre") if isinstance(novel.get("genre"), dict) else {}
    primary = genre.get("primary") if isinstance(genre.get("primary"), str) else ""
    secondary = genre.get("secondary") if isinstance(genre.get("secondary"), list) else []
    return primary, [item for item in secondary if isinstance(item, str)]


def read_payoffs(project: Path, current: int) -> list[tuple[int, dict | None]]:
    entries: list[tuple[int, dict | None]] = []
    for number in range(1, current + 1):
        path = numbered_path(project / "control-cards", "chapter", number, ("yaml", "yml"))
        if path is None:
            entries.append((number, None))
            continue
        try:
            card = read_yaml(path)
        except (OSError, ProjectYAMLError):
            entries.append((number, None))
            continue
        payoff = card.get("payoff") if isinstance(card, dict) else None
        entries.append((number, payoff if isinstance(payoff, dict) else None))
    return entries


def first_touch(transactions: list[dict], key: str) -> int | None:
    for chapter, tx in enumerate(transactions, 1):
        updates = tx.get("revelation_updates")
        if isinstance(updates, dict) and key in updates:
            return chapter
    return None


def main() -> int:
    args = parse_args()
    if args.deferred_streak < 1:
        print("ERROR: --deferred-streak must be a positive integer")
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
        transactions = [read_json(path) for path in transaction_paths(project)]
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 2

    current = state["project"]["current_chapter"]
    primary, secondary = genre_ids(novel)
    payoffs = read_payoffs(project, current)
    touched = last_touched_chapters(transactions)
    genres = {primary, *secondary}

    print(f"# Promise Report: {state['project'].get('title', '')}".rstrip())
    print()
    print(f"- Genre: {primary or 'unset'}" + (f" (secondary: {', '.join(secondary)})" if secondary else ""))
    print(f"- Current chapter: {current}")
    print()
    print("## Chapter payoffs")
    if any(payoff for _, payoff in payoffs):
        for number, payoff in payoffs:
            if payoff is None:
                continue
            detail = f" - {payoff.get('expected', '')}"
            if payoff.get("status") == "deferred" and payoff.get("reason"):
                detail += f" (reason: {payoff.get('reason')})"
            print(f"- chapter {number}: {payoff.get('status', '')}{detail}")
    else:
        print("(no card declares payoff.expected)")
    print()

    streak = 0
    for _, payoff in payoffs:
        if payoff is not None and payoff.get("status") == "deferred":
            streak += 1
        else:
            streak = 0
    print("## Deferred streak")
    if streak >= args.deferred_streak:
        print(
            f"NOTE [promise-deferred] {streak} consecutive chapters defer the declared payoff, "
            f"ending at chapter {current}; plan a payoff or record why the pause continues."
        )
    else:
        print(f"Current deferred streak: {streak} (threshold {args.deferred_streak})")
    print()

    if "mystery" in genres:
        print("## Mystery path (information control)")
        unrevealed = sorted(
            key
            for key, item in (state.get("revelations") or {}).items()
            if isinstance(item, dict) and item.get("reader_known") is not True
        )
        if unrevealed:
            for key in unrevealed:
                first = first_touch(transactions, key)
                print(f"- revelation {key}: first touched chapter {first or 'never'}, still reader_known=false at chapter {current}")
        else:
            print("(no unrevealed revelation)")
        print()

    if "romance" in genres:
        print("## Romance path (relationship movement)")
        relationships = state.get("relationships") if isinstance(state.get("relationships"), dict) else {}
        active = sorted(
            key
            for key, value in relationships.items()
            if isinstance(value, dict) and value.get("status", "open") != "resolved"
        )
        if active:
            for key in active:
                last = touched.get(key, 0)
                print(f"- relationship {key}: last updated chapter {last or 'never'}")
        else:
            print("(no open relationship)")
        print()

    print("This report is advisory; it does not impose one rhythm formula and never changes state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
