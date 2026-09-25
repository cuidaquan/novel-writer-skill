"""Contract and Skill-routing tests for the frozen v1.0 interface."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"\]\(([^)#]+\.md)\)")
MODE_MARKERS = [
    "短篇正文",
    "新建项目或整本小说",
    "续写章节",
    "重写旧章节",
    "定义或调整文风",
    "选择或混合题材",
    "改稿/审稿",
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


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def test_schema_version_is_frozen_and_required(self) -> None:
        template = (ROOT / "assets" / "templates" / "novel.yaml").read_text(encoding="utf-8")
        self.assertIn("schema_version: 1", template)
        project = Path(self.temp.name) / "novel"
        run_script("init_novel.py", project, "--title", "契约测试")
        novel_path = project / "novel.yaml"
        novel_path.write_text(
            novel_path.read_text(encoding="utf-8").replace("schema_version: 1\n", "", 1), encoding="utf-8"
        )
        result = run_script("project_check.py", project, "--preflight", "book", ok=False)
        self.assertIn("schema_version must be 1", result.stdout)

    def test_version_and_changelog_agree(self) -> None:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## {version}", changelog)

    def test_skill_modes_and_platform_neutral_description(self) -> None:
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for marker in MODE_MARKERS:
            self.assertIn(marker, skill)
        front_matter = skill.split("---")[1]
        for agent_name in ("Codex", "Claude", "Cursor", "OpenAI"):
            self.assertNotIn(agent_name, front_matter)
        for target in LINK_PATTERN.findall(skill):
            self.assertTrue((ROOT / target).is_file(), f"SKILL.md links a missing file: {target}")

    def test_all_reference_docs_are_reachable_from_skill(self) -> None:
        reachable: set[Path] = set()
        queue = [ROOT / "SKILL.md"]
        while queue:
            path = queue.pop()
            if path in reachable:
                continue
            reachable.add(path)
            text = path.read_text(encoding="utf-8")
            for target in LINK_PATTERN.findall(text):
                candidate = (path.parent / target).resolve()
                if candidate.is_file() and candidate.suffix == ".md" and candidate not in reachable:
                    queue.append(candidate)
        references = set((ROOT / "references").rglob("*.md"))
        unreachable = references - reachable
        self.assertEqual(
            unreachable,
            set(),
            "reference docs not reachable from SKILL.md: "
            + ", ".join(sorted(str(path.relative_to(ROOT)) for path in unreachable)),
        )


CARD_BASE = """chapter: 1
title: 第一章
viewpoint: hero
target_words: 100
goal: 找线索
conflict: 阻挠
change:
  plot: 推进
context:
  characters: [hero]
  world: []
"""

SENTENCE = "他把纸条摊在桌上，灯下的字迹被水汽晕开，只剩半行还能辨认。"


class CardFieldContract(unittest.TestCase):
    """v1.2: objectively checkable card fields are validated; semantics stay human."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "novel"
        run_script("init_novel.py", self.project, "--title", "字段契约")
        novel_path = self.project / "novel.yaml"
        novel = novel_path.read_text(encoding="utf-8")
        novel = novel.replace("viewpoint_characters: []", "viewpoint_characters: [hero]")
        novel = novel.replace("target_words: null", "target_words: 5000")
        novel = novel.replace("target_chapters: null", "target_chapters: 12")
        novel_path.write_text(novel, encoding="utf-8")
        (self.project / "characters" / "hero.yaml").write_text(
            "id: hero\nname: 主角\ncore:\n  desire: 找真相\n  fear: 失去线索\n", encoding="utf-8"
        )
        (self.project / "chapters" / "chapter-0001.md").write_text(
            "# 第一章\n\n" + SENTENCE * 8 + "\n", encoding="utf-8"
        )
        self.card = self.project / "control-cards" / "chapter-0001.yaml"
        self.write_card(CARD_BASE)

    def write_card(self, text: str) -> None:
        self.card.write_text(text, encoding="utf-8")

    def test_valid_card_passes(self) -> None:
        self.write_card(
            CARD_BASE
            + "scenes:\n  - 潜入仓库\nrequired_facts:\n  - 仓库在 23:10 停电\nforbidden:\n  - 直接自曝计划\n"
            + "ending:\n  mode: reversal\n  hook: 最后一页被撕走\n"
        )
        result = run_script("project_check.py", self.project)
        self.assertIn("OK:", result.stdout)

    def test_scenes_required_facts_and_forbidden_shapes(self) -> None:
        for fragment, expected in (
            ("scenes:\n  - 潜入仓库\n  - 3\n", "scenes must be a list of non-empty strings"),
            ('required_facts:\n  - ""\n', "required_facts must be a list of non-empty strings"),
            ("forbidden:\n  - 3\n", "forbidden must be a list of non-empty strings"),
        ):
            self.write_card(CARD_BASE + fragment)
            result = run_script("project_check.py", self.project, ok=False)
            self.assertEqual(result.returncode, 1)
            self.assertIn(expected, result.stdout)

    def test_ending_shape_is_checked_but_unknown_mode_only_warns(self) -> None:
        self.write_card(CARD_BASE + 'ending:\n  mode: ""\n')
        result = run_script("project_check.py", self.project, ok=False)
        self.assertIn("ending.mode must be a non-empty string", result.stdout)

        self.write_card(CARD_BASE + "ending: 5\n")
        result = run_script("project_check.py", self.project, ok=False)
        self.assertIn("ending must be a mapping", result.stdout)

        self.write_card(CARD_BASE + "ending:\n  mode: cliffhanger\n")
        result = run_script("project_check.py", self.project)
        self.assertIn("ending.mode 'cliffhanger'", result.stdout)

    def test_style_override_shape_and_keys(self) -> None:
        self.write_card(CARD_BASE + "style_override:\n  sentence-length: short\n")
        result = run_script("project_check.py", self.project, ok=False)
        self.assertIn("style_override has unknown parameter 'sentence-length'", result.stdout)

        self.write_card(CARD_BASE + 'style_override:\n  sentence_length: ""\n')
        result = run_script("project_check.py", self.project, ok=False)
        self.assertIn("style_override.sentence_length must not be empty", result.stdout)

        self.write_card(CARD_BASE + "style_override: 5\n")
        result = run_script("project_check.py", self.project, ok=False)
        self.assertIn("style_override must be a mapping", result.stdout)

    def test_card_forbidden_is_an_advisory_note(self) -> None:
        self.write_card(CARD_BASE + "forbidden:\n  - 他感到愤怒\n")
        (self.project / "chapters" / "chapter-0001.md").write_text(
            "# 第一章\n\n他感到愤怒，却没有说话。\n" + SENTENCE * 8 + "\n", encoding="utf-8"
        )
        result = run_script("review_chapter.py", self.project, "--chapter", 1, ok=False)
        self.assertEqual(result.returncode, 0)
        self.assertIn("[card-forbidden]", result.stdout)
        self.assertIn("'他感到愤怒'", result.stdout)


if __name__ == "__main__":
    unittest.main()
