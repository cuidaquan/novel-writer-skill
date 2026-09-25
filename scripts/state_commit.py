#!/usr/bin/env python3
"""Validate and atomically commit a chapter transaction."""

from __future__ import annotations

import argparse
from pathlib import Path

from state_model import apply_transaction, atomic_write_json, read_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Commit a novel chapter state transaction")
    parser.add_argument("state", type=Path)
    parser.add_argument("transaction", type=Path)
    args = parser.parse_args()
    try:
        state = read_json(args.state)
        tx = read_json(args.transaction)
        candidate = apply_transaction(state, tx)
        chapter = candidate["project"]["current_chapter"]
        journal = args.state.parent / "transactions" / f"chapter-{chapter:04d}.json"
        if journal.exists() and journal.resolve() != args.transaction.resolve():
            if read_json(journal) != tx:
                raise ValueError(f"journal already contains different chapter {chapter} transaction: {journal}")
        else:
            atomic_write_json(journal, tx)
        atomic_write_json(args.state, candidate)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Committed chapter {chapter} to {args.state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
