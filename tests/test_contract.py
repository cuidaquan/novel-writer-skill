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


if __name__ == "__main__":
    unittest.main()
