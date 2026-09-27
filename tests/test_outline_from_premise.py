"""Tests for turning a locked premise into the outline, cards and characters."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREMISE = """schema_version: 1
project: "测试小说"
version: 1
rounds: 0
status: draft

delivery: book
length:
  target_chapters: 5
  target_words: 12500

genre:
  primary: romance
  secondary: [urban]
  audience: adult

narration:
  pov: first-person retrospective
  tense: past
  viewpoint_characters: [lin]

intimacy:
  tier: frank
  hard_limits:
    - "不写性器官、性行为过程的细节与体液"
    - "性行为只发生在私密空间"

style:
  tone: "克制、低温"
  sentence_length: short-to-medium
  dialogue_density: high
  exposition_density: low
  sensory_detail: high
  metaphor_density: low
  humor: restrained
  ending_mode: emotional-beat
  forbidden:
    - "不露骨描写性器官、性行为过程或体液"

world:
  mode: real
  research_level: high
  must_be_verifiable: [日出日落]
  build_before_writing: []

cast:
  - id: lin
    name: 林野
    role: protagonist
    want: 被当成一个正常人
    flaw: 把话锁在屋子里
    change: 敢把话说出来
  - id: sister
    name: 苏姐
    role: counterpart
    want: 把院子买断
    avoid: [自怜, 讲道理]

arc:
  turns:
    - {chapter: 2, change: 两人第一次同行}
    - {chapter: 4, change: 她把过去讲给他听}

revelations:
  - {id: r-shame, truth: 他偷过她的东西, reader_known_at: 3, known_by: [lin]}

frame:
  opening_image: 地板上的水渍
  closing_image: 同一个拐角
  promises: [四次关系变化]

must_include: [早市]
must_avoid: [重逢, 怀孕]
unresolved: [她会不会去俄罗斯]
agent_added: [母题：天花板水渍]
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


class OutlineFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "premise.yaml"
        self.source.write_text(PREMISE, encoding="utf-8")

    def build(self, name: str = "novel", lock: bool = True) -> Path:
        source = self.source
        project = self.root / name
        run_script("init_novel.py", project, "--from-premise", source)
        summary = "初始提案" if lock else "初始提案（未锁定）"
        extra = ("--lock",) if lock else ()
        run_script("premise_log.py", project, "--record", summary, *extra)
        return project

    def generate(self, project: Path, *extra: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        return run_script("outline_from_premise.py", project, *extra, ok=ok)

    def revise(self, project: Path, premise_text: str, summary: str = "改决策") -> None:
        """Follow the documented order: edit the premise, record it, sync the config."""
        (project / "premise.yaml").write_text(premise_text, encoding="utf-8")
        run_script("premise_log.py", project, "--record", summary, "--input", "测试用", "--lock")
        run_script("novel_from_premise.py", project)


class Generation(OutlineFixture):
    def test_writes_outline_cards_and_characters(self) -> None:
        project = self.build()
        result = self.generate(project)
        self.assertIn("wrote 8 file(s)", result.stdout)
        self.assertTrue((project / "outline" / "master.md").is_file())
        for chapter in range(1, 6):
            self.assertTrue((project / "control-cards" / f"chapter-{chapter:04d}.yaml").is_file())
        self.assertTrue((project / "characters" / "lin.yaml").is_file())
        self.assertTrue((project / "characters" / "sister.yaml").is_file())

    def test_outline_carries_the_decided_shape(self) -> None:
        project = self.build()
        self.generate(project)
        outline = (project / "outline" / "master.md").read_text(encoding="utf-8")
        self.assertIn("| 5 |", outline)                       # one row per planned chapter
        self.assertIn("两人第一次同行", outline)
        self.assertIn("她把过去讲给他听", outline)
        self.assertIn("r-shame", outline)                     # the revelation schedule
        self.assertIn("重逢", outline)                        # 全书禁区
        self.assertIn("早市", outline)                        # 必须出现
        self.assertIn("她会不会去俄罗斯", outline)             # 有意悬置
        self.assertIn("被当成一个正常人", outline)             # protagonist want
        for field in ("起始失衡", "第一次不可逆选择", "中段认知/局势变化", "最严重失败或代价",
                      "终局选择", "核心读者回报", "主类型承诺将在何处兑现"):
            self.assertIn(field, outline)

    def test_cards_are_prefilled_where_the_premise_decides(self) -> None:
        project = self.build()
        self.generate(project)
        sys.path.insert(0, str(ROOT / "scripts"))
        from project_yaml import read_yaml  # noqa: PLC0415 - test-local import

        third = read_yaml(project / "control-cards" / "chapter-0003.yaml")
        self.assertEqual(third["viewpoint"], "lin")
        self.assertEqual(third["revelations"]["reveal"], ["r-shame"])
        self.assertEqual(third["ending"]["mode"], "emotional-beat")
        self.assertEqual(third["forbidden"], ["重逢", "怀孕"])
        self.assertEqual(third["context"]["characters"], ["lin", "sister"])

        second = read_yaml(project / "control-cards" / "chapter-0002.yaml")
        self.assertEqual(second["change"]["plot"], "两人第一次同行")
        self.assertEqual(second["revelations"]["reveal"], [])

        first = read_yaml(project / "control-cards" / "chapter-0001.yaml")
        self.assertEqual(first["change"]["plot"], "")

    def test_chapter_words_split_keeps_the_total(self) -> None:
        project = self.build()
        self.generate(project)
        sys.path.insert(0, str(ROOT / "scripts"))
        from project_yaml import read_yaml  # noqa: PLC0415 - test-local import

        total = sum(read_yaml(project / "control-cards" / f"chapter-{number:04d}.yaml")["target_words"]
                    for number in range(1, 6))
        self.assertEqual(total, 12500)

    def test_characters_carry_names_and_constraints(self) -> None:
        project = self.build()
        self.generate(project)
        sys.path.insert(0, str(ROOT / "scripts"))
        from project_yaml import read_yaml  # noqa: PLC0415 - test-local import

        lin = read_yaml(project / "characters" / "lin.yaml")
        self.assertEqual(lin["name"], "林野")
        self.assertEqual(lin["core"]["desire"], "被当成一个正常人")
        self.assertEqual(lin["core"]["fear"], "把话锁在屋子里")
        self.assertEqual(lin["arc"], "敢把话说出来")
        sister = read_yaml(project / "characters" / "sister.yaml")
        self.assertEqual(sister["voice"]["avoids"], ["自怜", "讲道理"])

    def test_pending_report_lists_what_the_author_must_decide(self) -> None:
        project = self.build()
        result = self.generate(project)
        self.assertIn("还需要你决定的", result.stdout)
        self.assertIn("关键转折六条", result.stdout)
        self.assertIn("goal / conflict", result.stdout)
        self.assertIn("1、3、5", result.stdout)   # chapters without an arc turn

    def test_dry_run_writes_nothing(self) -> None:
        project = self.build()
        before = sorted(path.name for path in (project / "control-cards").iterdir())
        result = self.generate(project, "--dry-run")
        self.assertIn("dry run", result.stdout)
        self.assertIn("空章卡", result.stdout)
        self.assertEqual(sorted(path.name for path in (project / "control-cards").iterdir()), before)
        self.assertFalse((project / "characters" / "lin.yaml").exists())


class Refusals(OutlineFixture):
    def test_generated_skeleton_leaves_only_content_gaps(self) -> None:
        project = self.build()
        self.generate(project)
        result = run_script("project_check.py", project, "--preflight", "book", "--require-premise", ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("fill goal", result.stdout)             # content still to write
        self.assertNotIn("missing control card", result.stdout)
        self.assertNotIn("missing viewpoint character file", result.stdout)

    def test_refuses_a_draft_premise(self) -> None:
        project = self.build("draft", lock=False)
        result = self.generate(project, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("still draft", result.stdout)

    def test_refuses_a_premise_with_blocking_findings(self) -> None:
        # 先用合规的立项书把项目建起来，再把立项书改坏——init 本身就会拒绝坏立项书。
        broken = PREMISE.replace("""  hard_limits:
    - "不写性器官、性行为过程的细节与体液"
    - "性行为只发生在私密空间"
""", "  hard_limits: []\n")
        project = self.build("broken")
        (project / "premise.yaml").write_text(broken, encoding="utf-8")
        result = self.generate(project, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not settled", result.stdout)
        self.assertIn("intimacy.hard_limits", result.stdout)
        self.assertIn("# 总纲", (project / "outline" / "master.md").read_text(encoding="utf-8"))

    def test_refuses_to_overwrite_authored_files(self) -> None:
        project = self.build()
        self.generate(project)
        card = project / "control-cards" / "chapter-0002.yaml"
        card.write_text(card.read_text(encoding="utf-8").replace('goal: ""', 'goal: "作者写的目标"'), encoding="utf-8")
        result = self.generate(project, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("your own edits", result.stdout)
        self.assertIn("chapter-0002.yaml", result.stdout)
        self.assertIn("作者写的目标", card.read_text(encoding="utf-8"))

    def test_force_overwrites_authored_files(self) -> None:
        project = self.build()
        self.generate(project)
        card = project / "control-cards" / "chapter-0002.yaml"
        card.write_text(card.read_text(encoding="utf-8").replace('goal: ""', 'goal: "作者写的目标"'), encoding="utf-8")
        self.generate(project, "--force")
        self.assertNotIn("作者写的目标", card.read_text(encoding="utf-8"))

    def test_rerun_is_idempotent_and_replaces_untouched_templates(self) -> None:
        project = self.build()
        self.generate(project)
        card = project / "control-cards" / "chapter-0002.yaml"
        before = card.read_text(encoding="utf-8")
        self.generate(project)                       # same content → no --force needed
        self.assertEqual(card.read_text(encoding="utf-8"), before)

    def test_fresh_project_template_outline_is_replaced_without_force(self) -> None:
        # init 会放一份模板总纲；那是骨架不是作者内容，不该要求 --force。
        project = self.build("fresh")
        template = (ROOT / "assets" / "templates" / "outline.md").read_text(encoding="utf-8")
        self.assertEqual((project / "outline" / "master.md").read_text(encoding="utf-8"), template)
        result = self.generate(project)
        self.assertIn("wrote", result.stdout)
        self.assertIn("章节节奏", (project / "outline" / "master.md").read_text(encoding="utf-8"))

    def test_usage_errors(self) -> None:
        project = self.build()
        self.assertEqual(self.generate(project / "missing", ok=False).returncode, 2)
        self.assertEqual(self.generate(project, "--words-per-chapter", "-5", ok=False).returncode, 2)
        empty = self.root / "empty"
        run_script("init_novel.py", empty)
        self.assertEqual(self.generate(empty, ok=False).returncode, 2)


class StaleFiles(OutlineFixture):
    def shrink(self, project: Path, chapters: int, words: int) -> None:
        premise = (project / "premise.yaml").read_text(encoding="utf-8")
        premise = premise.replace("target_chapters: 5", f"target_chapters: {chapters}")
        premise = premise.replace("target_words: 12500", f"target_words: {words}")
        premise = premise.replace("    - {chapter: 4, change: 她把过去讲给他听}\n", "")
        premise = premise.replace("reader_known_at: 3", "reader_known_at: 2")
        self.revise(project, premise, "章数改小")

    def test_reports_leftovers_after_the_plan_shrinks(self) -> None:
        project = self.build()
        self.generate(project)
        self.shrink(project, 3, 7500)
        result = self.generate(project, "--force")
        self.assertIn("旧计划的残留文件", result.stdout)
        self.assertIn("chapter-0004.yaml", result.stdout)
        self.assertIn("chapter-0005.yaml", result.stdout)

    def test_prune_removes_scaffold_leftovers(self) -> None:
        project = self.build()
        self.generate(project)
        self.shrink(project, 3, 7500)
        result = self.generate(project, "--force", "--prune")
        self.assertIn("已清掉的旧计划残留", result.stdout)
        self.assertFalse((project / "control-cards" / "chapter-0004.yaml").exists())
        self.assertFalse((project / "control-cards" / "chapter-0005.yaml").exists())
        self.assertTrue((project / "control-cards" / "chapter-0003.yaml").is_file())

    def test_prune_keeps_leftovers_that_carry_author_content(self) -> None:
        project = self.build()
        self.generate(project)
        card = project / "control-cards" / "chapter-0004.yaml"
        card.write_text(card.read_text(encoding="utf-8").replace('goal: ""', 'goal: "作者写的目标"'), encoding="utf-8")
        self.shrink(project, 3, 7500)
        result = self.generate(project, "--force", "--prune")
        self.assertIn("请手工处理", result.stdout)
        self.assertTrue(card.is_file())
        self.assertIn("作者写的目标", card.read_text(encoding="utf-8"))

    def test_gate_warns_mid_book_and_errors_at_completion(self) -> None:
        project = self.build()
        self.generate(project)
        stale = project / "control-cards" / "chapter-0009.yaml"
        stale.write_text((project / "control-cards" / "chapter-0001.yaml").read_text(encoding="utf-8")
                         .replace("chapter: 1", "chapter: 9"), encoding="utf-8")
        mid = run_script("project_check.py", project, ok=False)
        self.assertIn("WARN", mid.stdout)
        self.assertIn("chapter-0009.yaml", mid.stdout)
        done = run_script("project_check.py", project, "--complete", ok=False)
        self.assertIn("ERROR", done.stdout)
        self.assertIn("chapter-0009.yaml", done.stdout)

    def test_character_left_over_from_a_smaller_cast_is_reported(self) -> None:
        project = self.build()
        self.generate(project)
        premise = (project / "premise.yaml").read_text(encoding="utf-8")
        slim = premise.replace("""  - id: sister
    name: 苏姐
    role: counterpart
    want: 把院子买断
    avoid: [自怜, 讲道理]
""", "")
        self.revise(project, slim, "去掉一个角色")
        result = self.generate(project, "--force")
        self.assertIn("sister.yaml", result.stdout)


class EndToEnd(OutlineFixture):
    """The whole promise: decisions in, a startable project out."""

    def fill_skeleton(self, project: Path) -> None:
        """Stand in for the author: fill everything the pending list asks for."""
        master = project / "outline" / "master.md"
        text = master.read_text(encoding="utf-8")
        numbered = ["起始失衡", "第一次不可逆选择", "中段认知/局势变化", "最严重失败或代价", "终局选择"]
        for index, label in enumerate(numbered, 1):
            text = text.replace(f"{index}. {label}：待定", f"{index}. {label}：填好的转折")
        for label in ("失败代价", "核心读者回报", "关键关系从什么状态变到什么状态", "主类型承诺将在何处兑现"):
            text = text.replace(f"- {label}：待定", f"- {label}：填好的内容")
        master.write_text(text, encoding="utf-8")

        for number in range(1, 6):
            card = project / "control-cards" / f"chapter-{number:04d}.yaml"
            body = card.read_text(encoding="utf-8")
            body = body.replace('goal: ""', 'goal: "本章目标"')
            body = body.replace('conflict: ""', 'conflict: "本章阻力"')
            if '  character: ""' in body:            # every card needs at least one change
                body = body.replace('  character: ""', '  character: "他变了一点"')
            card.write_text(body, encoding="utf-8")

        for name, label in (("lin", "林野"), ("sister", "苏姐")):
            character = project / "characters" / f"{name}.yaml"
            character.write_text(character.read_text(encoding="utf-8").replace('name: ""', f'name: "{label}"'), encoding="utf-8")

    def test_filled_skeleton_passes_the_start_gate(self) -> None:
        project = self.build()
        self.generate(project)
        blocked = run_script("project_check.py", project, "--preflight", "book", "--require-premise", ok=False)
        self.assertEqual(blocked.returncode, 1)          # content gaps still stop it
        self.fill_skeleton(project)
        ready = run_script("project_check.py", project, "--preflight", "book", "--require-premise")
        self.assertIn("OK: book preflight", ready.stdout)

    def test_every_pending_item_is_reachable_from_the_generated_files(self) -> None:
        """The pending list must point at real placeholders, not at wishes."""
        project = self.build()
        result = self.generate(project)
        master = (project / "outline" / "master.md").read_text(encoding="utf-8")
        card = (project / "control-cards" / "chapter-0001.yaml").read_text(encoding="utf-8")
        character = (project / "characters" / "lin.yaml").read_text(encoding="utf-8")
        self.assertIn("关键转折六条", result.stdout)
        self.assertIn("change 里至少一条", result.stdout)
        self.assertIn("1. 起始失衡：待定", master)
        self.assertIn("5. 终局选择：待定", master)
        self.assertIn("- 失败代价：待定", master)
        self.assertIn('goal: ""', card)
        self.assertIn('name: "林野"', character)      # 立项书里写了名字就自动填入
        self.assertIn('speech_style: ""', character)  # 声音仍要作者写
        self.assertIn('  need: ""', character)


class EdgeCases(OutlineFixture):
    def test_single_chapter_premise(self) -> None:
        one = PREMISE.replace("target_chapters: 5", "target_chapters: 1").replace(
            """  turns:
    - {chapter: 2, change: 两人第一次同行}
    - {chapter: 4, change: 她把过去讲给他听}""",
            "  turns:\n    - {chapter: 1, change: 一次见面}")
        one = one.replace("reader_known_at: 3", "reader_known_at: 1")
        project = self.build("one")
        self.revise(project, one, "章数改到一章")
        self.generate(project, "--force")
        self.assertTrue((project / "control-cards" / "chapter-0001.yaml").is_file())
        self.assertFalse((project / "control-cards" / "chapter-0002.yaml").exists())

    def test_premise_without_turns_revelations_or_lists(self) -> None:
        bare = PREMISE.replace("""  turns:
    - {chapter: 2, change: 两人第一次同行}
    - {chapter: 4, change: 她把过去讲给他听}
""", "  turns:\n    - {chapter: 3, change: 唯一一次变化}\n")
        bare = bare.replace("""revelations:
  - {id: r-shame, truth: 他偷过她的东西, reader_known_at: 3, known_by: [lin]}
""", "revelations: []\n")
        bare = bare.replace("must_include: [早市]\n", "must_include: []\n")
        bare = bare.replace("must_avoid: [重逢, 怀孕]\n", "must_avoid: []\n")
        bare = bare.replace("unresolved: [她会不会去俄罗斯]\n", "unresolved: []\n")
        bare = bare.replace("agent_added: [母题：天花板水渍]\n", "agent_added: []\n")
        project = self.build("bare")
        self.revise(project, bare, "去掉揭示与清单")
        result = self.generate(project, "--force")
        self.assertIn("wrote", result.stdout)
        sys.path.insert(0, str(ROOT / "scripts"))
        from project_yaml import read_yaml  # noqa: PLC0415 - test-local import

        card = read_yaml(project / "control-cards" / "chapter-0003.yaml")
        self.assertEqual(card["change"]["plot"], "唯一一次变化")
        self.assertEqual(card["forbidden"], [])
        outline = (project / "outline" / "master.md").read_text(encoding="utf-8")
        self.assertIn("（无）", outline)          # 未决问题 empty marker
        self.assertIn("待定", outline)

    def test_three_digit_chapter_numbers(self) -> None:
        long_book = PREMISE.replace("target_chapters: 5", "target_chapters: 120").replace("target_words: 12500", "target_words: 300000").replace(
            "    - {chapter: 2, change: 两人第一次同行}\n    - {chapter: 4, change: 她把过去讲给他听}",
            "    - {chapter: 40, change: 中段变化}\n    - {chapter: 120, change: 结局}")
        long_book = long_book.replace("reader_known_at: 3", "reader_known_at: 60")
        project = self.build("long")
        self.revise(project, long_book, "扩到 120 章")
        self.generate(project, "--force")
        self.assertTrue((project / "control-cards" / "chapter-0100.yaml").is_file())
        self.assertTrue((project / "control-cards" / "chapter-0120.yaml").is_file())
        self.assertFalse((project / "control-cards" / "chapter-0121.yaml").exists())

    def test_words_per_chapter_override(self) -> None:
        project = self.build("perchapter")
        self.generate(project, "--force", "--words-per-chapter", "1800")
        sys.path.insert(0, str(ROOT / "scripts"))
        from project_yaml import read_yaml  # noqa: PLC0415 - test-local import

        card = read_yaml(project / "control-cards" / "chapter-0004.yaml")
        self.assertEqual(card["target_words"], 1800)

    def test_serial_outline_carries_the_serial_fields(self) -> None:
        serial = PREMISE.replace("delivery: book", "delivery: serial")
        project = self.build("serial")
        self.revise(project, serial, "改为连载")
        self.generate(project, "--force")
        outline = (project / "outline" / "master.md").read_text(encoding="utf-8")
        for field in ("结局状态", "主角从什么状态变到什么状态", "主类型承诺将在何处兑现"):
            self.assertIn(field, outline)


if __name__ == "__main__":
    unittest.main()
