"""Deterministic readiness checks before drafting planned fiction chapters."""

from __future__ import annotations

import re
from pathlib import Path

from modules import module_paths
from project_yaml import ProjectYAMLError, read_yaml
from state_model import integer, nonempty, read_json, validate_state


PROMISE_FIELDS = ("主角", "核心欲望", "最大阻力", "失败代价", "核心读者回报")
SERIAL_FIELDS = (*PROMISE_FIELDS, "结局状态", "主角从什么状态变到什么状态", "主类型承诺将在何处兑现")
BOOK_FIELDS = (
    *PROMISE_FIELDS,
    "起始失衡",
    "第一次不可逆选择",
    "中段认知/局势变化",
    "最严重失败或代价",
    "终局选择",
    "结局状态",
    "主角从什么状态变到什么状态",
    "主类型承诺将在何处兑现",
)
STAGE_FIELDS = ("阶段目标", "主冲突", "阶段末变化", "下一阶段压力")
PLACEHOLDERS = {"待定", "未定", "TODO", "TBD", "角色名", "未命名小说"}
PAYOFF_STATUS = {"fulfilled", "deferred"}


def filled(value: object) -> bool:
    return nonempty(value) and value.strip() not in PLACEHOLDERS


def missing_fields(path: Path, labels: tuple[str, ...], errors: list[str]) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"cannot read plan {path}: {exc}")
        return
    for label in labels:
        pattern = re.compile(rf"^\s*(?:[-*]|\d+[.)])\s*{re.escape(label)}[：:]\s*(.*?)\s*$")
        if not any((match := pattern.match(line)) and filled(match.group(1)) for line in lines):
            errors.append(f"{path.name}: fill {label}")


def check_payoff(card: dict, label: str, errors: list[str]) -> None:
    """Validate the optional per-chapter genre payoff record."""
    payoff = card.get("payoff")
    if payoff is None:
        return
    if not isinstance(payoff, dict):
        errors.append(f"{label}: payoff must be a mapping")
        return
    if not filled(payoff.get("expected")):
        errors.append(f"{label}: fill payoff.expected")
    status = payoff.get("status")
    if status not in PAYOFF_STATUS:
        errors.append(f"{label}: payoff.status must be one of {sorted(PAYOFF_STATUS)}")
    if status == "deferred" and not filled(payoff.get("reason")):
        errors.append(f"{label}: fill payoff.reason when payoff.status is deferred")


def numbered_path(directory: Path, prefix: str, number: int, extensions: tuple[str, ...]) -> Path | None:
    for extension in extensions:
        for stem in (f"{prefix}-{number:04d}", f"{prefix}-{number:02d}", f"{prefix}-{number}", f"{number:04d}", f"{number:02d}", str(number)):
            candidate = directory / f"{stem}.{extension}"
            if candidate.is_file():
                return candidate
    return None


def character_ids(project: Path) -> set[str]:
    directory = project / "characters"
    return {path.stem for extension in ("yaml", "yml", "md") for path in directory.glob(f"*.{extension}")}


def check_card(project: Path, novel: dict, number: int, allowed_povs: set[str], characters: set[str], errors: list[str]) -> int:
    path = numbered_path(project / "control-cards", "chapter", number, ("yaml", "yml"))
    if path is None:
        errors.append(f"missing planned control card for chapter {number}")
        return 0
    try:
        card = read_yaml(path)
    except (OSError, ProjectYAMLError) as exc:
        errors.append(str(exc))
        return 0
    if not isinstance(card, dict):
        errors.append(f"{path.name}: root must be a mapping")
        return 0
    if card.get("chapter") != number:
        errors.append(f"{path.name}: chapter must be {number}")
    for field in ("goal", "conflict"):
        if not filled(card.get(field)):
            errors.append(f"{path.name}: fill {field}")
    change = card.get("change")
    if not isinstance(change, dict) or not any(filled(change.get(name)) for name in ("plot", "character", "relationship")):
        errors.append(f"{path.name}: fill at least one change")
    viewpoint = card.get("viewpoint")
    if not filled(viewpoint) or viewpoint not in characters or (allowed_povs and viewpoint not in allowed_povs):
        errors.append(f"{path.name}: viewpoint must name an allowed character file")
    target = card.get("target_words")
    if not integer(target, 1):
        errors.append(f"{path.name}: target_words must be positive")
        target = 0
    refs = card.get("context", {})
    if not isinstance(refs, dict):
        errors.append(f"{path.name}: context must be a mapping")
    else:
        listed = refs.get("characters", [])
        if not isinstance(listed, list) or any(not nonempty(item) or item not in characters for item in listed):
            errors.append(f"{path.name}: context.characters must reference character files")
        worlds = refs.get("world", [])
        if not isinstance(worlds, list) or any(not nonempty(item) or not world_exists(project, item) for item in worlds):
            errors.append(f"{path.name}: context.world must reference files inside world/")
    try:
        module_paths(novel, card)
    except ValueError as exc:
        errors.append(f"{path.name}: {exc}")
    check_payoff(card, path.name, errors)
    return target


