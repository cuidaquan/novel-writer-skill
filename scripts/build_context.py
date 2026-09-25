#!/usr/bin/env python3
"""Build a deterministic context bundle for drafting the next novel chapter."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

import prose_metrics
from modules import genre_module_status, module_paths
from planning import check_plan
from project_yaml import ProjectYAMLError, read_yaml
from state_model import last_touched_chapters, read_json, validate_state
from state_rebuild import transaction_paths


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
    parser.add_argument("--fit", action="store_true", help="With --max-chars, shrink the compact view and recent chapters to fit the budget")
    parser.add_argument("--active-limit", type=int, help=f"Maximum active-pressure digests in the compact view (default: {DEFAULT_ACTIVE_LIMIT})")
    parser.add_argument("--style-anchor", action="store_true", help="Add a short observed style anchor derived from finalized chapters")
    parser.add_argument("--anchor-recent", type=int, default=5, help="Finalized chapters pooled for the style anchor (default: 5)")
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


ACTIVE_THREAD_STATUS = {"open", "paused"}
ACTIVE_FORESHADOWING_STATUS = {"planted", "active"}
DEFAULT_TIMELINE_LIMIT = 20
DEFAULT_NOTES_LIMIT = 20
DEFAULT_ACTIVE_LIMIT = 40


def active_pressure(
    state: dict,
    touched: dict[str, int],
    character_refs: set[str],
    referenced: set[str],
) -> list[dict]:
    """Digest of still-open items, referenced first, then longest untouched.

    Full objects stay in the sections for items the chapter references or the
    handoff carries over; everything else is only summarised here so a project
    with many live threads cannot inflate the context without bound.
    """
    items: list[dict] = []
    threads = state.get("plot_threads") if isinstance(state.get("plot_threads"), dict) else {}
    clues = state.get("foreshadowing") if isinstance(state.get("foreshadowing"), dict) else {}
    relationships = state.get("relationships") if isinstance(state.get("relationships"), dict) else {}
    for key, thread in threads.items():
        if isinstance(thread, dict) and thread.get("status", "open") in ACTIVE_THREAD_STATUS:
            items.append({
                "kind": "plot_thread",
                "id": key,
                "status": thread.get("status", "open"),
                "last_touched_chapter": touched.get(key, 0),
                "_referenced": key in referenced,
            })
    for key, clue in clues.items():
        if isinstance(clue, dict) and clue.get("status", "planted") in ACTIVE_FORESHADOWING_STATUS:
            items.append({
                "kind": "foreshadowing",
                "id": key,
                "status": clue.get("status", "planted"),
                "last_touched_chapter": touched.get(key, 0),
                "_referenced": key in referenced,
            })
    for key, relationship in relationships.items():
        if not isinstance(relationship, dict) or relationship.get("status", "open") == "resolved":
            continue
        if not any(name in key.split("__") for name in character_refs):
            continue
        items.append({
            "kind": "relationship",
            "id": key,
            "status": relationship.get("status", "open"),
            "last_touched_chapter": touched.get(key, 0),
            "_referenced": True,
        })
    items.sort(key=lambda item: (not item["_referenced"], item["last_touched_chapter"], item["kind"], item["id"]))
    return [{key: value for key, value in item.items() if key != "_referenced"} for item in items]


def compact_state(
    state: dict,
    characters: list[str],
    card: dict,
    transactions: list[dict],
    timeline_limit: int = DEFAULT_TIMELINE_LIMIT,
    notes_limit: int = DEFAULT_NOTES_LIMIT,
    active_limit: int = DEFAULT_ACTIVE_LIMIT,
) -> tuple[dict, dict]:
    """Prioritized state view: references and carry-over stay whole, the rest is a digest."""
    threads = card.get("threads") if isinstance(card.get("threads"), dict) else {}
    foreshadowing = card.get("foreshadowing") if isinstance(card.get("foreshadowing"), dict) else {}
    thread_refs = set((threads.get("advance") or []) + (threads.get("touch") or []))
    clue_refs = set((foreshadowing.get("plant") or []) + (foreshadowing.get("pay_off") or []))
    character_refs = set(characters)
    revelation_refs = card.get("revelations") if isinstance(card.get("revelations"), dict) else {}
    secret_ids = set((revelation_refs.get("touch") or []) + (revelation_refs.get("reveal") or []))
    handoff = state.get("handoff") if isinstance(state.get("handoff"), dict) else {}
    carry_over = handoff.get("carry_over") if isinstance(handoff.get("carry_over"), list) else []
    thread_refs.update(item for item in carry_over if item in state.get("plot_threads", {}))
    clue_refs.update(item for item in carry_over if item in state.get("foreshadowing", {}))
    touched = last_touched_chapters(transactions)
    active = active_pressure(state, touched, character_refs, thread_refs | clue_refs)
    digest = active[:active_limit] if active_limit else []
    omitted_active = len(active) - len(digest)
    focused = {
        "schema_version": state["schema_version"],
        "project": state["project"],
        "handoff": {
            "carry_over": list(carry_over),
            "notes": list(handoff.get("notes") or []),
        },
        "active_pressure": digest,
        "active_pressure_omitted": omitted_active,
        "characters": {key: value for key, value in state["characters"].items() if key in character_refs},
        "relationships": {key: value for key, value in state["relationships"].items() if any(name in key.split("__") for name in character_refs)},
        "plot_threads": {key: value for key, value in state["plot_threads"].items() if key in thread_refs},
        "foreshadowing": {key: value for key, value in state["foreshadowing"].items() if key in clue_refs},
        "revelations": {key: value for key, value in state.get("revelations", {}).items() if key in secret_ids},
        "timeline": state["timeline"][-timeline_limit:] if timeline_limit else [],
        "continuity_notes": state["continuity_notes"][-notes_limit:] if notes_limit else [],
    }
    omitted = {
        "characters": len(state["characters"]) - len(focused["characters"]),
        "relationships": len(state["relationships"]) - len(focused["relationships"]),
        "plot_threads": len(state["plot_threads"]) - len(focused["plot_threads"]),
        "foreshadowing": len(state["foreshadowing"]) - len(focused["foreshadowing"]),
        "revelations": len(state.get("revelations", {})) - len(focused["revelations"]),
        "timeline": len(state["timeline"]) - len(focused["timeline"]),
        "continuity_notes": len(state["continuity_notes"]) - len(focused["continuity_notes"]),
        "active_pressure": omitted_active,
    }
    return focused, omitted


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
    if args.fit and args.max_chars is None:
        raise SystemExit("--fit requires --max-chars")
    if args.anchor_recent < 1:
        raise SystemExit("--anchor-recent must be positive")
    if args.active_limit is not None and args.active_limit < 0:
        raise SystemExit("--active-limit must be zero or greater")

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
    plan_errors = check_plan(project, "chapter", chapter, state_path)
    if plan_errors:
        raise SystemExit("chapter preflight failed:\n" + "\n".join(f"- {error}" for error in plan_errors))

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
    try:
        novel_data = read_yaml(novel)
        if not isinstance(novel_data, dict):
            raise ValueError("novel.yaml must be a mapping")
        selected_modules = module_paths(novel_data, card_data)
        present_genres, missing_genres = genre_module_status(novel_data)
    except (ProjectYAMLError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    refs = card_data.get("context") or {}
    if not isinstance(refs, dict):
        raise SystemExit("Control card context must be an object")
    auto_characters = refs.get("characters", [])
    auto_world = refs.get("world", [])
    if not isinstance(auto_characters, list) or not isinstance(auto_world, list) or any(not isinstance(item, str) or not item for item in auto_characters + auto_world):
        raise SystemExit("Control card context.characters and context.world must be lists of non-empty strings")
    revelation_refs = card_data.get("revelations") or {}
    if not isinstance(revelation_refs, dict) or any(
        not isinstance(revelation_refs.get(name, []), list)
        or any(not isinstance(item, str) or not item for item in revelation_refs.get(name, []))
        for name in ("touch", "reveal")
    ):
        raise SystemExit("Control card revelations.touch and revelations.reveal must be lists of non-empty ids")
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
    sources.extend(selected_modules)

    deduplicated_sources: list[Path] = []
    seen: set[Path] = set()
    for path in sources:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduplicated_sources.append(resolved)

    anchor_lines = ""
    anchor_chapters: list[int] = []
    if args.style_anchor:
        anchor_texts: list[str] = []
        for number in range(max(1, current - args.anchor_recent + 1), current + 1):
            path = numbered_file(project / "chapters", "chapter", number, ("md", "txt"))
            if path is not None:
                anchor_texts.append(path.read_text(encoding="utf-8"))
                anchor_chapters.append(number)
        pooled = prose_metrics.pooled_metrics(anchor_texts)
        if pooled["paragraphs"] >= prose_metrics.MIN_BASELINE_PARAGRAPHS and pooled["characters"] >= prose_metrics.MIN_BASELINE_CHARACTERS:
            proposals = prose_metrics.style_proposals(pooled)
            anchor_lines = "\n".join(
                [
                    f"## Style anchor (observed from {len(anchor_chapters)} finalized chapter(s))",
                    "",
                    f"- chapters: {', '.join(map(str, anchor_chapters))}",
                    f"- avg_sentence_chars: {pooled['avg_sentence_chars']}",
                    f"- avg_paragraph_chars: {pooled['avg_paragraph_chars']}",
                    f"- dialogue_line_ratio: {pooled['dialogue_line_ratio']}",
                    f"- suggested style.sentence_length: {proposals['sentence_length']}",
                    f"- suggested style.dialogue_density: {proposals['dialogue_density']}",
                    "- Observed from finalized chapters; confirm against novel.yaml before treating it as a rule.",
                    "",
                ]
            )

    transaction_files = transaction_paths(project)
    transactions = [read_json(path) for path in transaction_files]

    recent_path_numbers: dict[Path, int] = {}
    for number in recent_chapters:
        path = numbered_file(project / "chapters", "chapter", number, ("md", "txt"))
        if path is not None:
            recent_path_numbers[path.resolve()] = number

    active_limit = args.active_limit if args.active_limit is not None else DEFAULT_ACTIVE_LIMIT
    timeline_limit = DEFAULT_TIMELINE_LIMIT
    notes_limit = DEFAULT_NOTES_LIMIT
    selected_recent = set(recent_chapters)
    trim_notes: list[str] = []

    def render(active: int, timeline: int, notes: int, recent: set[int]) -> tuple[str, list[tuple[int, str]], dict | None]:
        blocks: list[str] = []
        sizes: list[tuple[int, str]] = []
        omitted: dict | None = None
        included: list[Path] = []
        for path in deduplicated_sources:
            number = recent_path_numbers.get(path)
            if number is not None and number not in recent:
                continue
            included.append(path)
            relative = display_path(project, path)
            if path == state_path and args.compact_state:
                focused, omitted = compact_state(state, character_ids, card_data, transactions, timeline, notes, active)
                content = json.dumps(focused, ensure_ascii=False, indent=2)
                block = f"## Source: `{relative}` (focused view)\n\n<source path=\"{relative}\">\n{content}\n</source>\n"
            else:
                block = source_block(project, path)
            blocks.append(block)
            sizes.append((len(block), relative))
        if anchor_lines:
            blocks.append(anchor_lines)
            sizes.append((len(anchor_lines), "style-anchor"))
        selected_list = [number for number in recent_chapters if number in recent]
        manifest = [
            "# Chapter Context",
            "",
            f"- Target chapter: {chapter}",
            f"- State current chapter: {current}",
            f"- Recent chapters: {', '.join(map(str, selected_list)) if selected_list else 'none'}",
            f"- Characters: {', '.join(character_ids) if character_ids else 'none'}",
            f"- World entries: {', '.join(world_names) if world_names else 'none'}",
            f"- State view: {'compact' if args.compact_state else 'full'}",
        ]
        genre_note = ", ".join(present_genres) if present_genres else "none"
        if missing_genres:
            genre_note += f"; no module for: {', '.join(missing_genres)} (generic path)"
        manifest.append(f"- Genre modules: {genre_note}")
        override = card_data.get("style_override") if isinstance(card_data.get("style_override"), dict) else {}
        if override:
            manifest.append("- Style override: " + ", ".join(f"{key}={value}" for key, value in sorted(override.items())))
        if args.compact_state and omitted is not None:
            omitted_note = ", ".join(f"{key} {value}" for key, value in omitted.items() if value)
            manifest.append(f"- Compact view omitted: {omitted_note or 'none'}")
            if omitted.get("active_pressure"):
                manifest.append("- Full active list: run scripts/handoff_report.py")
        if trim_notes:
            manifest.append("- Trimmed for --max-chars: " + "; ".join(trim_notes))
        if args.style_anchor:
            manifest.append(
                f"- Style anchor: chapters {', '.join(map(str, anchor_chapters))}"
                if anchor_lines
                else "- Style anchor: unavailable (insufficient finalized sample)"
            )
        manifest.append("- Information boundary: revelations.truth is author-only; reader_known=false is not confirmed to readers. A viewpoint character knows a truth only when listed in known_by. A planned reveal must be earned on the page before the transaction marks it reader-known.")
        manifest.append("- Sources:")
        manifest.extend(f"  - {display_path(project, path)}" for path in included)
        manifest.append("")
        return "\n".join(manifest) + "\n" + "\n".join(blocks), sizes, omitted

    bundle, sizes, omitted = render(active_limit, timeline_limit, notes_limit, selected_recent)
    if args.max_chars and len(bundle) > args.max_chars and args.fit:
        for step_active, step_timeline, step_notes in ((20, 10, 10), (10, 5, 5), (5, 2, 2), (0, 0, 0)):
            active_limit = min(active_limit, step_active)
            timeline_limit, notes_limit = step_timeline, step_notes
            trim_notes = [f"compact view reduced to active<={active_limit}, timeline<={timeline_limit}, notes<={notes_limit}"]
            bundle, sizes, omitted = render(active_limit, timeline_limit, notes_limit, selected_recent)
            if len(bundle) <= args.max_chars:
                break
        while len(bundle) > args.max_chars and selected_recent:
            ordered = [number for number in recent_chapters if number in selected_recent]
            selected_recent.discard(ordered[0])
            dropped = [number for number in recent_chapters if number not in selected_recent]
            trim_notes = trim_notes[:1] + [f"dropped recent chapters: {', '.join(map(str, dropped))}"]
            bundle, sizes, omitted = render(active_limit, timeline_limit, notes_limit, selected_recent)
    if args.max_chars and len(bundle) > args.max_chars:
        largest = ", ".join(f"{label} ({size} chars)" for size, label in sorted(sizes, reverse=True)[:3])
        raise SystemExit(f"Context has {len(bundle)} characters, above --max-chars={args.max_chars}; largest sources: {largest}. Reduce --recent, use --compact-state or pass --fit.")

    if args.output:
        atomic_write(args.output, bundle)
        print(args.output.expanduser().resolve())
    else:
        print(bundle, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
