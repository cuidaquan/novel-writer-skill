"""End-to-end drills from an empty directory plus failure-recovery regressions."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENTENCE = "他把纸条摊在桌上，灯下的字迹被水汽晕开，只剩半行还能辨认。"

BOOK_MASTER = """# 总纲
## 故事承诺
- 主角：调查员
- 核心欲望：找到真相
- 最大阻力：线索被篡改
- 失败代价：真相沉没
- 核心读者回报：拼出真相
## 关键转折
1. 起始失衡：朋友失踪
2. 第一次不可逆选择：公开调查
3. 中段认知/局势变化：发现自己被利用
4. 最严重失败或代价：证人遇险
5. 终局选择：公开证据
6. 结局状态：真相大白
## 跨章弧线
- 主角从什么状态变到什么状态：从退缩到承担
- 关键关系从什么状态变到什么状态：从怀疑到合作
- 主类型承诺将在何处兑现：终章
"""

STAGE = """# 第一阶段
- 阶段目标：找到第一条可靠线索
- 主冲突：调查遭到阻挠
- 阶段末变化：主角确定朋友还活着
- 下一阶段压力：证人的安全受到威胁
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


def card_text(number: int) -> str:
    return (
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
    )


def transaction(number: int) -> dict:
    return {
        "expected_chapter": number - 1,
        "chapter": number,
        "chapter_title": f"第{number}章",
        "summary": f"第{number}章推进。",
    }


class EndToEndDrills(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def make_project(self, name: str, count: int, word_sentence: int = 8) -> Path:
        project = Path(self.temp.name) / name
        run_script("init_novel.py", project, "--title", name)
        novel_path = project / "novel.yaml"
        novel = novel_path.read_text(encoding="utf-8")
        novel = novel.replace("target_words: null", f"target_words: {count * 100}")
        novel = novel.replace("target_chapters: null", f"target_chapters: {count}")
        novel = novel.replace("viewpoint_characters: []", "viewpoint_characters: [hero]")
        novel_path.write_text(novel, encoding="utf-8")
        (project / "characters" / "hero.yaml").write_text(
            "id: hero\nname: 主角\ncore:\n  desire: 找到真相\n  fear: 失去线索\n", encoding="utf-8"
        )
        (project / "outline" / "master.md").write_text(BOOK_MASTER, encoding="utf-8")
        (project / "outline" / "volumes" / "volume-01.md").write_text(STAGE, encoding="utf-8")
        for number in range(1, count + 1):
            (project / "control-cards" / f"chapter-{number:04d}.yaml").write_text(card_text(number), encoding="utf-8")
            (project / "chapters" / f"chapter-{number:04d}.md").write_text(
                f"# 第{number}章\n\n" + (SENTENCE * word_sentence) + "\n", encoding="utf-8"
            )
        return project

    def commit(self, project: Path, number: int, tx: dict | None = None) -> None:
        tx_path = Path(self.temp.name) / f"{project.name}-tx-{number}.json"
        tx_path.write_text(json.dumps(tx or transaction(number), ensure_ascii=False) + "\n", encoding="utf-8")
        run_script("state_commit.py", project / "state" / "state.json", tx_path)

    def state(self, project: Path) -> dict:
        return json.loads((project / "state" / "state.json").read_text(encoding="utf-8"))

    def test_single_chapter_short_project_completes(self) -> None:
        project = self.make_project("short", 1)
        run_script("project_check.py", project, "--preflight", "book")
        context = run_script("build_context.py", project, "--compact-state").stdout
        self.assertIn("State current chapter: 0", context)
        review = run_script("review_chapter.py", project, "--chapter", 1, ok=False)
        self.assertEqual(review.returncode, 0)
        self.commit(project, 1)
        run_script("project_check.py", project, "--complete")

    def test_continuous_serial_project_loop(self) -> None:
        project = self.make_project("serial", 3)
        run_script("project_check.py", project, "--preflight", "serial")
        self.commit(project, 1)
        run_script("project_check.py", project, "--preflight", "serial")
        context = run_script("build_context.py", project, "--compact-state", "--chapter", 2).stdout
        self.assertIn("State current chapter: 1", context)
        review = run_script("review_chapter.py", project, "--chapter", 2, ok=False)
        self.assertEqual(review.returncode, 0)
        self.commit(project, 2)
        run_script("project_check.py", project)
        self.commit(project, 3)
        run_script("project_check.py", project, "--complete")

    def test_complete_gate_rejects_missing_underlength_and_open_thread(self) -> None:
        missing = self.make_project("missing", 3)
        for number in (1, 2, 3):
            self.commit(missing, number)
        (missing / "chapters" / "chapter-0003.md").unlink()
        result = run_script("project_check.py", missing, "--complete", ok=False)
        self.assertIn("no body file", result.stdout)

        short = self.make_project("underlength", 3, word_sentence=1)
        for number in (1, 2, 3):
            self.commit(short, number)
        novel_path = short / "novel.yaml"
        novel_path.write_text(
            novel_path.read_text(encoding="utf-8").replace("target_words: 300", "target_words: 10000"),
            encoding="utf-8",
        )
        result = run_script("project_check.py", short, "--complete", ok=False)
        self.assertIn("below 90%", result.stdout)

        open_thread = self.make_project("open", 3)
        state_path = open_thread / "state" / "state.json"
        state = self.state(open_thread)
        state["plot_threads"] = {"main": {"status": "open"}}
        payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
        state_path.write_text(payload, encoding="utf-8")
        (open_thread / "state" / "initial.json").write_text(payload, encoding="utf-8")
        for number in (1, 2, 3):
            self.commit(open_thread, number)
        result = run_script("project_check.py", open_thread, "--complete", ok=False)
        self.assertIn("unresolved plot thread: main", result.stdout)

    def test_interrupted_write_recovers_with_rebuild(self) -> None:
        project = self.make_project("interrupted", 3)
        self.commit(project, 1)
        self.commit(project, 2)
        journal = project / "state" / "transactions" / "chapter-0003.json"
        journal.write_text(json.dumps(transaction(3), ensure_ascii=False) + "\n", encoding="utf-8")

        result = run_script("project_check.py", project, ok=False)
        self.assertIn("state_rebuild", result.stdout)
        run_script("state_rebuild.py", project, "--write")
        self.assertEqual(self.state(project)["project"]["current_chapter"], 3)
        run_script("project_check.py", project, "--complete")

    def test_missing_card_recovery(self) -> None:
        project = self.make_project("cardless", 3)
        for number in (1, 2, 3):
            self.commit(project, number)
        card = project / "control-cards" / "chapter-0003.yaml"
        content = card.read_text(encoding="utf-8")
        card.unlink()
        result = run_script("project_check.py", project, ok=False)
        self.assertIn("chapter 3 has no control card", result.stdout)
        card.write_text(content, encoding="utf-8")
        run_script("project_check.py", project, "--complete")


if __name__ == "__main__":
    unittest.main()
