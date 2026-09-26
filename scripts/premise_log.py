#!/usr/bin/env python3
"""Record, inspect and restore the decision history of a book project.

`history/log.jsonl` is append-only: every round of the premise discussion is one
event carrying the author's own words, the field-level diff, what it propagated
into, and the hashes of the files it produced. Nothing is ever rewritten, so a
round cannot be silently overwritten — and every snapshot can be proven to be
the round it claims to be.

Exit codes: 0 success, 1 drift or a failed restore check, 2 usage or input error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from premise import (
    KINDS,
    brief_path,
    file_hash,
    flatten,
    latest_event,
    load_premise,
    next_event_id,
    now_stamp,
    premise_hashes,
    premise_path,
    read_log,
    append_log,
    set_header_field,
    snapshot_path,
)
from project_yaml import ProjectYAMLError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Append a premise round to history/log.jsonl (--record), list rounds (--list), "
            "show one round (--show ID), diff two rounds (--diff A B), check the working copy "
            "against the last round (--verify), or go back to a round (--restore ID)."
        )
    )
    parser.add_argument("project", type=Path, help="Novel project directory")
    parser.add_argument("--record", metavar="SUMMARY", help="Append a round with this one-line summary")
    parser.add_argument("--input", default="", help="The author's own words that triggered this round")
    parser.add_argument("--author", default="agent", choices=("agent", "user"), help="Who moved this round")
    parser.add_argument("--kind", default="premise", choices=KINDS, help="premise decisions, structure, or a text version")
    parser.add_argument("--lock", action="store_true", help="With --record: mark the premise locked")
    parser.add_argument("--list", action="store_true", help="List recorded rounds")
    parser.add_argument("--show", metavar="ID", help="Print one round's decisions and context")
    parser.add_argument("--diff", nargs=2, metavar=("FROM", "TO"), help="Diff two rounds")
    parser.add_argument("--verify", action="store_true", help="Check the working copy against the last round")
    parser.add_argument("--restore", metavar="ID", help="Restore a round (prints the plan unless --apply)")
    parser.add_argument("--apply", action="store_true", help="With --restore: actually write the files back")
    return parser.parse_args()


def snapshot_files(project: Path) -> list[Path]:
    files = [premise_path(project), brief_path(project), project / "novel.yaml"]
    files += sorted((project / "chapters").glob("chapter-*")) if (project / "chapters").is_dir() else []
    return [path for path in files if path.is_file()]


def write_snapshot(project: Path, event_id: str) -> str:
    target = snapshot_path(project, event_id)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    for source in snapshot_files(project):
        relative = source.relative_to(project)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return str(target.relative_to(project))


BOOKKEEPING_FIELDS = ("version", "rounds", "locked_at")


def field_diff(before: Path, after: Path) -> dict[str, Any]:
    """Field-level diff of two premise snapshots."""
    if not before.is_file():
        return {"created": True}
    if not after.is_file():
        return {"removed": True}
    from project_yaml import read_yaml

    old = flatten(read_yaml(before) or {})
    new = flatten(read_yaml(after) or {})
    changed: dict[str, Any] = {}
    for key in sorted(set(old) | set(new)):
        if key in BOOKKEEPING_FIELDS:
            continue  # premise_log 自己维护的计数，不是作者的决策
        before_value, after_value = old.get(key), new.get(key)
        if before_value == after_value:
            continue
        # A list of scalars reads better as added/removed than as shifted indices.
        if (isinstance(before_value, list) or isinstance(after_value, list)) and all(
            not isinstance(item, (list, dict)) for item in (before_value or []) + (after_value or [])
        ):
            before_items, after_items = list(before_value or []), list(after_value or [])
            added = [item for item in after_items if item not in before_items]
            removed = [item for item in before_items if item not in after_items]
            if added or removed:
                changed[key] = {"added": added, "removed": removed}
            continue
        changed[key] = {"from": before_value, "to": after_value}
    return changed


def propagated(project: Path, previous: dict[str, Any] | None, current: dict[str, str]) -> list[str]:
    if not previous:
        return []
    old_hashes = previous.get("hashes") or {}
    labels = {
        "novel.yaml": "novel.yaml 已同步",
        "control-cards": "章卡已同步",
        "outline/brief.md": "brief.md 已更新",
        "chapters": "正文已更新",
    }
    return [label for key, label in labels.items()
            if key in current and old_hashes.get(key) not in (None, current[key])]


def text_stats(project: Path) -> dict[str, Any]:
    chapters = sorted((project / "chapters").glob("chapter-*")) if (project / "chapters").is_dir() else []
    if not chapters:
        return {}
    from hashlib import sha256

    combined = sha256()
    words = 0
    for chapter in chapters:
        raw = chapter.read_text(encoding="utf-8")
        combined.update(raw.encode("utf-8"))
        words += len(raw)
    return {"chapters": len(chapters), "merged_hash": combined.hexdigest()[:16], "bytes": words}


def hashes_for(project: Path, kind: str) -> dict[str, str]:
    hashes = premise_hashes(project)
    if kind == "text":
        stats = text_stats(project)
        if stats:
            hashes["chapters"] = stats["merged_hash"]
    return hashes


def do_record(project: Path, args: argparse.Namespace) -> int:
    premise = load_premise(project)
    if premise is None:
        print(f"ERROR: {premise_path(project)} not found; the premise must exist before it can be recorded")
        return 2
    try:
        events = read_log(project)
    except ProjectYAMLError as error:
        print(f"ERROR: {error}")
        return 2
    previous = latest_event(events)
    event_id = next_event_id(events, args.kind)
    snapshot = write_snapshot(project, event_id)
    hashes = hashes_for(project, args.kind)
    rounds = len([event for event in events if event.get("kind") in ("premise", "structure")]) + 1
    changed = field_diff(snapshot_path(project, previous["id"]) / "premise.yaml", project / "premise.yaml") if previous else {"created": True}

    if args.kind in ("premise", "structure"):
        set_header_field(premise_path(project), "version", str(rounds))
        set_header_field(premise_path(project), "rounds", str(rounds))
        if args.lock:
            set_header_field(premise_path(project), "status", "locked")
            set_header_field(premise_path(project), "locked_at", json.dumps(now_stamp(), ensure_ascii=False))
        hashes = hashes_for(project, args.kind)
        shutil.copy2(premise_path(project), snapshot_path(project, event_id) / "premise.yaml")

    entry = {
        "id": event_id,
        "time": now_stamp(),
        "kind": args.kind,
        "author": args.author,
        "summary": args.record,
        "input": args.input,
        "diff": changed,
        "propagated": propagated(project, previous, hashes),
        "status": load_premise(project).get("status", "draft") if args.kind != "text" else "n/a",
        "hashes": hashes,
        "snapshot": snapshot,
    }
    if args.kind == "text":
        entry["text"] = text_stats(project)
    append_log(project, entry)

    print(f"recorded {event_id} ({args.kind}) → history/log.jsonl")
    print(f"  summary   : {args.record}")
    if args.input:
        print(f"  input     : {args.input}")
    print(f"  snapshot  : {snapshot}/")
    if not changed and args.kind != "text" and not args.lock:
        print("  note      : 这一轮没有任何字段变化；如果只是复述，不必单独记一轮")
    if isinstance(changed, dict) and len(changed) == 1 and "created" in changed:
        print("  fields    : (first round)")
    elif isinstance(changed, dict) and len(changed) == 1 and "removed" in changed:
        print("  fields    : (premise removed)")
    else:
        print(f"  fields    : {len(changed)} changed")
    for line in entry["propagated"]:
        print(f"  propagated: {line}")
    print(f"  hashes    : " + ", ".join(f"{key}={value[:8]}" for key, value in hashes.items()))
    print("\nnext:")
    print(f"  python3 scripts/premise_log.py {project} --verify")
    print(f"  python3 scripts/brief_check.py {project}")
    print(f"  git -C {project} add -A && git -C {project} commit -m \"{event_id}: {args.record}\"")
    return 0


def do_list(project: Path, events: list[dict[str, Any]]) -> int:
    if not events:
        print("no rounds recorded yet; start with --record \"初始提案\"")
        return 0
    print(f"# {len(events)} round(s)")
    print(f"{'id':<20}{'time':<21}{'kind':<10}{'author':<8}{'status':<8}summary")
    for event in events:
        print(f"{event.get('id', '?'):<20}{event.get('time', ''):<21}{event.get('kind', ''):<10}"
              f"{event.get('author', ''):<8}{str(event.get('status', '')):<8}{event.get('summary', '')}")
    return 0


def do_show(project: Path, events: list[dict[str, Any]], event_id: str) -> int:
    event = next((item for item in events if item.get("id") == event_id), None)
    if event is None:
        print(f"ERROR: no round {event_id!r} in history/log.jsonl")
        return 2
    print(f"# {event['id']} · {event['time']} · {event['kind']} · by {event['author']}")
    print(f"- summary: {event.get('summary', '')}")
    if event.get("input"):
        print(f"- input  : {event['input']}")
    print(f"- status : {event.get('status')}")
    print(f"- files  : " + ", ".join(f"{key}={value[:8]}" for key, value in (event.get("hashes") or {}).items()))
    changed = event.get("diff") or {}
    print(f"\n## Changed fields ({len(changed)})")
    for key, value in list(changed.items())[:40]:
        if isinstance(value, dict) and "from" in value:
            print(f"- {key}: {value['from']!r} → {value['to']!r}")
        elif isinstance(value, dict) and ("added" in value or "removed" in value):
            for item in value.get("added") or []:
                print(f"- {key}: + {item}")
            for item in value.get("removed") or []:
                print(f"- {key}: - {item}")
        else:
            print(f"- {key}: {value}")
    if event.get("propagated"):
        print("\n## Propagated")
        print("\n".join(f"- {line}" for line in event["propagated"]))
    snapshot = project / (event.get("snapshot") or "")
    if (snapshot / "premise.yaml").is_file():
        print(f"\n## Snapshot\n- {snapshot.relative_to(project)}/premise.yaml")
    return 0


def do_diff(project: Path, events: list[dict[str, Any]], pair: list[str]) -> int:
    from_id, to_id = pair
    known = {event.get("id"): event for event in events}
    missing = [item for item in (from_id, to_id) if item not in known]
    if missing:
        print(f"ERROR: unknown round(s): {', '.join(missing)}")
        return 2
    before = snapshot_path(project, from_id) / "premise.yaml"
    after = snapshot_path(project, to_id) / "premise.yaml"
    if not after.is_file():
        print(f"ERROR: snapshot for {to_id} is missing ({after})")
        return 2
    print(f"# diff {from_id} → {to_id}")
    print(f"- {from_id}: {known[from_id].get('summary', '')}")
    print(f"- {to_id}: {known[to_id].get('summary', '')}")
    changed = field_diff(before, after)
    print(f"\n## Changed fields ({len(changed)})")
    for key, value in list(changed.items())[:60]:
        if isinstance(value, dict) and "from" in value:
            print(f"- {key}: {value['from']!r} → {value['to']!r}")
        else:
            print(f"- {key}: {value}")
    between = [event for event in events
               if from_id in known and to_id in known
               and events.index(known[from_id]) < events.index(event) <= events.index(known[to_id])]
    inputs = [f"- {event['id']} ({event.get('author')}): {event.get('input') or event.get('summary', '')}"
              for event in between if event.get("input") or event.get("summary")]
    if inputs:
        print("\n## Why (recorded inputs)")
        print("\n".join(inputs))
    return 0


def do_verify(project: Path, events: list[dict[str, Any]]) -> int:
    if not events:
        print("DRIFT: no rounds recorded; run --record first")
        return 1
    latest = latest_event(events)
    assert latest is not None
    current = hashes_for(project, str(latest.get("kind", "premise")))
    recorded = latest.get("hashes") or {}
    drifted = [key for key, value in recorded.items() if key in current and current[key] != value]
    print(f"# verify against {latest['id']} ({latest.get('kind')}, {latest.get('time')})")
    for key, value in recorded.items():
        state = "ok" if current.get(key) == value else ("drift" if key in current else "missing")
        print(f"- {key:<18} recorded={value[:8]:<10} current={str(current.get(key))[:8]:<10} {state}")
    if drifted:
        print(f"\nDRIFT: {', '.join(drifted)} changed since {latest['id']}; "
              f"record a new round (--record) so the change has a reason and a snapshot.")
        return 1
    print("\nOK: the working copy matches the last recorded round.")
    return 0


def do_restore(project: Path, events: list[dict[str, Any]], event_id: str, apply: bool) -> int:
    event = next((item for item in events if item.get("id") == event_id), None)
    if event is None:
        print(f"ERROR: no round {event_id!r} in history/log.jsonl")
        return 2
    snapshot = project / (event.get("snapshot") or "")
    if not snapshot.is_dir():
        print(f"ERROR: snapshot missing for {event_id} ({snapshot})")
        return 2
    files = sorted(path for path in snapshot.rglob("*") if path.is_file())
    print(f"# restore {event_id} ({event.get('summary', '')})")
    print(f"- snapshot: {snapshot.relative_to(project)}/ ({len(files)} file(s))")
    for path in files:
        print(f"  {path.relative_to(snapshot)} → {path.relative_to(snapshot)}")
    if not apply:
        print("\n(dry run) add --apply to write these files back. A pre-restore round is recorded first.")
        print(f"  python3 scripts/premise_log.py {project} --restore {event_id} --apply")
        return 0

    before_id = next_event_id(events, "premise")
    write_snapshot(project, f"{before_id}-pre-restore")
    append_log(project, {
        "id": f"{before_id}-pre-restore",
        "time": now_stamp(),
        "kind": "premise",
        "author": "agent",
        "summary": f"回退到 {event_id} 之前的状态",
        "input": "",
        "diff": {},
        "propagated": [],
        "status": load_premise(project).get("status", "draft") if load_premise(project) else "draft",
        "hashes": hashes_for(project, "premise"),
        "snapshot": f"history/snapshots/{before_id}-pre-restore",
    })
    restored = []
    for path in files:
        relative = path.relative_to(snapshot)
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        restored.append(str(relative))
    print(f"\nrestored {len(restored)} file(s): " + ", ".join(restored))
    print(f"pre-restore state kept as history/snapshots/{before_id}-pre-restore/")

    # The pre-restore event records the state we left behind (the safety net).
    # This second event makes the log's newest baseline the state we restored
    # to, so --verify and brief_check agree with the working copy again.
    after_id = next_event_id(events + [{"id": f"{before_id}-pre-restore"}], "premise")
    write_snapshot(project, f"{after_id}-restored")
    append_log(project, {
        "id": f"{after_id}-restored",
        "time": now_stamp(),
        "kind": "premise",
        "author": "agent",
        "summary": f"已回退到 {event_id}",
        "input": "",
        "diff": {},
        "propagated": [],
        "restored_from": event_id,
        "status": load_premise(project).get("status", "draft") if load_premise(project) else "draft",
        "hashes": hashes_for(project, "premise"),
        "snapshot": f"history/snapshots/{after_id}-restored",
    })
    print(f"recorded {after_id}-restored as the new baseline (restored_from={event_id})")

    check = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "brief_check.py"), str(project)],
        capture_output=True, text=True,
    )
    tail = [line for line in check.stdout.splitlines() if line.startswith(("PASS", "FAIL"))]
    print(f"brief_check exit={check.returncode}: {tail[0] if tail else ''}")
    if check.returncode != 0:
        print("restore is not clean — fix the findings above before writing.")
    return 1 if check.returncode not in (0,) else 0


def main() -> int:
    args = parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"ERROR: project directory not found: {project}")
        return 2
    try:
        events = read_log(project)
    except ProjectYAMLError as error:
        print(f"ERROR: {error}")
        return 2

    if args.record:
        return do_record(project, args)
    if args.show:
        return do_show(project, events, args.show)
    if args.diff:
        return do_diff(project, events, args.diff)
    if args.restore:
        return do_restore(project, events, args.restore, args.apply)
    if args.verify:
        return do_verify(project, events)
    if args.lock:
        print("ERROR: --lock only makes sense together with --record")
        return 2
    return do_list(project, events)


if __name__ == "__main__":
    raise SystemExit(main())
