"""Regression tests for post-draft chapter review and the advisory style report."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CLEAN_BODY = """# 第一章 雨夜

他把伞收起来，靠在门边。雨水沿着伞骨滴到地砖上。

“你迟到了。”她说。
"""

LONG_LINES = [
    "夜色像一层没有边缘的布，缓慢地覆盖了旧城区的屋顶和狭窄巷道。",
    "他沿着潮湿的台阶向下走，每一步都能听见鞋底与石面摩擦的细碎声响。",
    "远处传来火车经过铁桥时的震动，那声音让他想起多年前的一个同样安静的夜晚。",
    "墙上的水渍在灯光下显出某种模糊的形状，像是被人刻意涂抹过又重新掩盖。",
    "他把手伸进口袋，指尖碰到那张折了又折的纸条，纸边已经被汗水浸软。",
    "巷子尽头有一盏忽明忽暗的路灯，灯下停着一辆没有牌照的旧货车。",
    "他没有立刻靠近，而是站在阴影里数着货车轮胎上的泥点，试图判断它来自哪里。",
    "雨又下起来了，细密而耐心，把整条街洗成一面模糊的镜子。",
]

DIALOGUE_LINES = [
    "“你来了。”",
    "“嗯。”",
    "“东西呢？”",
    "“在车上。”",
    "“别骗我。”",
    "“我没骗你。”",
    "“打开看看。”",
    "“现在不行。”",
]

ROMANCE_LINES = [
    "他看着窗外。",
    "雨还在下。",
    "她没有回头。",
    "他也没有开口。",
    "沉默停在两个人之间。",
    "他说了再见。",
    "她轻轻点头。",
    "门在身后合上。",
]


def run_script(script: str, *args: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
    )
    if ok and result.returncode != 0:
        raise AssertionError(f"{script} failed:\n{result.stdout}\n{result.stderr}")
    return result


def card_text(number: int, goal: str = "找到线索", conflict: str = "有人阻挠", change: str = "主角拿到线索", viewpoint: str = "hero", target_words: object = 50) -> str:
    return (
        f"chapter: {number}\n"
        f"title: 第{number}章\n"
        f"viewpoint: {viewpoint}\n"
        f"target_words: {target_words}\n"
        f"goal: {goal}\n"
        f"conflict: {conflict}\n"
        "change:\n"
        f"  plot: {change}\n"
        "context:\n"
        "  characters: [hero]\n"
        "  world: []\n"
    )


class ReviewTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "novel"
        run_script("init_novel.py", self.project, "--title", "测试故事")

    def write_card(self, number: int, **fields: object) -> Path:
        path = self.project / "control-cards" / f"chapter-{number:04d}.yaml"
        path.write_text(card_text(number, **fields), encoding="utf-8")
        return path

    def write_body(self, number: int, text: str) -> Path:
        path = self.project / "chapters" / f"chapter-{number:04d}.md"
        path.write_text(text, encoding="utf-8")
        return path

    def set_current(self, number: int) -> None:
        state_path = self.project / "state" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["project"]["current_chapter"] = number
        if isinstance(state.get("handoff"), dict):
            state["handoff"]["chapter"] = number
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ChapterReview(ReviewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_card(1)
        self.write_body(1, CLEAN_BODY)

    def test_clean_chapter_passes_without_blocking(self) -> None:
        result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("PASS: no blocking findings", result.stdout)
        self.assertNotIn("BLOCK ", result.stdout)

    def test_report_carries_a_digest_of_the_reviewed_revision(self) -> None:
        """A stale report must be detectable: advisory findings are not re-run."""
        import re as regex

        first = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False).stdout
        digest = regex.search(r"- Body digest: sha256:([0-9a-f]{12})", first)
        self.assertIsNotNone(digest)

        again = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False).stdout
        self.assertIn(f"sha256:{digest.group(1)}", again)

        self.write_body(1, CLEAN_BODY + "\n他把窗关上了。\n")
        changed = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False).stdout
        self.assertNotIn(f"sha256:{digest.group(1)}", changed)

    def test_empty_body_is_a_blocking_finding(self) -> None:
        self.write_body(1, "\n\n")
        result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[empty-body]", result.stdout)
        self.assertIn("chapter-0001.md:1", result.stdout)

    def test_placeholder_lines_are_reported_with_numbers(self) -> None:
        self.write_body(1, "# 第一章\n\n他把伞收起来。\nTODO\n待补\n")
        result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("chapter-0001.md:4 [placeholder]", result.stdout)
        self.assertIn("chapter-0001.md:5 [placeholder]", result.stdout)
        self.assertIn("'TODO'", result.stdout)

    def test_dangling_punctuation_is_a_blocking_finding(self) -> None:
        self.write_body(1, "# 第一章\n\n他推开门，\n")
        result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[dangling-ending]", result.stdout)
        self.assertIn("chapter-0001.md:3", result.stdout)

    def test_unclosed_quote_is_a_blocking_finding(self) -> None:
        self.write_body(1, "# 第一章\n\n“你迟到了。\n")
        result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[unclosed-delimiter]", result.stdout)

    def test_straight_quotes_are_reviewed_like_full_width_quotes(self) -> None:
        """A manuscript written with ASCII quotes must not collect false notes."""
        self.write_body(1, '# 第一章\n\n雨停了。\n\n"你迟到了。"她说。\n')
        result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("[ending-punctuation]", result.stdout)
        self.assertNotIn("[unclosed-delimiter]", result.stdout)

        self.write_body(1, '# 第一章\n\n雨停了。\n\n"你迟到了。\n')
        broken = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(broken.returncode, 1)
        self.assertIn("[unclosed-delimiter]", broken.stdout)

    def test_unfilled_control_card_is_blocking(self) -> None:
        self.write_card(1, goal="")
        result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("[card-goal]", result.stdout)

    def test_missing_card_is_blocking_but_missing_body_is_an_input_error(self) -> None:
        (self.project / "control-cards" / "chapter-0001.yaml").unlink()
        card_result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(card_result.returncode, 1)
        self.assertIn("[card-missing]", card_result.stdout)

        (self.project / "chapters" / "chapter-0001.md").unlink()
        body_result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(body_result.returncode, 2)
        self.assertIn("ERROR:", body_result.stdout)

    def test_advisory_only_findings_keep_exit_code_zero(self) -> None:
        body = "# 第一章\n\n" + "\n\n".join("他走进房间，看见桌上的信件。" for _ in range(3)) + "\n"
        self.write_body(1, body)
        result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("PASS: no blocking findings", result.stdout)
        self.assertIn("[repeated-opening]", result.stdout)

    def test_review_is_read_only(self) -> None:
        state_path = self.project / "state" / "state.json"
        body_path = self.project / "chapters" / "chapter-0001.md"
        before_state = state_path.read_bytes()
        before_body = body_path.read_bytes()
        before_journal = sorted((self.project / "state" / "transactions").glob("*.json"))
        run_script("review_chapter.py", self.project, "--chapter", 1, "--style", ok=False)
        self.assertEqual(before_state, state_path.read_bytes())
        self.assertEqual(before_body, body_path.read_bytes())
        self.assertEqual(before_journal, sorted((self.project / "state" / "transactions").glob("*.json")))

    def test_default_chapter_is_the_next_uncommitted_chapter(self) -> None:
        result = run_script("review_chapter.py", self.project, ok=False)
        self.assertIn("# Chapter Review: chapter 1", result.stdout)


class StyleReport(ReviewTestCase):
    def build_project(self, name: str, genre: str, chapters: dict[int, str], current: int) -> Path:
        project = Path(self.temp.name) / name
        run_script("init_novel.py", project, "--title", name)
        novel_path = project / "novel.yaml"
        novel = novel_path.read_text(encoding="utf-8")
        novel = novel.replace("primary: urban", f"primary: {genre}")
        novel = novel.replace("viewpoint_characters: []", "viewpoint_characters: [hero]")
        novel_path.write_text(novel, encoding="utf-8")
        for number, text in chapters.items():
            (project / "chapters" / f"chapter-{number:04d}.md").write_text(text, encoding="utf-8")
            (project / "control-cards" / f"chapter-{number:04d}.yaml").write_text(card_text(number), encoding="utf-8")
        state_path = project / "state" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["project"]["current_chapter"] = current
        if isinstance(state.get("handoff"), dict):
            state["handoff"]["chapter"] = current
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return project

    def test_mystery_sample_reports_dialogue_drift(self) -> None:
        baseline = "# 第一章\n\n" + "\n\n".join(LONG_LINES) + "\n"
        target = "# 第三章\n\n" + "\n\n".join(DIALOGUE_LINES) + "\n"
        project = self.build_project("mystery", "mystery", {1: baseline, 2: baseline, 3: target}, 2)
        result = run_script("style_report.py", project, "--chapter", 3, ok=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Baseline chapters: 1, 2", result.stdout)
        self.assertIn("[style-dialogue-ratio]", result.stdout)

    def test_romance_sample_reports_sentence_drift(self) -> None:
        baseline = "# 第一章\n\n" + "\n\n".join(LONG_LINES) + "\n"
        target = "# 第三章\n\n" + "\n\n".join(ROMANCE_LINES) + "\n"
        project = self.build_project("romance", "romance", {1: baseline, 2: baseline, 3: target}, 2)
        result = run_script("style_report.py", project, "--chapter", 3, ok=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Baseline chapters: 1, 2", result.stdout)
        self.assertIn("[style-sentence-length]", result.stdout)

    def test_small_sample_reports_no_baseline_instead_of_guessing(self) -> None:
        project = self.build_project("tiny", "romance", {1: CLEAN_BODY}, 0)
        result = run_script("style_report.py", project, "--chapter", 1, ok=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Baseline: none", result.stdout)
        self.assertIn("baseline paragraphs", result.stdout)

    def test_style_report_never_fails_on_drift(self) -> None:
        baseline = "# 第一章\n\n" + "\n\n".join(LONG_LINES) + "\n"
        target = "# 第三章\n\n" + "\n\n".join(ROMANCE_LINES) + "\n"
        project = self.build_project("advisory", "urban", {1: baseline, 2: baseline, 3: target}, 2)
        result = run_script("style_report.py", project, "--chapter", 3, ok=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("These hints are advisory", result.stdout)


if __name__ == "__main__":
    unittest.main()
