"""Regression tests for the advisory cross-chapter duplicate scan."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRAME_LINE = "我醒过来的时候，后脑勺贴在地板上，凉得像一块铁案板。"
CLEAN_ONE = "他把伞收起来，靠在门边。雨水沿着伞骨滴到地砖上。"
CLEAN_TWO = "街口的红灯亮了很久，久到他把口袋里那张纸又折了一遍。"


def run_script(script: str, *args: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
    )
    if ok and result.returncode != 0:
        raise AssertionError(f"{script} failed:\n{result.stdout}\n{result.stderr}")
    return result


class DuplicateScan(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "novel"
        (self.project / "chapters").mkdir(parents=True)

    def write_chapter(self, number: int, *paragraphs: str) -> None:
        path = self.project / "chapters" / f"chapter-{number:04d}.md"
        path.write_text(f"# 第{number}章\n\n" + "\n\n".join(paragraphs) + "\n", encoding="utf-8")

    def test_clean_project_reports_nothing(self) -> None:
        self.write_chapter(1, CLEAN_ONE)
        self.write_chapter(2, CLEAN_TWO)
        result = run_script("duplicates.py", self.project)
        self.assertIn("## Duplicated paragraphs (0)", result.stdout)
        self.assertIn("## Duplicated sentences (0)", result.stdout)
        self.assertIn("## Near-duplicate sentences (0)", result.stdout)

    def test_copied_paragraph_and_sentence_are_reported_with_locations(self) -> None:
        self.write_chapter(1, CLEAN_ONE, CLEAN_TWO)
        self.write_chapter(2, CLEAN_ONE, CLEAN_TWO)
        result = run_script("duplicates.py", self.project)
        self.assertIn("## Duplicated paragraphs (2)", result.stdout)
        self.assertIn("chapter 1:3", result.stdout)
        self.assertIn("chapter 2:3", result.stdout)

    def test_a_deliberate_frame_echo_is_a_near_duplicate_not_a_copy(self) -> None:
        self.write_chapter(1, FRAME_LINE)
        self.write_chapter(2, "再" + FRAME_LINE)
        result = run_script("duplicates.py", self.project)
        self.assertIn("## Duplicated sentences (0)", result.stdout)
        self.assertIn("## Near-duplicate sentences (1)", result.stdout)
        self.assertIn("0.9", result.stdout)

    def test_motif_phrases_are_reported_as_advisory(self) -> None:
        self.write_chapter(1, "天花板上有一块水渍，形状像一条趴着的狗。", CLEAN_TWO)
        self.write_chapter(2, "天花板上有一块水渍，形状像一条趴着的狗，颜色深了一圈。", CLEAN_ONE)
        self.write_chapter(3, "他想起那块水渍，形状像一条趴着的狗。", CLEAN_ONE)
        result = run_script("duplicates.py", self.project, "--window", "6", "--min-count", "2")
        self.assertIn("Repeated 6-character phrases", result.stdout)
        self.assertIn("never blocks a commit", result.stdout)

    def test_usage_errors_exit_two(self) -> None:
        self.assertEqual(run_script("duplicates.py", self.project / "missing", ok=False).returncode, 2)
        self.write_chapter(1, CLEAN_ONE)
        self.assertEqual(run_script("duplicates.py", self.project, "--similarity", "0.2", ok=False).returncode, 2)
        self.assertEqual(run_script("duplicates.py", self.project, "--window", "1", ok=False).returncode, 2)


if __name__ == "__main__":
    unittest.main()
