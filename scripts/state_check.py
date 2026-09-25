#!/usr/bin/env python3
"""Validate a novel continuity state file."""

from __future__ import annotations

import argparse
from pathlib import Path

from state_model import read_json, validate_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate novel continuity state")
    parser.add_argument("state", type=Path)
    args = parser.parse_args()
    try:
        errors = validate_state(read_json(args.state))
    except ValueError as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("OK: state is structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
