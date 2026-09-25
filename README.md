# novel-writer-skill

面向 AI Agent 的长篇小说创作 Skill。它把题材、文风、POV、节奏等创作参数与人物、伏笔、剧情线、时间线等连续性事实分开管理，适合从开书到多章节续写的项目化创作。

## 能做什么

- 用 `novel.yaml` 定义主类型、混合类型、叙事视角、语气、句式、对话密度、描写密度、节奏与禁用表达。
- 用章节控制卡明确每章的字数预算、POV、目标、冲突、状态变化和需要读取的资料。
- 用标准库脚本按章装配配置、状态、纲要、近期正文及章卡引用的人物/世界观资料。
- 用第 0 章快照和逐章事务记录连续性事实，支持旧章改稿后的状态重建。
- 分开记录作者已确定的真相、角色知情范围和读者已知边界；章节事务校验揭示时间。
- 在章节上下文中按需加载悬疑、言情与场景文风模块。
- 用项目校验检查章节数量、字数、事务重放及完结时的未解决剧情线。
- 写正文后用只读的单章审查报告定位空正文、残留占位、明显截断和章卡缺项，按 BLOCK/NOTE 分级并给出文件/行号、命中依据和修订方向。
- 用近期定稿章节做基线，提示句长、段落长度、对话比例和重复开头/结尾的偏移；样本不足时明确标记无基线，偏移只作提示。
- 用 `handoff` 契约记录下一章必须承接的压力，事务重放得到唯一的当前交接状态；`scripts/handoff_report.py` 报出长期未推进的主线/关系/伏笔。
- `--compact-state` 优先装配 POV、章卡引用、活跃压力与知识边界，并给出省略摘要；`--fit` 可在预算内裁剪。
- 用 `style_profile.py` 从定稿章节或样章提取可复核画像并建议文风参数；`build_context.py --style-anchor` 可把简短观测锚点放进上下文。
- 章卡可用 `payoff` 记录类型回报，`promise_report.py` 提示连续延后，并在悬疑/言情下分别追踪信息控制与关系推进。
- 提交前重跑确定性审查，未放行的 BLOCK 会拒绝写入；刻意命中可用带理由的 `--allow` 放行并留痕，完结校验会复核已提交章节。
- 完结时收口类型承诺：仍标为延后的承诺会被 `--complete` 列出，`dropped`（需理由）视为作者已明确放弃。
- 精简上下文分层：本章引用与交接承诺保完整，其余活跃条目按上限摘要；`--active-limit` 可控，`--fit` 逐级裁剪。
- 章卡字段按“脚本校验 / 人工核对 / 仅上下文”分级；`scenes`、`required_facts`、`forbidden`、`ending` 的结构由脚本校验，语义兑现仍由作者核对。
- 章卡可用 `style_override` 声明本章局部文风覆盖；`style_report` 把与声明一致的偏移标为覆盖而不是漂移。
- `style_report` 对照近期定稿章的开场/结尾签名，提示连续同类开场或悬念句；`style_profile` 输出词频、标点频率与字符型例比（只作观察，不设阈值）。
- `progress_report.py` 给出进度、剩余章节、按均速的预计完稿与未收束条目；`state_view.py --write/--check` 生成并校验派生状态视图；`stage_review.py` 把进度、交接、承诺与文风聚合成阶段复盘。
- `build_context.py` 清单标注哪些题材有专门模块、哪些走通用路径。
- `prose_lint.py` 按项目规则扫描重复用词、句式套路与标点习惯；全部命中只作提示，规则默认不启用。
- 写正文前可分别检查整本规划或连载当前阶段；未就绪的章卡不能生成下一章上下文。
- 支持悬疑、惊悚、言情、奇幻、仙侠、科幻、历史、都市等题材，也允许组合。
- 改稿时按结构、人物、对话、描写、语言和连续性的顺序检查。

## 使用

把本仓库作为 Agent Skill 使用；在支持 Skill 加载机制的环境中，可将目录安装、复制或链接到对应的 skills 目录。调用示例：

```text
Use $novel-writer-skill to create a 60-chapter urban mystery novel with a restrained tone,
third-person limited POV, high dialogue density, and low exposition density.
```

