"""End-to-end checks for a small completed and revised novel project."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_script(script: str, *args: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
    )
    if ok and result.returncode != 0:
        raise AssertionError(f"{script} failed:\n{result.stdout}\n{result.stderr}")
    return result


class NovelProjectWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "novel"
        run_script("init_novel.py", self.project, "--title", "测试故事")
        novel = (self.project / "novel.yaml").read_text(encoding="utf-8")
        novel = novel.replace("target_words: null", "target_words: 100")
        novel = novel.replace("target_words: 100", "target_words: 100 # planning target")
        novel = novel.replace("target_chapters: null", "target_chapters: 2")
        novel = novel.replace("viewpoint_characters: []", "viewpoint_characters: [hero]")
        (self.project / "novel.yaml").write_text(novel, encoding="utf-8")
        (self.project / "characters" / "hero.yaml").write_text("id: hero\nname: 主角\n", encoding="utf-8")
        (self.project / "world" / "town.md").write_text("# 城镇\n", encoding="utf-8")
        for number in (1, 2):
            card = f"""chapter: {number}
title: 第{number}章
viewpoint: hero
target_words: 50
goal: 找到真相
conflict: 有人阻挠
context:
  characters: [hero]
  world: [town]
threads:
  advance: [case]
  touch: []
foreshadowing:
  plant: [clue]
  pay_off: []
