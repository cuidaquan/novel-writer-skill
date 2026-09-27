#!/usr/bin/env python3
"""Initialize a novel project from the skill's bundled templates."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from brief_check import check_consistency, check_required
from premise import field_value, is_unset, tier_limit_lines
from project_yaml import ProjectYAMLError, read_yaml

SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL_ROOT / "assets" / "templates"

NOVEL_DEFAULTS = {
    "language": "zh-CN",
    "pov_distance": "close",
    "sentence_length": "short-to-medium",
    "dialogue_density": "high",
    "exposition_density": "low",
    "description_density": "medium",
    "sensory_detail": "high",
    "interiority": "direct",
    "metaphor_density": "low",
    "humor": "restrained",
    "rhythm": "场景切换干脆",
}


def _line(key: str, value: Any, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(value, bool):
        return f"{prefix}{key}: {'true' if value else 'false'}"
    if isinstance(value, int):
        return f"{prefix}{key}: {value}"
    return f"{prefix}{key}: {json.dumps(str(value), ensure_ascii=False)}"


def _list(key: str, values: list[Any], indent: int = 0) -> list[str]:
    prefix = " " * indent
    if not values:
        return [f"{prefix}{key}: []"]
    lines = [f"{prefix}{key}:"]
    for value in values:
        lines.append(f"{prefix}  - {json.dumps(str(value), ensure_ascii=False)}")
    return lines


def render_novel_yaml(premise: dict[str, Any]) -> str:
    """Render novel.yaml from the settled decisions, so config and premise cannot drift."""
    def value(dotted: str, default: Any = "") -> Any:
        found = field_value(premise, dotted)
        return default if is_unset(found) else found

    def text(dotted: str, default: str = "") -> str:
        return str(value(dotted, default))

    tier = text("intimacy.tier")
    lines = [
        "schema_version: 1",
        _line("title", text("project", "未命名小说")),
        _line("language", NOVEL_DEFAULTS["language"]),
        _line("audience", text("genre.audience", "general")),
        "",
        "genre:",
        _line("primary", text("genre.primary"), 2),
    ]
    lines += _list("secondary", [str(item) for item in (field_value(premise, "genre.secondary") or [])], 2)
    lines += [
        "",
        "length:",
        _line("target_words", int(value("length.target_words", 0)), 2),
        _line("target_chapters", int(value("length.target_chapters", 0)), 2),
        "",
        "narration:",
        _line("pov", text("narration.pov"), 2),
        _line("tense", text("narration.tense", "past"), 2),
    ]
    lines += _list("viewpoint_characters",
                   [str(item) for item in (field_value(premise, "narration.viewpoint_characters") or [])], 2)
    lines += [
        "",
        "style:",
        _line("tone", text("style.tone"), 2),
        _line("pov_distance", NOVEL_DEFAULTS["pov_distance"], 2),
        _line("sentence_length", text("style.sentence_length", NOVEL_DEFAULTS["sentence_length"]), 2),
        _line("rhythm", text("style.rhythm", NOVEL_DEFAULTS["rhythm"]), 2),
        _line("dialogue_density", text("style.dialogue_density", NOVEL_DEFAULTS["dialogue_density"]), 2),
        _line("exposition_density", text("style.exposition_density", NOVEL_DEFAULTS["exposition_density"]), 2),
        _line("description_density", text("style.description_density", NOVEL_DEFAULTS["description_density"]), 2),
        _line("sensory_detail", text("style.sensory_detail", NOVEL_DEFAULTS["sensory_detail"]), 2),
        _line("interiority", NOVEL_DEFAULTS["interiority"], 2),
        _line("metaphor_density", text("style.metaphor_density", NOVEL_DEFAULTS["metaphor_density"]), 2),
        _line("humor", text("style.humor", NOVEL_DEFAULTS["humor"]), 2),
        _line("ending_mode", text("style.ending_mode"), 2),
    ]
    if tier in ("sensual", "frank"):
        lines += ["  modules:", "    - intimacy"]
    lines += _list("forbidden", [str(item) for item in (field_value(premise, "style.forbidden") or [])], 2)

    limits = ["所有出场人物均为成年人；亲密接触明确自愿、可随时中止"]
    for limit in tier_limit_lines(tier) + [str(item) for item in (field_value(premise, "intimacy.hard_limits") or [])]:
        # 同一条边界可能既来自分级默认写法又来自立项书，按包含关系去重
        if any(limit in existing or existing in limit for existing in limits):
            continue
        limits.append(limit)
    lines += [""]
    lines += _list("content_limits", limits)
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a novel project")
    parser.add_argument("path", type=Path, help="Destination project directory")
    parser.add_argument("--title", default="", help="Defaults to the premise's project name when --from-premise is used")
    parser.add_argument("--force", action="store_true", help="Allow an existing empty directory")
    parser.add_argument("--from-premise", type=Path, metavar="PREMISE",
                        help="Generate novel.yaml from a settled premise.yaml (copied into the project)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = args.path.expanduser().resolve()

    if getattr(args, "from_premise", None):
        # Validate before creating anything: "nothing was initialized" must be true.
        source = args.from_premise.expanduser().resolve()
        if not source.is_file():
            print(f"ERROR: premise file not found: {source}")
            return 2
        try:
            checked = read_yaml(source)
        except ProjectYAMLError as error:
            print(f"ERROR: {error}")
            return 2
        if not isinstance(checked, dict) or not checked:
            print(f"ERROR: {source} is not a premise mapping")
            return 2
        findings: list[tuple[str, str, str]] = []
        check_required(checked, findings)
        check_consistency(checked, findings)
        blocking = [message for level, _label, message in findings if level == "BLOCK"]
        if blocking:
            print("ERROR: the premise is not settled yet:")
            for message in blocking:
                print(f"  - {message}")
            print("finish the intake (references/premise-proposal.md) first; nothing was initialized")
            return 1
        # The premise names the book; --title still wins when given explicitly.
        if not args.title:
            args.title = str(checked.get("project") or "未命名小说")

    if target.exists():
        if any(target.iterdir()):
            raise SystemExit(f"Refusing to initialize non-empty directory: {target}")
        if not args.force:
            raise SystemExit("Destination already exists; pass --force only for an empty directory")
    else:
        target.mkdir(parents=True)

    for directory in (
        "outline/volumes",
        "characters",
        "world",
        "chapters",
        "control-cards",
        "state/transactions",
    ):
        (target / directory).mkdir(parents=True, exist_ok=True)

    shutil.copy2(TEMPLATES / "novel.yaml", target / "novel.yaml")
    shutil.copy2(TEMPLATES / "outline.md", target / "outline" / "master.md")
    shutil.copy2(TEMPLATES / "state.json", target / "state" / "state.json")

    state_path = target / "state" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["project"]["title"] = args.title
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target / "state" / "initial.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    novel_path = target / "novel.yaml"
    novel_text = novel_path.read_text(encoding="utf-8")
    yaml_safe_title = json.dumps(args.title, ensure_ascii=False)
    novel_text = novel_text.replace("title: 未命名小说", f"title: {yaml_safe_title}", 1)
    novel_path.write_text(novel_text, encoding="utf-8")

    if args.from_premise:
        source = args.from_premise.expanduser().resolve()
        if not source.is_file():
            print(f"ERROR: premise file not found: {source}")
            return 2
        try:
            premise = read_yaml(source)
        except ProjectYAMLError as error:
            print(f"ERROR: {error}")
            return 2
        if not isinstance(premise, dict) or not premise:
            print(f"ERROR: {source} is not a premise mapping")
            return 2
        shutil.copy2(source, target / "premise.yaml")
        (target / "novel.yaml").write_text(render_novel_yaml(premise), encoding="utf-8")
        print(f"novel.yaml generated from {source.name}")

    print(target)
    if args.from_premise:
        print("next:")
        print(f'  python3 scripts/premise_log.py {target} --record "立项书导入" --author agent')
        print(f"  python3 scripts/brief_check.py {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
