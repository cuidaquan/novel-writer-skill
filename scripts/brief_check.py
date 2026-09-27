#!/usr/bin/env python3
"""Check a locked premise against the project it is supposed to drive.

Findings are split the same way as the chapter review: `BLOCK` means the
project cannot start (or resume) writing, `NOTE` is for the author. Exit code 1
means at least one blocking finding, 2 means a usage or input error.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from premise import (
    DELIVERIES,
    REQUIRED_FIELDS,
    STATUSES,
    TIERS,
    field_value,
    is_unset,
    latest_event,
    load_premise,
    premise_hashes,
    premise_path,
    read_log,
)
from project_yaml import ProjectYAMLError, read_yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate premise.yaml: required decisions are set, they do not contradict each "
            "other, every round is recorded in history/log.jsonl, and novel.yaml still matches "
            "the locked decisions."
        )
    )
    parser.add_argument(
        "project", type=Path,
        help="Novel project directory, or a premise.yaml file to check on its own "
             "(during the intake the project does not exist yet)",
    )
    return parser.parse_args()


def blocking(findings: list[tuple[str, str, str]], label: str, location: str, message: str) -> None:
    findings.append(("BLOCK", label, f"{location}: {message}"))


def note(findings: list[tuple[str, str, str]], label: str, location: str, message: str) -> None:
    findings.append(("NOTE", label, f"{location}: {message}"))


def check_required(premise: dict[str, Any], findings: list[tuple[str, str, str]]) -> None:
    for dotted, label in REQUIRED_FIELDS:
        value = field_value(premise, dotted)
        if is_unset(value):
            blocking(findings, "missing-decision", dotted, f"未决或空：{label}")
    if premise.get("delivery") not in DELIVERIES and not is_unset(premise.get("delivery")):
        blocking(findings, "bad-value", "delivery", f"未知交付形态 {premise.get('delivery')!r}，应为 {'/'.join(DELIVERIES)}")
    if premise.get("status") not in STATUSES and not is_unset(premise.get("status")):
        blocking(findings, "bad-value", "status", f"未知状态 {premise.get('status')!r}，应为 {'/'.join(STATUSES)}")
    tier = field_value(premise, "intimacy.tier")
    if tier and tier not in TIERS:
        blocking(findings, "bad-value", "intimacy.tier", f"未知亲密分级 {tier!r}，应为 {'/'.join(TIERS)}")


def check_consistency(premise: dict[str, Any], findings: list[tuple[str, str, str]]) -> None:
    chapters = field_value(premise, "length.target_chapters")
    words = field_value(premise, "length.target_words")
    tier = field_value(premise, "intimacy.tier")

    if isinstance(chapters, int) and isinstance(words, int):
        if chapters < 1:
            blocking(findings, "contradiction", "length.target_chapters", "章数必须为正")
        elif words < 1000:
            blocking(findings, "contradiction", "length.target_words", "整本字数低于 1000，确认是否笔误")
        elif chapters and words / chapters < 500:
            note(findings, "thin-chapter", "length", f"平均每章只有 {words // chapters} 字，确认是否笔误")

    if tier == "frank" and is_unset(field_value(premise, "intimacy.hard_limits")):
        blocking(findings, "contradiction", "intimacy.hard_limits",
                 "frank 级必须写出硬边界（否则写作时会越界）")

    turns = field_value(premise, "arc.turns") or []
    seen: list[int] = []
    for index, turn in enumerate(turns if isinstance(turns, list) else []):
        chapter = turn.get("chapter") if isinstance(turn, dict) else None
        location = f"arc.turns[{index}].chapter"
        if not isinstance(chapter, int):
            blocking(findings, "bad-value", location, "变化节拍必须写明章号")
            continue
        if isinstance(chapters, int) and not 1 <= chapter <= chapters:
            blocking(findings, "contradiction", location, f"章号 {chapter} 超出计划章数 {chapters}")
        if chapter in seen:
            blocking(findings, "contradiction", location, f"章号 {chapter} 重复")
        if seen and chapter <= seen[-1]:
            blocking(findings, "contradiction", location, f"章节须递增：{seen[-1]} → {chapter}")
        seen.append(chapter)
        if is_unset(turn.get("change")):
            blocking(findings, "missing-decision", f"{location} 的 change", "每个节拍都要写清状态变化")

    cast = field_value(premise, "cast") or []
    identifiers: list[str] = []
    has_protagonist = False
    for index, person in enumerate(cast if isinstance(cast, list) else []):
        if not isinstance(person, dict):
            blocking(findings, "bad-value", f"cast[{index}]", "人物条目必须是映射")
            continue
        identifier = person.get("id")
        if is_unset(identifier):
            blocking(findings, "missing-decision", f"cast[{index}].id", "人物缺少 id")
        elif identifier in identifiers:
            blocking(findings, "contradiction", f"cast[{index}].id", f"id 重复：{identifier}")
        else:
            identifiers.append(str(identifier))
        if person.get("role") == "protagonist":
            has_protagonist = True
            for key in ("want", "flaw", "change"):
                if is_unset(person.get(key)):
                    blocking(findings, "missing-decision", f"cast[{index}].{key}",
                             f"主角必须写明 {key}")
    if cast and not has_protagonist:
        blocking(findings, "missing-decision", "cast", "人物表里没有 role: protagonist 的条目")

    for index, item in enumerate(field_value(premise, "revelations") or []):
        revealed = item.get("reader_known_at") if isinstance(item, dict) else None
        if revealed is None:
            continue
        if not isinstance(revealed, int):
            blocking(findings, "bad-value", f"revelations[{index}].reader_known_at", "必须是章号")
        elif isinstance(chapters, int) and not 1 <= revealed <= chapters:
            blocking(findings, "contradiction", f"revelations[{index}].reader_known_at",
                     f"章号 {revealed} 超出计划章数 {chapters}")

    forbidden = field_value(premise, "style.forbidden")
    if isinstance(forbidden, list) and len(forbidden) == 0:
        blocking(findings, "missing-decision", "style.forbidden", "风格禁区不能为空")

    agent_added = premise.get("agent_added") or []
    if agent_added:
        note(findings, "agent-added", "agent_added",
             f"{len(agent_added)} 条是提案方替你补的，逐条确认或删除")
    unresolved = premise.get("unresolved") or []
    if unresolved:
        note(findings, "unresolved", "unresolved", f"{len(unresolved)} 项有意悬置，确认读者不会被绊住")
    if (premise.get("must_include") or []) and not turns:
        note(findings, "no-home", "must_include", "「必须出现」的清单还没有对应章")


def check_against_novel(project: Path, premise: dict[str, Any], findings: list[tuple[str, str, str]]) -> None:
    path = project / "novel.yaml"
    if not path.is_file():
        return
    novel = read_yaml(path)
    if not isinstance(novel, dict):
        return
    comparisons = (
        ("length.target_chapters", ("length", "target_chapters")),
        ("length.target_words", ("length", "target_words")),
        ("genre.primary", ("genre", "primary")),
        ("genre.audience", ("audience",)),
        ("narration.pov", ("narration", "pov")),
    )
    for premise_field, novel_path in comparisons:
        declared = field_value(premise, premise_field)
        actual = field_value(novel, ".".join(novel_path))
        if is_unset(declared):
            continue
        if str(declared) != str(actual):
            blocking(findings, "novel-drift", f"novel.yaml:{'.'.join(novel_path)}",
                     f"与 premise 不一致：novel={actual!r} premise={declared!r}")

    declared_forbidden = [str(item) for item in (field_value(premise, "style.forbidden") or [])]
    actual_forbidden = [str(item) for item in (field_value(novel, "style.forbidden") or [])]
    for rule in declared_forbidden:
        if rule not in actual_forbidden:
            blocking(findings, "novel-drift", "novel.yaml:style.forbidden",
                     f"premise 的禁区没有写进配置：{rule}")

    hard_limits = [str(item) for item in (field_value(premise, "intimacy.hard_limits") or [])]
    limits = [str(item) for item in (field_value(novel, "content_limits") or [])]
    joined = " ".join(limits)
    for limit in hard_limits:
        if limit not in joined:
            blocking(findings, "novel-drift", "novel.yaml:content_limits",
                     f"premise 的硬边界没有写进配置：{limit}")


def check_recorded(project: Path, premise: dict[str, Any], findings: list[tuple[str, str, str]]) -> None:
    try:
        events = read_log(project)
    except ProjectYAMLError as error:
        blocking(findings, "log-unreadable", str(error), "事件日志无法解析")
        return
    if not events:
        blocking(findings, "unrecorded-round", "history/log.jsonl",
                 "premise 没有任何轮次记录；用 premise_log.py --record 落一条")
        return
    latest = latest_event(events, "premise") or latest_event(events)
    if latest is None:
        blocking(findings, "unrecorded-round", "history/log.jsonl", "日志里没有可用事件")
        return
    recorded = (latest.get("hashes") or {}).get("premise.yaml")
    current = premise_hashes(project)["premise.yaml"]
    if recorded and recorded != current:
        blocking(findings, "unrecorded-round", "premise.yaml",
                 f"已改动但没有对应轮次（记录 {recorded} / 当前 {current}）；先 premise_log.py --record")


def render_standalone(premise_file: Path, premise: dict[str, Any], findings: list[tuple[str, str, str]]) -> str:
    blocking_findings = [item for item in findings if item[0] == "BLOCK"]
    notes = [item for item in findings if item[0] == "NOTE"]
    lines = [
        "# Premise Check (standalone draft): " + str(premise.get("project") or premise_file.stem),
        "",
        f"- Draft: {premise_file}",
        f"- Chapters/words: {field_value(premise, 'length.target_chapters')} / {field_value(premise, 'length.target_words')}",
        "",
        "记录与配置一致性要等项目存在之后才检查；这份只判决策是否写全、是否自相矛盾。",
        "",
        f"## Blocking ({len(blocking_findings)})",
    ]
    lines += [f"- [{label}] {message}" for _, label, message in blocking_findings] or ["(none)"]
    lines += ["", f"## Advisory ({len(notes)})"]
    lines += [f"- [{label}] {message}" for _, label, message in notes] or ["(none)"]
    lines += ["", "## Result"]
    lines.append(
        f"FAIL: {len(blocking_findings)} blocking finding(s); settle them before creating the project."
        if blocking_findings else "PASS (draft): decisions are settled enough to create the project."
    )
    return "\n".join(lines) + "\n"


def render(project: Path, premise: dict[str, Any], findings: list[tuple[str, str, str]]) -> str:
    blocking_findings = [item for item in findings if item[0] == "BLOCK"]
    notes = [item for item in findings if item[0] == "NOTE"]
    status = premise.get("status", "draft")
    lines = [
        "# Premise Check: " + str(premise.get("project") or project.name),
        "",
        f"- Premise: {premise_path(project)}",
        f"- Version: {premise.get('version', '?')} ({status}, {premise.get('rounds', '?')} 轮已记录)",
        f"- Chapters/words: {field_value(premise, 'length.target_chapters')} / {field_value(premise, 'length.target_words')}",
        "",
        f"## Blocking ({len(blocking_findings)})",
    ]
    lines += [f"- [{label}] {message}" for _, label, message in blocking_findings] or ["(none)"]
    lines += ["", f"## Advisory ({len(notes)})"]
    lines += [f"- [{label}] {message}" for _, label, message in notes] or ["(none)"]
    lines += ["", "## Result"]
    if any(label == "novel-drift" for _, label, _ in blocking_findings):
        lines.append("novel.yaml 与立项书不一致：用 python3 scripts/novel_from_premise.py <项目> 重新生成配置"
                     "（不要用 init_novel --force，那会重置 state 与总纲），或在 novel.yaml 里同步同一处改动。")
    if blocking_findings:
        lines.append(f"FAIL: {len(blocking_findings)} blocking finding(s); the book cannot start until they are settled.")
    elif status != "locked":
        lines.append("PASS (draft): no blocking findings, but the premise is not locked yet; "
                     "locking is required before --preflight book.")
    else:
        lines.append("PASS: the premise is locked, recorded and consistent with novel.yaml.")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    target = args.project.expanduser().resolve()
    if target.is_file():
        # Standalone draft: the intake happens before the project exists.
        try:
            premise = read_yaml(target)
        except ProjectYAMLError as error:
            print(f"ERROR: {error}")
            return 2
        if not isinstance(premise, dict) or not premise:
            print(f"ERROR: {target} is not a premise mapping")
            return 2
        findings: list[tuple[str, str, str]] = []
        check_required(premise, findings)
        check_consistency(premise, findings)
        print(render_standalone(target, premise, findings))
        return 1 if any(item[0] == "BLOCK" for item in findings) else 0
    project = target
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    try:
        premise = load_premise(project)
    except ProjectYAMLError as error:
        print(f"ERROR: {error}")
        return 2
    if premise is None:
        print(f"ERROR: {premise_path(project)} not found; run the premise intake first "
              "(see references/premise-proposal.md)")
        return 2
    if not premise:
        print(f"ERROR: {premise_path(project)} is empty")
        return 2

    findings: list[tuple[str, str, str]] = []
    check_required(premise, findings)
    check_consistency(premise, findings)
    check_against_novel(project, premise, findings)
    check_recorded(project, premise, findings)
    print(render(project, premise, findings))
    return 1 if any(item[0] == "BLOCK" for item in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
