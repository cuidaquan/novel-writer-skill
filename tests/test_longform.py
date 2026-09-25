"""Long-form continuity tests: twelve chapters, handoff, drift and replay."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENTENCE = "他把纸条摊在桌上，灯下的字迹被水汽晕开，只剩半行还能辨认。"

CHAPTER_PLAN = {
    1: {"advance": ["main"], "plant": ["f-1"], "relationship": True},
    2: {"advance": ["main"]},
    3: {"advance": ["sub"]},
    4: {"relationship": True},
    5: {"advance": ["main"], "revelation_touch": ["secret"]},
    6: {"advance": ["main"]},
    7: {"advance": ["sub"]},
    8: {"advance": ["main"], "pay_off": ["f-1"], "revelation_reveal": ["secret"]},
    9: {"advance": ["sub"]},
    10: {"advance": ["main"]},
    11: {"advance": ["main"]},
    12: {"advance": ["main", "sub"]},
}


def run_script(script: str, *args: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
    )
    if ok and result.returncode != 0:
        raise AssertionError(f"{script} failed:\n{result.stdout}\n{result.stderr}")
    return result


def transaction(number: int) -> dict:
    plan = CHAPTER_PLAN[number]
    tx: dict = {
        "expected_chapter": number - 1,
        "chapter": number,
        "chapter_title": f"第{number}章",
        "summary": f"第{number}章推进。",
    }
    updates = {thread: {"status": "open"} for thread in plan.get("advance", [])}
    if number == 12:
        for thread in ("main", "sub"):
            updates[thread] = {"status": "resolved"}
    if updates:
        tx["plot_thread_updates"] = updates
    if plan.get("relationship"):
        tx["relationship_updates"] = {"hero__partner": {"trust": "low" if number == 1 else "high"}}
    if plan.get("plant"):
        tx["foreshadowing_updates"] = {"f-1": {"status": "active", "note": "first"}}
    if number == 8:
        tx["foreshadowing_updates"] = {"f-1": {"status": "resolved", "resolved_chapter": 8}}
    if plan.get("revelation_touch"):
        tx["revelation_updates"] = {"secret": {"known_by": ["hero"]}}
    if plan.get("revelation_reveal"):
        tx["revelation_updates"] = {"secret": {"reader_known": True, "revealed_chapter": 8}}
    if number == 11:
        tx["handoff"] = {"carry_over": ["main", "sub"], "notes": ["两条线仍待收束"]}
    if number == 12:
        tx["relationship_updates"] = {"hero__partner": {"status": "resolved"}}
        tx["handoff"] = {"carry_over": [], "notes": []}
    return tx


def card(number: int) -> str:
    plan = CHAPTER_PLAN[number]
    return (
        f"chapter: {number}\n"
        f"title: 第{number}章\n"
        "viewpoint: hero\n"
        "target_words: 100\n"
        "goal: 推进主线\n"
        "conflict: 有人阻挠\n"
        "change:\n"
        "  plot: 局势变化\n"
        "context:\n"
        "  characters: [hero]\n"
        "  world: []\n"
        "threads:\n"
        f"  advance: {plan.get('advance', [])}\n"
        "  touch: []\n"
        "foreshadowing:\n"
        f"  plant: {plan.get('plant', [])}\n"
        f"  pay_off: {plan.get('pay_off', [])}\n"
        "revelations:\n"
        f"  touch: {plan.get('revelation_touch', [])}\n"
        f"  reveal: {plan.get('revelation_reveal', [])}\n"
    )


MASTER = """# 总纲
## 故事承诺
- 主角：调查员
- 核心欲望：找到真相
- 最大阻力：线索被篡改
- 失败代价：真相沉没
- 核心读者回报：拼出真相
- 结局状态：真相大白，主角失去职位
- 主角从什么状态变到什么状态：从退缩到承担
- 主类型承诺将在何处兑现：第十二章
"""


class LongFormProject(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "novel"
        run_script("init_novel.py", self.project, "--title", "长程测试")
        novel_path = self.project / "novel.yaml"
        novel = novel_path.read_text(encoding="utf-8")
        novel = novel.replace("target_words: null", "target_words: 1200")
        novel = novel.replace("target_chapters: null", "target_chapters: 12")
        novel = novel.replace("viewpoint_characters: []", "viewpoint_characters: [hero]")
        novel_path.write_text(novel, encoding="utf-8")
        (self.project / "characters" / "hero.yaml").write_text(
            "id: hero\nname: 主角\ncore:\n  desire: 找到真相\n  fear: 失去线索\n",
            encoding="utf-8",
        )
        (self.project / "outline" / "master.md").write_text(MASTER, encoding="utf-8")
        for number in range(1, 13):
            (self.project / "control-cards" / f"chapter-{number:04d}.yaml").write_text(card(number), encoding="utf-8")
            (self.project / "chapters" / f"chapter-{number:04d}.md").write_text(
                f"# 第{number}章\n\n" + (SENTENCE * 8) + "\n",
                encoding="utf-8",
            )
        state_path = self.project / "state" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["plot_threads"] = {"main": {"status": "open"}, "sub": {"status": "open"}}
        state["foreshadowing"] = {"f-1": {"status": "planted"}}
        state["relationships"] = {"hero__partner": {"trust": "medium", "status": "open"}}
        state["characters"] = {"hero": {"location": "旧城"}}
        state["revelations"] = {"secret": {"truth": "钥匙在钟楼", "known_by": [], "reader_known": False}}
        payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
        state_path.write_text(payload, encoding="utf-8")
        (self.project / "state" / "initial.json").write_text(payload, encoding="utf-8")

    def commit(self, number: int) -> None:
        tx_path = Path(self.temp.name) / f"tx-{number}.json"
        tx_path.write_text(json.dumps(transaction(number), ensure_ascii=False) + "\n", encoding="utf-8")
        run_script("state_commit.py", self.project / "state" / "state.json", tx_path)

    def state(self) -> dict:
        return json.loads((self.project / "state" / "state.json").read_text(encoding="utf-8"))

    def test_twelve_chapter_end_to_end(self) -> None:
        for number in range(1, 6):
            self.commit(number)

        context = run_script("build_context.py", self.project, "--compact-state", "--chapter", 6).stdout
        self.assertIn('"handoff"', context)
        self.assertIn("active_pressure", context)
        self.assertIn("Compact view omitted", context)
        self.assertIn("revelations.truth is author-only", context)
        self.assertIn("State current chapter: 5", context)

        review = run_script("review_chapter.py", self.project, "--chapter", 6, ok=False)
        self.assertEqual(review.returncode, 0)

        for number in range(6, 13):
            self.commit(number)
        run_script("project_check.py", self.project, "--complete")

        rebuilt = run_script("state_rebuild.py", self.project).stdout
        state = self.state()
        self.assertEqual(json.loads(rebuilt), state)
        self.assertEqual(state["handoff"]["chapter"], 12)
        self.assertEqual(state["handoff"]["carry_over"], [])
        self.assertTrue(state["revelations"]["secret"]["reader_known"])
        self.assertEqual(state["revelations"]["secret"]["known_by"], ["hero"])
        self.assertEqual(state["plot_threads"]["main"]["status"], "resolved")
        self.assertEqual(state["foreshadowing"]["f-1"]["status"], "resolved")

    def test_old_chapter_replay_keeps_single_truth(self) -> None:
        for number in range(1, 13):
            self.commit(number)
        run_script("project_check.py", self.project, "--complete")

        first = self.project / "state" / "transactions" / "chapter-0001.json"
        data = json.loads(first.read_text(encoding="utf-8"))
        data["foreshadowing_updates"]["f-1"]["note"] = "rewritten"
        first.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")

        self.assertIn("differs from replayed", run_script("project_check.py", self.project, ok=False).stdout)
        run_script("state_rebuild.py", self.project, "--write")
        state = self.state()
        self.assertEqual(state["foreshadowing"]["f-1"]["note"], "rewritten")
        run_script("project_check.py", self.project, "--complete")

    def test_budget_reports_largest_sources_and_fit_trims(self) -> None:
        for number in range(1, 6):
            self.commit(number)
        over = run_script(
            "build_context.py", self.project, "--compact-state", "--chapter", 6, "--max-chars", "1200", ok=False
        )
        self.assertNotEqual(over.returncode, 0)
        self.assertIn("largest sources:", over.stderr)

        full = run_script("build_context.py", self.project, "--compact-state", "--chapter", 6).stdout
        budget = len(full) - 200
        fitted = run_script(
            "build_context.py", self.project, "--compact-state", "--chapter", 6, "--max-chars", str(budget), "--fit"
        )
        self.assertIn("# Chapter Context", fitted.stdout)
        self.assertLessEqual(len(fitted.stdout), budget)

    def test_compact_view_tiers_active_pressure_under_budget(self) -> None:
        state_path = self.project / "state" / "state.json"
        state = self.state()
        state["plot_threads"] = {f"t{index:03d}": {"status": "open"} for index in range(150)}
        state["foreshadowing"] = {f"f{index:03d}": {"status": "active"} for index in range(60)}
        state["project"]["current_chapter"] = 5
        state["handoff"] = {"chapter": 5, "carry_over": ["t000", "t001"], "notes": ["长期压力"]}
        payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
        state_path.write_text(payload, encoding="utf-8")
        (self.project / "state" / "initial.json").write_text(payload, encoding="utf-8")
        card6 = self.project / "control-cards" / "chapter-0006.yaml"
        card6.write_text(
            card6.read_text(encoding="utf-8").replace("advance: ['main']", "advance: ['main', 't005']"),
            encoding="utf-8",
        )

        context = run_script(
            "build_context.py", self.project, "--compact-state", "--chapter", 6, "--max-chars", "12000"
        ).stdout
        self.assertLessEqual(len(context), 12000)
        focused_text = context.split("focused view", 1)[1]
        focused = json.loads(focused_text[focused_text.index("{"):focused_text.rindex("}") + 1])
        self.assertEqual(focused["handoff"]["carry_over"], ["t000", "t001"])
        self.assertIn("t000", focused["plot_threads"])
        self.assertIn("t005", focused["plot_threads"])
        self.assertEqual(len(focused["active_pressure"]), 40)
        self.assertEqual(focused["active_pressure_omitted"], 211 - 40)
        self.assertIn("Full active list: run scripts/handoff_report.py", context)

        limited = run_script(
            "build_context.py", self.project, "--compact-state", "--chapter", 6, "--active-limit", "0"
        ).stdout
        limited_text = limited.split("focused view", 1)[1]
        limited_data = json.loads(limited_text[limited_text.index("{"):limited_text.rindex("}") + 1])
        self.assertEqual(limited_data["active_pressure"], [])
        self.assertEqual(limited_data["active_pressure_omitted"], 211)

        over = run_script(
            "build_context.py", self.project, "--compact-state", "--chapter", 6, "--max-chars", "1500", ok=False
        )
        self.assertEqual(over.returncode, 1)
        self.assertIn("largest sources:", over.stderr)

        full = run_script("build_context.py", self.project, "--compact-state", "--chapter", 6).stdout
        budget = len(full) - 300
        fitted = run_script(
            "build_context.py", self.project, "--compact-state", "--chapter", 6, "--fit", "--max-chars", str(budget)
        )
        self.assertLessEqual(len(fitted.stdout), budget)
        self.assertIn("Trimmed for --max-chars", fitted.stdout)

    def test_handoff_report_after_completion(self) -> None:
        for number in range(1, 13):
            self.commit(number)
        report = run_script("handoff_report.py", self.project, "--stale", "3").stdout
        self.assertIn("# Handoff Report", report)
        self.assertIn("Explicit carry-over", report)
        self.assertIn("Active pressure (0)", report)


class HandoffReport(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "novel"
        run_script("init_novel.py", self.project, "--title", "交接报告")
        state_path = self.project / "state" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["plot_threads"] = {
            "case": {"status": "open"},
            "old": {"status": "open"},
            "romance": {"status": "paused", "note": "主角暂时离开旧城"},
        }
        state["foreshadowing"] = {"clue": {"status": "active"}}
        state["relationships"] = {"hero__partner": {"status": "open"}}
        state["project"]["current_chapter"] = 5
        state["handoff"] = {"chapter": 5, "carry_over": ["case", "clue"], "notes": ["证人的安全仍受威胁"]}
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for number in range(1, 6):
            tx: dict = {
                "expected_chapter": number - 1,
                "chapter": number,
                "summary": "推进。",
            }
            if number == 5:
                tx["plot_thread_updates"] = {
                    "case": {"status": "open"},
                    "clue": {"status": "active"},
                    "romance": {"status": "paused", "note": "主角暂时离开旧城"},
                }
            elif number == 4:
                tx["relationship_updates"] = {"hero__partner": {"trust": "low"}}
            else:
                tx["plot_thread_updates"] = {"case": {"status": "open"}}
            if number == 5:
                tx["handoff"] = {"carry_over": ["case", "clue"], "notes": ["证人的安全仍受威胁"]}
            (self.project / "state" / "transactions" / f"chapter-{number:04d}.json").write_text(
                json.dumps(tx, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    def test_stale_and_paused_are_separated(self) -> None:
        report = run_script("handoff_report.py", self.project, "--stale", "3").stdout
        self.assertIn("case (plot thread, status open, last touched chapter 5)", report)
        self.assertIn("证人的安全仍受威胁", report)
        stale = report.split("## Stale hints")[1].split("## Paused")[0]
        self.assertIn("old", stale)
        self.assertNotIn("romance", stale)
        paused = report.split("## Paused")[1]
        self.assertIn("romance", paused)
        self.assertIn("主角暂时离开旧城", paused)


if __name__ == "__main__":
    unittest.main()