"""
            (self.project / "control-cards" / f"chapter-{number:04d}.yaml").write_text(card, encoding="utf-8")
            (self.project / "chapters" / f"chapter-{number:04d}.md").write_text(
                f"# 第{number}章\n" + "故事" * 30, encoding="utf-8"
            )

    def transaction(self, number: int) -> dict:
        return {
            "expected_chapter": number - 1,
            "chapter": number,
            "chapter_title": f"第{number}章",
            "summary": f"第{number}章发生了变化。",
            "character_updates": {"hero": {"location": "旧城"}} if number == 1 else {},
            "plot_thread_updates": {"case": {"status": "open" if number == 1 else "resolved"}},
            "foreshadowing_updates": {"clue": {"status": "planted"}} if number == 1 else {"clue": {"status": "resolved", "resolved_chapter": 2}},
            "timeline_events": [{"id": f"event-{number}", "event": "推进"}],
        }

    def save_transaction(self, number: int, tx: dict | None = None) -> Path:
        path = self.project / "state" / "transactions" / f"chapter-{number:04d}.json"
        path.write_text(json.dumps(tx or self.transaction(number), ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def commit(self, number: int) -> None:
        run_script("state_commit.py", self.project / "state" / "state.json", self.save_transaction(number))

    def test_complete_book_and_rebuild_after_revision(self) -> None:
        context = run_script("build_context.py", self.project, "--compact-state").stdout
        self.assertIn("characters/hero.yaml", context)
        self.assertIn("world/town.md", context)
        self.assertIn("State current chapter: 0", context)
        self.commit(1)
        self.assertEqual(run_script("project_check.py", self.project).returncode, 0)
        self.assertNotEqual(run_script("project_check.py", self.project, "--complete", ok=False).returncode, 0)
        self.commit(2)
        self.assertEqual(run_script("project_check.py", self.project, "--complete").returncode, 0)

        first = self.save_transaction(1)
        changed = json.loads(first.read_text(encoding="utf-8"))
        changed["character_updates"]["hero"]["location"] = "新城"
        first.write_text(json.dumps(changed, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertIn("differs from replayed", run_script("project_check.py", self.project, ok=False).stdout)
        old_state = Path(self.temp.name) / "before-one.json"
        run_script("state_rebuild.py", self.project, "--through", 0, "--output", old_state)
        old_context = run_script("build_context.py", self.project, "--chapter", 1, "--state", old_state).stdout
        self.assertIn("State current chapter: 0", old_context)
        run_script("state_rebuild.py", self.project, "--write")
        state = json.loads((self.project / "state" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["characters"]["hero"]["location"], "新城")
        run_script("project_check.py", self.project, "--complete")

    def test_invalid_transaction_does_not_change_state(self) -> None:
        self.commit(1)
        state_path = self.project / "state" / "state.json"
        before = state_path.read_bytes()
        bad = self.transaction(2)
        bad["timeline_events"][0]["id"] = "event-1"
        external = Path(self.temp.name) / "bad.json"
        external.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        result = run_script("state_commit.py", state_path, external, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate timeline id", result.stderr)
        self.assertEqual(before, state_path.read_bytes())
        self.assertFalse((self.project / "state" / "transactions" / "chapter-0002.json").exists())

    def test_complete_gate_catches_underlength_and_open_plot(self) -> None:
        self.commit(1)
        second = self.transaction(2)
        second["plot_thread_updates"]["case"]["status"] = "open"
        run_script("state_commit.py", self.project / "state" / "state.json", self.save_transaction(2, second))
        novel_path = self.project / "novel.yaml"
        novel_path.write_text(novel_path.read_text(encoding="utf-8").replace("target_words: 100 # planning target", "target_words: 1000"), encoding="utf-8")
        result = run_script("project_check.py", self.project, "--complete", ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("below 90%", result.stdout)
        self.assertIn("unresolved plot thread", result.stdout)

    def test_revelation_boundary_and_selected_modules(self) -> None:
        novel_path = self.project / "novel.yaml"
        novel = novel_path.read_text(encoding="utf-8")
        novel = novel.replace("primary: urban", "primary: mystery")
        novel = novel.replace("secondary: []", "secondary: [romance]")
        novel = novel.replace("modules: []", "modules: [suspense]")
        novel_path.write_text(novel, encoding="utf-8")

        state_dir = self.project / "state"
        initial = json.loads((state_dir / "initial.json").read_text(encoding="utf-8"))
        initial["revelations"] = {
            "hidden": {"truth": "钥匙在旧城", "known_by": [], "reader_known": False},
            "later": {"truth": "另一条秘密", "known_by": [], "reader_known": False},
        }
        for name in ("initial.json", "state.json"):
            (state_dir / name).write_text(json.dumps(initial, ensure_ascii=False) + "\n", encoding="utf-8")

        first_card = self.project / "control-cards" / "chapter-0001.yaml"
        first_card.write_text(first_card.read_text(encoding="utf-8") + "revelations:\n  touch: [hidden]\n  reveal: []\nstyle_modules: [intimacy]\n", encoding="utf-8")
        second_card = self.project / "control-cards" / "chapter-0002.yaml"
        second_card.write_text(second_card.read_text(encoding="utf-8") + "revelations:\n  touch: []\n  reveal: [hidden]\n", encoding="utf-8")

        context = run_script("build_context.py", self.project, "--compact-state").stdout
        for name in ("genres/mystery.md", "genres/romance.md", "style-modules/suspense.md", "style-modules/intimacy.md", "钥匙在旧城", "reader_known=false"):
            self.assertIn(name, context)
        self.assertNotIn("另一条秘密", context)

        first = self.transaction(1)
        first["revelation_updates"] = {"hidden": {"known_by": ["hero"]}}
        run_script("state_commit.py", state_dir / "state.json", self.save_transaction(1, first))
        self.assertEqual(run_script("project_check.py", self.project).returncode, 0)

        second = self.transaction(2)
        second["revelation_updates"] = {"hidden": {"reader_known": True, "revealed_chapter": 2}}
        (self.project / "chapters" / "chapter-0002.md").write_text("# 第二章\n钥匙在旧城。" + "故事" * 30, encoding="utf-8")
        run_script("state_commit.py", state_dir / "state.json", self.save_transaction(2, second))
        run_script("project_check.py", self.project, "--complete")
        run_script("state_rebuild.py", self.project, "--output", Path(self.temp.name) / "replayed.json")

        revoke = {"expected_chapter": 2, "chapter": 3, "summary": "错误撤销", "revelation_updates": {"hidden": {"reader_known": False}}}
        external = Path(self.temp.name) / "revoke.json"
        external.write_text(json.dumps(revoke, ensure_ascii=False), encoding="utf-8")
        before = (state_dir / "state.json").read_bytes()
        result = run_script("state_commit.py", state_dir / "state.json", external, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot become unknown", result.stderr)
        self.assertEqual(before, (state_dir / "state.json").read_bytes())

        revoke["revelation_updates"] = {"hidden": {"truth": "钥匙在新城"}}
        external.write_text(json.dumps(revoke, ensure_ascii=False), encoding="utf-8")
        result = run_script("state_commit.py", state_dir / "state.json", external, ok=False)
        self.assertIn("truth cannot change", result.stderr)
        self.assertEqual(before, (state_dir / "state.json").read_bytes())

    def test_reveal_requires_matching_chapter_and_plan(self) -> None:
        state_dir = self.project / "state"
        initial = json.loads((state_dir / "initial.json").read_text(encoding="utf-8"))
        initial["revelations"] = {"secret": {"truth": "门后有人", "known_by": [], "reader_known": False}}
        for name in ("initial.json", "state.json"):
            (state_dir / name).write_text(json.dumps(initial, ensure_ascii=False) + "\n", encoding="utf-8")
        tx = self.transaction(1)
        tx["revelation_updates"] = {"secret": {"reader_known": True, "revealed_chapter": 2}}
        result = run_script("state_commit.py", state_dir / "state.json", self.save_transaction(1, tx), ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must equal 1", result.stderr)
        self.assertEqual(initial, json.loads((state_dir / "state.json").read_text(encoding="utf-8")))

        tx["revelation_updates"]["secret"]["revealed_chapter"] = 1
        run_script("state_commit.py", state_dir / "state.json", self.save_transaction(1, tx))
        result = run_script("project_check.py", self.project, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing from control card", result.stdout)

    def test_unknown_style_module_is_rejected(self) -> None:
        card_path = self.project / "control-cards" / "chapter-0001.yaml"
        card_path.write_text(card_path.read_text(encoding="utf-8") + "style_modules: [missing-module]\n", encoding="utf-8")
        result = run_script("build_context.py", self.project, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown style module", result.stderr)


if __name__ == "__main__":
    unittest.main()
