#!/usr/bin/env python3
"""Configurable, advisory prose lint for AI-tell words, sentence patterns and punctuation.

Every finding is a NOTE with a file, line and matched fragment; nothing here
blocks a commit. Rules are off unless the project ships checks/prose-rules.json
or the caller passes --default-rules, because word lists are cultural and easy
to over-apply.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import prose_metrics
from planning import numbered_path
from review import Finding, format_finding
from state_model import read_json, validate_state


DEFAULT_RULES = {
    "words": ["仿佛", "似乎", "宛如", "不禁"],
    "patterns": [],
    "punctuation_per_100": {},
}

PROJECT_RULES = Path("checks") / "prose-rules.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Scan one chapter (or every committed chapter) for configured words, regular-expression "
            "patterns and punctuation rates. All findings are advisory NOTEs; without a project rule "
            "file or --default-rules the command reports that no rules are configured."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--chapter", type=int, help="Chapter number; defaults to current_chapter + 1")
    parser.add_argument("--all", action="store_true", help="Scan every committed chapter instead of one")
    parser.add_argument("--rules", type=Path, help="Rule JSON file; defaults to checks/prose-rules.json when it exists")
    parser.add_argument("--default-rules", action="store_true", help="Use the small built-in word list when no rule file exists")
    return parser.parse_args()


def load_rules(project: Path, rules_path: Path | None, use_default: bool) -> tuple[dict | None, str]:
    path = rules_path.expanduser().resolve() if rules_path else project / PROJECT_RULES
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read rules {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{path}: rules must be a JSON object")
        words = data.get("words", [])
        if not isinstance(words, list) or any(not isinstance(word, str) or not word.strip() for word in words):
            raise ValueError(f"{path}: words must be a list of non-empty strings")
        patterns = data.get("patterns", [])
        if not isinstance(patterns, list):
            raise ValueError(f"{path}: patterns must be a list")
        for index, rule in enumerate(patterns):
            if not isinstance(rule, dict) or not isinstance(rule.get("regex"), str) or not rule["regex"].strip():
                raise ValueError(f"{path}: patterns[{index}].regex must be a non-empty string")
            try:
                re.compile(rule["regex"])
            except re.error as exc:
                raise ValueError(f"{path}: patterns[{index}].regex is invalid: {exc}") from exc
        punctuation = data.get("punctuation_per_100", {})
        if not isinstance(punctuation, dict) or any(type(value) not in (int, float) or value <= 0 for value in punctuation.values()):
            raise ValueError(f"{path}: punctuation_per_100 must map punctuation to a positive number")
        return {
            "words": words,
            "patterns": patterns,
            "punctuation_per_100": punctuation,
        }, str(path)
    if use_default:
        return dict(DEFAULT_RULES), "built-in defaults (--default-rules)"
    return None, "none (create checks/prose-rules.json, pass --rules, or use --default-rules)"


def lint_text(path: Path, text: str, rules: dict) -> list[Finding]:
    findings: list[Finding] = []
    paragraphs = prose_metrics.paragraphs(text)
    for word in rules["words"]:
        occurrences = text.count(word)
        if not occurrences:
            continue
        lines = [number for number, line in paragraphs if word in line]
        findings.append(
            Finding(
                "NOTE", "lint-word", path, lines[0] if lines else 1,
                f"{word!r} appears {occurrences} time(s)",
                "matches a word in the prose-lint rules; lines " + ", ".join(map(str, lines[:10])),
                "keep it only if the repetition is intended.",
            )
        )
    for rule in rules["patterns"]:
        regex = re.compile(rule["regex"])
        hits = [number for number, line in paragraphs if regex.search(line)]
        if not hits:
            continue
        label = rule.get("id") or rule["regex"]
        findings.append(
            Finding(
                "NOTE", "lint-pattern", path, hits[0],
                f"pattern {label!r} matches {len(hits)} line(s)",
                f"regex: {rule['regex']}; lines " + ", ".join(map(str, hits[:10])),
                rule.get("note") or "revise the sentence pattern unless the repetition is intended.",
            )
        )
    if rules["punctuation_per_100"]:
        profile = prose_metrics.punctuation_profile(text, limit=len(prose_metrics.PUNCTUATION_MARKS))
        rates = {mark: rate for mark, _, rate in profile}
        for mark, threshold in rules["punctuation_per_100"].items():
            rate = rates.get(mark, 0.0)
            if rate > threshold:
                findings.append(
                    Finding(
                        "NOTE", "lint-punctuation", path, 1,
                        f"{mark!r} rate is {rate} per 100 chars, above the configured {threshold}",
                        f"the project rule file sets punctuation_per_100.{mark}={threshold}",
                        "check whether the habit is intentional.",
                    )
                )
    return findings


def main() -> int:
    args = parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    try:
        state = read_json(project / "state" / "state.json")
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    errors = validate_state(state)
    if errors:
        print("ERROR: invalid state: " + "; ".join(errors))
        return 2
    current = state["project"]["current_chapter"]
    chapter = args.chapter if args.chapter is not None else current + 1
    if args.all:
        numbers = list(range(1, current + 1))
    else:
        numbers = [chapter]
        if chapter < 1:
            print("ERROR: --chapter must be a positive integer")
            return 2
    try:
        rules, source = load_rules(project, args.rules, args.default_rules)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    print(f"# Prose Lint: {'all committed chapters' if args.all else f'chapter {chapter}'}")
    print()
    print(f"- Rules: {source}")
    print()
    if rules is None:
        print("## Findings")
        print("(no rules configured; prose lint never runs unasked because word lists are easy to over-apply)")
        return 0

    total = 0
    for number in numbers:
        body = numbered_path(project / "chapters", "chapter", number, ("md", "txt"))
        if body is None:
            print(f"ERROR: chapter {number} body not found")
            return 2
        findings = lint_text(body, body.read_text(encoding="utf-8"), rules)
        total += len(findings)
        print(f"## Chapter {number} ({len(findings)} finding(s))")
        if findings:
            for finding in findings:
                print(format_finding(project, finding))
        else:
            print("(none)")
        print()
    print(f"Total advisory findings: {total}. Nothing here blocks a commit; use the review gate for BLOCK items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
