# 项目契约（v1.0）

本文件是新建项目公开字段的唯一权威说明。代码、模板与样例以本文为准；本版不提供旧项目导入或迁移。字段名使用 YAML/JSON 键名。

## 版本标识

- `novel.yaml` 与 `state/*.json` 都带 `schema_version`，当前为 `1`。缺失或不等于 `1` 时，写前检查与项目校验报错。
- 技能版本见仓库根目录 `VERSION`，变更见 [CHANGELOG.md](../CHANGELOG.md)，已知限制见 [已知限制](known-limitations.md)。

## 目录结构

```text
novel-project/
├── novel.yaml
├── outline/master.md
├── outline/volumes/volume-NN.md
├── characters/<id>.yaml
├── world/<topic>.md
├── chapters/chapter-NNNN.md
├── control-cards/chapter-NNNN.yaml
└── state/{initial.json, state.json, transactions/chapter-NNNN.json}
```

正文与章卡也兼容 `chapter-N.*`、`NNNN.*`、`N.*`。事务必须是连续的 `chapter-0001.json`、`chapter-0002.json`……

## novel.yaml

- `schema_version`：整数，必须为 `1`。
- `title`：非空字符串，必须与 `state.project.title` 一致。
- `language`、`audience`：字符串。
- `genre.primary`：模块 id（小写字母、数字、连字符）；`genre.secondary`：模块 id 列表，最多两个。
- `length.target_words`、`length.target_chapters`：正整数或 `null`。
- `narration.pov`、`narration.tense`：字符串。
- `narration.viewpoint_characters`：人物 id 列表，每个都要有 `characters/<id>.(yaml|yml)`。
- `style`：`tone`、`pov_distance`、`sentence_length`、`rhythm`、`dialogue_density`、`exposition_density`、`description_density`、`sensory_detail`、`interiority`、`metaphor_density`、`humor`、`ending_mode` 等可观察参数。
- `style.modules`：已知场景模块 id 列表；`style.forbidden`：字符串列表。
- `content_limits`：字符串列表。

## 章节控制卡 control-cards/chapter-NNNN.yaml

- `chapter`：整数，必须等于文件名编号。
- `title`：字符串。
- `viewpoint`：人物 id，必须属于 `narration.viewpoint_characters`。
- `target_words`：正整数。
- `goal`、`conflict`：非空字符串。
- `context.characters`：人物 id 列表；`context.world`：`world/` 下的相对路径列表。
- `scenes`：列表（可选）。
- `change.plot`、`change.character`、`change.relationship`：至少一项非空。
- `threads.advance`、`threads.touch`：已有剧情线 id 列表。
- `foreshadowing.plant`、`foreshadowing.pay_off`：已有伏笔 id 列表。
- `revelations.touch`、`revelations.reveal`：已有真相 id 列表；`reveal` 必须在同章事务中标为读者已知，事务里的读者揭示也必须在章卡出现。
- `style_modules`：已知场景模块 id 列表，可覆盖本书的 `style.modules`。
- `required_facts`、`forbidden`：字符串列表。
- `payoff.expected`、`payoff.status`、`payoff.reason`：可选类型回报；`status` 取 `fulfilled` 或 `deferred`，延后时 `reason` 必填。
- `ending.mode`、`ending.hook`：字符串。

## 状态 state/initial.json 与 state/state.json

- `schema_version`：必须为 `1`。
- `project`：`title`（与 novel.yaml 一致）、`current_volume`（正整数）、`current_chapter`（非负整数）、`last_chapter_title`、`last_chapter_summary`。
- `characters`、`relationships`：id → 对象。
- `plot_threads`：id → 对象，`status` 取 `open`、`paused`、`resolved`。
- `foreshadowing`：id → 对象，`status` 取 `planted`、`active`、`resolved`、`dropped`；`resolved` 必须有 `resolved_chapter`，且不晚于当前章。
- `revelations`：id → 对象，含 `truth`（作者真相）、`known_by`（人物 id 列表）、`reader_known`（布尔）；`reader_known` 为真时必须有 `revealed_chapter`。读者已知不能撤销，`truth` 不能在事务中更改。
- `timeline`：事件对象列表，`id` 唯一，`chapter` 在 `1..current_chapter`。
- `continuity_notes`：非空字符串列表。
- `handoff`：`chapter`（必须等于 `current_chapter`）、`carry_over`（引用仍然活跃的 `plot_threads` 或 `foreshadowing` id）、`notes`（字符串列表）。

`initial.json` 是第 0 章快照（`current_chapter=0`）；`state.json` 由 `initial.json` 加逐章事务重放得到，是唯一当前快照。

## 事务 state/transactions/chapter-NNNN.json

- `expected_chapter`：必须等于提交前的 `current_chapter`。
- `chapter`：必须等于 `expected_chapter + 1`。
- `chapter_title`：字符串；已提交时须与章卡 `title` 一致。
- `summary`：非空字符串。
- `character_updates`、`relationship_updates`、`plot_thread_updates`、`foreshadowing_updates`、`revelation_updates`：id → 对象或 `null`；`revelations` 不能用 `null` 删除。
- `timeline_events`：事件对象列表，`id` 非空且全局唯一，章号隐含为本章。
- `continuity_notes_add`：非空字符串列表。
- `handoff`：`carry_over`、`notes`（可选）。

旧章改动后必须重放：先确认 `initial.json` 可信，逐章核对事务，再 `state_rebuild.py --write`。

## 输出与退出码

- `review_chapter.py`：逐行 `BLOCK` / `NOTE`，含文件、行号、依据与修订方向；有 `BLOCK` 退出 1，仅 `NOTE` 退出 0，输入错误退出 2。
- `style_report.py`、`handoff_report.py`、`promise_report.py`：只读、advisory；成功退出 0，输入错误退出 2。
- `style_profile.py`：样本不足时输出 `INSUFFICIENT` 且退出 1；成功退出 0，输入错误退出 2。
- `project_check.py`：有问题退出 1，否则 0；`ERROR` 为阻断，`WARN` 为提示。
- `state_commit.py`：非法事务不改动状态，退出 1；成功打印提交章号。

## 校验层级

1. 写前：`project_check.py --preflight book|serial`；`build_context.py` 也会检查目标章。
2. 写后：`review_chapter.py`（可加 `--style`）。
3. 提交：`state_commit.py`。
4. 项目：`project_check.py`；完结 `--complete`。
5. 连续性：`state_rebuild.py`、`handoff_report.py`。
6. 风格与类型：`style_report.py`、`style_profile.py`、`promise_report.py`。

## 错误级别

- 阻断：结构、状态、事务、章卡必填项、承诺缺失、揭示时间、完结门禁、写前缺项。
- 提示：字数偏差、重复开头/结尾、文风偏移、交接漂移、连续延后、知识边界提示。
