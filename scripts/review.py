"""Deterministic, read-only review of one drafted chapter.

The module separates two kinds of output:

- BLOCK findings are reproducible structural problems (empty body, leftover
  placeholder text, obvious truncation, an unfilled control card).
- NOTE findings are evidence for author judgement (word-count gaps, repeated
  openings or endings, knowledge-boundary hints, style drift).

The review never changes the body, state or transactions, and a NOTE never
decides whether a chapter may be committed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import prose_metrics
from planning import filled, numbered_path
from project_yaml import ProjectYAMLError, read_yaml
from state_model import read_json, validate_state


HARD_PLACEHOLDER_PATTERNS = (
    ("marker", re.compile(r"\bTODO\b|\bTBD\b|\bFIXME\b|\bXXX\b", re.IGNORECASE)),
    ("template", re.compile(r"\{\{|\}\}|<!--|-->")),
    ("unfinished", re.compile(r"待补|待写|待填|待展开|此处补|此处展开")),
)

# Words that also occur in ordinary prose ("结果待定。"). They stay advisory so the
# blocking gate cannot false-block drafted dialogue.
SOFT_PLACEHOLDER_PATTERNS = (
    ("ambiguous", re.compile(r"待定|待续|占位|placeholder|lorem ipsum", re.IGNORECASE)),
)

DELIMITER_PAIRS = (
    ("“", "”"),
    ("‘", "’"),
    ("「", "」"),
    ("『", "』"),
    ("（", "）"),
    ("【", "】"),
    ("《", "》"),
    ("(", ")"),
    ("[", "]"),
    # Manuscripts written with straight quotes are common; an odd count is a
    # reproducible defect just like an unclosed full-width quote.
    ('"', '"'),
)

DANGLING_PUNCTUATION = "，,、：:；;"
DANGLING_WORDS = (
    "但是", "可是", "然而", "不过", "因为", "所以", "然后", "而且",
    "并且", "于是", "接着", "以及", "如果", "虽然", "尽管", "无论",
)
TERMINAL_CHARS = "。！？!?…”’\"'」』）)】]〉》"
MARKDOWN_PREFIXES = ("#", "-", "*", ">")

STYLE_FIELDS = (
    "tone", "pov_distance", "sentence_length", "rhythm",
    "dialogue_density", "description_density", "interiority", "ending_mode",
)


class ReviewInputError(Exception):
    """The chapter cannot be reviewed at all (missing body, bad state, bad YAML)."""


@dataclass
class Finding:
    level: str
    check: str
    path: Path
    line: int
    message: str
    basis: str
    fix: str


@dataclass
class Chapter:
    project: Path
    number: int
    body_path: Path | None
    body_text: str
    card_path: Path | None
    card: dict
    novel: dict
    state: dict


@dataclass
class StyleBaseline:
    chapters: list[int]
    paths: list[Path]
    metrics: dict
    available: bool
    reason: str


def display_path(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path)


def find_key_line(path: Path, key: str) -> int | None:
    """Best-effort line number for a top-level YAML key, for report locations."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:")
    for number, line in enumerate(lines, 1):
        if pattern.match(line) and not line.startswith((" ", "\t")):
            return number
    for number, line in enumerate(lines, 1):
        if pattern.match(line):
            return number
    return None


def load_chapter(project: Path, chapter: int | None = None) -> Chapter:
    """Read the body, card, config and state for one chapter without writing."""
    try:
        novel = read_yaml(project / "novel.yaml")
        state = read_json(project / "state" / "state.json")
    except (OSError, ValueError, ProjectYAMLError) as exc:
        raise ReviewInputError(str(exc)) from exc
    if not isinstance(novel, dict):
        raise ReviewInputError("novel.yaml must be a mapping")
    errors = validate_state(state)
    if errors:
        raise ReviewInputError("invalid state: " + "; ".join(errors))
    if chapter is None:
        chapter = state["project"]["current_chapter"] + 1
    if type(chapter) is not int or chapter < 1:
        raise ReviewInputError("--chapter must be a positive integer")

    body_path = numbered_path(project / "chapters", "chapter", chapter, ("md", "txt"))
    if body_path is None:
        raise ReviewInputError(
            f"chapter {chapter} body not found; expected chapters/chapter-{chapter:04d}.md "
            "or another supported numbered form"
        )
    try:
        body_text = body_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReviewInputError(f"cannot read chapter body {body_path}: {exc}") from exc

    card_path = numbered_path(project / "control-cards", "chapter", chapter, ("yaml", "yml"))
    card: dict = {}
    if card_path is not None:
        try:
            loaded = read_yaml(card_path)
        except (OSError, ProjectYAMLError) as exc:
            raise ReviewInputError(str(exc)) from exc
        if not isinstance(loaded, dict):
            raise ReviewInputError(f"{card_path}: root must be a mapping")
        card = loaded
    return Chapter(project, chapter, body_path, body_text, card_path, card, novel, state)


