#!/usr/bin/env python3
"""Advisory timeline audit for a novel project.

Two classes of continuity bug are cheap to miss and expensive to find by eye:

* a recurring arrangement ("she is on air from eight to two") that the scene
  contradicts ("she came downstairs at ten"), and
* clock times that run backwards inside one scene.

This report extracts every time statement per chapter, separates recurring
arrangements from one-off clock times, and flags clock times that appear out of
order inside a scene block. It cannot know who is awake, so every row is for
human judgement: the report is always advisory and never changes the exit code.
Exit code 2 is reserved for usage or input errors.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from planning import numbered_path

PERIODS = (
    "凌晨", "天亮", "一大早", "清晨", "早上", "早晨", "上午", "中午", "晌午",
    "下午", "傍晚", "擦黑", "天黑", "晚上", "夜里", "半夜", "后半夜", "深夜", "白天",
)
PERIOD_PATTERN = "|".join(PERIODS)

NUMERALS = "0-9０-９一二三四五六七八九十两半两"
# Clock expressions: a numeral plus 点 (optionally qualified), or HH:MM.
CLOCK = re.compile(
    rf"(?:{PERIOD_PATTERN})?\s*(?:\d{{1,2}}|[{NUMERALS}]{{1,3}})\s*点(?:半|一刻|钟|\d{{1,2}}\s*分|出头|多|左右)?"
    r"|\d{1,2}\s*[:：]\s*\d{2}"
)
# "一点也不知道" and friends are not times.
CLOCK_FALSE_FRIEND = re.compile(r"^一点(?:也|都|儿|点|滴)")
DAY = re.compile(
    r"第[二三四五六七八九十\d]+天|次日|当晚|头一天|昨天|前天|今天|明天|那天|隔天"
    r"|\d{1,2}\s*月\s*\d{1,2}\s*[日号]|[一二三四五六七八九十]{1,3}月[一二三四五六七八九十]{1,3}[日号]"
    r"|周[一二三四五六日天]|星期[一二三四五六日天]"
)
DURATION = re.compile(
    r"半(?:个)?(?:小时|钟头)|一(?:个)?(?:小时|钟头)|\d{1,3}\s*分钟|一整天|一晚上|一夜|三四个小时"
)
MEAL = re.compile(r"早饭|午饭|晚饭|夜宵|早餐|中饭|晚饭|宵夜")
SKY = re.compile(r"日出|日落|太阳|天蒙蒙亮|蒙蒙亮|黑透了|月亮")
RECURRING = re.compile(r"每天|天天|常年|平时|照例|固定|总是|从不|一般来说|一年到头")
ROUTINE_VERB = re.compile(
    r"起床|起来|开播|下播|上播|上班|下班|到岗|出门|到家|回家|睡觉|睡下|做早饭|收摊|开门|关门"
)
RETROSPECTIVE = re.compile(r"后来|之前|此前|昨天|前天|那天|以前|原来|小时候|事后|回头|第二年|前年|去年|起初|当时")
BLOCK_SPLIT = "—"

HALF_HOUR = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract every time statement per chapter, separate recurring arrangements from "
            "one-off clock times, and flag clock times that run backwards inside one scene. "
            "Advisory only: the report cannot know who is awake at a given hour."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--chapter", type=int, help="Audit one chapter instead of every committed chapter")
    parser.add_argument("--summary", action="store_true", help="Print only counts and out-of-order flags")
    parser.add_argument("--limit", type=int, default=40, help="Maximum rows per section (default: 40)")
    return parser.parse_args()


def load_chapters(project: Path, only: int | None) -> list[tuple[int, list[tuple[int, str]]]]:
    """Return [(chapter, [(line number, text), ...]), ...] for drafted chapters."""
    chapters = []
    number = 1
    while (path := numbered_path(project / "chapters", "chapter", number, ("md", "txt"))) is not None:
        if only is None or number == only:
            lines = []
            for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                line = raw.strip()
                if line and not line.startswith("#"):
                    lines.append((line_number, line))
            chapters.append((number, lines))
        number += 1
    return chapters


def blocks(lines: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """Split a chapter into scene blocks on the em-dash separator."""
    out: list[list[tuple[int, str]]] = [[]]
    for line in lines:
        if line[1] == BLOCK_SPLIT:
            out.append([])
        else:
            out[-1].append(line)
    return [block for block in out if block]


def minutes_of_day(token: str, fallback_period: str | None) -> tuple[int | None, str | None]:
    """Best-effort hour:minute for a clock token, plus the period it implies."""
    clock = re.match(r"^(\d{1,2})\s*[:：]\s*(\d{2})", token)
    if clock:
        hour, minute = int(clock.group(1)), int(clock.group(2))
        return (hour % 24) * 60 + minute, fallback_period
    period = next((p for p in PERIODS if token.startswith(p)), fallback_period)
    digits = re.search(r"(\d{1,2}|[一二三四五六七八九十两]{1,3})\s*点", token)
    if not digits:
        return None, period
    raw = digits.group(1)
    hour = int(raw) if raw.isdigit() else chinese_number(raw)
    if hour is None:
        return None, period
    minute = 30 if "半" in token else 0
    if "一刻" in token:
        minute = 15
    tail = re.search(r"点\s*(\d{1,2})\s*分", token)
    if tail:
        minute = int(tail.group(1))
    if period in ("下午", "傍晚", "晚上", "夜里", "半夜", "后半夜", "深夜", "天黑", "擦黑") and hour < 12:
        hour += 12
    if period in ("凌晨", "后半夜", "半夜") and hour == 12:
        hour = 0
    return hour * 60 + minute, period


def chinese_number(text: str) -> int | None:
    digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text == "十":
        return 10
    if text.startswith("十"):
        return 10 + digits.get(text[1:2], 0)
    if "十" in text:
        head, _, tail = text.partition("十")
        return digits.get(head, 0) * 10 + (digits.get(tail, 0) if tail else 0)
    return digits.get(text)


def clock_tokens(line: str) -> list[str]:
    found = []
    for match in CLOCK.finditer(line):
        token = match.group(0).strip()
        plain = token.replace(" ", "")
        if CLOCK_FALSE_FRIEND.match(plain):
            continue
        # "一点樟脑丸的味道" / "混着一点护手霜的香味": a bare 一 or 两 is only a
        # time when a qualifier follows it. Higher numerals stay, since a line
        # saying 三点 is far more often a clock than a list item.
        if not any(plain.startswith(period) for period in PERIODS) and not re.match(r"^\d", plain):
            numeral = re.match(r"^([一二两])", plain)
            if numeral and not re.match(r"^[一两]点(?:半|一刻|钟|多|左右|整|出头|两|二|\d{1,2}\s*分)", plain):
                continue
        found.append(token)
    return found


def audit_chapter(number: int, lines: list[tuple[int, str]]) -> dict[str, object]:
    schedules, clocks, anchors, flags = [], [], [], []
    schedule_lines = set()
    for line_number, text in lines:
        tokens = clock_tokens(text)
        if tokens and (RECURRING.search(text) or ROUTINE_VERB.search(text)):
            schedules.append((line_number, text, tokens))
            schedule_lines.add(line_number)
        for token in tokens:
            clocks.append((line_number, token, text))
        for label, pattern in (("时段", re.compile(PERIOD_PATTERN)), ("天象", SKY), ("日/星期", DAY), ("时长", DURATION), ("餐", MEAL)):
            if pattern.search(text):
                anchors.append((label, line_number, text))
                break
    for block in blocks(lines):
        # A line that states a recurring arrangement lists several hours at once;
        # its hours are not a narrative sequence. Date and day markers open a new
        # segment, so a frame or flashback is not read as one continuous evening.
        seen: list[tuple[int, int, str]] = []
        fallback = None
        for line_number, text in block:
            opens_segment = bool(DAY.search(text))
            if opens_segment and seen:
                flags.extend(out_of_order(seen))
                seen = []
            if line_number in schedule_lines:
                continue
            tokens = clock_tokens(text)
            for index, token in enumerate(tokens):
                if index and tokens[index - 1] in text:
                    continue  # two hours on one line: a schedule, not a sequence
                value, fallback = minutes_of_day(token, fallback)
                if value is not None:
                    seen.append((value, line_number, token))
        flags.extend(out_of_order(seen))
    return {"schedules": schedules, "clocks": clocks, "anchors": anchors, "flags": flags}


def out_of_order(seen: list[tuple[int, int, str]]) -> list[tuple[int, str, int, str]]:
    flags = []
    for (before, before_line, before_token), (after, after_line, after_token) in zip(seen, seen[1:]):
        if before - after >= HALF_HOUR:
            flags.append((before_line, before_token, after_line, after_token))
    return flags


def render(project: Path, chapters: list[tuple[int, list[tuple[int, str]]]], args: argparse.Namespace) -> str:
    results = [(number, audit_chapter(number, lines)) for number, lines in chapters]
    total_clocks = sum(len(result["clocks"]) for _, result in results)
    total_schedules = sum(len(result["schedules"]) for _, result in results)
    total_flags = sum(len(result["flags"]) for _, result in results)
    lines = [
        "# Timeline Audit",
        "",
        f"- Project: {project}",
        f"- Audited chapters: {len(chapters)}",
        f"- Time statements: {total_clocks} clock expressions, {total_schedules} recurring-arrangement lines",
        f"- Out-of-order flags: {total_flags}",
        "",
        "Advisory only: this report extracts what the text says, it cannot know who is awake or",
        "where anyone is. Read every row against the scene it belongs to.",
    ]
    if args.summary:
        for number, result in results:
            lines.append(
                f"- chapter {number}: {len(result['clocks'])} clock expressions, "
                f"{len(result['schedules'])} arrangement lines, {len(result['flags'])} out-of-order flags"
            )
        return "\n".join(lines) + "\n"

    for number, result in results:
        lines += ["", f"## Chapter {number}", ""]
        lines.append(f"### Recurring arrangements ({len(result['schedules'])})")
        if result["schedules"]:
            for line_number, text, tokens in result["schedules"][: args.limit]:
                lines.append(f"- chapter {number}:{line_number} [{'/'.join(tokens)}] {text[:88]}")
            lines.append("- Check each of these against every scene that happens inside the stated window.")
        else:
            lines.append("(none)")

        lines += ["", f"### Clock expressions in reading order ({len(result['clocks'])})"]
        if result["clocks"]:
            for line_number, token, text in result["clocks"][: args.limit]:
                lines.append(f"- {token:<10} chapter {number}:{line_number}  {text[:70]}")
        else:
            lines.append("(none)")

        lines += ["", f"### Out-of-order clock times inside one scene ({len(result['flags'])})"]
        if result["flags"]:
            for before_line, before_token, after_line, after_token in result["flags"]:
                lines.append(
                    f"- chapter {number}: {before_token} (line {before_line}) is followed by "
                    f"{after_token} (line {after_line}) — a flashback needs a marker, otherwise retime one of them"
                )
        else:
            lines.append("(none)")

        lines += ["", f"### Other time anchors ({len(result['anchors'])})"]
        if result["anchors"]:
            for label, line_number, text in result["anchors"][: args.limit]:
                lines.append(f"- [{label}] chapter {number}:{line_number} {text[:70]}")
        else:
            lines.append("(none)")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    if args.limit < 1:
        print("ERROR: --limit must be at least 1")
        return 2
    if not (project / "chapters").is_dir():
        print(f"ERROR: no chapters directory under {project}")
        return 2
    chapters = load_chapters(project, args.chapter)
    if not chapters:
        print(f"ERROR: no drafted chapter found{' for that number' if args.chapter else ''}")
        return 2
    print(render(project, chapters, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
