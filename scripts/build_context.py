#!/usr/bin/env python3
"""Build a deterministic context bundle for drafting the next novel chapter."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

from project_yaml import ProjectYAMLError, read_yaml
from state_model import read_json, validate_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build context for the next novel chapter")
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--chapter", type=int, help="Target chapter; defaults to current + 1")
    parser.add_argument("--recent", type=int, default=3, help="Number of recent chapters to include")
    parser.add_argument(
        "--character",
        action="append",
        default=[],
        metavar="ID",
        help="Character file stem to include; repeat as needed",
    )
    parser.add_argument(
        "--world",
        action="append",
        default=[],
        metavar="PATH",
        help="World entry path relative to world/; repeat as needed",
    )
    parser.add_argument("--output", type=Path, help="Write bundle to a file instead of stdout")
    parser.add_argument("--state", type=Path, help="Use a reviewed historical state snapshot for revision")
    parser.add_argument("--compact-state", action="store_true", help="Include a focused state view instead of all history")
    parser.add_argument("--max-chars", type=int, help="Fail if the generated context exceeds this many characters")
    return parser.parse_args()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing required file: {path}") from exc


def numbered_file(directory: Path, prefix: str, number: int, extensions: tuple[str, ...]) -> Path | None:
    names: list[str] = []
    for extension in extensions:
        names.extend(
            (
                f"{prefix}-{number:04d}.{extension}",
                f"{prefix}-{number:02d}.{extension}",
                f"{prefix}-{number}.{extension}",
                f"{number:04d}.{extension}",
                f"{number:02d}.{extension}",
                f"{number}.{extension}",
            )
        )
    for name in names:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def resolve_character(project: Path, character_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", character_id):
        raise SystemExit(f"Invalid character id: {character_id!r}")
    directory = project / "characters"
    for extension in ("yaml", "yml", "md"):
        candidate = directory / f"{character_id}.{extension}"
        if candidate.is_file():
            if not candidate.resolve().is_relative_to(directory.resolve()):
                raise SystemExit(f"Character file escapes characters/: {character_id}")
            return candidate
    raise SystemExit(f"Character file not found for id: {character_id}")


def resolve_world(project: Path, relative_name: str) -> Path:
    world_root = (project / "world").resolve()
    candidate = (world_root / relative_name).resolve()
    try:
        candidate.relative_to(world_root)
    except ValueError as exc:
        raise SystemExit(f"World path escapes world/: {relative_name}") from exc

    if candidate.is_file():
        return candidate
    if candidate.suffix:
        raise SystemExit(f"World entry not found: {relative_name}")
    for extension in (".md", ".yaml", ".yml"):
        with_extension = candidate.with_suffix(extension)
        if with_extension.is_file():
            return with_extension
    raise SystemExit(f"World entry not found: {relative_name}")


def optional_volume_outline(project: Path, volume: object) -> Path | None:
    if not isinstance(volume, int) or volume < 1:
        return None
    return numbered_file(project / "outline" / "volumes", "volume", volume, ("md",))


def source_block(project: Path, path: Path) -> str:
    relative = display_path(project, path)
    content = read_text(path).rstrip()
    return f"## Source: `{relative}`\n\n<source path=\"{relative}\">\n{content}\n</source>\n"


def display_path(project: Path, path: Path) -> str:
    try:
        return path.relative_to(project).as_posix()
    except ValueError:
        return str(path)


def compact_state(state: dict, characters: list[str], card: dict) -> dict:
    threads = card.get("threads") if isinstance(card.get("threads"), dict) else {}
    foreshadowing = card.get("foreshadowing") if isinstance(card.get("foreshadowing"), dict) else {}
    thread_refs = set((threads.get("advance") or []) + (threads.get("touch") or []))
    clue_refs = set((foreshadowing.get("plant") or []) + (foreshadowing.get("pay_off") or []))
    character_refs = set(characters)
    return {
        "schema_version": state["schema_version"],
        "project": state["project"],
        "characters": {key: value for key, value in state["characters"].items() if key in character_refs},
        "relationships": {key: value for key, value in state["relationships"].items() if any(name in key.split("__") for name in character_refs)},
        "plot_threads": {key: value for key, value in state["plot_threads"].items() if key in thread_refs or value.get("status", "open") != "resolved"},
        "foreshadowing": {key: value for key, value in state["foreshadowing"].items() if key in clue_refs or value.get("status", "planted") in {"planted", "active"}},
        "timeline": state["timeline"][-20:],
        "continuity_notes": state["continuity_notes"][-20:],
    }


def atomic_write(path: Path, content: str) -> None:
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
    if args.recent < 0:
        raise SystemExit("--recent must be zero or greater")
    if args.max_chars is not None and args.max_chars < 1:
        raise SystemExit("--max-chars must be positive")

    project = args.project.expanduser().resolve()
    if not project.is_dir():
        raise SystemExit(f"Project directory not found: {project}")

    novel = project / "novel.yaml"
    state_path = (args.state or project / "state" / "state.json").expanduser().resolve()
    master_outline = project / "outline" / "master.md"

    try:
        state = read_json(state_path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    state_errors = validate_state(state)
    if state_errors:
        raise SystemExit("invalid state: " + "; ".join(state_errors))
    current = state.get("project", {}).get("current_chapter")
    if not isinstance(current, int) or current < 0:
        raise SystemExit("state.project.current_chapter must be a non-negative integer")

    chapter = args.chapter if args.chapter is not None else current + 1
    if chapter != current + 1:
        raise SystemExit(
            f"Target chapter must be the next chapter ({current + 1}); got {chapter}. "
            "Revision contexts need manual review because state.json may contain later facts."
        )

    card = numbered_file(project / "control-cards", "chapter", chapter, ("yaml", "yml"))
    if card is None:
        raise SystemExit(
            f"Control card for chapter {chapter} not found. "
            f"Expected control-cards/chapter-{chapter:04d}.yaml or another supported numbered form."
        )
    try:
        card_data = read_yaml(card)
    except ProjectYAMLError as exc:
        raise SystemExit(str(exc)) from exc
    if not isinstance(card_data, dict) or card_data.get("chapter") != chapter:
        raise SystemExit(f"Control card {card} must have chapter: {chapter}")
    refs = card_data.get("context") or {}
    if not isinstance(refs, dict):
        raise SystemExit("Control card context must be an object")
    auto_characters = refs.get("characters", [])
    auto_world = refs.get("world", [])
    if not isinstance(auto_characters, list) or not isinstance(auto_world, list) or any(not isinstance(item, str) or not item for item in auto_characters + auto_world):
        raise SystemExit("Control card context.characters and context.world must be lists of non-empty strings")
    viewpoint = card_data.get("viewpoint")
    character_ids = list(dict.fromkeys(([viewpoint] if isinstance(viewpoint, str) and viewpoint else []) + auto_characters + args.character))
    world_names = list(dict.fromkeys(auto_world + args.world))

    sources: list[Path] = [novel, state_path, master_outline]
    volume_outline = optional_volume_outline(project, state.get("project", {}).get("current_volume"))
    if volume_outline is not None:
        sources.append(volume_outline)
    sources.append(card)

    recent_start = max(1, chapter - args.recent)
    recent_chapters: list[int] = []
    for number in range(recent_start, chapter):
        path = numbered_file(project / "chapters", "chapter", number, ("md", "txt"))
        if path is None:
            raise SystemExit(
                f"Recent chapter {number} is missing. "
                f"Expected chapters/chapter-{number:04d}.md or another supported numbered form."
            )
        recent_chapters.append(number)
        sources.append(path)

    character_paths = [resolve_character(project, character_id) for character_id in character_ids]
    world_paths = [resolve_world(project, name) for name in world_names]
    sources.extend(character_paths)
    sources.extend(world_paths)

    deduplicated_sources: list[Path] = []
    seen: set[Path] = set()
    for path in sources:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduplicated_sources.append(resolved)

    manifest = [
        "# Chapter Context",
        "",
        f"- Target chapter: {chapter}",
        f"- State current chapter: {current}",
        f"- Recent chapters: {', '.join(map(str, recent_chapters)) if recent_chapters else 'none'}",
        f"- Characters: {', '.join(character_ids) if character_ids else 'none'}",
        f"- World entries: {', '.join(world_names) if world_names else 'none'}",
        f"- State view: {'compact' if args.compact_state else 'full'}",
        "- Sources:",
    ]
    manifest.extend(f"  - {display_path(project, path)}" for path in deduplicated_sources)
    manifest.append("")

    blocks: list[str] = []
    for path in deduplicated_sources:
        if path == state_path and args.compact_state:
            relative = display_path(project, path)
            focused = json.dumps(compact_state(state, character_ids, card_data), ensure_ascii=False, indent=2)
            blocks.append(f"## Source: `{relative}` (focused view)\n\n<source path=\"{relative}\">\n{focused}\n</source>\n")
        else:
            blocks.append(source_block(project, path))
    bundle = "\n".join(manifest) + "\n" + "\n".join(blocks)
    if args.max_chars and len(bundle) > args.max_chars:
        raise SystemExit(f"Context has {len(bundle)} characters, above --max-chars={args.max_chars}; reduce --recent or use --compact-state")

    if args.output:
        atomic_write(args.output, bundle)
        print(args.output.expanduser().resolve())
    else:
        print(bundle, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