def unclosed_delimiters(text: str) -> list[tuple[int, str, str, int]]:
    """Return (line, open, close, count) for each delimiter left unmatched."""
    findings: list[tuple[int, str, str, int]] = []
    for open_char, close_char in DELIMITER_PAIRS:
        if open_char == close_char:
            count = text.count(open_char)
            if count % 2 == 1:
                last_line = max(
                    (number for number, raw in enumerate(text.splitlines(), 1) if open_char in raw),
                    default=1,
                )
                findings.append((last_line, open_char, close_char, 1))
            continue
        balance = 0
        last_open_line = 1
        for number, raw in enumerate(text.splitlines(), 1):
            for char in raw:
                if char == open_char:
                    balance += 1
                    last_open_line = number
                elif char == close_char:
                    balance -= 1
        if balance > 0:
            findings.append((last_open_line, open_char, close_char, balance))
    return findings


def knowledge_findings(chapter: Chapter) -> list[Finding]:
    """Advisory: an author-only truth appears on the page through this viewpoint."""
    if chapter.body_path is None:
        return []
    viewpoint = chapter.card.get("viewpoint")
    findings: list[Finding] = []
    revelations = chapter.state.get("revelations")
    if not isinstance(revelations, dict):
        return findings
    for revelation_id, item in revelations.items():
        if not isinstance(item, dict) or item.get("reader_known") is True:
            continue
        known_by = item.get("known_by") or []
        if isinstance(known_by, list) and viewpoint in known_by:
            continue
        truth = item.get("truth")
        if not isinstance(truth, str) or len(truth.strip()) < 4:
            continue
        index = chapter.body_text.find(truth.strip())
        if index < 0:
            continue
        line = chapter.body_text.count("\n", 0, index) + 1
        findings.append(
            Finding(
                "NOTE", "knowledge-boundary", chapter.body_path, line,
                f"author-only truth {revelation_id!r} appears in the body",
                f"revelations.{revelation_id}.reader_known is false and viewpoint "
                f"{viewpoint!r} is not in known_by",
                "confirm the viewpoint could know this on the page, or revise the "
                "card and transaction before commit.",
            )
        )
    return findings


def text_blocks(path: Path, text: str) -> list[Finding]:
    """Deterministic blocking prose checks shared by review, commit and project check."""
    findings: list[Finding] = []
    if not text.strip():
        return [
            Finding(
                "BLOCK", "empty-body", path, 1,
                "chapter body is empty",
                "the file contains no non-whitespace content",
                "write the chapter body before reviewing; an empty file must not be committed.",
            )
        ]

    lines = prose_metrics.paragraphs(text)
    for number, line in lines:
        for label, pattern in HARD_PLACEHOLDER_PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(
                    Finding(
                        "BLOCK", "placeholder", path, number,
                        f"leftover placeholder text: {match.group(0)!r}",
                        f"matched the {label} placeholder pattern in this line",
                        "replace the placeholder with drafted prose, or acknowledge it with "
                        "--allow placeholder --reason <text> when it is intentional.",
                    )
                )
                break

    for number, open_char, close_char, count in unclosed_delimiters(text):
        findings.append(
            Finding(
                "BLOCK", "unclosed-delimiter", path, number,
                f"{count} unclosed {open_char!r} without a matching {close_char!r}",
                f"the chapter has more {open_char!r} than {close_char!r}",
                "close the quoted or bracketed passage, or remove the stray delimiter.",
            )
        )

    last_number, last_line = lines[-1]
    stripped = last_line.rstrip()
    if stripped and stripped[-1] in DANGLING_PUNCTUATION:
        findings.append(
            Finding(
                "BLOCK", "dangling-ending", path, last_number,
                f"chapter ends with dangling punctuation {stripped[-1]!r}",
                "the last non-empty line stops mid-sentence",
                "finish the sentence or remove the fragment before committing.",
            )
        )
    else:
        connector = next((word for word in DANGLING_WORDS if stripped.endswith(word)), None)
        if connector:
            findings.append(
                Finding(
                    "BLOCK", "dangling-ending", path, last_number,
                    f"chapter ends with the connector {connector!r}",
                    "the last non-empty line stops before its clause completes",
                    "finish the sentence or remove the fragment before committing.",
                )
            )
    return findings