## 按工作模式的最短路径

- **短篇正文**：用户只要正文时直接写，不必建项目；需要文件化时可建单章项目走整本流程。
- **中篇/新书整本**：要求完整故事或项目文件时都按整本处理：`init_novel.py` → 填 `novel.yaml`、总纲与章卡 → `project_check.py --preflight book` → 每章 `build_context.py` → 写正文 → `review_chapter.py` → `state_commit.py`（未放行的 BLOCK 会拒绝提交）→ `project_check.py`，阶段复盘用 `stage_review.py` 汇总，最后 `--complete`。
- **连载续写**：确认当前阶段纲后 `project_check.py --preflight serial` → `build_context.py --compact-state` → 写正文 → `review_chapter.py` → `state_commit.py` → `project_check.py`；阶段回顾加 `handoff_report.py` 与 `promise_report.py`。
- **改稿/审稿**：先 `review_chapter.py`（必要时 `--style`）与 `style_report.py`，再按 [改稿顺序](references/revision-quality.md) 人工核对；步骤见 [写后审查](references/post-draft-review.md)。
- **重写旧章**：`state_rebuild.py --through N-1` 取快照 → `build_context.py --chapter N --state ...` → 改正文与事务 → `state_rebuild.py --write` → `project_check.py`。
- **完结验收**：`handoff_report.py` 清点承接，`project_check.py --complete` 校验章节、字数与未收束线索。

命令失败时按 [失败恢复](references/failure-recovery.md) 处理。

初始化小说项目：

```bash
python3 scripts/init_novel.py /path/to/my-novel --title "小说名"
```

动笔前检查规划（按创作模式二选一）：

```bash
python3 scripts/project_check.py /path/to/my-novel --preflight book
python3 scripts/project_check.py /path/to/my-novel --preflight serial
```

生成下一章上下文包：

```bash
python3 scripts/build_context.py /path/to/my-novel \
  --compact-state \
  --output /tmp/chapter-context.md
```

正文完成后先做只读审查，再按修订结果提交事务：

```bash
python3 scripts/review_chapter.py /path/to/my-novel --chapter 1
python3 scripts/style_report.py /path/to/my-novel --chapter 1
python3 scripts/handoff_report.py /path/to/my-novel --stale 5
python3 scripts/style_profile.py /path/to/my-novel --recent 5
python3 scripts/promise_report.py /path/to/my-novel --deferred-streak 3
python3 scripts/progress_report.py /path/to/my-novel
python3 scripts/state_view.py /path/to/my-novel --write /tmp/state-view.md
python3 scripts/stage_review.py /path/to/my-novel
python3 scripts/prose_lint.py /path/to/my-novel --all --default-rules
```

每章完成后可提交状态事务：

```bash
python3 scripts/state_commit.py /path/to/my-novel/state/state.json /path/to/my-novel/state/transactions/chapter-0001.json
python3 scripts/project_check.py /path/to/my-novel
```

整本完成后运行 `python3 scripts/project_check.py /path/to/my-novel --complete`。重写旧章用 `scripts/state_rebuild.py` 从 `state/initial.json` 和事务日志重建状态；具体步骤见 [完整成书流程](references/full-book-workflow.md) 与 [连续性事务](references/continuity-state.md)。

校验器按汉字逐字、英文逐词计数，不计标点和空行。项目 YAML 使用常见的缩进映射、列表和标量；当前标准库解析器不支持锚点、标签和多行块标量。

## 支持环境

- 当前版本 1.4.0；变更见 [CHANGELOG.md](CHANGELOG.md)，公开字段见 [项目契约](references/project-contract.md)，已知限制见 [已知限制](references/known-limitations.md)。
- Python 3.9 及以上；脚本只用标准库，不安装第三方包。
- 路径处理使用 `pathlib`，展示路径统一用正斜杠；Windows 上命令分隔符与本地路径写法需按 shell 调整。
- 自动化测试在 macOS/POSIX 上运行；Windows 未纳入本仓库的自动化验证，限制如实标注，不以文档代替验证。

详细流程见 [SKILL.md](SKILL.md)。
