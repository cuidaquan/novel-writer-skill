#!/usr/bin/env python3
"""Initialize a novel project from the skill's bundled templates."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = SKILL_ROOT / "assets" / "templates"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a novel project")
    parser.add_argument("path", type=Path, help="Destination project directory")
    parser.add_argument("--title", default="未命名小说")
    parser.add_argument("--force", action="store_true", help="Allow an existing empty directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = args.path.expanduser().resolve()

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

    novel_path = target / "novel.yaml"
    novel_text = novel_path.read_text(encoding="utf-8")
    yaml_safe_title = json.dumps(args.title, ensure_ascii=False)
    novel_text = novel_text.replace("title: 未命名小说", f"title: {yaml_safe_title}", 1)
    novel_path.write_text(novel_text, encoding="utf-8")

    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