def body_findings(chapter: Chapter) -> list[Finding]:
    assert chapter.body_path is not None
    path = chapter.body_path
    text = chapter.body_text
    findings = text_blocks(path, text)
    if not text.strip():
        return findings

    lines = prose_metrics.paragraphs(text)
    for number, line in lines:
        for label, pattern in SOFT_PLACEHOLDER_PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(
                    Finding(
                        "NOTE", "placeholder-hint", path, number,
                        f"possible placeholder text: {match.group(0)!r}",
                        f"matched the {label} placeholder pattern; advisory because the word can occur in prose",
                        "confirm the line is drafted prose and not a leftover marker.",
                    )
                )
                break

    last_number, last_line = lines[-1]
    stripped = last_line.rstrip()
    if not any(finding.check == "dangling-ending" for finding in findings) and stripped and stripped[-1] not in TERMINAL_CHARS and not stripped.startswith(MARKDOWN_PREFIXES):
        findings.append(
            Finding(
                "NOTE", "ending-punctuation", path, last_number,
                f"last line has no terminal punctuation (ends with {stripped[-1]!r})",
                "prose lines normally end with a full stop, question mark or closing quote",
                "confirm the chapter is complete and not cut off.",
            )
        )

    target = chapter.card.get("target_words")
    words = prose_metrics.count_words(text)
    if type(target) is int and target > 0 and words < target * 0.8:
        findings.append(
            Finding(
                "NOTE", "word-count", path, 1,
                f"chapter has {words} words, below 80% of its {target} word target",
                "counted Chinese characters, English words and numbers; punctuation excluded",
                "expand the chapter or update target_words if the plan changed.",
            )
        )

    openings = prose_metrics.repeated_signatures(
        [(number, prose_metrics.opening_signature(line)) for number, line in lines]
    )
    for signature, numbers in openings:
        findings.append(
            Finding(
                "NOTE", "repeated-opening", path, numbers[0],
                f"{len(numbers)} paragraphs start with {signature!r}",
                "identical opening characters: lines " + ", ".join(map(str, numbers)),
                "vary paragraph openings or merge repeated beats.",
            )
        )

    endings = prose_metrics.repeated_signatures(
        [(number, prose_metrics.ending_signature(line)) for number, line in lines]
    )
    for signature, numbers in endings:
        findings.append(
            Finding(
                "NOTE", "repeated-ending", path, numbers[0],
                f"{len(numbers)} paragraphs end with {signature!r}",
                "identical closing characters: lines " + ", ".join(map(str, numbers)),
                "vary sentence endings and check for a repeated hook formula.",
            )
        )

    forbidden_sources: list[tuple[list, str, str]] = []
    style = chapter.novel.get("style")
    if isinstance(style, dict) and isinstance(style.get("forbidden"), list):
        forbidden_sources.append((style["forbidden"], "novel.yaml style.forbidden", "forbidden-expression"))
    card_forbidden = chapter.card.get("forbidden")
    if isinstance(card_forbidden, list):
        card_label = chapter.card_path.name if chapter.card_path is not None else "control card"
        forbidden_sources.append((card_forbidden, f"{card_label} forbidden", "card-forbidden"))
    for items, source, check in forbidden_sources:
        for item in items:
            if not isinstance(item, str) or not item.strip():
                continue
            index = text.find(item)
            if index < 0:
                continue
            line = text.count("\n", 0, index) + 1
            findings.append(
                Finding(
                    "NOTE", check, path, line,
                    f"matches forbidden expression {item!r}",
                    f"{source} lists this expression",
                    "revise it unless the match is intentional.",
                )
            )

    findings.extend(knowledge_findings(chapter))
    return findings


