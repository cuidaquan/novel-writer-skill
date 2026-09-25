"""Differentiated acceptance tests for style profiles, anchors and genre promises."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LONG_LINES = [
    "夜色像一层没有边缘的布，缓慢地覆盖了旧城区的屋顶和狭窄巷道。",
    "他沿着潮湿的台阶向下走，每一步都能听见鞋底与石面摩擦的细碎声响。",
    "远处传来火车经过铁桥时的震动，那声音让他想起多年前的一个同样安静的夜晚。",
    "墙上的水渍在灯光下显出某种模糊的形状，像是被人刻意涂抹过又重新掩盖。",
    "他把手伸进口袋，指尖碰到那张折了又折的纸条，纸边已经被汗水浸软。",
    "巷子尽头有一盏忽明忽暗的路灯，灯下停着一辆没有牌照的旧货车。",
    "他没有立刻靠近，而是站在阴影里数着货车轮胎上的泥点，试图判断它来自哪里。",
    "雨又下起来了，细密而耐心，把整条街洗成一面模糊的镜子。",
    "他想起很多年前也有人在这条街上等过他，只是他始终没有回头。",
    "钟楼的指针停在某个不该停下的位置，像一句没有说完的话。",
    "他决定先绕到仓库后面，从那里或许能看清货车车厢上的编号。",
    "脚下的积水映出他的影子，被风一吹就碎成了几段摇晃的轮廓。",
]

DIALOGUE_LINES = [
    "“你真的打算一个人进去吗？”她压低声音问他。",
    "“总得有人先走一步。”他把手电筒递给她。",
    "“里面可能有陷阱。”她盯着那扇半开的铁门。",
    "“所以我们才要一起进去。”他没有回头。",
    "“别把话说得那么好听。”她冷笑了一声。",
    "“我只是不想再失去一个人。”他声音很轻。",
    "“那你最好活着出来。”她握紧了手里的绳子。",
    "“会的。”他点了点头，推开了铁门。",
    "“等等。”她忽然叫住他，从口袋里掏出一样东西。",
    "“这是什么？”他借着微弱的光看了一眼。",
    "“你母亲留下的钥匙。”她把钥匙放进他掌心。",
    "“你一直带着它？”他愣在原地没有动。",
    "“现在不是问这个的时候。”她把他推进门里。",
    "“回去以后你要告诉我全部。”他低声说。",
    "“回去以后再说。”她替他把门轻轻掩上。",
    "黑暗里只剩下两个人的呼吸和远处的水声。",
]

MASTER = """# 总纲
## 故事承诺
- 主角：调查员
- 核心欲望：找到真相
- 最大阻力：线索被篡改
- 失败代价：真相沉没
- 核心读者回报：拼出真相
- 结局状态：真相大白
- 主角从什么状态变到什么状态：从退缩到承担
- 主类型承诺将在何处兑现：终章
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


def card_text(number: int, style_modules: str = "[]", payoff: str = "") -> str:
    text = (
        f"chapter: {number}\n"
        f"title: 第{number}章\n"
        "viewpoint: hero\n"
        "target_words: 100\n"
        "goal: 找线索\n"
        "conflict: 阻挠\n"
        "change:\n"
        "  plot: 推进\n"
        "context:\n"
        "  characters: [hero]\n"
        "  world: []\n"
        f"style_modules: {style_modules}\n"
    )
    return text + payoff


class ProjectFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def build(
        self,
        name: str,
        genre: str,
        texts: dict[int, str],
        current: int,
        cards: dict[int, str] | None = None,
        revelations: dict | None = None,
        relationships: dict | None = None,
        secondary: str = "",
    ) -> Path:
        project = Path(self.temp.name) / name
        run_script("init_novel.py", project, "--title", name)
        novel_path = project / "novel.yaml"
        novel = novel_path.read_text(encoding="utf-8")
        novel = novel.replace("primary: urban", f"primary: {genre}")
        if secondary:
            novel = novel.replace("secondary: []", f"secondary: [{secondary}]")
        novel = novel.replace("viewpoint_characters: []", "viewpoint_characters: [hero]")
        novel = novel.replace("target_words: null", "target_words: 5000")
        novel = novel.replace("target_chapters: null", "target_chapters: 12")
        novel_path.write_text(novel, encoding="utf-8")
        (project / "characters" / "hero.yaml").write_text(
            "id: hero\nname: 主角\ncore:\n  desire: 找真相\n  fear: 失去线索\n", encoding="utf-8"
        )
        (project / "outline" / "master.md").write_text(MASTER, encoding="utf-8")
        for number, text in texts.items():
            (project / "chapters" / f"chapter-{number:04d}.md").write_text(text, encoding="utf-8")
        for number, body in (cards or {}).items():
            (project / "control-cards" / f"chapter-{number:04d}.yaml").write_text(body, encoding="utf-8")
        state_path = project / "state" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["project"]["current_chapter"] = current
        state["handoff"]["chapter"] = current
        if revelations is not None:
            state["revelations"] = revelations
        if relationships is not None:
            state["relationships"] = relationships
        payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
        state_path.write_text(payload, encoding="utf-8")
        (project / "state" / "initial.json").write_text(payload, encoding="utf-8")
        return project


