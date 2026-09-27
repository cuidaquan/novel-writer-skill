"""Tests for the decisions-first intake: premise checks, its log, and the gate."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "assets" / "templates" / "premise.yaml"

VALID_PREMISE = """schema_version: 1
project: "测试小说"
version: 1
rounds: 0
status: draft

delivery: book
length:
  target_chapters: 4
  target_words: 12000

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
  build_before_writing: [world/timeline.md]

cast:
  - id: lin
    role: protagonist
    want: 被当成一个正常人
    flaw: 把话锁在屋子里
    change: 敢把话说出来
  - id: sister
    role: counterpart
    want: 把院子买断
    avoid: [自怜]

arc:
  turns:
    - {chapter: 1, change: 两人第一次同行}
    - {chapter: 4, change: 分别}

revelations:
  - {id: r-shame, truth: 他偷过她的东西, reader_known_at: 2, known_by: [lin]}

frame:
  opening_image: 地板上的水渍
  closing_image: 同一个拐角
  promises: [四次关系变化]

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


class PremiseFixture(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.premise_file = self.root / "premise.yaml"
        self.premise_file.write_text(VALID_PREMISE, encoding="utf-8")

    def build_project(self, name: str = "novel", premise: str | None = None) -> Path:
        """Create a project whose novel.yaml is generated from the premise."""
        project = self.root / name
        source = self.premise_file
        if premise is not None:
            source = self.root / f"{name}-premise.yaml"
            source.write_text(premise, encoding="utf-8")
        run_script("init_novel.py", project, "--from-premise", source)
        return project

    def record(self, project: Path, summary: str = "初始提案", *extra: str) -> None:
        run_script("premise_log.py", project, "--record", summary, *extra)


class BriefCheck(PremiseFixture):
    def test_unsettled_template_blocks(self) -> None:
        project = self.root / "blank"
        run_script("init_novel.py", project)
        (project / "premise.yaml").write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        result = run_script("brief_check.py", project, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing-decision", result.stdout)
        self.assertIn("FAIL", result.stdout)

    def test_placeholder_value_blocks(self) -> None:
        premise = VALID_PREMISE.replace("  target_words: 12000", "  target_words: 待定")
        project = self.root / "placeholder"
        run_script("init_novel.py", project)
        (project / "premise.yaml").write_text(premise, encoding="utf-8")
        result = run_script("brief_check.py", project, ok=False)
        self.assertIn("length.target_words", result.stdout)
        self.assertEqual(result.returncode, 1)

    def test_frank_without_hard_limits_blocks(self) -> None:
        premise = VALID_PREMISE.replace("""  hard_limits:
    - "不写性器官、性行为过程的细节与体液"
    - "性行为只发生在私密空间"
""", "  hard_limits: []\n")
        project = self.build_project("frank")
        (project / "premise.yaml").write_text(premise, encoding="utf-8")
        result = run_script("brief_check.py", project, ok=False)
        self.assertIn("intimacy.hard_limits", result.stdout)
        self.assertEqual(result.returncode, 1)

    def test_out_of_order_turns_block(self) -> None:
        premise = VALID_PREMISE.replace("    - {chapter: 4, change: 分别}", "    - {chapter: 5, change: 超出计划章数}")
        project = self.build_project("turns")
        (project / "premise.yaml").write_text(premise, encoding="utf-8")
        result = run_script("brief_check.py", project, ok=False)
        self.assertIn("arc.turns", result.stdout)

    def test_missing_viewpoint_characters_blocks(self) -> None:
        premise = VALID_PREMISE.replace("  viewpoint_characters: [lin]", "  viewpoint_characters: []")
        project = self.build_project("viewpoint")
        (project / "premise.yaml").write_text(premise, encoding="utf-8")
        result = run_script("brief_check.py", project, ok=False)
        self.assertIn("narration.viewpoint_characters", result.stdout)

    def test_unknown_tier_blocks(self) -> None:
        premise = VALID_PREMISE.replace("  tier: frank", "  tier: 很辣")
        project = self.build_project("tier")
        (project / "premise.yaml").write_text(premise, encoding="utf-8")
        result = run_script("brief_check.py", project, ok=False)
        self.assertIn("未知亲密分级", result.stdout)

    def test_unrecorded_premise_blocks(self) -> None:
        project = self.build_project()
        result = run_script("brief_check.py", project, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("unrecorded-round", result.stdout)

    def test_changed_premise_without_round_blocks(self) -> None:
        project = self.build_project()
        self.record(project)
        path = project / "premise.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("target_chapters: 4", "target_chapters: 5"), encoding="utf-8")
        result = run_script("brief_check.py", project, ok=False)
        self.assertIn("unrecorded-round", result.stdout)

    def test_novel_drift_blocks(self) -> None:
        project = self.build_project()
        self.record(project)
        novel = project / "novel.yaml"
        novel.write_text(novel.read_text(encoding="utf-8").replace("target_chapters: 4", "target_chapters: 7"), encoding="utf-8")
        result = run_script("brief_check.py", project, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("novel-drift", result.stdout)

    def test_agent_added_is_advisory_only(self) -> None:
        project = self.build_project()
        self.record(project)
        result = run_script("brief_check.py", project)
        self.assertIn("agent-added", result.stdout)
        self.assertIn("PASS", result.stdout)

    def test_locked_recorded_premise_passes(self) -> None:
        project = self.build_project()
        self.record(project, "初始提案", "--lock")
        result = run_script("brief_check.py", project)
        self.assertEqual(result.returncode, 0)
        self.assertIn("PASS: the premise is locked", result.stdout)

    def test_standalone_draft_can_be_checked_before_the_project_exists(self) -> None:
        draft = self.root / "draft.yaml"
        draft.write_text(VALID_PREMISE.replace("  hard_limits:\n    - \"不写性器官、性行为过程的细节与体液\"\n    - \"性行为只发生在私密空间\"\n", "  hard_limits: []\n"), encoding="utf-8")
        result = run_script("brief_check.py", draft, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("standalone draft", result.stdout)
        self.assertIn("intimacy.hard_limits", result.stdout)

    def test_standalone_draft_passes_when_settled(self) -> None:
        result = run_script("brief_check.py", self.premise_file)
        self.assertEqual(result.returncode, 0)
        self.assertIn("PASS (draft)", result.stdout)

    def test_missing_premise_is_a_usage_error(self) -> None:
        project = self.root / "empty"
        run_script("init_novel.py", project)
        result = run_script("brief_check.py", project, ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("premise.yaml", result.stdout)


class PremiseLog(PremiseFixture):
    def test_record_writes_event_and_snapshot(self) -> None:
        project = self.build_project()
        self.record(project, "初始提案", "--input", "一句话需求")
        events = (project / "history" / "log.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(events), 1)
        event = json.loads(events[0])
        self.assertEqual(event["id"], "p001")
        self.assertEqual(event["input"], "一句话需求")
        self.assertTrue((project / "history" / "snapshots" / "p001" / "premise.yaml").is_file())
        self.assertIn("premise.yaml", event["hashes"])

    def test_list_shows_rounds(self) -> None:
        project = self.build_project()
        self.record(project, "初始提案")
        self.record(project, "改章数")
        result = run_script("premise_log.py", project, "--list")
        self.assertIn("p001", result.stdout)
        self.assertIn("p002", result.stdout)
        self.assertIn("改章数", result.stdout)

    def test_diff_reports_changed_field_and_input(self) -> None:
        project = self.build_project()
        self.record(project, "初始提案")
        path = project / "premise.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("target_chapters: 4", "target_chapters: 6"), encoding="utf-8")
        self.record(project, "四章太少", "--input", "加到六章")
        result = run_script("premise_log.py", project, "--diff", "p001", "p002")
        self.assertIn("length.target_chapters: 4 → 6", result.stdout)
        self.assertIn("加到六章", result.stdout)

    def test_show_prints_one_round(self) -> None:
        project = self.build_project()
        self.record(project, "初始提案")
        result = run_script("premise_log.py", project, "--show", "p001")
        self.assertIn("p001", result.stdout)
        self.assertIn("snapshots/p001", result.stdout)

    def test_verify_detects_drift(self) -> None:
        project = self.build_project()
        self.record(project)
        clean = run_script("premise_log.py", project, "--verify")
        self.assertEqual(clean.returncode, 0)
        path = project / "premise.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("target_chapters: 4", "target_chapters: 8"), encoding="utf-8")
        drift = run_script("premise_log.py", project, "--verify", ok=False)
        self.assertEqual(drift.returncode, 1)
        self.assertIn("DRIFT", drift.stdout)

    def test_restore_dry_run_changes_nothing(self) -> None:
        project = self.build_project()
        self.record(project)
        path = project / "premise.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("target_chapters: 4", "target_chapters: 6"), encoding="utf-8")
        self.record(project, "改章数")
        result = run_script("premise_log.py", project, "--restore", "p001")
        self.assertIn("dry run", result.stdout)
        self.assertIn("target_chapters: 6", path.read_text(encoding="utf-8"))
        self.assertEqual(len((project / "history" / "log.jsonl").read_text(encoding="utf-8").strip().splitlines()), 2)

    def test_restore_apply_restores_and_rebaselines(self) -> None:
        project = self.build_project()
        self.record(project, "初始提案", "--lock")
        path = project / "premise.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("target_chapters: 4", "target_chapters: 6"), encoding="utf-8")
        self.record(project, "改章数")
        result = run_script("premise_log.py", project, "--restore", "p001", "--apply")
        self.assertIn("restored", result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertIn("target_chapters: 4", path.read_text(encoding="utf-8"))
        events = [json.loads(line) for line in (project / "history" / "log.jsonl").read_text(encoding="utf-8").strip().splitlines()]
        self.assertTrue(any(event["id"].endswith("-pre-restore") for event in events))
        self.assertEqual(events[-1].get("restored_from"), "p001")
        self.assertEqual(run_script("brief_check.py", project).returncode, 0)

    def test_unknown_round_is_a_usage_error(self) -> None:
        project = self.build_project()
        self.record(project)
        self.assertEqual(run_script("premise_log.py", project, "--show", "p099", ok=False).returncode, 2)
        self.assertEqual(run_script("premise_log.py", project, "--restore", "p099", ok=False).returncode, 2)
        self.assertEqual(run_script("premise_log.py", project / "missing", "--list", ok=False).returncode, 2)


class FromPremise(PremiseFixture):
    def test_generates_a_config_that_matches(self) -> None:
        project = self.build_project()
        from project_yaml import read_yaml  # noqa: PLC0415 - test-local import

        novel = read_yaml(project / "novel.yaml")
        self.assertEqual(novel["length"]["target_chapters"], 4)
        self.assertEqual(novel["length"]["target_words"], 12000)
        self.assertEqual(novel["genre"]["primary"], "romance")
        self.assertEqual(novel["audience"], "adult")
        self.assertEqual(novel["narration"]["pov"], "first-person retrospective")
        self.assertEqual(novel["style"]["ending_mode"], "emotional-beat")
        self.assertIn("intimacy", novel["style"]["modules"])
        self.assertIn("不露骨描写性器官、性行为过程或体液", novel["style"]["forbidden"])
        self.assertTrue(any("性器官" in item for item in novel["content_limits"]))
        self.assertTrue((project / "premise.yaml").is_file())

    def test_refuses_an_unsettled_premise(self) -> None:
        source = self.root / "unsettled.yaml"
        source.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        project = self.root / "refused"
        result = run_script("init_novel.py", project, "--from-premise", source, ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not settled yet", result.stdout)
        self.assertFalse(project.exists())

    def test_missing_premise_file_is_a_usage_error(self) -> None:
        result = run_script("init_novel.py", self.root / "x", "--from-premise", self.root / "nope.yaml", ok=False)
        self.assertEqual(result.returncode, 2)


class PreflightGate(PremiseFixture):
    def test_require_premise_blocks_without_one(self) -> None:
        project = self.root / "no-premise"
        run_script("init_novel.py", project)
        result = run_script("project_check.py", project, "--preflight", "book", "--require-premise", ok=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("premise.yaml missing", result.stdout)

    def test_default_preflight_only_hints(self) -> None:
        project = self.root / "hint"
        run_script("init_novel.py", project)
        result = run_script("project_check.py", project, "--preflight", "book", ok=False)
        self.assertIn("NOTE: premise.yaml missing", result.stdout)
        self.assertNotIn("ERROR: premise.yaml missing", result.stdout)

    def test_a_locked_premise_satisfies_the_gate(self) -> None:
        project = self.build_project()
        self.record(project, "初始提案", "--lock")
        result = run_script("project_check.py", project, "--preflight", "book", "--require-premise", ok=False)
        self.assertNotIn("premise.yaml", result.stdout)


class YAMLSubset(PremiseFixture):
    def test_list_mapping_items_and_inline_maps_parse(self) -> None:
        from project_yaml import read_yaml  # noqa: PLC0415 - test-local import

        data = read_yaml(self.premise_file)
        self.assertEqual(data["cast"][0], {"id": "lin", "role": "protagonist", "want": "被当成一个正常人",
                                           "flaw": "把话锁在屋子里", "change": "敢把话说出来"})
        self.assertEqual(data["arc"]["turns"][0], {"chapter": 1, "change": "两人第一次同行"})
        self.assertEqual(data["world"]["must_be_verifiable"], ["日出日落"])

    def test_scalar_items_stay_scalars(self) -> None:
        from project_yaml import read_yaml  # noqa: PLC0415 - test-local import

        path = self.root / "scalars.yaml"
        path.write_text("schedule:\n  - 12:30 出发\n  - http://example.com\n  - {a: 1, b: [2, 3]}\n", encoding="utf-8")
        self.assertEqual(read_yaml(path)["schedule"], ["12:30 出发", "http://example.com", {"a": 1, "b": [2, 3]}])


if __name__ == "__main__":
    unittest.main()
