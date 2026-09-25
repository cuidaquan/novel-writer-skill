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
PAYOFF_STATUS = {"fulfilled", "deferred", "dropped"}
ENDING_MODES = {"hook", "reversal", "emotional-beat", "resolution"}
STYLE_OVERRIDE_KEYS = {
    "tone",
    "pov_distance",
    "sentence_length",
    "rhythm",
    "dialogue_density",
    "exposition_density",
    "description_density",
    "sensory_detail",
    "interiority",
    "metaphor_density",
    "humor",
    "ending_mode",
    "violence",
}


BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s*")
EMPHASIS = "*_`~ \t"


def tidy(text: str) -> str:
    """Drop list and markdown emphasis decoration so labels compare literally."""
    return text.strip().strip(EMPHASIS).strip()


def filled(value: object) -> bool:
    return nonempty(value) and tidy(value) not in PLACEHOLDERS


def plan_entry(line: str) -> tuple[str, str] | None:
    """Split a `label：value` plan line, tolerating bullets and **emphasis**."""
    text = BULLET.sub("", line, count=1)
    for index, char in enumerate(text):
        if char in "：:":
            return tidy(text[:index]), tidy(text[index + 1 :])
    return None


def missing_fields(path: Path, labels: tuple[str, ...], errors: list[str]) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        errors.append(f"cannot read plan {path}: {exc}")
        return
    found: dict[str, str] = {}
    for line in lines:
        entry = plan_entry(line)
        if entry is not None and entry[0] and entry[0] not in found:
            found[entry[0]] = entry[1]
    for label in labels:
        if not filled(found.get(label)):
            errors.append(f"{path.name}: fill {label}")


ADULT_AUDIENCES = {"adult", "mature", "explicit"}


def declared_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def boundary_errors(novel: dict) -> list[str]:
    """Validate the fields that bound what the book may contain.

    A malformed `content_limits` or `style.forbidden` would silently drop the
    only written record of the project's content boundary.
    """
    errors: list[str] = []
    audience = novel.get("audience")
    if audience is not None and not (isinstance(audience, str) and audience.strip()):
        errors.append("novel.yaml audience must be a non-empty string")
    if "content_limits" in novel and not declared_string_list(novel.get("content_limits")):
        errors.append("novel.yaml content_limits must be a list of non-empty strings")
    style = novel.get("style")
    if isinstance(style, dict) and "forbidden" in style and not declared_string_list(style.get("forbidden")):
        errors.append("novel.yaml style.forbidden must be a list of non-empty strings")
    return errors


def boundary_lines(novel: dict) -> list[str]:
    """Render the declared content boundary for a chapter context bundle."""
    audience = novel.get("audience")
    audience = audience.strip() if isinstance(audience, str) and audience.strip() else "unspecified"
    limits = novel.get("content_limits")
    limits = [item.strip() for item in limits if isinstance(item, str) and item.strip()] if isinstance(limits, list) else []
    if limits:
        limit_note = "; ".join(limits)
    elif audience.lower() in ADULT_AUDIENCES:
        limit_note = "NONE DECLARED for an adult-audience project; declare content_limits in novel.yaml before drafting"
    else:
        limit_note = "none declared"
    lines = [f"- Audience: {audience}", f"- Content limits: {limit_note}"]
    style = novel.get("style")
    forbidden = style.get("forbidden") if isinstance(style, dict) else None
    forbidden = [item.strip() for item in forbidden if isinstance(item, str) and item.strip()] if isinstance(forbidden, list) else []
    if forbidden:
        lines.append("- Style forbidden: " + "; ".join(forbidden))
    return lines


def check_card_fields(card: dict, label: str, errors: list[str]) -> None:
    """Validate the card fields whose shape is objectively checkable.

    Semantic fulfilment (whether a scene or required fact really landed in the
    prose) stays an author judgement and is deliberately not checked here.
    """
    title = card.get("title")
    if title is not None and not isinstance(title, str):
        errors.append(f"{label}: title must be a string")
    for field in ("scenes", "required_facts", "forbidden"):
        value = card.get(field)
        if value is None:
            continue
        if not isinstance(value, list) or any(not nonempty(item) for item in value):
            errors.append(f"{label}: {field} must be a list of non-empty strings")
    ending = card.get("ending")
    if ending is not None:
        if not isinstance(ending, dict):
            errors.append(f"{label}: ending must be a mapping")
        else:
            mode = ending.get("mode")
            if mode is not None and not nonempty(mode):
                errors.append(f"{label}: ending.mode must be a non-empty string")
            hook = ending.get("hook")
            if hook is not None and not isinstance(hook, str):
                errors.append(f"{label}: ending.hook must be a string")
    override = card.get("style_override")
    if override is not None:
        if not isinstance(override, dict):
            errors.append(f"{label}: style_override must be a mapping")
        else:
            for key, value in override.items():
                if key not in STYLE_OVERRIDE_KEYS:
                    errors.append(f"{label}: style_override has unknown parameter {key!r}")
                if isinstance(value, str):
                    if not value.strip():
                        errors.append(f"{label}: style_override.{key} must not be empty")
                elif type(value) not in (int, float, bool):
                    errors.append(f"{label}: style_override.{key} must be a string, number or boolean")


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
    identifier = payoff.get("id")
    if identifier is not None and not filled(identifier):
        errors.append(f"{label}: payoff.id must be a non-empty string when present")
    status = payoff.get("status")
    if status not in PAYOFF_STATUS:
        errors.append(f"{label}: payoff.status must be one of {sorted(PAYOFF_STATUS)}")
    if status in {"deferred", "dropped"} and not filled(payoff.get("reason")):
        errors.append(f"{label}: fill payoff.reason when payoff.status is {status}")


def payoff_key(payoff: dict) -> str:
    """Group a promise by payoff.id, falling back to the exact expected text."""
    identifier = payoff.get("id")
    if isinstance(identifier, str) and identifier.strip():
        return f"id:{identifier.strip()}"
    expected = payoff.get("expected")
    if isinstance(expected, str) and expected.strip():
        return f"expected:{expected.strip()}"
    return ""


def payoff_groups(project: Path, current: int) -> list[tuple[str, list[tuple[int, dict]]]]:
    """Return promise groups in first-declaration order: (key, [(chapter, payoff)])."""
    groups: dict[str, list[tuple[int, dict]]] = {}
    for number in range(1, current + 1):
        path = numbered_path(project / "control-cards", "chapter", number, ("yaml", "yml"))
        if path is None:
            continue
        try:
            card = read_yaml(path)
        except (OSError, ProjectYAMLError):
            continue
        payoff = card.get("payoff") if isinstance(card, dict) else None
        if not isinstance(payoff, dict):
            continue
        key = payoff_key(payoff)
        if not key:
            continue
        groups.setdefault(key, []).append((number, payoff))
    return [(key, entries) for key, entries in sorted(groups.items(), key=lambda item: item[1][0][0])]


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
    check_card_fields(card, path.name, errors)
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
    errors.extend(boundary_errors(novel))
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
        if current == planned_count:
            errors.append(
                f"all {planned_count} planned chapters are committed, so there is no next chapter to preflight; "
                "run project_check.py --complete for the finished book"
            )
        else:
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
