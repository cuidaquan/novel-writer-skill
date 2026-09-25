"""Regression tests for the v1.4 advisory prose lint."""

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


class ProseLint(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "novel"
        run_script("init_novel.py", self.project, "--title", "套路扫描")
        novel_path = self.project / "novel.yaml"
        novel = novel_path.read_text(encoding="utf-8")
        novel = novel.replace("viewpoint_characters: []", "viewpoint_characters: [hero]")
        novel_path.write_text(novel, encoding="utf-8")
        (self.project / "characters" / "hero.yaml").write_text(
            "id: hero\nname: 主角\ncore:\n  desire: 找真相\n  fear: 失去线索\n", encoding="utf-8"
        )
        (self.project / "control-cards" / "chapter-0001.yaml").write_text(CARD, encoding="utf-8")
        self.body = self.project / "chapters" / "chapter-0001.md"
        self.body.write_text(
            "# 第一章\n\n他仿佛听见了什么，仿佛又什么都没有听见……\n" + SENTENCE * 8 + "\n", encoding="utf-8"
        )

    def commit(self) -> None:
        tx_path = Path(self.temp.name) / "tx.json"
        tx_path.write_text(
            json.dumps(
                {"expected_chapter": 0, "chapter": 1, "chapter_title": "第一章", "summary": "推进。"},
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        run_script("state_commit.py", self.project / "state" / "state.json", tx_path)

    def test_no_rules_configured_by_default(self) -> None:
        result = run_script("prose_lint.py", self.project)
        self.assertEqual(result.returncode, 0)
        self.assertIn("no rules configured", result.stdout)

    def test_default_rules_report_word_repetition(self) -> None:
        result = run_script("prose_lint.py", self.project, "--default-rules")
        self.assertEqual(result.returncode, 0)
        self.assertIn("[lint-word]", result.stdout)
        self.assertIn("'仿佛' appears 2 time(s)", result.stdout)
        self.assertIn("Nothing here blocks a commit", result.stdout)

    def test_project_rules_report_patterns_and_punctuation(self) -> None:
        rules = self.project / "checks" / "prose-rules.json"
        rules.parent.mkdir(parents=True, exist_ok=True)
        rules.write_text(
            json.dumps(
                {
                    "words": [],
                    "patterns": [{"id": "hearing", "regex": "听见", "note": "重复的听觉描写"}],
                    "punctuation_per_100": {"…": 0.5},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result = run_script("prose_lint.py", self.project)
        self.assertIn("[lint-pattern]", result.stdout)
        self.assertIn("'hearing'", result.stdout)
        self.assertIn("[lint-punctuation]", result.stdout)
        self.assertIn("prose-rules.json", result.stdout)

    def test_invalid_regex_is_an_input_error(self) -> None:
        rules = Path(self.temp.name) / "bad.json"
        rules.write_text(json.dumps({"patterns": [{"regex": "["}]}), encoding="utf-8")
        result = run_script("prose_lint.py", self.project, "--rules", rules, ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("regex is invalid", result.stdout)

    def test_all_scans_committed_chapters(self) -> None:
        self.commit()
        result = run_script("prose_lint.py", self.project, "--all", "--default-rules")
        self.assertIn("# Prose Lint: all committed chapters", result.stdout)
        self.assertIn("## Chapter 1", result.stdout)


if __name__ == "__main__":
    unittest.main()
