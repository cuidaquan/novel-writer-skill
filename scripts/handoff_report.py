#!/usr/bin/env python3
"""Report the current cross-chapter handoff and stale commitments.

Read-only and advisory. It shows the explicit carry-over recorded by the latest
transaction, the active pressure derived from replayed state, and which
commitments have not moved for several chapters. Paused threads are listed with
their recorded reason instead of being flagged.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from state_model import last_touched_chapters, read_json, validate_state
from state_rebuild import transaction_paths


DEFAULT_STALE = 5
OPEN_THREAD_STATUS = {"open", "paused"}
ACTIVE_CLUE_STATUS = {"planted", "active"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Show the explicit next-chapter carry-over, the active pressure derived from "
            "state, and traceable hints for commitments that have not moved for several "
            "chapters. Read-only and advisory; it never changes state."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument(
        "--stale",
        type=int,
        default=DEFAULT_STALE,
        help="Chapters without movement before a commitment is flagged (default: 5)",
    )
    return parser.parse_args()


def describe(state: dict, item: str) -> tuple[str, str] | None:
    sections = (
        ("plot_threads", "plot thread", "open"),
        ("foreshadowing", "foreshadowing", "planted"),
        ("relationships", "relationship", "open"),
    )
    for section, label, default in sections:
        values = state.get(section)
        if isinstance(values, dict) and item in values and isinstance(values[item], dict):
            return label, values[item].get("status", default)
    return None


def active_items(state: dict, touched: dict[str, int]) -> list[dict]:
    items: list[dict] = []
    threads = state.get("plot_threads") if isinstance(state.get("plot_threads"), dict) else {}
    clues = state.get("foreshadowing") if isinstance(state.get("foreshadowing"), dict) else {}
    relationships = state.get("relationships") if isinstance(state.get("relationships"), dict) else {}
    for key, thread in threads.items():
        if isinstance(thread, dict) and thread.get("status", "open") in OPEN_THREAD_STATUS:
            items.append({"kind": "plot thread", "id": key, "status": thread.get("status", "open"), "last": touched.get(key, 0), "note": thread.get("note", "")})
    for key, clue in clues.items():
        if isinstance(clue, dict) and clue.get("status", "planted") in ACTIVE_CLUE_STATUS:
            items.append({"kind": "foreshadowing", "id": key, "status": clue.get("status", "planted"), "last": touched.get(key, 0), "note": clue.get("note", "")})
    for key, relationship in relationships.items():
        if isinstance(relationship, dict) and relationship.get("status", "open") != "resolved":
            items.append({"kind": "relationship", "id": key, "status": relationship.get("status", "open"), "last": touched.get(key, 0), "note": relationship.get("note", "")})
    items.sort(key=lambda item: (item["last"], item["kind"], item["id"]))
    return items


def source_label(chapter: int) -> str:
    return f"chapter {chapter}" if chapter >= 1 else "chapter 0 (initial)"


def main() -> int:
    args = parse_args()
    if args.stale < 1:
        print("ERROR: --stale must be a positive integer")
        return 2
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    try:
        state = read_json(project / "state" / "state.json")
    except ValueError as exc:
        print(f"ERROR: {exc}")
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
    touched = last_touched_chapters(transactions)
    handoff = state.get("handoff") if isinstance(state.get("handoff"), dict) else {}
    carry_over = handoff.get("carry_over") if isinstance(handoff.get("carry_over"), list) else []
    notes = handoff.get("notes") if isinstance(handoff.get("notes"), list) else []

    print(f"# Handoff Report: {state['project'].get('title', '')}".rstrip())
    print()
    print(f"- Current chapter: {current}")
    print(f"- Next chapter: {current + 1}")
    print()
    print("## Explicit carry-over")
    if carry_over:
        for item in carry_over:
            described = describe(state, item)
            last = touched.get(item, 0)
            if described is None:
                print(f"- {item}: recorded carry-over no longer resolves in state (source {source_label(last)})")
            else:
                kind, status = described
                print(f"- {item} ({kind}, status {status}, last touched {source_label(last)})")
    else:
        print("(none)")
    if notes:
        print("- notes: " + "; ".join(notes))
    print()

    items = active_items(state, touched)
    print(f"## Active pressure ({len(items)})")
    if items:
        for item in items:
            print(f"- {item['id']} ({item['kind']}, status {item['status']}, last touched {source_label(item['last'])})")
    else:
        print("(none)")
    print()

    paused = [item for item in items if item["status"] == "paused"]
    stale = [item for item in items if item["status"] != "paused" and current - item["last"] >= args.stale]
    print(f"## Stale hints ({len(stale)}, threshold {args.stale})")
    if stale:
        for item in stale:
            age = current - item["last"]
            print(f"NOTE [{item['kind']}-stale] {item['id']} last moved at {source_label(item['last'])}, {age} chapters before {current}; keep it moving or record a pause")
    else:
        print("(none)")
    print()

    print(f"## Paused ({len(paused)}, not flagged)")
    if paused:
        for item in paused:
            reason = f": {item['note']}" if item["note"] else ""
            print(f"- {item['id']} ({item['kind']}, status paused, last touched {source_label(item['last'])}){reason}")
    else:
        print("(none)")
    print()
    print("This report is advisory; it does not prove plot causality and never changes state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
