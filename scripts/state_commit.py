#!/usr/bin/env python3
"""Validate, review-gate and atomically commit a chapter transaction.

The transaction is validated against state first, so semantic errors keep their
existing messages. Only then does the deterministic blocking review run: a
chapter with an unacknowledged BLOCK finding is refused and nothing is written.
Intentional blocks can be acknowledged with --allow plus a required --reason,
which is recorded in the transaction journal and surfaced by project_check.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import review
from state_model import apply_transaction, atomic_write_json, nonempty, read_json, validate_transaction


def chapter_block_gate(project: Path, chapter: int, allow: list[str], reason: str | None) -> list[dict]:
    """Return acknowledgement records for this chapter, or raise ValueError."""
    if allow and not nonempty(reason):
        raise ValueError("--allow requires a non-empty --reason so the waiver stays auditable")
    if reason and not allow:
        raise ValueError("--reason is only valid together with --allow")
    try:
        drafted = review.load_chapter(project, chapter)
    except review.ReviewInputError as exc:
        raise ValueError(f"commit gate could not review chapter {chapter}: {exc}") from exc
    blocks = [finding for finding in review.chapter_findings(drafted) if finding.level == "BLOCK"]
    reported = sorted({finding.check for finding in blocks})
    unknown = sorted(set(allow) - set(reported))
    if unknown:
        raise ValueError(
            f"--allow names check(s) that are not reported for chapter {chapter}: {', '.join(unknown)}; "
            f"reported checks: {', '.join(reported) if reported else 'none'}"
        )
    remaining = [finding for finding in blocks if finding.check not in set(allow)]
    if remaining:
        detail = "\n".join(review.format_finding(project, finding) for finding in remaining)
        raise ValueError(
            f"chapter {chapter} has blocking review findings; fix the prose or acknowledge a check with "
            f"--allow <check> --reason <text>:\n{detail}"
        )
    return [{"check": check, "reason": (reason or "").strip()} for check in allow]


def merge_acknowledgements(existing: object, added: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    items = [*(existing if isinstance(existing, list) else []), *added]
    for item in items:
        if not isinstance(item, dict) or not nonempty(item.get("check")):
            continue
        check = item["check"]
        if check in seen:
            continue
        merged.append({"check": check, "reason": str(item.get("reason", "")).strip()})
        seen.add(check)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a chapter transaction, refuse it when the chapter has unacknowledged blocking "
            "review findings, then update the journal and state atomically."
        )
    )
    parser.add_argument("state", type=Path, help="Live project state path (state/state.json)")
    parser.add_argument("transaction", type=Path, help="Chapter transaction JSON to commit")
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="CHECK",
        help="Acknowledge a blocking review check reported for this chapter; requires --reason",
    )
    parser.add_argument("--reason", help="Why the acknowledged check is acceptable; recorded in the transaction")
    args = parser.parse_args()
    try:
        state_path = args.state.expanduser().resolve()
        state = read_json(state_path)
        tx = read_json(args.transaction)
        candidate = apply_transaction(state, tx)
        chapter = candidate["project"]["current_chapter"]

        project = state_path.parent.parent
        expected_state = (project / "state" / "state.json").resolve()
        if state_path != expected_state or not (project / "novel.yaml").is_file():
            raise ValueError(
                f"cannot run the commit gate: {args.state} is not a project state/state.json with novel.yaml; "
                "the gate needs the control card and the chapter body"
            )
        acknowledgements = chapter_block_gate(project, chapter, args.allow, args.reason)
        if acknowledgements:
            tx = {**tx, "acknowledged_blocks": merge_acknowledgements(tx.get("acknowledged_blocks"), acknowledgements)}
            ack_errors = validate_transaction(tx, state["project"]["current_chapter"])
            if ack_errors:
                raise ValueError("invalid transaction: " + "; ".join(ack_errors))

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
