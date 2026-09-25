#!/usr/bin/env python3
"""Render a derived, human-readable view of the replayed novel state.

The view is explicitly derived: state/state.json plus the transaction journal
stay the only source of truth, and the file header says so. --check compares an
existing file with a fresh render so a stale derived document becomes visible.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from state_model import last_touched_chapters, read_json, validate_state
from state_rebuild import transaction_paths


HEADER = (
    "# State View (derived)\n\n"
    "> Derived from state/state.json and the transaction journal. This file is NOT a source of truth;\n"
    "> when it conflicts with state, the prose or the transactions, they win.\n"
    "> Regenerate with: python3 scripts/state_view.py <project> --write <this-file>\n"
    "> revelations.truth is author-only information; never narrate it as reader-known.\n"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render a readable view of characters, relationships, threads, clues, revelations, "
            "timeline and handoff from state, or --check that an existing derived file is current. "
            "The view is derived and never becomes a second source of truth."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--write", type=Path, metavar="PATH", help="Write the derived view atomically")
    parser.add_argument("--check", type=Path, metavar="PATH", help="Fail if the derived view is stale")
    return parser.parse_args()


def render_mapping(values: dict, touched: dict[str, int] | None = None) -> list[str]:
    lines: list[str] = []
    if not isinstance(values, dict) or not values:
        return ["(none)"]
    for key in sorted(values):
        value = values[key]
        if not isinstance(value, dict):
            lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
            continue
        parts = [f"{name}={json.dumps(item, ensure_ascii=False)}" for name, item in sorted(value.items())]
        if touched is not None:
            parts.append(f"last_touched_chapter={touched.get(key, 0)}")
        lines.append(f"- {key}: " + ", ".join(parts))
    return lines


def render_view(project: Path) -> str:
    state = read_json(project / "state" / "state.json")
    errors = validate_state(state)
    if errors:
        raise ValueError("invalid state: " + "; ".join(errors))
    transactions = [read_json(path) for path in transaction_paths(project)]
    touched = last_touched_chapters(transactions)
    project_info = state.get("project") if isinstance(state.get("project"), dict) else {}
    handoff = state.get("handoff") if isinstance(state.get("handoff"), dict) else {}

    lines = [HEADER.rstrip(), ""]
    lines.append("## Project")
    lines.append(f"- title: {project_info.get('title', '')}")
    lines.append(f"- current_volume: {project_info.get('current_volume', '')}")
    lines.append(f"- current_chapter: {project_info.get('current_chapter', '')}")
    lines.append(f"- last_chapter_title: {project_info.get('last_chapter_title', '')}")
    lines.append(f"- last_chapter_summary: {project_info.get('last_chapter_summary', '')}")
    lines.append("")

    lines.append("## Timeline")
    timeline = state.get("timeline") if isinstance(state.get("timeline"), list) else []
    if timeline:
        for event in timeline:
            if isinstance(event, dict):
                chapter = event.get("chapter", "")
                event_id = event.get("id", "")
                detail = ", ".join(
                    f"{key}={json.dumps(value, ensure_ascii=False)}"
                    for key, value in sorted(event.items())
                    if key not in {"id", "chapter"}
                )
                lines.append(f"- chapter {chapter} [{event_id}]: {detail}")
    else:
        lines.append("(none)")
    lines.append("")

    lines.append("## Characters")
    lines.extend(render_mapping(state.get("characters", {})))
    lines.append("")
    lines.append("## Relationships")
    lines.extend(render_mapping(state.get("relationships", {}), touched))
    lines.append("")
    lines.append("## Plot threads")
    lines.extend(render_mapping(state.get("plot_threads", {}), touched))
    lines.append("")
    lines.append("## Foreshadowing")
    lines.extend(render_mapping(state.get("foreshadowing", {}), touched))
    lines.append("")
    lines.append("## Revelations (author truth)")
    revelations = state.get("revelations") if isinstance(state.get("revelations"), dict) else {}
    if revelations:
        for key in sorted(revelations):
            item = revelations[key] if isinstance(revelations[key], dict) else {}
            lines.append(
                f"- {key}: reader_known={item.get('reader_known')}, "
                f"known_by={json.dumps(item.get('known_by', []), ensure_ascii=False)}, "
                f"truth={json.dumps(item.get('truth', ''), ensure_ascii=False)}"
            )
    else:
        lines.append("(none)")
    lines.append("")
    lines.append("## Handoff")
    carry_over = handoff.get("carry_over") if isinstance(handoff.get("carry_over"), list) else []
    lines.append("- carry_over: " + (", ".join(carry_over) if carry_over else "(none)"))
    notes = handoff.get("notes") if isinstance(handoff.get("notes"), list) else []
    for note in notes:
        lines.append(f"- note: {note}")
    lines.append("")
    lines.append("## Continuity notes")
    notes_list = state.get("continuity_notes") if isinstance(state.get("continuity_notes"), list) else []
    lines.extend(f"- {note}" for note in notes_list) if notes_list else lines.append("(none)")
    lines.append("")
    return "\n".join(lines)


def atomic_write_text(path: Path, content: str) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
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
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    try:
        view = render_view(project)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.write:
        try:
            atomic_write_text(args.write, view)
        except OSError as exc:
            print(f"ERROR: cannot write {args.write}: {exc}")
            return 2
        print(args.write.expanduser().resolve())
        return 0
    if args.check:
        target = args.check.expanduser().resolve()
        if not target.is_file():
            print(f"ERROR: derived view not found: {target}")
            return 2
        existing = target.read_text(encoding="utf-8")
        if existing != view:
            print(f"STALE: {target} differs from a fresh render; regenerate with --write")
            return 1
        print(f"OK: state view is current: {target}")
        return 0
    print(view, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
