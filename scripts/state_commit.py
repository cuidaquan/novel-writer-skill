#!/usr/bin/env python3
"""Apply a single chapter transaction to state.json atomically."""

from __future__ import annotations

import argparse
import copy
import json
import os
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Commit a novel chapter state transaction")
    parser.add_argument("state", type=Path, help="Path to state.json")
    parser.add_argument("transaction", type=Path, help="Path to transaction JSON")
    return parser.parse_args()


def merge_mapping(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            target[key].update(value)
        else:
            target[key] = copy.deepcopy(value)


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    args = parse_args()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    tx = json.loads(args.transaction.read_text(encoding="utf-8"))

    project = state.setdefault("project", {})
    current = project.get("current_chapter", 0)
    expected = tx.get("expected_chapter")
    chapter = tx.get("chapter")

    if expected != current:
        raise SystemExit(f"expected_chapter={expected} does not match current_chapter={current}")
    if chapter != current + 1:
        raise SystemExit(f"transaction chapter must be {current + 1}, got {chapter}")
    if not isinstance(tx.get("summary"), str) or not tx["summary"].strip():
        raise SystemExit("transaction summary must be a non-empty string")

    for key in ("characters", "relationships", "plot_threads", "foreshadowing"):
        state.setdefault(key, {})

    merge_mapping(state["characters"], tx.get("character_updates", {}))
    merge_mapping(state["relationships"], tx.get("relationship_updates", {}))
    merge_mapping(state["plot_threads"], tx.get("plot_thread_updates", {}))
    merge_mapping(state["foreshadowing"], tx.get("foreshadowing_updates", {}))

    timeline = state.setdefault("timeline", [])
    for event in tx.get("timeline_events", []):
        event_copy = copy.deepcopy(event)
        event_copy.setdefault("chapter", chapter)
        timeline.append(event_copy)

    notes = state.setdefault("continuity_notes", [])
    for note in tx.get("continuity_notes_add", []):
        if note not in notes:
            notes.append(note)

    project["current_chapter"] = chapter
    project["last_chapter_title"] = tx.get("chapter_title", "")
    project["last_chapter_summary"] = tx["summary"].strip()

    atomic_write_json(args.state, state)
    print(f"Committed chapter {chapter} to {args.state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
