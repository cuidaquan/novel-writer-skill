#!/usr/bin/env python3
"""Check chapter files, plans, transaction history and a completed book gate."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from modules import module_paths
from planning import check_payoff, check_plan
from prose_metrics import count_words
from project_yaml import ProjectYAMLError, read_yaml
from state_model import integer, nonempty, read_json, validate_state
from state_rebuild import rebuild, transaction_paths


def numbered_files(directory: Path, extensions: set[str], label: str, errors: list[str]) -> dict[int, Path]:
    result: dict[int, Path] = {}
    if not directory.is_dir():
        errors.append(f"missing {label} directory: {directory}")
        return result
    for path in directory.iterdir():
        if path.suffix.lstrip(".") not in extensions:
            continue
        match = re.fullmatch(r"(?:chapter-)?0*(\d+)", path.stem)
        if not match or int(match.group(1)) == 0:
            errors.append(f"unrecognized {label} filename: {path.name}")
            continue
        number = int(match.group(1))
        if number in result:
            errors.append(f"duplicate {label} chapter {number}: {path.name}")
        result[number] = path
    return result


def mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def id_list(value: object, where: str, errors: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not nonempty(item) for item in value):
        errors.append(f"{where} must be a list of non-empty strings")
        return []
    return value


def check(project: Path, complete: bool) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    stats = {"chapters": 0, "words": 0, "committed": 0}
    try:
        novel = read_yaml(project / "novel.yaml")
        state = read_json(project / "state" / "state.json")
        initial = read_json(project / "state" / "initial.json")
    except (OSError, ValueError, ProjectYAMLError) as exc:
        return [str(exc)], warnings, stats
    if not isinstance(novel, dict):
        return ["novel.yaml must be a mapping"], warnings, stats
    if novel.get("schema_version") != 1:
        errors.append("novel.yaml schema_version must be 1")
    errors.extend(validate_state(state))
    errors.extend(f"initial: {error}" for error in validate_state(initial))
    if mapping(initial.get("project")).get("current_chapter") != 0:
        errors.append("state/initial.json must be a chapter-zero snapshot")
    if novel.get("title") != mapping(state.get("project")).get("title"):
        errors.append("novel.yaml title differs from state.project.title")
    chapters = numbered_files(project / "chapters", {"md", "txt"}, "chapter", errors)
    cards = numbered_files(project / "control-cards", {"yaml", "yml"}, "control card", errors)
    stats["chapters"] = len(chapters)
    try:
        journals = transaction_paths(project)
        rebuilt = rebuild(project)
        if rebuilt != state:
            errors.append("state/state.json differs from replayed transactions; run state_rebuild.py after reviewing edits")
    except (OSError, ValueError) as exc:
        errors.append(f"transaction history: {exc}")
        journals = []
    current = mapping(state.get("project")).get("current_chapter")
    if not integer(current):
        current = 0
    stats["committed"] = current
    if current != len(journals):
        errors.append(
            f"state.current_chapter={current} but transaction count={len(journals)}; "
            "run state_rebuild.py --write to resynchronize the derived snapshot from the journal"
        )
    if current and set(range(1, current + 1)) - chapters.keys():
        errors.append("one or more committed chapters have no body file")
    if current and set(range(1, current + 1)) - cards.keys():
        errors.append("one or more committed chapters have no control card")
    for number in chapters.keys() - cards.keys():
        errors.append(f"chapter {number} has no control card")
    for number in cards.keys() - chapters.keys():
        if complete or number <= current:
            errors.append(f"control card {number} has no chapter body")
    if chapters and sorted(chapters) != list(range(1, max(chapters) + 1)):
        errors.append("chapter body numbering has gaps")

    narration = mapping(novel.get("narration"))
    allowed_povs = id_list(narration.get("viewpoint_characters", []), "narration.viewpoint_characters", errors)
    known_characters = {path.stem for path in (project / "characters").glob("*.yaml")}
    known_characters |= {path.stem for path in (project / "characters").glob("*.yml")}
    known_characters |= {path.stem for path in (project / "characters").glob("*.md")}
    for character in allowed_povs:
        if character not in known_characters:
            errors.append(f"viewpoint character has no character file: {character}")
    available_threads = set(mapping(initial.get("plot_threads")))
    available_foreshadowing = set(mapping(initial.get("foreshadowing")))
    available_revelations = set(mapping(initial.get("revelations")))
    for revelation_id, item in mapping(state.get("revelations")).items():
        known_by = item.get("known_by", []) if isinstance(item, dict) else []
        for character in known_by if isinstance(known_by, list) else []:
            if character not in known_characters:
                errors.append(f"revelations.{revelation_id}: unknown character in known_by: {character}")

    for number, path in sorted(chapters.items()):
        tx: dict = {}
        if number <= len(journals):
            try:
                tx = read_json(journals[number - 1])
                available_threads.update(mapping(tx.get("plot_thread_updates")))
                available_foreshadowing.update(mapping(tx.get("foreshadowing_updates")))
                available_revelations.update(mapping(tx.get("revelation_updates")))
            except ValueError as exc:
                errors.append(str(exc))
        body = path.read_text(encoding="utf-8")
        words = count_words(body)
        stats["words"] += words
        if not body.strip():
            errors.append(f"chapter {number} body is empty")
        card_path = cards.get(number)
        if card_path is None:
            continue
        try:
            card = read_yaml(card_path)
        except (OSError, ProjectYAMLError) as exc:
            errors.append(str(exc))
            continue
        if not isinstance(card, dict):
            errors.append(f"{card_path}: root must be a mapping")
            continue
        try:
            module_paths(novel, card)
        except ValueError as exc:
            errors.append(f"{card_path.name}: {exc}")
        check_payoff(card, card_path.name, errors)
        if card.get("chapter") != number:
            errors.append(f"{card_path.name}: chapter field must be {number}")
        if number <= current and nonempty(card.get("title")) and tx.get("chapter_title") != card["title"]:
            errors.append(f"chapter {number} transaction title differs from its control card")
        viewpoint = card.get("viewpoint")
        if viewpoint is not None:
            if viewpoint not in known_characters:
                errors.append(f"{card_path.name}: unknown viewpoint character {viewpoint}")
            if allowed_povs and viewpoint not in allowed_povs:
                errors.append(f"{card_path.name}: viewpoint is not in novel.yaml narration.viewpoint_characters")
        target = card.get("target_words")
        if target is not None:
            if not integer(target, 1):
                errors.append(f"{card_path.name}: target_words must be positive")
            elif number <= current and words < target * 0.8:
                warnings.append(f"chapter {number} has {words} words, below 80% of its {target} word target")
        elif complete:
            errors.append(f"{card_path.name}: completed book needs target_words for every chapter")
        if card.get("context") is not None and not isinstance(card["context"], dict):
            errors.append(f"{card_path.name}: context must be a mapping")
        refs = mapping(card.get("context"))
        for character in id_list(refs.get("characters", []), f"{card_path.name} context.characters", errors):
            if character not in known_characters:
                errors.append(f"{card_path.name}: context character missing: {character}")
        for world in id_list(refs.get("world", []), f"{card_path.name} context.world", errors):
            root = (project / "world").resolve()
            path_ref = (root / world).resolve()
            if not path_ref.is_relative_to(root) or not any(candidate.is_file() for candidate in (path_ref, path_ref.with_suffix(".md"), path_ref.with_suffix(".yaml"), path_ref.with_suffix(".yml"))):
                errors.append(f"{card_path.name}: context world entry missing or outside world/: {world}")
        if number <= current:
            transaction_threads = mapping(tx.get("plot_thread_updates"))
            threads = mapping(card.get("threads"))
            for name in ("advance", "touch"):
                for item in id_list(threads.get(name, []), f"{card_path.name} threads.{name}", errors):
                    if item not in available_threads:
                        errors.append(f"{card_path.name}: unknown plot thread {item}")
                    elif item not in transaction_threads:
                        if name == "advance":
                            errors.append(f"{card_path.name}: promised plot thread advance {item} is missing from the chapter transaction")
                        else:
                            warnings.append(f"{card_path.name}: promised plot thread touch {item} is missing from the chapter transaction")
            transaction_foreshadowing = mapping(tx.get("foreshadowing_updates"))
            foreshadowing = mapping(card.get("foreshadowing"))
            for name in ("plant", "pay_off"):
                for item in id_list(foreshadowing.get(name, []), f"{card_path.name} foreshadowing.{name}", errors):
                    if item not in available_foreshadowing:
                        errors.append(f"{card_path.name}: unknown foreshadowing {item}")
                    elif item not in transaction_foreshadowing:
                        errors.append(f"{card_path.name}: promised foreshadowing {name} {item} is missing from the chapter transaction")
            if card.get("revelations") is not None and not isinstance(card["revelations"], dict):
                errors.append(f"{card_path.name}: revelations must be a mapping")
            transaction_revelations = mapping(tx.get("revelation_updates"))
            revelations = mapping(card.get("revelations"))
            planned_reveals: set[str] = set()
            for name in ("touch", "reveal"):
                for item in id_list(revelations.get(name, []), f"{card_path.name} revelations.{name}", errors):
                    if item not in available_revelations:
                        errors.append(f"{card_path.name}: unknown revelation {item}")
                    if name == "reveal":
                        planned_reveals.add(item)
                        update = transaction_revelations.get(item)
                        if not isinstance(update, dict) or update.get("reader_known") is not True or update.get("revealed_chapter") != number:
                            errors.append(f"{card_path.name}: planned reveal {item} is missing from chapter transaction")
                    elif item in available_revelations and item not in transaction_revelations:
                        warnings.append(f"{card_path.name}: promised revelation touch {item} is missing from the chapter transaction")
            for item, update in transaction_revelations.items():
                if isinstance(update, dict) and update.get("reader_known") is True and update.get("revealed_chapter") == number and item not in planned_reveals:
                    errors.append(f"{card_path.name}: reader reveal {item} is missing from control card")

    length = mapping(novel.get("length"))
    target_chapters = length.get("target_chapters")
    target_words = length.get("target_words")
    for name, value in (("target_chapters", target_chapters), ("target_words", target_words)):
        if value is not None and not integer(value, 1):
            errors.append(f"length.{name} must be a positive integer or null")
    if integer(target_chapters, 1) and current > target_chapters:
        errors.append("current_chapter exceeds target_chapters")
    if complete:
        if not integer(target_chapters, 1) or not integer(target_words, 1):
            errors.append("completed book needs positive target_chapters and target_words")
        else:
            if current != target_chapters or len(chapters) != target_chapters:
                errors.append(f"complete book requires {target_chapters} committed chapters and body files")
            if stats["words"] < target_words * 0.9:
                errors.append(f"complete book has {stats['words']} words, below 90% of target {target_words}")
        for name, thread in mapping(state.get("plot_threads")).items():
            if isinstance(thread, dict) and thread.get("status", "open") != "resolved":
                errors.append(f"unresolved plot thread: {name}")
        for name, item in mapping(state.get("foreshadowing")).items():
            if isinstance(item, dict) and item.get("status", "planted") in {"planted", "active"}:
                errors.append(f"unresolved foreshadowing: {name}")
    return errors, warnings, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a novel project and optional finished-book gate")
    parser.add_argument("project", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--complete", action="store_true", help="Require every planned chapter, word target and resolved plot")
    mode.add_argument("--preflight", choices=("book", "serial"), help="Check the plan before writing a full book or the next serial chapter")
    args = parser.parse_args()
    project = args.project.expanduser().resolve()
    errors, warnings, stats = check(project, args.complete)
    if args.preflight and not errors:
        errors.extend(check_plan(project, args.preflight))
    for warning in warnings:
        print(f"WARN: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    if args.preflight:
        print(f"OK: {args.preflight} preflight, next chapter {stats['committed'] + 1}")
    else:
        print(f"OK: {stats['committed']} committed chapters, {stats['chapters']} body files, {stats['words']} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