def card_findings(chapter: Chapter) -> list[Finding]:
    if chapter.card_path is None:
        return [
            Finding(
                "BLOCK", "card-missing", chapter.project / "control-cards", 0,
                f"chapter {chapter.number} has no control card",
                "no supported control-cards/chapter-NNNN.yaml was found",
                "create the control card before drafting or reviewing this chapter.",
            )
        ]
    path = chapter.card_path
    card = chapter.card
    findings: list[Finding] = []

    def locate(key: str) -> int:
        return find_key_line(path, key) or 1

    if card.get("chapter") != chapter.number:
        findings.append(
            Finding(
                "BLOCK", "card-chapter", path, locate("chapter"),
                f"card chapter field is {card.get('chapter')!r}, expected {chapter.number}",
                "the control card must describe the chapter under review",
                "set chapter to match the body file.",
            )
        )
    for key in ("goal", "conflict"):
        if not filled(card.get(key)):
            findings.append(
                Finding(
                    "BLOCK", f"card-{key}", path, locate(key),
                    f"control card {key} is empty or still a placeholder",
                    "a deterministic chapter-readiness field is unfilled",
                    f"fill {key} before committing.",
                )
            )
    change = card.get("change")
    if not isinstance(change, dict) or not any(filled(change.get(name)) for name in ("plot", "character", "relationship")):
        findings.append(
            Finding(
                "BLOCK", "card-change", path, locate("change"),
                "control card records no committed change",
                "change.plot, change.character and change.relationship are all empty",
                "fill at least one change so the chapter has an outcome.",
            )
        )
    if not filled(card.get("viewpoint")):
        findings.append(
            Finding(
                "BLOCK", "card-viewpoint", path, locate("viewpoint"),
                "control card viewpoint is empty",
                "every drafted chapter needs a viewpoint character",
                "set viewpoint to an allowed character id.",
            )
        )
    target = card.get("target_words")
    if type(target) is not int or target <= 0:
        findings.append(
            Finding(
                "NOTE", "card-target-words", path, locate("target_words"),
                "control card target_words is missing or not positive",
                "a word-count comparison is impossible without a target",
                "set target_words or accept the missing planning value.",
            )
        )
    return findings


def chapter_findings(chapter: Chapter) -> list[Finding]:
    findings = body_findings(chapter)
    findings.extend(card_findings(chapter))
    return findings


def baseline_chapters(project: Path, state: dict, chapter: int, window: int) -> StyleBaseline:
    current = state["project"]["current_chapter"]
    selected: list[tuple[int, Path]] = []
    for number in range(max(1, chapter - window), chapter):
        if number > current:
            continue
        path = numbered_path(project / "chapters", "chapter", number, ("md", "txt"))
        if path is not None:
            selected.append((number, path))
    texts: list[str] = []
    for _, path in selected:
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ReviewInputError(f"cannot read baseline chapter {path}: {exc}") from exc
    pooled = "\n\n".join(texts)
    value = prose_metrics.metrics(pooled)
    available = (
        value["paragraphs"] >= prose_metrics.MIN_BASELINE_PARAGRAPHS
        and value["characters"] >= prose_metrics.MIN_BASELINE_CHARACTERS
    )
    if available:
        reason = f"{len(selected)} chapter(s), {value['paragraphs']} paragraphs"
    else:
        reason = (
            f"only {value['paragraphs']} baseline paragraphs and {value['characters']} characters; "
            f"need at least {prose_metrics.MIN_BASELINE_PARAGRAPHS} paragraphs and "
            f"{prose_metrics.MIN_BASELINE_CHARACTERS} characters"
        )
    return StyleBaseline([number for number, _ in selected], [path for _, path in selected], value, available, reason)


