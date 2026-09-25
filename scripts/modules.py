"""Select optional genre and scene-style guidance for one chapter."""

from __future__ import annotations

import re
from pathlib import Path


REFERENCE_ROOT = Path(__file__).resolve().parents[1] / "references"
MODULE_ID = re.compile(r"[a-z][a-z0-9-]*\Z")


def genre_module_status(novel: dict) -> tuple[list[str], list[str]]:
    """Return (genre ids with a module, genre ids on the generic path)."""
    genre = novel.get("genre") or {}
    if not isinstance(genre, dict):
        raise ValueError("novel.yaml genre must be a mapping")
    secondary = genre.get("secondary", [])
    if not isinstance(secondary, list):
        raise ValueError("novel.yaml genre.secondary must be a list")
    ids: list[str] = []
    for genre_id in [genre.get("primary"), *secondary]:
        if not isinstance(genre_id, str) or not MODULE_ID.fullmatch(genre_id):
            raise ValueError(f"invalid genre module id: {genre_id!r}")
        if genre_id not in ids:
            ids.append(genre_id)
    present = [genre_id for genre_id in ids if (REFERENCE_ROOT / "genres" / f"{genre_id}.md").is_file()]
    missing = [genre_id for genre_id in ids if genre_id not in present]
    return present, missing


def module_paths(novel: dict, card: dict) -> list[Path]:
    genre = novel.get("genre") or {}
    if not isinstance(genre, dict):
        raise ValueError("novel.yaml genre must be a mapping")
    secondary = genre.get("secondary", [])
    if not isinstance(secondary, list):
        raise ValueError("novel.yaml genre.secondary must be a list")
    genres = [genre.get("primary"), *secondary]

    style = novel.get("style") or {}
    if not isinstance(style, dict):
        raise ValueError("novel.yaml style must be a mapping")
    book_styles = style.get("modules", [])
    chapter_styles = card.get("style_modules", [])
    if not isinstance(book_styles, list) or not isinstance(chapter_styles, list):
        raise ValueError("style.modules and chapter style_modules must be lists")

    paths: list[Path] = []
    seen_genres: set[str] = set()
    for genre_id in genres:
        if not isinstance(genre_id, str) or not MODULE_ID.fullmatch(genre_id):
            raise ValueError(f"invalid genre module id: {genre_id!r}")
        if genre_id in seen_genres:
            continue
        seen_genres.add(genre_id)
        path = REFERENCE_ROOT / "genres" / f"{genre_id}.md"
        if path.is_file():
            paths.append(path)
    seen_styles: set[str] = set()
    for style_id in [*book_styles, *chapter_styles]:
        if not isinstance(style_id, str) or not MODULE_ID.fullmatch(style_id):
            raise ValueError(f"invalid style module id: {style_id!r}")
        if style_id in seen_styles:
            continue
        seen_styles.add(style_id)
        path = REFERENCE_ROOT / "style-modules" / f"{style_id}.md"
        if not path.is_file():
            raise ValueError(f"unknown style module: {style_id}")
        paths.append(path)
    return paths
