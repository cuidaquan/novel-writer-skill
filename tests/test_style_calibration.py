"""v1.2 style calibration: recorded behaviour of the current thresholds.

These samples are the evidence base for the threshold decisions written to
.doc/style-calibration.md. They do not judge prose quality; they only pin down
when the current metrics fire, stay quiet, or miss a deviation.
"""

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

MEDIUM_LINES = [
    "他沿着走廊慢慢向前走，脚步声在空旷的走廊里来回回荡。",
    "窗外的天色一点点暗下来，像有人缓缓合上了一层幕布。",
    "他停下来仔细听了一会儿，确认身后没有别的动静。",
    "桌上的茶杯还留着一点余温，说明人刚刚离开不久。",
    "走廊尽头有一扇半掩的门，门缝里透出微弱的灯光。",
    "他把手轻轻放在门把上，犹豫了几秒才慢慢推开。",
    "房间里没有人，只有一台老式录音机还在缓缓转动。",
    "磁带里传来沙沙的杂音，夹杂着一段听不清的对话。",
    "他按下停止键，房间里忽然安静得有些过分。",
    "窗台上落了一层薄灰，灰上有两道新鲜的指痕。",
    "他把指痕的位置记下来，又仔细检查了一遍门锁。",
    "楼下传来汽车发动的声音，很快又朝着远处消失了。",
]

SHORT_LINES = [
    "他看着窗外。",
    "雨还在下。",
    "她没有回头。",
    "他也没有开口。",
    "沉默停在两人之间。",
    "他说了再见。",
    "她轻轻点头。",
    "门在身后合上。",
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


def run_script(script: str, *args: object, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
    )
    if ok and result.returncode != 0:
        raise AssertionError(f"{script} failed:\n{result.stdout}\n{result.stderr}")
    return result


class StyleCalibration(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def build(self, name: str, baseline: list[str], target: list[str], override: str = "") -> Path:
        project = Path(self.temp.name) / name
        run_script("init_novel.py", project, "--title", name)
        novel_path = project / "novel.yaml"
        novel = novel_path.read_text(encoding="utf-8")
        novel = novel.replace("viewpoint_characters: []", "viewpoint_characters: [hero]")
        novel = novel.replace("target_words: null", "target_words: 5000")
        novel = novel.replace("target_chapters: null", "target_chapters: 12")
        novel_path.write_text(novel, encoding="utf-8")
        (project / "characters" / "hero.yaml").write_text(
            "id: hero\nname: 主角\ncore:\n  desire: 找真相\n  fear: 失去线索\n", encoding="utf-8"
        )
        for number in range(1, 6):
            lines = baseline if number < 5 else target
            (project / "chapters" / f"chapter-{number:04d}.md").write_text(
                f"# 第{number}章\n\n" + "\n\n".join(lines) + "\n", encoding="utf-8"
            )
        if override:
            card = (
                "chapter: 5\n"
                "title: 第五章\n"
                "viewpoint: hero\n"
                "target_words: 100\n"
                "goal: 推进\n"
                "conflict: 阻挠\n"
                "change:\n"
                "  plot: 推进\n"
                "context:\n"
                "  characters: [hero]\n"
                "  world: []\n"
            ) + override
            (project / "control-cards" / "chapter-0005.yaml").write_text(card, encoding="utf-8")
        state_path = project / "state" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["project"]["current_chapter"] = 4
        state["handoff"]["chapter"] = 4
        payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
        state_path.write_text(payload, encoding="utf-8")
        (project / "state" / "initial.json").write_text(payload, encoding="utf-8")
        return project

    def report(self, project: Path) -> str:
        return run_script("style_report.py", project, "--chapter", 5, "--baseline", 4).stdout

    def test_same_style_chapter_reports_no_drift(self) -> None:
        report = self.report(self.build("same", LONG_LINES, LONG_LINES))
        self.assertIn("Drift hints (0)", report)

    def test_large_undeclared_deviation_is_reported(self) -> None:
        report = self.report(self.build("large", LONG_LINES, SHORT_LINES))
        self.assertIn("[style-sentence-length]", report)
        self.assertIn("[style-paragraph-length]", report)

    def test_subtle_deviation_is_a_documented_false_negative(self) -> None:
        report = self.report(self.build("subtle", LONG_LINES, MEDIUM_LINES))
        self.assertIn("Drift hints (0)", report)

    def test_romance_dialogue_drop_is_reported(self) -> None:
        report = self.report(self.build("romance", DIALOGUE_LINES, LONG_LINES))
        self.assertIn("[style-dialogue-ratio]", report)


    def test_repeated_cross_chapter_formulas_are_reported(self) -> None:
        line = "他推开那扇门，听见里面传来低低的呼吸声。"
        lines = [line] * 16
        report = self.report(self.build("formula", lines, lines))
        self.assertIn("## Cross-chapter patterns", report)
        self.assertIn("[cross-chapter-opening]", report)
        self.assertIn("[cross-chapter-ending]", report)

    def test_varied_openings_and_endings_are_not_flagged(self) -> None:
        report = self.report(self.build("varied", LONG_LINES, MEDIUM_LINES))
        patterns = report.split("## Cross-chapter patterns", 1)[1].split("These hints")[0]
        self.assertIn("(none)", patterns)


if __name__ == "__main__":
    unittest.main()