def style_findings(chapter: Chapter, baseline: StyleBaseline) -> list[Finding]:
    if chapter.body_path is None or not baseline.available:
        return []
    target = prose_metrics.metrics(chapter.body_text)
    base = baseline.metrics
    path = chapter.body_path
    sample = ", ".join(map(str, baseline.chapters))
    override = chapter.card.get("style_override") if isinstance(chapter.card.get("style_override"), dict) else {}
    proposed = prose_metrics.style_proposals(target)
    findings: list[Finding] = []
    for check, key, threshold, declared_key in (
        ("style-sentence-length", "avg_sentence_chars", prose_metrics.SENTENCE_DRIFT, "sentence_length"),
        ("style-paragraph-length", "avg_paragraph_chars", prose_metrics.PARAGRAPH_DRIFT, None),
    ):
        base_value = base[key]
        target_value = target[key]
        if base_value <= 0:
            continue
        delta = (target_value - base_value) / base_value
        if abs(delta) <= threshold:
            continue
        declared = override.get(declared_key) if declared_key else None
        if declared_key and declared and declared == proposed.get(declared_key):
            findings.append(
                Finding(
                    "NOTE", "style-override", path, 1,
                    f"{key} is {target_value} vs baseline {base_value} ({delta:+.0%}), matching the declared override {declared!r}",
                    f"the control card declares style_override.{declared_key}={declared}; baseline pools chapters {sample}",
                    "no action needed unless the chapter reads differently than intended.",
                )
            )
            continue
        direction = "higher" if delta > 0 else "lower"
        basis = f"baseline pools chapters {sample}; threshold {threshold:.0%}"
        if declared_key and declared:
            basis += f"; the card declares {declared_key}={declared!r} but the chapter reads {proposed.get(declared_key)!r}"
        findings.append(
            Finding(
                "NOTE", check, path, 1,
                f"{key} is {target_value} vs baseline {base_value} ({delta:+.0%})",
                basis,
                f"this chapter reads {direction} in this dimension; adjust only if unintended.",
            )
        )
    delta = target["dialogue_line_ratio"] - base["dialogue_line_ratio"]
    if abs(delta) > prose_metrics.DIALOGUE_DRIFT:
        declared = override.get("dialogue_density")
        if declared and declared == proposed.get("dialogue_density"):
            findings.append(
                Finding(
                    "NOTE", "style-override", path, 1,
                    f"dialogue line ratio is {target['dialogue_line_ratio']} vs baseline {base['dialogue_line_ratio']} ({delta:+.3f}), matching the declared override {declared!r}",
                    f"the control card declares style_override.dialogue_density={declared}; baseline pools chapters {sample}",
                    "no action needed unless the chapter reads differently than intended.",
                )
            )
        else:
            direction = "more" if delta > 0 else "less"
            basis = f"baseline pools chapters {sample}; threshold {prose_metrics.DIALOGUE_DRIFT:.2f}"
            if declared:
                basis += f"; the card declares dialogue_density={declared!r} but the chapter reads {proposed.get('dialogue_density')!r}"
            findings.append(
                Finding(
                    "NOTE", "style-dialogue-ratio", path, 1,
                    f"dialogue line ratio is {target['dialogue_line_ratio']} vs baseline {base['dialogue_line_ratio']} ({delta:+.3f})",
                    basis,
                    f"this chapter carries {direction} dialogue than the baseline; confirm it is intended.",
                )
            )
    return findings


HOOK_PHRASES = ("他不知道的是", "她不知道的是", "然而", "但", "与此同时", "此刻", "而在另一边")


def first_prose_line(lines: list[tuple[int, str]]) -> str:
    """First non-heading paragraph, so chapter numbers do not count as an opening."""
    for _, line in lines:
        if not line.startswith("#"):
            return line
    return lines[0][1] if lines else ""


def _chapter_signatures(path: Path) -> tuple[str, str, bool] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = prose_metrics.paragraphs(text)
    if not lines:
        return None
    first = prose_metrics.opening_signature(first_prose_line(lines))
    last_line = lines[-1][1]
    return first, prose_metrics.ending_signature(last_line), any(phrase in last_line for phrase in HOOK_PHRASES)


