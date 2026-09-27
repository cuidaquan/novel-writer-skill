#!/usr/bin/env python3
"""Shared helpers for premise intake, its decision log and its checks.

A book project locks its decisions before the first chapter: `premise.yaml`
holds them, `outline/brief.md` explains them, and `history/log.jsonl` records
every round of the discussion as an append-only event. This module owns the
schema, the log format and the hashing so `brief_check.py` and
`premise_log.py` cannot drift apart.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from project_yaml import ProjectYAMLError, read_yaml

PREMISE_FILE = "premise.yaml"
BRIEF_FILE = "outline/brief.md"
LOG_FILE = "history/log.jsonl"
SNAPSHOT_DIR = "history/snapshots"

TIERS = ("fade", "sensual", "frank")
DELIVERIES = ("book", "serial")
STATUSES = ("draft", "locked")
KINDS = ("premise", "structure", "text")

# tier -> the content_limits lines a project at that tier must carry
TIER_LIMITS: dict[str, list[str]] = {
    "fade": ["亲密场景在门外结束：只写前后与后果，不写过程"],
    "sensual": ["亲密场景写感官与情绪，不写具体做法，不写性器官与体液"],
    "frank": [
        "亲密场景可以点名姿势与做法，直白写身体感受、欲望、边界与节奏",
        "仍不写性器官、性行为过程的细节与体液",
        "性行为只发生在私密空间；公共空间只写散步、交谈和克制的亲昵",
    ],
}

# field path -> human label, in the order the intake asks for them
REQUIRED_FIELDS: tuple[tuple[str, str], ...] = (
    ("delivery", "交付形态（book / serial）"),
    ("length.target_chapters", "计划章数"),
    ("length.target_words", "目标总字数"),
    ("genre.primary", "主类型"),
    ("genre.audience", "读者定位"),
    ("narration.pov", "视角与人称"),
    ("narration.viewpoint_characters", "视角人物（必须有对应人物卡）"),
    ("intimacy.tier", "亲密分级"),
    ("style.tone", "语气基调"),
    ("style.forbidden", "风格禁区（至少一条）"),
    ("style.ending_mode", "章末/结局模式"),
    ("world.mode", "世界设定（真实或架空）"),
    ("world.research_level", "考据等级"),
    ("cast", "人物表（至少一位主角，含 want / flaw / change）"),
    ("arc.turns", "关系或主线变化节拍（至少两次，章号递增）"),
    ("frame.opening_image", "首章的开场意象"),
    ("frame.closing_image", "末章的收束意象"),
)

PLACEHOLDER = re.compile(r"待定|待填|TODO|TBD|待确认|\?\?\?|^[?？]+$", re.IGNORECASE)


def premise_path(project: Path) -> Path:
    return project / PREMISE_FILE


def brief_path(project: Path) -> Path:
    return project / BRIEF_FILE


def log_path(project: Path) -> Path:
    return project / LOG_FILE


def load_premise(project: Path) -> dict[str, Any] | None:
    """Return the parsed premise, or None when the file does not exist."""
    path = premise_path(project)
    if not path.is_file():
        return None
    data = read_yaml(path)
    return data if isinstance(data, dict) else {}


def file_hash(path: Path) -> str:
    if not path.is_file():
        return ""
    return sha256(path.read_bytes()).hexdigest()[:16]


def premise_hashes(project: Path) -> dict[str, str]:
    """Hashes recorded with every round: the decisions and what they produced."""
    hashes = {"premise.yaml": file_hash(premise_path(project))}
    if brief_path(project).is_file():
        hashes["outline/brief.md"] = file_hash(brief_path(project))
    if (project / "novel.yaml").is_file():
        hashes["novel.yaml"] = file_hash(project / "novel.yaml")
    cards = sorted((project / "control-cards").glob("chapter-*.yaml")) if (project / "control-cards").is_dir() else []
    if cards:
        combined = sha256()
        for card in cards:
            combined.update(card.read_bytes())
        hashes["control-cards"] = combined.hexdigest()[:16]
    return hashes


def flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts/lists into dotted paths so rounds can be diffed."""
    flat: dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            flat.update(flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(data, list):
        if all(not isinstance(item, (dict, list)) for item in data):
            # A list of scalars stays whole so a round can show what was added
            # or removed instead of shifting indices.
            flat[prefix] = list(data)
        else:
            for index, value in enumerate(data):
                flat.update(flatten(value, f"{prefix}[{index}]"))
    else:
        flat[prefix] = data
    return flat


def read_log(project: Path) -> list[dict[str, Any]]:
    path = log_path(project)
    if not path.is_file():
        return []
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ProjectYAMLError(f"{LOG_FILE}:{number}: invalid JSON event ({error.msg})") from error
    return events


def append_log(project: Path, event: dict[str, Any]) -> None:
    path = log_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def next_event_id(events: list[dict[str, Any]], kind: str) -> str:
    prefix = "p" if kind == "premise" else ("s" if kind == "structure" else "t")
    numbers = [int(match.group(1)) for event in events
               if (match := re.match(rf"{prefix}(\d+)", str(event.get("id", ""))))]
    return f"{prefix}{(max(numbers) + 1) if numbers else 1:03d}"


def premise_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("kind") in ("premise", "structure")]


def latest_event(events: list[dict[str, Any]], kind: str | None = None) -> dict[str, Any] | None:
    pool = [event for event in events if kind is None or event.get("kind") == kind]
    return pool[-1] if pool else None


def snapshot_path(project: Path, event_id: str) -> Path:
    return project / SNAPSHOT_DIR / event_id


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def set_header_field(path: Path, field: str, value: str) -> bool:
    """Update one top-level `field: value` line in place. Returns False when absent."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(field)}:.*$", re.MULTILINE)
    if not pattern.search(text):
        return False
    path.write_text(pattern.sub(f"{field}: {value}", text, count=1), encoding="utf-8")
    return True


def field_value(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def is_unset(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip() or bool(PLACEHOLDER.search(value.strip()))
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def tier_limit_lines(tier: str) -> list[str]:
    return list(TIER_LIMITS.get(tier, []))
