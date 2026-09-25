"""Shared validation and deterministic chapter transaction mechanics."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any


PLOT_STATUS = {"open", "paused", "resolved"}
FORESHADOWING_STATUS = {"planted", "active", "resolved", "dropped"}
MAPPING_UPDATES = {
    "characters": "character_updates",
    "relationships": "relationship_updates",
    "plot_threads": "plot_thread_updates",
    "foreshadowing": "foreshadowing_updates",
    "revelations": "revelation_updates",
}


def integer(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


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


def validate_state(state: dict) -> list[str]:
    errors: list[str] = []
    if state.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    project = state.get("project")
    if not isinstance(project, dict):
        errors.append("project must be an object")
        project = {}
    if not nonempty(project.get("title")):
        errors.append("project.title must be a non-empty string")
    current = project.get("current_chapter")
    if not integer(current):
        errors.append("project.current_chapter must be a non-negative integer")
    if not integer(project.get("current_volume"), 1):
        errors.append("project.current_volume must be a positive integer")
    for section in MAPPING_UPDATES:
        mapping = state.get(section, {}) if section == "revelations" else state.get(section)
        if not isinstance(mapping, dict):
            errors.append(f"{section} must be an object")
            continue
        for key, item in mapping.items():
            if not nonempty(key) or not isinstance(item, dict):
                errors.append(f"{section}.{key} must be an object with a non-empty id")
                continue
            if section == "plot_threads" and item.get("status", "open") not in PLOT_STATUS:
                errors.append(f"plot_threads.{key}.status is invalid")
            if section == "foreshadowing":
                status = item.get("status", "planted")
                if status not in FORESHADOWING_STATUS:
                    errors.append(f"foreshadowing.{key}.status is invalid")
                if status == "resolved" and not integer(item.get("resolved_chapter"), 1):
                    errors.append(f"foreshadowing.{key}.resolved_chapter is required")
                if status == "resolved" and integer(current) and integer(item.get("resolved_chapter"), 1) and item["resolved_chapter"] > current:
                    errors.append(f"foreshadowing.{key}.resolved_chapter is in the future")
            if section == "revelations":
                if not nonempty(item.get("truth")):
                    errors.append(f"revelations.{key}.truth must be a non-empty string")
                known_by = item.get("known_by")
                if not isinstance(known_by, list) or any(not nonempty(name) for name in known_by) or len(known_by) != len(set(known_by)):
                    errors.append(f"revelations.{key}.known_by must be a list of distinct character ids")
                reader_known = item.get("reader_known")
                if type(reader_known) is not bool:
                    errors.append(f"revelations.{key}.reader_known must be a boolean")
                elif reader_known:
                    revealed = item.get("revealed_chapter")
                    if not integer(revealed, 1) or (integer(current) and revealed > current):
                        errors.append(f"revelations.{key}.revealed_chapter must be between 1 and current_chapter")
                elif "revealed_chapter" in item:
                    errors.append(f"revelations.{key}.revealed_chapter requires reader_known=true")
    timeline = state.get("timeline")
    if not isinstance(timeline, list):
        errors.append("timeline must be a list")
    else:
        seen: set[str] = set()
        for index, event in enumerate(timeline):
            if not isinstance(event, dict):
                errors.append(f"timeline[{index}] must be an object")
                continue
            event_id = event.get("id")
            if not nonempty(event_id):
                errors.append(f"timeline[{index}].id must be a non-empty string")
            elif event_id in seen:
                errors.append(f"duplicate timeline id: {event_id}")
            else:
                seen.add(event_id)
            chapter = event.get("chapter")
            if not integer(chapter, 1) or (integer(current) and chapter > current):
                errors.append(f"timeline[{index}].chapter must be between 1 and current_chapter")
    notes = state.get("continuity_notes")
    if not isinstance(notes, list) or any(not nonempty(note) for note in notes):
        errors.append("continuity_notes must be a list of non-empty strings")
    handoff = state.get("handoff")
    if handoff is not None:
        if not isinstance(handoff, dict):
            errors.append("handoff must be an object")
        else:
            chapter = handoff.get("chapter")
            if not integer(chapter) or (integer(current) and chapter != current):
                errors.append("handoff.chapter must equal project.current_chapter")
            carry_over = handoff.get("carry_over", [])
            if not isinstance(carry_over, list) or any(not nonempty(item) for item in carry_over) or len(carry_over) != len(set(carry_over)):
                errors.append("handoff.carry_over must be a list of distinct non-empty ids")
            elif integer(chapter):
                threads = state.get("plot_threads") if isinstance(state.get("plot_threads"), dict) else {}
                clues = state.get("foreshadowing") if isinstance(state.get("foreshadowing"), dict) else {}
                for item in carry_over:
                    thread = threads.get(item)
                    clue = clues.get(item)
                    if thread is None and clue is None:
                        errors.append(f"handoff.carry_over references unknown item: {item}")
                    elif isinstance(thread, dict) and thread.get("status", "open") == "resolved":
                        errors.append(f"handoff.carry_over cannot reference a resolved plot thread: {item}")
                    elif isinstance(clue, dict) and clue.get("status", "planted") in {"resolved", "dropped"}:
                        errors.append(f"handoff.carry_over cannot reference closed foreshadowing: {item}")
            handoff_notes = handoff.get("notes", [])
            if not isinstance(handoff_notes, list) or any(not nonempty(note) for note in handoff_notes):
                errors.append("handoff.notes must be a list of non-empty strings")
    return errors


def validate_transaction(tx: dict, current: int) -> list[str]:
    errors: list[str] = []
    if not integer(tx.get("expected_chapter")) or tx["expected_chapter"] != current:
        errors.append(f"expected_chapter must equal {current}")
    if not integer(tx.get("chapter"), 1) or tx["chapter"] != current + 1:
        errors.append(f"chapter must equal {current + 1}")
    if not nonempty(tx.get("summary")):
        errors.append("summary must be a non-empty string")
    if not isinstance(tx.get("chapter_title", ""), str):
        errors.append("chapter_title must be a string")
    for field in MAPPING_UPDATES.values():
        updates = tx.get(field, {})
        if not isinstance(updates, dict):
            errors.append(f"{field} must be an object")
            continue
        for key, value in updates.items():
            if not nonempty(key) or (value is not None and not isinstance(value, dict)):
                errors.append(f"{field}.{key} must be an object or null")
    events = tx.get("timeline_events", [])
    if not isinstance(events, list):
        errors.append("timeline_events must be a list")
    else:
        for index, event in enumerate(events):
            if not isinstance(event, dict) or not nonempty(event.get("id")):
                errors.append(f"timeline_events[{index}].id must be a non-empty string")
            elif "chapter" in event and event["chapter"] != current + 1:
                errors.append(f"timeline_events[{index}].chapter must equal {current + 1}")
    notes = tx.get("continuity_notes_add", [])
    if not isinstance(notes, list) or any(not nonempty(note) for note in notes):
        errors.append("continuity_notes_add must be a list of non-empty strings")
    handoff = tx.get("handoff")
    if handoff is not None:
        if not isinstance(handoff, dict):
            errors.append("handoff must be an object")
        else:
            carry_over = handoff.get("carry_over", [])
            if not isinstance(carry_over, list) or any(not nonempty(item) for item in carry_over):
                errors.append("handoff.carry_over must be a list of non-empty ids")
            handoff_notes = handoff.get("notes", [])
            if not isinstance(handoff_notes, list) or any(not nonempty(note) for note in handoff_notes):
                errors.append("handoff.notes must be a list of non-empty strings")
    return errors


def apply_transaction(state: dict, tx: dict) -> dict:
    errors = validate_state(state)
    if errors:
        raise ValueError("invalid current state: " + "; ".join(errors))
    current = state["project"]["current_chapter"]
    errors = validate_transaction(tx, current)
    if errors:
        raise ValueError("invalid transaction: " + "; ".join(errors))
    result = copy.deepcopy(state)
    if tx.get("revelation_updates"):
        result.setdefault("revelations", {})
    for section, field in MAPPING_UPDATES.items():
        for key, value in tx.get(field, {}).items():
            if section == "revelations" and value is None:
                raise ValueError(f"revelations.{key} cannot be deleted by a chapter transaction")
            if section == "revelations" and key in result[section]:
                previous = result[section][key]
                if "truth" in value and value["truth"] != previous["truth"]:
                    raise ValueError(f"revelations.{key}.truth cannot change in a chapter transaction")
                if previous["reader_known"] and value.get("reader_known") is False:
                    raise ValueError(f"revelations.{key} cannot become unknown to the reader")
                if previous["reader_known"] and "revealed_chapter" in value and value["revealed_chapter"] != previous["revealed_chapter"]:
                    raise ValueError(f"revelations.{key}.revealed_chapter cannot change")
            if section == "revelations" and value.get("reader_known") is True:
                previous = result[section].get(key, {})
                if not previous.get("reader_known") and value.get("revealed_chapter") != current + 1:
                    raise ValueError(f"revelations.{key}.revealed_chapter must equal {current + 1} when revealed")
            if value is None:
                result[section].pop(key, None)
            elif isinstance(result[section].get(key), dict):
                result[section][key].update(copy.deepcopy(value))
            else:
                result[section][key] = copy.deepcopy(value)
    for event in tx.get("timeline_events", []):
        item = copy.deepcopy(event)
        item.setdefault("chapter", current + 1)
        result["timeline"].append(item)
    for note in tx.get("continuity_notes_add", []):
        if note not in result["continuity_notes"]:
            result["continuity_notes"].append(note)
    result["project"]["current_chapter"] = current + 1
    result["project"]["last_chapter_title"] = tx.get("chapter_title", "")
    result["project"]["last_chapter_summary"] = tx["summary"].strip()
    supplied = tx.get("handoff")
    supplied = supplied if isinstance(supplied, dict) else {}
    carry_over = supplied.get("carry_over", [])
    handoff_notes = supplied.get("notes", [])
    result["handoff"] = {
        "chapter": current + 1,
        "carry_over": list(dict.fromkeys(item for item in carry_over if isinstance(item, str) and item.strip())),
        "notes": [note.strip() for note in handoff_notes if isinstance(note, str) and note.strip()],
    }
    errors = validate_state(result)
    if errors:
        raise ValueError("transaction would produce invalid state: " + "; ".join(errors))
    return result


def last_touched_chapters(transactions: list[dict]) -> dict[str, int]:
    """Map every state key updated by a transaction to its latest chapter."""
    touched: dict[str, int] = {}
    for chapter, tx in enumerate(transactions, 1):
        for field in (
            "character_updates",
            "relationship_updates",
            "plot_thread_updates",
            "foreshadowing_updates",
            "revelation_updates",
        ):
            updates = tx.get(field)
            if isinstance(updates, dict):
                for key in updates:
                    touched[key] = chapter
    return touched


def replay(initial: dict, transactions: list[dict]) -> dict:
    errors = validate_state(initial)
    project = initial.get("project")
    if not isinstance(project, dict) or project.get("current_chapter") != 0:
        errors.append("project.current_chapter must be 0")
    if errors:
        raise ValueError("initial state must be valid at chapter 0: " + "; ".join(errors))
    state = copy.deepcopy(initial)
    for index, tx in enumerate(transactions, 1):
        try:
            state = apply_transaction(state, tx)
        except ValueError as exc:
            raise ValueError(f"chapter {index}: {exc}") from exc
    return state