def cross_chapter_findings(chapter: Chapter, baseline: StyleBaseline) -> list[Finding]:
    """Advisory: the target repeats the opening or ending formula of recent chapters."""
    if chapter.body_path is None or not baseline.available or not baseline.paths:
        return []
    target_lines = prose_metrics.paragraphs(chapter.body_text)
    if not target_lines:
        return []
    target_first = prose_metrics.opening_signature(first_prose_line(target_lines))
    target_last_line = target_lines[-1][1]
    target_last = prose_metrics.ending_signature(target_last_line)
    target_hook = any(phrase in target_last_line for phrase in HOOK_PHRASES)

    opening_matches: list[int] = []
    ending_matches: list[int] = []
    hook_matches: list[int] = []
    for number, path in zip(baseline.chapters, baseline.paths):
        signatures = _chapter_signatures(path)
        if signatures is None:
            continue
        first, last, hook = signatures
        if target_first and first == target_first:
            opening_matches.append(number)
        if target_last and last == target_last:
            ending_matches.append(number)
        if target_hook and hook:
            hook_matches.append(number)

    path = chapter.body_path
    findings: list[Finding] = []
    if len(opening_matches) >= 2:
        findings.append(
            Finding(
                "NOTE", "cross-chapter-opening", path, 1,
                f"opening signature {target_first!r} also opens chapters {', '.join(map(str, opening_matches))}",
                "the same first characters open several recent chapters",
                "vary how chapters enter their scene.",
            )
        )
    if len(ending_matches) >= 2:
        findings.append(
            Finding(
                "NOTE", "cross-chapter-ending", path, 1,
                f"ending signature {target_last!r} also ends chapters {', '.join(map(str, ending_matches))}",
                "the same closing characters end several recent chapters",
                "vary the closing beat.",
            )
        )
    if target_hook and len(hook_matches) >= 2:
        findings.append(
            Finding(
                "NOTE", "cross-chapter-hook", path, 1,
                f"the closing line uses a hook formula also used by chapters {', '.join(map(str, hook_matches))}",
                "a hook phrase from the shared list repeats across chapters",
                "keep it only if the repetition is intentional.",
            )
        )
    return findings


def format_finding(project: Path, finding: Finding) -> str:
    location = display_path(project, finding.path)
    if finding.line >= 1:
        location += f":{finding.line}"
    return (
        f"{finding.level} {location} [{finding.check}] {finding.message}; "
        f"basis: {finding.basis}; fix: {finding.fix}"
    )


