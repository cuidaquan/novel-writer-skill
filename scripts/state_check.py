#!/usr/bin/env python3
"""Validate the structural invariants of a novel state.json file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FORESHADOWING_STATUS = {"planted", "active", "resolved", "dropped"}
PLOT_STATUS = {"open", "paused", "resolved"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate novel continuity state")
    parser.add_argument("state", type=Path, help="Path to state.json")
    return parser.parse_args()


def require_type(obj: dict, key: str, expected: type, errors: list[str]) -> None:
    if key not in obj:
        errors.append(f"missing top-level key: {key}")
    elif not isinstance(obj[key], expected):
        errors.append(f"{key} must be {expected.__name__}")


def main() -> int:
    args = parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    errors: list[str] = []

    if state.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    require_type(state, "project", dict, errors)
    require_type(state, "characters", dict, errors)
    require_type(state, "relationships", dict, errors)
    require_type(state, "plot_threads", dict, errors)
    require_type(state, "foreshadowing", dict, errors)
    require_type(state, "timeline", list, errors)
    require_type(state, "continuity_notes", list, errors)

    current_chapter = state.get("project", {}).get("current_chapter")
    if not isinstance(current_chapter, int) or current_chapter < 0:
        errors.append("project.current_chapter must be a non-negative integer")

    for thread_id, thread in state.get("plot_threads", {}).items():
        if not isinstance(thread, dict):
            errors.append(f"plot_threads.{thread_id} must be an object")
            continue
        status = thread.get("status", "open")
        if status not in PLOT_STATUS:
            errors.append(f"plot_threads.{thread_id}.status invalid: {status}")

    for item_id, item in state.get("foreshadowing", {}).items():
        if not isinstance(item, dict):
            errors.append(f"foreshadowing.{item_id} must be an object")
            continue
        status = item.get("status", "planted")
        if status not in FORESHADOWING_STATUS:
            errors.append(f"foreshadowing.{item_id}.status invalid: {status}")
        if status == "resolved" and "resolved_chapter" not in item:
            errors.append(f"foreshadowing.{item_id} resolved without resolved_chapter")

    seen_event_ids: set[str] = set()
    for index, event in enumerate(state.get("timeline", [])):
        if not isinstance(event, dict):
            errors.append(f"timeline[{index}] must be an object")
            continue
        event_id = event.get("id")
        if event_id:
            if event_id in seen_event_ids:
                errors.append(f"duplicate timeline id: {event_id}")
            seen_event_ids.add(event_id)
        chapter = event.get("chapter")
        if isinstance(current_chapter, int) and isinstance(chapter, int) and chapter > current_chapter:
            errors.append(f"timeline[{index}].chapter is ahead of current_chapter")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("OK: state is structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
