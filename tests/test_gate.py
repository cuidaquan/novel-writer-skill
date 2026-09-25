"""Regression tests for the v1.1 commit gate and acknowledgement trail."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENTENCE = "他把纸条摊在桌上，灯下的字迹被水汽晕开，只剩半行还能辨认。"
CARD = """chapter: 1
title: 第一章
viewpoint: hero
target_words: 100
goal: 找线索
conflict: 阻挠
change:
  plot: 推进
context:
  characters: [hero]
  world: []
"""


def run_script(script: str, *args: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
    )
    if ok and result.returncode != 0:
        raise AssertionError(f"{script} failed:\n{result.stdout}\n{result.stderr}")
    return result


class CommitGate(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "novel"
        run_script("init_novel.py", self.project, "--title", "门禁测试")
        novel_path = self.project / "novel.yaml"
        novel = novel_path.read_text(encoding="utf-8")
        novel = novel.replace("target_words: null", "target_words: 100")
        novel = novel.replace("target_chapters: null", "target_chapters: 1")
        novel = novel.replace("viewpoint_characters: []", "viewpoint_characters: [hero]")
        novel_path.write_text(novel, encoding="utf-8")
        (self.project / "characters" / "hero.yaml").write_text(
            "id: hero\nname: 主角\ncore:\n  desire: 找真相\n  fear: 失去线索\n", encoding="utf-8"
        )
        (self.project / "control-cards" / "chapter-0001.yaml").write_text(CARD, encoding="utf-8")
        self.body = self.project / "chapters" / "chapter-0001.md"
        self.body.write_text("# 第一章\n\n" + SENTENCE * 8 + "\n", encoding="utf-8")
        self.state = self.project / "state" / "state.json"
        self.journal = self.project / "state" / "transactions" / "chapter-0001.json"

    def transaction(self) -> dict:
        return {"expected_chapter": 0, "chapter": 1, "chapter_title": "第一章", "summary": "推进。"}

    def commit(self, *extra: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        tx_path = self.root / "tx.json"
        tx_path.write_text(json.dumps(self.transaction(), ensure_ascii=False) + "\n", encoding="utf-8")
        return run_script("state_commit.py", self.state, tx_path, *extra, ok=ok)

    def test_blocking_marker_refuses_commit_without_writing(self) -> None:
        self.body.write_text("# 第一章\n\n" + SENTENCE * 8 + "\nTODO\n" + SENTENCE * 8 + "\n", encoding="utf-8")
        before = self.state.read_bytes()
        result = self.commit(ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("blocking review findings", result.stderr)
        self.assertIn("[placeholder]", result.stderr)
        self.assertFalse(self.journal.exists())
        self.assertEqual(before, self.state.read_bytes())

    def test_ordinary_dialogue_word_is_not_blocking(self) -> None:
        self.body.write_text("# 第一章\n\n" + SENTENCE * 6 + "\n“结果待定。”他说。\n" + SENTENCE * 3 + "\n", encoding="utf-8")
        self.assertEqual(self.commit().returncode, 0)
        review = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(review.returncode, 0)
        self.assertIn("[placeholder-hint]", review.stdout)

    def test_acknowledged_block_is_recorded_and_visible(self) -> None:
        self.body.write_text("# 第一章\n\n" + SENTENCE * 8 + "\nTODO\n" + SENTENCE * 8 + "\n", encoding="utf-8")
        self.assertEqual(self.commit("--allow", "placeholder", "--reason", "反派字条上确实是 TODO").returncode, 0)
        recorded = json.loads(self.journal.read_text(encoding="utf-8"))["acknowledged_blocks"]
        self.assertEqual(recorded, [{"check": "placeholder", "reason": "反派字条上确实是 TODO"}])
        check = run_script("project_check.py", self.project, ok=False)
        self.assertEqual(check.returncode, 0)
        self.assertIn("acknowledged placeholder", check.stdout)
        self.assertEqual(run_script("project_check.py", self.project, "--complete").returncode, 0)

    def test_removing_the_acknowledgement_fails_the_project_check(self) -> None:
        self.body.write_text("# 第一章\n\n" + SENTENCE * 8 + "\nTODO\n" + SENTENCE * 8 + "\n", encoding="utf-8")
        self.commit("--allow", "placeholder", "--reason", "临时放行")
        data = json.loads(self.journal.read_text(encoding="utf-8"))
        data.pop("acknowledged_blocks", None)
        self.journal.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        check = run_script("project_check.py", self.project, ok=False)
        self.assertEqual(check.returncode, 1)
        self.assertIn("[placeholder]", check.stdout)
        self.assertEqual(run_script("project_check.py", self.project, "--complete", ok=False).returncode, 1)

    def test_allow_requires_a_reason_and_a_reported_check(self) -> None:
        self.body.write_text("# 第一章\n\n" + SENTENCE * 8 + "\nTODO\n" + SENTENCE * 8 + "\n", encoding="utf-8")
        missing_reason = self.commit("--allow", "placeholder", ok=False)
        self.assertIn("requires a non-empty --reason", missing_reason.stderr)
        unknown = self.commit("--allow", "empty-body", "--reason", "n/a", ok=False)
        self.assertIn("not reported for chapter 1", unknown.stderr)
        self.assertFalse(self.journal.exists())

    def test_project_check_leaves_uncommitted_drafts_alone(self) -> None:
        self.assertEqual(self.commit().returncode, 0)
        (self.project / "control-cards" / "chapter-0002.yaml").write_text(
            CARD.replace("chapter: 1", "chapter: 2").replace("title: 第一章", "title: 第二章"), encoding="utf-8"
        )
        (self.project / "chapters" / "chapter-0002.md").write_text("# 第二章\n\nTODO\n", encoding="utf-8")
        result = run_script("project_check.py", self.project, ok=False)
        self.assertEqual(result.returncode, 0)

    def test_state_outside_a_project_is_refused(self) -> None:
        bare = self.root / "bare.json"
        bare.write_text(self.state.read_text(encoding="utf-8"), encoding="utf-8")
        tx_path = self.root / "tx-bare.json"
        tx_path.write_text(json.dumps(self.transaction(), ensure_ascii=False) + "\n", encoding="utf-8")
        result = run_script("state_commit.py", bare, tx_path, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot run the commit gate", result.stderr)


if __name__ == "__main__":
    unittest.main()