def body_digest(text: str) -> str:
    """Short fingerprint of the reviewed text.

    Advisory findings and style drift are computed once; after the body changes
    the report silently describes an older revision. Printing the digest lets a
    later run show that the report is stale instead of being quoted as current.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def render_report(chapter: Chapter, findings: list[Finding]) -> str:
    def key(finding: Finding) -> tuple:
        return (finding.level != "BLOCK", display_path(chapter.project, finding.path), finding.line, finding.check)

    blocks = sorted((f for f in findings if f.level == "BLOCK"), key=key)
    notes = sorted((f for f in findings if f.level == "NOTE"), key=key)
    lines = [f"# Chapter Review: chapter {chapter.number}", ""]
    lines.append(f"- Body: {display_path(chapter.project, chapter.body_path)}")
    lines.append(f"- Control card: {display_path(chapter.project, chapter.card_path)}" if chapter.card_path else "- Control card: (missing)")
    lines.append(f"- Words: {prose_metrics.count_words(chapter.body_text)}")
    lines.append(
        f"- Body digest: sha256:{body_digest(chapter.body_text)} "
        "(re-run and compare after editing; a different digest means this report is stale)"
    )
    lines.append("")
    lines.append(f"## Blocking ({len(blocks)})")
    if blocks:
        lines.extend(format_finding(chapter.project, finding) for finding in blocks)
    else:
        lines.append("(none)")
    lines.append("")
    lines.append(f"## Advisory ({len(notes)})")
    if notes:
        lines.extend(format_finding(chapter.project, finding) for finding in notes)
    else:
        lines.append("(none)")
    lines.append("")
    lines.append("## Result")
    if blocks:
        lines.append(
            f"FAIL: {len(blocks)} blocking finding(s); clear them before committing the chapter transaction."
        )
    else:
        lines.append(f"PASS: no blocking findings; {len(notes)} advisory finding(s) for author judgement.")
    return "\n".join(lines)


def render_style_report(chapter: Chapter, baseline: StyleBaseline, findings: list[Finding], cross_findings: list[Finding] | None = None) -> str:
    target = prose_metrics.metrics(chapter.body_text)
    lines = [f"# Style Report: chapter {chapter.number}", ""]
    lines.append(f"- Sample: {display_path(chapter.project, chapter.body_path)}")
    lines.append(
        "- Baseline chapters: " + (", ".join(map(str, baseline.chapters)) if baseline.chapters else "none")
    )
    if baseline.available:
        lines.append(
            f"- Baseline size: {baseline.metrics['paragraphs']} paragraphs, "
            f"{baseline.metrics['characters']} characters"
        )
    else:
        lines.append(f"- Baseline: none ({baseline.reason})")
    lines.append("")
    lines.append("## Definitions")
    lines.append("- sentence: split on 。！？!?… and line breaks; length excludes whitespace")
    lines.append("- paragraph: each non-empty line; length excludes whitespace")
    lines.append("- dialogue ratio: non-empty lines carrying full-width or straight quotes, or opening with a speech tag, divided by all non-empty lines")
    lines.append(
        f"- drift thresholds: sentence +/-{prose_metrics.SENTENCE_DRIFT:.0%}, "
        f"paragraph +/-{prose_metrics.PARAGRAPH_DRIFT:.0%}, "
        f"dialogue ratio +/-{prose_metrics.DIALOGUE_DRIFT:.2f}"
    )
    lines.append(f"- repeated signature length: {prose_metrics.OPENING_LENGTH} characters, minimum "
                 f"{prose_metrics.REPEAT_MINIMUM} occurrences")
    lines.append("")

    lines.append("## Declared style (novel.yaml)")
    style = chapter.novel.get("style") if isinstance(chapter.novel.get("style"), dict) else {}
    declared = [f"- {field}: {style[field]}" for field in STYLE_FIELDS if field in style]
    lines.extend(declared if declared else ["(none)"])
    lines.append("")

    override = chapter.card.get("style_override") if isinstance(chapter.card.get("style_override"), dict) else {}
    lines.append("## Declared override (control card)")
    lines.extend([f"- {key}: {value}" for key, value in sorted(override.items())] if override else ["(none)"])
    lines.append("")

    lines.append("## Metrics")
    base = baseline.metrics
    lines.append(
        f"- sentences: chapter {target['sentences']} | baseline {base['sentences']}"
    )
    lines.append(
        f"- avg_sentence_chars: chapter {target['avg_sentence_chars']} | "
        f"baseline {base['avg_sentence_chars']}"
    )
    lines.append(
        f"- avg_paragraph_chars: chapter {target['avg_paragraph_chars']} | "
        f"baseline {base['avg_paragraph_chars']}"
    )
    lines.append(
        f"- dialogue_line_ratio: chapter {target['dialogue_line_ratio']} | "
        f"baseline {base['dialogue_line_ratio']}"
    )
    for label, signature, numbers in _repeat_lines("repeated openings", target["repeated_openings"]):
        lines.append(f"- {label} ({signature!r}): lines " + ", ".join(map(str, numbers)))
    if not target["repeated_openings"]:
        lines.append("- repeated openings: none")
    for label, signature, numbers in _repeat_lines("repeated endings", target["repeated_endings"]):
        lines.append(f"- {label} ({signature!r}): lines " + ", ".join(map(str, numbers)))
    if not target["repeated_endings"]:
        lines.append("- repeated endings: none")
    lines.append("")

    lines.append("## Habits (chapter)")
    lines.append("- top bigrams: " + (", ".join(f"{term} {count}" for term, count in target["top_bigrams"]) or "none"))
    if target["top_latin_words"]:
        lines.append("- top latin words: " + ", ".join(f"{term} {count}" for term, count in target["top_latin_words"]))
    lines.append("- punctuation per 100 chars: " + (", ".join(f"{mark} {rate}" for mark, _, rate in target["punctuation_profile"]) or "none"))
    lines.append(f"- CJK type-token ratio: {target['cjk_type_token_ratio']}")
    lines.append("")

    lines.append(f"## Drift hints ({len(findings)})")
    if findings:
        lines.extend(format_finding(chapter.project, finding) for finding in findings)
    else:
        lines.append("(none)")
    lines.append("")
    cross = cross_findings or []
    lines.append(f"## Cross-chapter patterns ({len(cross)})")
    if cross:
        lines.extend(format_finding(chapter.project, finding) for finding in cross)
    else:
        lines.append("(none)")
    lines.append("")
    lines.append("These hints are advisory. They never replace an author read of the chapter.")
    return "\n".join(lines)


def _repeat_lines(label: str, repeats: list[tuple[str, list[int]]]) -> list[tuple[str, str, list[int]]]:
    return [(label, signature, numbers) for signature, numbers in repeats]
