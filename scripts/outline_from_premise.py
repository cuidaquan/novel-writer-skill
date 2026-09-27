#!/usr/bin/env python3
"""Turn a locked premise into the story skeleton: outline, cards, characters.

The premise already decides the shape of the book — how many chapters, where the
relationship turns, when the reader learns what, who the cast is. This script
writes that shape out as the artifacts the rest of the workflow reads, marking
everything the decisions do not determine as 待定 instead of inventing it.

It refuses to run when the premise is not settled (the same findings
`brief_check.py` prints), when it is not locked, or when it would overwrite
existing files without --force. Exit codes: 0 written, 1 refused, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from brief_check import check_against_novel, check_consistency, check_recorded, check_required
from premise import field_value, is_unset, load_premise, premise_path

TODO = "待定"
PLACEHOLDER = "（待定）"


TEMPLATES = Path(__file__).resolve().parents[1] / "assets" / "templates"


def untouched_template(path: Path, chapter: int | None = None) -> bool:
    """True when the file is still the shipped scaffold, so writing over it loses nothing."""
    template = TEMPLATES / ("outline.md" if path.name == "master.md" else "chapter-card.yaml")
    if not template.is_file() or not path.is_file():
        return False
    expected = template.read_text(encoding="utf-8")
    if chapter is not None:
        expected = expected.replace("chapter: 1", f"chapter: {chapter}", 1)
    return path.read_text(encoding="utf-8").strip() == expected.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render outline/master.md, one control card per planned chapter and one character "
            "file per cast member from a locked premise.yaml. Known decisions are prefilled; "
            "everything else is marked 待定 and listed at the end for the author."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing outline, cards or character files")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be written without writing it")
    parser.add_argument("--words-per-chapter", type=int, default=0,
                        help="Target words per chapter; defaults to a round split of the premise target")
    parser.add_argument("--prune", action="store_true",
                        help="Delete cards and character files left over from an earlier plan when they carry no author content")
    return parser.parse_args()


def quote(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def text_of(value: Any, default: str = TODO) -> str:
    return default if is_unset(value) else str(value)


def line(key: str, value: Any, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(value, bool):
        return f"{prefix}{key}: {'true' if value else 'false'}"
    if isinstance(value, int):
        return f"{prefix}{key}: {value}"
    return f"{prefix}{key}: {quote(value)}"


def block(key: str, values: list[str], indent: int = 0) -> list[str]:
    prefix = " " * indent
    if not values:
        return [f"{prefix}{key}: []"]
    return [f"{prefix}{key}:"] + [f"{prefix}  - {quote(item)}" for item in values]


def notes_block(key: str, values: list[str], indent: int = 0) -> list[str]:
    prefix = " " * indent
    if not values:
        return [f"{prefix}{key}: []"]
    return [f"{prefix}{key}:"] + [f"{prefix}  - {quote(item)}" for item in values]


class Plan:
    """Everything the premise determines, in the shape the artifacts need."""

    def __init__(self, premise: dict[str, Any], words_per_chapter: int) -> None:
        self.premise = premise
        self.chapters = int(field_value(premise, "length.target_chapters") or 0)
        self.target_words = int(field_value(premise, "length.target_words") or 0)
        self.words_per_chapter = words_per_chapter
        self.turns = [turn for turn in (field_value(premise, "arc.turns") or []) if isinstance(turn, dict)]
        self.turns_by_chapter = {int(turn.get("chapter")): turn for turn in self.turns if isinstance(turn.get("chapter"), int)}
        self.revelations = [item for item in (field_value(premise, "revelations") or []) if isinstance(item, dict)]
        self.cast = [person for person in (field_value(premise, "cast") or []) if isinstance(person, dict)]
        self.viewpoint = [str(item) for item in (field_value(premise, "narration.viewpoint_characters") or [])]
        self.protagonist = next((person for person in self.cast if person.get("role") == "protagonist"), {})
        self.must_avoid = [str(item) for item in (field_value(premise, "must_avoid") or [])]
        self.must_include = [str(item) for item in (field_value(premise, "must_include") or [])]
        self.unresolved = [str(item) for item in (premise.get("unresolved") or [])]
        self.agent_added = [str(item) for item in (premise.get("agent_added") or [])]
        self.ending_mode = text_of(field_value(premise, "style.ending_mode"), "emotional-beat")

    def reveals_at(self, chapter: int) -> list[str]:
        found = []
        for index, item in enumerate(self.revelations, 1):
            revealed = item.get("reader_known_at")
            if isinstance(revealed, int) and revealed == chapter:
                found.append(str(item.get("id") or f"r-{index}"))
        return found

    def words_for(self, chapter: int) -> int:
        if self.words_per_chapter:
            return self.words_per_chapter
        if not self.chapters or not self.target_words:
            return 0
        base = self.target_words // self.chapters
        # Spread the rounding remainder over the first chapters instead of losing it.
        remainder = self.target_words - base * self.chapters
        return base + (1 if chapter <= remainder else 0)

    def threads(self) -> list[str]:
        return []


def render_outline(plan: Plan) -> str:
    premise = plan.premise
    protagonist = plan.protagonist
    promises = [str(item) for item in (field_value(premise, "frame.promises") or [])]
    lines = [
        "# 总纲",
        "",
        "> 由 `premise.yaml` 生成：立项书已决定的部分已填入，其余标为「" + TODO + "」。",
        "> 逐条填完后运行 `python3 scripts/project_check.py . --preflight book`。",
        "",
        "## 故事承诺",
        "",
        f"- 主角：{text_of(protagonist.get('id'))}（{text_of(protagonist.get('role'))}）",
        f"- 核心欲望：{text_of(protagonist.get('want'))}",
        f"- 最大阻力：{text_of(protagonist.get('flaw'))}",
        f"- 失败代价：{TODO}",
        f"- 核心读者回报：{promises[0] if promises else TODO}",
        "",
        "## 关键转折",
        "",
        f"1. 起始失衡：{TODO}",
        f"2. 第一次不可逆选择：{TODO}",
        f"3. 中段认知/局势变化：{TODO}",
        f"4. 最严重失败或代价：{TODO}",
        f"5. 终局选择：{TODO}",
        f"6. 结局状态：{text_of(protagonist.get('change'))}",
        "",
        "## 跨章弧线",
        "",
        f"- 主角从什么状态变到什么状态：{text_of(protagonist.get('flaw'))} → {text_of(protagonist.get('change'))}",
        f"- 关键关系从什么状态变到什么状态：{TODO}",
        f"- 主类型承诺将在何处兑现：{TODO}",
        "",
        "## 章节节奏",
        "",
        "| 章 | 变化节拍 | 揭示 | 章末 | 目标字数 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for chapter in range(1, plan.chapters + 1):
        turn = plan.turns_by_chapter.get(chapter)
        beat = text_of(turn.get("change")) if turn else "—"
        reveals = "、".join(plan.reveals_at(chapter)) or "—"
        lines.append(f"| {chapter} | {beat} | {reveals} | {TODO} | {plan.words_for(chapter) or TODO} |")
    lines += [
        "",
        "## 揭示时间表",
        "",
    ]
    if plan.revelations:
        lines += ["| 真相 | 读者在第几章知道 | 谁知道 |", "| --- | --- | --- |"]
        for index, item in enumerate(plan.revelations, 1):
            known_by = "、".join(str(name) for name in (item.get("known_by") or [])) or "—"
            lines.append(f"| {item.get('id') or f'r-{index}'}：{text_of(item.get('truth'))} | "
                         f"{text_of(item.get('reader_known_at'))} | {known_by} |")
    else:
        lines.append(f"- {TODO}")
    lines += [
        "",
        "## 全书禁区",
        "",
    ]
    lines += [f"- {item}" for item in plan.must_avoid] or [f"- {TODO}"]
    lines += ["", "## 必须出现", ""]
    lines += [f"- {item}" for item in plan.must_include] or [f"- {TODO}"]
    lines += ["", "## 未决问题", ""]
    lines += [f"- {item}" for item in plan.unresolved + plan.agent_added] or ["-（无）"]
    return "\n".join(lines) + "\n"


def render_card(plan: Plan, chapter: int) -> str:
    turn = plan.turns_by_chapter.get(chapter)
    viewpoint = plan.viewpoint[0] if plan.viewpoint else TODO
    characters = [str(person.get("id")) for person in plan.cast if person.get("id")]
    lines = [
        f"chapter: {chapter}",
        line("title", ""),
        line("viewpoint", viewpoint),
        line("target_words", plan.words_for(chapter) or 0),
        line("goal", ""),
        line("conflict", ""),
        "context:",
        *block("characters", characters, 2),
        "  world: []",
        "scenes: []",
        "change:",
        line("plot", text_of(turn.get("change")) if turn else "", 2),
        line("character", "", 2),
        line("relationship", "", 2),
        "threads:",
        "  advance: []",
        "  touch: []",
        "foreshadowing:",
        "  plant: []",
        "  advance: []",
        "  pay_off: []",
        "revelations:",
        "  touch: []",
        *block("reveal", plan.reveals_at(chapter), 2),
        "style_modules: []",
        "required_facts: []",
        *block("forbidden", plan.must_avoid),
        "ending:",
        line("mode", plan.ending_mode, 2),
        line("hook", "", 2),
    ]
    if turn:
        lines += [
            "# 这一章是立项书里的变化节拍：把 change.plot 拆成 plot / character / relationship 三条。",
        ]
    return "\n".join(lines) + "\n"


def render_character(plan: Plan, person: dict[str, Any]) -> str:
    identifier = text_of(person.get("id"), "character-id")
    lines = [
        line("id", identifier),
        line("name", text_of(person.get("name"), "")),
        line("role", text_of(person.get("role"), "supporting")),
        "core:",
        line("desire", text_of(person.get("want"), ""), 2),
        line("fear", text_of(person.get("flaw"), ""), 2),
        line("need", "", 2),
        line("secret", "", 2),
        line("contradiction", "", 2),
        "voice:",
        line("speech_style", "", 2),
        *block("avoids", [str(item) for item in (person.get("avoid") or [])], 2),
        "relationships: {}",
        line("arc", text_of(person.get("change"), ""), 0),
        "notes: []",
    ]
    return "\n".join(lines) + "\n"


def stale_files(project: Path, plan: Plan) -> list[Path]:
    """Files from an earlier plan: cards beyond the chapter count, characters no longer cast."""
    stale = []
    planned = set(range(1, plan.chapters + 1))
    for path in sorted((project / "control-cards").glob("chapter-*.yaml")):
        match = re.fullmatch(r"chapter-(\d+)", path.stem)
        if match and int(match.group(1)) not in planned:
            stale.append(path)
    cast = {str(person.get("id")) for person in plan.cast if person.get("id")}
    for path in sorted((project / "characters").glob("*.yaml")):
        if path.stem not in cast:
            stale.append(path)
    return stale


def is_scaffold_payload(project: Path, path: Path) -> bool:
    """True when a leftover file holds nothing the author wrote.

    Leftovers are judged by field, not by bytes: the generator itself filled
    viewpoint, target words, the arc beat, reveals and the global forbidden list,
    so only the fields a human writes count as content here.
    """
    from project_yaml import ProjectYAMLError, read_yaml

    try:
        data = read_yaml(path)
    except (OSError, ProjectYAMLError):
        return False
    if not isinstance(data, dict):
        return False

    if path.parent.name == "characters":
        core = data.get("core") if isinstance(data.get("core"), dict) else {}
        voice = data.get("voice") if isinstance(data.get("voice"), dict) else {}
        authored = [
            core.get("need"), core.get("secret"), core.get("contradiction"),
            voice.get("speech_style"), data.get("relationships"), data.get("notes"),
        ]
        return not any(item for item in authored)

    change = data.get("change") if isinstance(data.get("change"), dict) else {}
    ending = data.get("ending") if isinstance(data.get("ending"), dict) else {}
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    revelations = data.get("revelations") if isinstance(data.get("revelations"), dict) else {}
    authored = [
        data.get("title"), data.get("goal"), data.get("conflict"),
        data.get("scenes"), data.get("required_facts"),
        change.get("character"), change.get("relationship"),
        ending.get("hook"), context.get("world"), revelations.get("touch"),
    ]
    for group in ("threads", "foreshadowing"):
        value = data.get(group)
        if isinstance(value, dict):
            authored.extend(value.values())
    return not any(item for item in authored)


def pending_items(plan: Plan) -> list[str]:
    """What the author still has to decide, grouped for the closing report."""
    pending: list[str] = []
    if not plan.turns:
        pending.append("总纲：一次变化节拍都没写（arc.turns 为空）")
    missing_beats = [number for number in range(1, plan.chapters + 1) if number not in plan.turns_by_chapter]
    if missing_beats and plan.turns:
        pending.append("章卡：这些章没有变化节拍，需要自己定：" + "、".join(str(item) for item in missing_beats))
    pending += [
        "总纲：关键转折六条（起始失衡、第一次不可逆选择、中段变化、最严重代价、终局选择）——只有结局状态是从立项书推出来的",
        "总纲：主类型承诺在哪一章兑现；每条剧情线的收束章",
        "人物卡：voice.speech_style 与 relationships 需要填写（名字若已在立项书里写就会自动填入）",
        "章卡：每章的 goal / conflict，以及 change 里至少一条（plot / character / relationship）——门禁要求",
        "章卡：每章的 scenes / required_facts / 章末 hook",
        "章卡：threads 与 foreshadowing 的 id（立项书不含线索编号）",
    ]
    if plan.must_include:
        pending.append("把「必须出现」的元素分配到具体章：" + "、".join(plan.must_include))
    if plan.unresolved:
        pending.append("确认有意悬置的项不会被读者当成没写完：" + "、".join(plan.unresolved))
    return pending


def main() -> int:
    args = parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    if args.words_per_chapter < 0:
        print("ERROR: --words-per-chapter cannot be negative")
        return 2

    premise = load_premise(project)
    if premise is None:
        print(f"ERROR: {premise_path(project)} not found; run the intake first (references/premise-proposal.md)")
        return 2
    if not premise:
        print(f"ERROR: {premise_path(project)} is empty")
        return 2

    findings: list[tuple[str, str, str]] = []
    check_required(premise, findings)
    check_consistency(premise, findings)
    check_against_novel(project, premise, findings)
    check_recorded(project, premise, findings)
    blocking = [f"{label}: {message}" for level, label, message in findings if level == "BLOCK"]
    if blocking:
        print("ERROR: the premise is not settled; fix these first (python3 scripts/brief_check.py .):")
        for item in blocking:
            print(f"  - {item}")
        return 1
    if premise.get("status") != "locked":
        print('ERROR: premise.yaml is still draft; settle the decisions and record with --lock '
              '(python3 scripts/premise_log.py . --record "确认锁定" --input "<你的原话>" --lock)')
        return 1

    plan = Plan(premise, args.words_per_chapter)
    if plan.chapters < 1:
        print("ERROR: length.target_chapters must be at least 1")
        return 2

    outline = project / "outline" / "master.md"
    cards = {chapter: project / "control-cards" / f"chapter-{chapter:04d}.yaml"
             for chapter in range(1, plan.chapters + 1)}
    characters = {}
    for person in plan.cast:
        identifier = person.get("id")
        if identifier:
            characters[str(identifier)] = project / "characters" / f"{identifier}.yaml"
    targets = [outline, *cards.values(), *characters.values()]
    chapters_by_path = {path: chapter for chapter, path in cards.items()}
    # Rendering first lets the overwrite rule be exact: a file is safe to
    # replace when it is the untouched template, or when it is byte-identical to
    # what this run would write (so re-running stays idempotent), and it always
    # asks before discarding anything the author has since edited.
    outputs: dict[Path, str] = {outline: render_outline(plan)}
    for chapter, path in cards.items():
        outputs[path] = render_card(plan, chapter)
    for identifier, path in characters.items():
        person = next(item for item in plan.cast if str(item.get("id")) == identifier)
        outputs[path] = render_character(plan, person)

    authored = [
        path for path, text in outputs.items()
        if path.is_file() and path.read_text(encoding="utf-8") != text
        and not untouched_template(path, chapters_by_path.get(path))
    ]
    if authored and not args.force:
        print("ERROR: these files already contain your own edits; pass --force to overwrite them:")
        for path in authored:
            print(f"  - {path.relative_to(project)}")
        return 1

    if args.dry_run:
        print(f"# dry run: would write {len(targets)} file(s)")
        print(f"- outline/master.md  ({plan.chapters} 章节奏表，{len(plan.revelations)} 条揭示)")
        for chapter in range(1, plan.chapters + 1):
            turn = plan.turns_by_chapter.get(chapter)
            mark = "变化节拍" if turn else "空章卡"
            print(f"- control-cards/chapter-{chapter:04d}.yaml  ({mark}，目标 {plan.words_for(chapter)} 字)")
        for identifier in characters:
            print(f"- characters/{identifier}.yaml")
        return 0

    outline.parent.mkdir(parents=True, exist_ok=True)
    (project / "control-cards").mkdir(parents=True, exist_ok=True)
    (project / "characters").mkdir(parents=True, exist_ok=True)
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    stale = stale_files(project, plan)
    prunable = [path for path in stale if path.suffix in (".yaml", ".yml") and is_scaffold_payload(project, path)]
    kept = [path for path in stale if path not in prunable]
    if stale:
        removable = [path for path in prunable if args.prune]
        for path in removable:
            path.unlink()
        for path in prunable:
            if path not in removable:
                kept.append(path)

    print(f"wrote {len(targets)} file(s) from premise.yaml (version {premise.get('version', '?')}, locked)")
    print(f"- outline/master.md（{plan.chapters} 章节奏表）")
    print(f"- control-cards/chapter-0001.yaml … chapter-{plan.chapters:04d}.yaml")
    if characters:
        print("- characters/：" + "、".join(characters))
    if stale:
        if args.prune and prunable:
            print("\n## 已清掉的旧计划残留（没有作者内容）")
            for path in prunable:
                print(f"- {path.relative_to(project)}")
        if kept:
            print("\n## 旧计划的残留文件（请手工处理：删除或改回计划内）")
            for path in kept:
                print(f"- {path.relative_to(project)}")
            print("  目录里没有内容的旧章卡可以用 --prune 自动清掉。")

    print("\n## 还需要你决定的（按优先级）")
    for item in pending_items(plan):
        print(f"- {item}")
    print("\nnext:")
    print("  1. 先把 outline/master.md 的「" + TODO + "」填掉，它决定每章要发生什么")
    print("  2. 逐章填章卡：goal / conflict / scenes / required_facts / ending.hook")
    print("  3. python3 scripts/project_check.py . --preflight book")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
