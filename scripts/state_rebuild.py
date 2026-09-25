#!/usr/bin/env python3
"""Replay the chapter journal from a chapter-zero snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from state_model import atomic_write_json, read_json, replay


def transaction_paths(project: Path) -> list[Path]:
    directory = project / "state" / "transactions"
    paths = sorted(directory.glob("*.json"))
    expected = [directory / f"chapter-{number:04d}.json" for number in range(1, len(paths) + 1)]
    if paths != expected:
        raise ValueError("transaction files must be consecutively named chapter-0001.json, chapter-0002.json, ...")
    return paths


def rebuild(project: Path, through: int | None = None, base: Path | None = None) -> dict:
    paths = transaction_paths(project)
    if through is None:
        through = len(paths)
    if through < 0 or through > len(paths):
        raise ValueError(f"--through must be between 0 and {len(paths)}")
    initial = read_json(base or project / "state" / "initial.json")
    transactions = [read_json(path) for path in paths[:through]]
    return replay(initial, transactions)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild novel state from chapter transactions")
    parser.add_argument("project", type=Path)
    parser.add_argument("--through", type=int, help="Replay only through this chapter")
    parser.add_argument("--base", type=Path, help="Verified chapter-zero snapshot for an older project")
    parser.add_argument("--output", type=Path, help="Write a reviewable snapshot to this path")
    parser.add_argument("--write", action="store_true", help="Replace state/state.json after replaying every transaction")
    args = parser.parse_args()
    try:
        project = args.project.expanduser().resolve()
        paths = transaction_paths(project)
        if args.write and (args.output or args.through not in (None, len(paths))):
            raise ValueError("--write must replay all transactions and cannot be combined with --output")
        state = rebuild(project, args.through, args.base)
        if args.write:
            atomic_write_json(project / "state" / "state.json", state)
            print(project / "state" / "state.json")
        elif args.output:
            atomic_write_json(args.output, state)
            print(args.output)
        else:
            print(json.dumps(state, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