def world_exists(project: Path, name: str) -> bool:
    root = (project / "world").resolve()
    candidate = (root / name).resolve()
    if not candidate.is_relative_to(root):
        return False
    return any(path.is_file() for path in (candidate, candidate.with_suffix(".md"), candidate.with_suffix(".yaml"), candidate.with_suffix(".yml")))


def check_plan(project: Path, mode: str, chapter: int | None = None, state_path: Path | None = None) -> list[str]:
    """Check book, serial, or next-chapter readiness without judging prose quality."""
    if mode not in {"book", "serial", "chapter"}:
        raise ValueError(f"unknown planning mode: {mode}")
    errors: list[str] = []
    try:
        novel = read_yaml(project / "novel.yaml")
        state = read_json(state_path or project / "state" / "state.json")
    except (OSError, ValueError, ProjectYAMLError) as exc:
        return [str(exc)]
    if not isinstance(novel, dict):
        return ["novel.yaml must be a mapping"]
    if novel.get("schema_version") != 1:
        errors.append("novel.yaml schema_version must be 1")
    errors.extend(validate_state(state))
    if errors:
        return errors
    if not filled(novel.get("title")):
        errors.append("novel.yaml: fill title")
    genre = novel.get("genre")
    if not isinstance(genre, dict) or not filled(genre.get("primary")):
        errors.append("novel.yaml: fill genre.primary")
    narration = novel.get("narration")
    povs = narration.get("viewpoint_characters") if isinstance(narration, dict) else None
    if not isinstance(povs, list) or not povs or any(not nonempty(item) for item in povs):
        errors.append("novel.yaml: set narration.viewpoint_characters")
        povs = []
    characters = character_ids(project)
    for pov in povs:
        if pov not in characters:
            errors.append(f"missing viewpoint character file: {pov}")
            continue
        character_path = next((project / "characters" / f"{pov}.{ext}" for ext in ("yaml", "yml") if (project / "characters" / f"{pov}.{ext}").is_file()), None)
        if character_path is not None:
            try:
                character = read_yaml(character_path)
            except (OSError, ProjectYAMLError) as exc:
                errors.append(str(exc))
                continue
            core = character.get("core") if isinstance(character, dict) else None
            if not isinstance(character, dict) or character.get("id") != pov or not filled(character.get("name")) or not isinstance(core, dict) or not filled(core.get("desire")) or not filled(core.get("fear")):
                errors.append(f"{character_path.name}: fill id, name, core.desire and core.fear")

    master = project / "outline" / "master.md"
    missing_fields(master, BOOK_FIELDS if mode == "book" else SERIAL_FIELDS, errors)
    current = state["project"]["current_chapter"]
    next_chapter = chapter if chapter is not None else current + 1
    if next_chapter != current + 1:
        errors.append(f"next chapter must be {current + 1}")
        return errors
    length = novel.get("length") if isinstance(novel.get("length"), dict) else {}
    planned_count = length.get("target_chapters")
    if integer(planned_count, 1) and next_chapter > planned_count:
        errors.append(f"next chapter {next_chapter} exceeds target_chapters={planned_count}")

    if mode == "book":
        target_words = length.get("target_words")
        if not integer(planned_count, 1) or not integer(target_words, 1):
            errors.append("book preflight needs positive length.target_chapters and length.target_words")
            check_card(project, novel, next_chapter, set(povs), characters, errors)
            return errors
        budget = sum(check_card(project, novel, number, set(povs), characters, errors) for number in range(1, planned_count + 1))
        if budget < target_words * 0.9:
            errors.append(f"planned chapter word budget {budget} is below 90% of target_words={target_words}")
    else:
        check_card(project, novel, next_chapter, set(povs), characters, errors)
        if mode == "serial":
            volume = state["project"]["current_volume"]
            stage = numbered_path(project / "outline" / "volumes", "volume", volume, ("md",))
            if stage is None:
                errors.append(f"missing current stage outline: outline/volumes/volume-{volume:02d}.md")
            else:
                missing_fields(stage, STAGE_FIELDS, errors)
    return errors