class StyleProfile(ProjectFixture):
    def test_two_genres_yield_distinct_bands(self) -> None:
        long_body = "# 第一章\n\n" + "\n\n".join(LONG_LINES) + "\n"
        dialogue_body = "# 第一章\n\n" + "\n\n".join(DIALOGUE_LINES) + "\n"
        mystery = self.build("mystery", "mystery", {1: long_body, 2: long_body}, 2)
        romance = self.build("romance", "romance", {1: dialogue_body, 2: dialogue_body}, 2)

        mystery_report = run_script("style_profile.py", mystery).stdout
        romance_report = run_script("style_profile.py", romance).stdout

        self.assertIn("chapters/chapter-0001.md", mystery_report)
        self.assertIn("dialogue_density: low", mystery_report)
        self.assertIn("dialogue_density: high", romance_report)
        self.assertIn("Only aggregate numbers are stored", mystery_report)

    def test_insufficient_sample_proposes_nothing(self) -> None:
        project = self.build("tiny", "urban", {1: "# 第一章\n\n短。\n"}, 1)
        result = run_script("style_profile.py", project, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("INSUFFICIENT", result.stdout)
        self.assertNotIn("Proposed novel.yaml style", result.stdout)


class StyleAnchor(ProjectFixture):
    def test_anchor_is_opt_in_and_coexists_with_card_override(self) -> None:
        texts = {number: "# 第一章\n\n" + "\n\n".join(LONG_LINES) + "\n" for number in range(1, 6)}
        cards = {number: card_text(number) for number in range(1, 7)}
        cards[6] = card_text(6, style_modules="[intimacy]")
        project = self.build("anchor", "mystery", texts, 5, cards=cards)

        without = run_script("build_context.py", project, "--chapter", 6).stdout
        self.assertNotIn("Style anchor", without)

        with_anchor = run_script("build_context.py", project, "--chapter", 6, "--style-anchor").stdout
        self.assertIn("Style anchor", with_anchor)
        self.assertIn("suggested style.sentence_length", with_anchor)
        self.assertIn("style-modules/intimacy.md", with_anchor)
        self.assertIn("- Information boundary", with_anchor)

    def test_anchor_reports_unavailable_without_sample(self) -> None:
        project = self.build("noanchor", "urban", {}, 0, cards={1: card_text(1)})
        result = run_script("build_context.py", project, "--chapter", 1, "--style-anchor").stdout
        self.assertIn("Style anchor: unavailable", result)


class PromiseReport(ProjectFixture):
    def _payoff_card(self, number: int, status: str, reason: str = "") -> str:
        payoff = f"payoff:\n  expected: 给出线索\n  status: {status}\n"
        if reason:
            payoff += f"  reason: {reason}\n"
        return card_text(number, payoff=payoff)

    def test_deferred_streak_and_genre_paths(self) -> None:
        cards = {
            1: self._payoff_card(1, "fulfilled"),
            2: self._payoff_card(2, "deferred", "先处理证人的安全"),
            3: self._payoff_card(3, "deferred", "围堵主线"),
            4: self._payoff_card(4, "deferred", "需要收束支线"),
        }
        texts = {number: "# 第一章\n\n" + "\n\n".join(LONG_LINES) + "\n" for number in range(1, 5)}
        project = self.build(
            "promise",
            "mystery",
            texts,
            4,
            cards=cards,
            revelations={"secret": {"truth": "钥匙在钟楼", "known_by": [], "reader_known": False}},
            relationships={"hero__partner": {"status": "open"}},
            secondary="romance",
        )
        for number in range(1, 5):
            tx: dict = {"expected_chapter": number - 1, "chapter": number, "summary": "推进。"}
            if number == 2:
                tx["revelation_updates"] = {"secret": {"known_by": ["hero"]}}
            if number == 3:
                tx["relationship_updates"] = {"hero__partner": {"trust": "low"}}
            (project / "state" / "transactions" / f"chapter-{number:04d}.json").write_text(
                json.dumps(tx, ensure_ascii=False) + "\n", encoding="utf-8"
            )

        report = run_script("promise_report.py", project, "--deferred-streak", "3").stdout
        self.assertIn("promise-deferred", report)
        self.assertIn("Mystery path", report)
        self.assertIn("revelation secret: first touched chapter 2", report)
        self.assertIn("Romance path", report)
        self.assertIn("relationship hero__partner: last updated chapter 3", report)

    def test_other_genres_use_generic_path(self) -> None:
        cards = {number: self._payoff_card(number, "deferred", "延后") for number in (1, 2, 3)}
        texts = {number: "# 第一章\n\n" + "\n\n".join(LONG_LINES) + "\n" for number in (1, 2, 3)}
        project = self.build("urban", "urban", texts, 3, cards=cards)
        report = run_script("promise_report.py", project).stdout
        self.assertIn("promise-deferred", report)
        self.assertNotIn("Mystery path", report)
        self.assertNotIn("Romance path", report)

    def test_deferred_payoff_requires_a_reason(self) -> None:
        project = self.build(
            "invalid",
            "mystery",
            {1: "# 第一章\n\n" + "\n\n".join(LONG_LINES) + "\n"},
            0,
            cards={1: card_text(1, payoff="payoff:\n  expected: 给出线索\n  status: deferred\n")},
        )
        result = run_script("build_context.py", project, "--chapter", 1, ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fill payoff.reason", result.stderr)


if __name__ == "__main__":
    unittest.main()
