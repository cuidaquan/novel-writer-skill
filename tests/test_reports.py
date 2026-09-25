"""Regression tests for the v1.3 progress, derived-view and stage-review commands."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENTENCE = "他把纸条摊在桌上，灯下的字迹被水汽晕开，只剩半行还能辨认。"


def run_script(script: str, *args: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
    )
    if ok and result.returncode != 0:
        raise AssertionError(f"{script} failed:\n{result.stdout}\n{result.stderr}")
    return result


def card_text(number: int, target_words: int = 100) -> str:
    return (
        f"chapter: {number}\n"
        f"title: 第{number}章\n"
        "viewpoint: hero\n"
        f"target_words: {target_words}\n"
        "goal: 找线索\n"
        "conflict: 阻挠\n"
        "change:\n"
        "  plot: 推进\n"
        "context:\n"
        "  characters: [hero]\n"
        "  world: []\n"
    )


class ReportingCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "novel"
        run_script("init_novel.py", self.project, "--title", "报告测试")
        novel_path = self.project / "novel.yaml"
        novel = novel_path.read_text(encoding="utf-8")
        novel = novel.replace("target_words: null", "target_words: 300")
        novel = novel.replace("target_chapters: null", "target_chapters: 3")
        novel = novel.replace("viewpoint_characters: []", "viewpoint_characters: [hero]")
        novel_path.write_text(novel, encoding="utf-8")
        (self.project / "characters" / "hero.yaml").write_text(
            "id: hero\nname: 主角\ncore:\n  desire: 找真相\n  fear: 失去线索\n", encoding="utf-8"
        )
        (self.project / "outline" / "master.md").write_text(
            "# 总纲\n## 故事承诺\n- 主角：调查员\n- 核心欲望：找到真相\n- 最大阻力：线索被篡改\n"
            "- 失败代价：真相沉没\n- 核心读者回报：拼出真相\n- 结局状态：真相大白\n"
            "- 主角从什么状态变到什么状态：从退缩到承担\n- 主类型承诺将在何处兑现：终章\n",
            encoding="utf-8",
        )
        for number in range(1, 4):
            (self.project / "control-cards" / f"chapter-{number:04d}.yaml").write_text(
                card_text(number), encoding="utf-8"
            )
            (self.project / "chapters" / f"chapter-{number:04d}.md").write_text(
                f"# 第{number}章\n\n" + SENTENCE * 8 + "\n", encoding="utf-8"
            )
        for number in (1, 2):
            self.commit(number)

    def commit(self, number: int) -> None:
        tx_path = Path(self.temp.name) / f"tx-{number}.json"
        tx_path.write_text(
            json.dumps(
                {
                    "expected_chapter": number - 1,
                    "chapter": number,
                    "chapter_title": f"第{number}章",
                    "summary": f"第{number}章推进。",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        run_script("state_commit.py", self.project / "state" / "state.json", tx_path)

    def test_progress_report_shows_plan_and_projection(self) -> None:
        report = run_script("progress_report.py", self.project).stdout
        self.assertIn("- Committed chapters: 2 / 3", report)
        self.assertIn("Written words:", report)
        self.assertIn("- Remaining chapters: 1", report)
        self.assertIn("- Projected words at the current pace:", report)
        self.assertIn("## Unsettled items", report)

    def test_state_view_roundtrip_and_staleness(self) -> None:
        view = Path(self.temp.name) / "state-view.md"
        run_script("state_view.py", self.project, "--write", view)
        content = view.read_text(encoding="utf-8")
        self.assertIn("NOT a source of truth", content)
        self.assertIn("## Revelations (author truth)", content)
        self.assertEqual(run_script("state_view.py", self.project, "--check", view).returncode, 0)

        state_path = self.project / "state" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["continuity_notes"].append("新备注")
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        stale = run_script("state_view.py", self.project, "--check", view, ok=False)
        self.assertEqual(stale.returncode, 1)
        self.assertIn("STALE", stale.stdout)

    def test_stage_review_aggregates_sections(self) -> None:
        result = run_script("stage_review.py", self.project)
        self.assertIn("# Stage Review", result.stdout)
        for section in ("Progress", "Handoff", "Promises", "Style profile"):
            self.assertIn(f"## {section} (scripts/", result.stdout)
        self.assertIn("this aggregator adds no state logic", result.stdout)

    def test_context_annotates_genre_modules(self) -> None:
        context = run_script("build_context.py", self.project, "--chapter", 3).stdout
        self.assertIn("- Genre modules: none; no module for: urban (generic path)", context)

        novel_path = self.project / "novel.yaml"
        novel_path.write_text(
            novel_path.read_text(encoding="utf-8").replace("primary: urban", "primary: mystery"),
            encoding="utf-8",
        )
        context = run_script("build_context.py", self.project, "--chapter", 3).stdout
        self.assertIn("- Genre modules: mystery", context)
        self.assertNotIn("no module for", context)


if __name__ == "__main__":
    unittest.main()
