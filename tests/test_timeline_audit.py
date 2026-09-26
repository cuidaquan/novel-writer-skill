"""Regression tests for the advisory timeline audit."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = "主卧是二房东，做直播的场控。她跟的那个主播排晚上七点到九点，所以她九点半到家，一两点睡。"
BACKWARDS = ["我回房间坐到天亮。", "天蒙蒙亮的时候——大概七点出头——我想通了一件事。", "六点半，楼下有动静了。"]
FLASHBACK = ["我回房间坐到天亮。", "天蒙蒙亮的时候——大概七点出头——我想通了一件事。", "昨天六点半，楼下也有过动静。"]


def run_script(*args: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "timeline_audit.py"), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
    )
    if ok and result.returncode != 0:
        raise AssertionError(f"timeline_audit failed:\n{result.stdout}\n{result.stderr}")
    return result


class TimelineAudit(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "novel"
        (self.project / "chapters").mkdir(parents=True)

    def write_chapter(self, number: int, *paragraphs: str) -> None:
        path = self.project / "chapters" / f"chapter-{number:04d}.md"
        path.write_text(f"# 第{number}章\n\n" + "\n\n".join(paragraphs) + "\n", encoding="utf-8")

    def test_recurring_arrangement_is_listed_for_human_check(self) -> None:
        self.write_chapter(1, SCHEDULE)
        result = run_script(self.project)
        self.assertIn("### Recurring arrangements (1)", result.stdout)
        self.assertIn("七点", result.stdout)
        self.assertIn("Check each of these against every scene", result.stdout)

    def test_hours_inside_an_arrangement_are_not_read_as_a_sequence(self) -> None:
        self.write_chapter(1, SCHEDULE)
        result = run_script(self.project)
        self.assertIn("### Out-of-order clock times inside one scene (0)", result.stdout)

    def test_backwards_clocks_in_one_scene_are_flagged(self) -> None:
        self.write_chapter(1, *BACKWARDS)
        result = run_script(self.project)
        self.assertIn("### Out-of-order clock times inside one scene (1)", result.stdout)
        self.assertIn("retime one of them", result.stdout)

    def test_a_flashback_marker_is_not_flagged(self) -> None:
        self.write_chapter(1, *FLASHBACK)
        result = run_script(self.project)
        self.assertIn("### Out-of-order clock times inside one scene (0)", result.stdout)

    def test_bare_yi_is_not_a_clock_but_a_qualified_one_is(self) -> None:
        self.write_chapter(1, "布很薄，留着一股洗衣粉味，底下压着一点樟脑丸的味道。")
        self.write_chapter(2, "凌晨一点，他还没睡。")
        result = run_script(self.project)
        chapter_one = result.stdout.split("## Chapter 2")[0]
        self.assertIn("### Clock expressions in reading order (0)", chapter_one)
        self.assertIn("凌晨一点", result.stdout)

    def test_summary_mode_reports_counts_only(self) -> None:
        self.write_chapter(1, SCHEDULE, *BACKWARDS)
        result = run_script(self.project, "--summary")
        self.assertIn("clock expressions", result.stdout)
        self.assertNotIn("### Recurring arrangements", result.stdout)

    def test_usage_errors_exit_two(self) -> None:
        self.assertEqual(run_script(self.project / "missing", ok=False).returncode, 2)
        self.assertEqual(run_script(self.project, ok=False).returncode, 2)
        self.write_chapter(1, SCHEDULE)
        self.assertEqual(run_script(self.project, "--chapter", 9, ok=False).returncode, 2)
        self.assertEqual(run_script(self.project, "--limit", 0, ok=False).returncode, 2)


if __name__ == "__main__":
    unittest.main()
