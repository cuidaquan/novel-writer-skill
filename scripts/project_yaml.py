"""Read the small YAML subset used by novel projects without extra packages.

Supported: indented mappings/lists, quoted or plain scalars, inline lists and {}.
Block scalars, anchors, tags and other flow mappings are deliberately
outside this format; errors are explicit so they cannot be silently misread.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class ProjectYAMLError(ValueError):
    pass


def _split_inline(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote = ""
    escaped = False
    depth = 0
    for index, char in enumerate(value):
        if escaped:
            escaped = False
        elif char == "\\" and quote == '"':
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
    if quote or depth != 0:
        raise ProjectYAMLError("unclosed quoted or inline value")
    parts.append(value[start:].strip())
    return parts


def _scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ProjectYAMLError(f"invalid double-quoted value: {value}") from exc
        if not isinstance(parsed, str):
            raise ProjectYAMLError("quoted value must be a string")
        return parsed
    if value.startswith("'"):
        if not value.endswith("'") or len(value) < 2:
            raise ProjectYAMLError(f"invalid single-quoted value: {value}")
        return value[1:-1].replace("''", "'")
    if value.startswith("[") and value.endswith("]"):
        content = value[1:-1].strip()
        return [] if not content else [_scalar(part) for part in _split_inline(content)]
    if value.startswith("{") and value.endswith("}"):
        content = value[1:-1].strip()
        if not content:
            return {}
        mapping: dict[str, Any] = {}
        for part in _split_inline(content):
            key, separator, raw = part.partition(":")
            key = key.strip()
            if not separator or not key or key in mapping:
                raise ProjectYAMLError(f"invalid inline mapping entry: {part}")
            mapping[key] = _scalar(raw.strip())
        return mapping
    if value in {"null", "~"}:
        return None
    if value in {"true", "false"}:
        return value == "true"
    if re.fullmatch(r"-?(?:0|[1-9]\d*)", value):
        return int(value)
    if re.fullmatch(r"-?(?:0|[1-9]\d*)\.\d+", value):
        return float(value)
    if value.startswith(("|", ">", "&", "*", "!")):
        raise ProjectYAMLError(f"unsupported YAML syntax: {value}")
    return value


def _without_comment(content: str) -> str:
    quote = ""
    escaped = False
    for index, char in enumerate(content):
        if escaped:
            escaped = False
        elif char == "\\" and quote == '"':
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or content[index - 1].isspace()):
            return content[:index].rstrip()
    return content


def read_yaml(path: Path) -> Any:
    lines: list[tuple[int, str, int]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ProjectYAMLError(f"{path}:{number}: indentation must use spaces")
        content = _without_comment(raw.strip())
        if content and not content.startswith("#"):
            lines.append((len(raw) - len(raw.lstrip(" ")), content, number))
    if not lines:
        raise ProjectYAMLError(f"{path}: empty YAML document")

    def mapping_item_head(item: str) -> tuple[str, str] | None:
        """Split `key: value` at the head of a list item, or None for a scalar.

        `- 12:30 出发` stays a scalar because its value does not start with a
        space; quoted and inline-collection items are never read as keys.
        """
        if not item or item.startswith(("\"", "'", "{", "[")):
            return None
        key, separator, raw_value = item.partition(":")
        if not separator:
            return None
        key = key.strip()
        if not key or not re.fullmatch(r"[\w.\-]+", key, re.UNICODE):
            return None
        if raw_value and not raw_value.startswith(" "):
            return None
        return key, raw_value.strip()

    def parse(index: int, indent: int) -> tuple[Any, int]:
        if lines[index][0] != indent:
            raise ProjectYAMLError(f"{path}:{lines[index][2]}: unexpected indentation")
        is_list = lines[index][1].startswith("- ")
        result: Any = [] if is_list else {}
        while index < len(lines):
            column, content, number = lines[index]
            if column < indent:
                break
            if column > indent:
                raise ProjectYAMLError(f"{path}:{number}: unexpected indentation")
            if is_list:
                if not content.startswith("- "):
                    raise ProjectYAMLError(f"{path}:{number}: mixed list and mapping")
                item = content[2:].strip()
                head = mapping_item_head(item)
                if head is not None:
                    # `- key: value` plus the following keys at a deeper indent
                    # are one mapping item, the shape hand-written lists use.
                    key, raw_value = head
                    mapping: dict[str, Any] = {}
                    if raw_value:
                        mapping[key] = _scalar(raw_value)
                        index += 1
                    elif index + 1 < len(lines) and lines[index + 1][0] > column:
                        mapping[key], index = parse(index + 1, lines[index + 1][0])
                    else:
                        mapping[key] = None
                        index += 1
                    if index < len(lines) and lines[index][0] > column and not lines[index][1].startswith("- "):
                        extra, index = parse(index, lines[index][0])
                        if not isinstance(extra, dict):
                            raise ProjectYAMLError(f"{path}:{lines[index][2]}: expected key: value")
                        for extra_key, extra_value in extra.items():
                            if extra_key in mapping:
                                raise ProjectYAMLError(
                                    f"{path}:{lines[index][2]}: invalid or duplicate key: {extra_key}"
                                )
                            mapping[extra_key] = extra_value
                    result.append(mapping)
                elif not item:
                    if index + 1 >= len(lines) or lines[index + 1][0] <= indent:
                        raise ProjectYAMLError(f"{path}:{number}: empty list item")
                    value, index = parse(index + 1, lines[index + 1][0])
                    result.append(value)
                else:
                    value = _scalar(item)
                    index += 1
                    result.append(value)
            else:
                if content.startswith("- ") or ":" not in content:
                    raise ProjectYAMLError(f"{path}:{number}: expected key: value")
                key, raw_value = content.split(":", 1)
                key = key.strip()
                if not key or key in result or (raw_value and not raw_value.startswith(" ")):
                    raise ProjectYAMLError(f"{path}:{number}: invalid or duplicate key: {key}")
                raw_value = raw_value.strip()
                if raw_value:
                    result[key] = _scalar(raw_value)
                    index += 1
                elif index + 1 < len(lines) and lines[index + 1][0] > indent:
                    result[key], index = parse(index + 1, lines[index + 1][0])
                else:
                    result[key] = None
                    index += 1
        return result, index

    value, end = parse(0, lines[0][0])
    if end != len(lines):
        raise ProjectYAMLError(f"{path}:{lines[end][2]}: could not parse document")
    return value
