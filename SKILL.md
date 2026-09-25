---
name: novel-writer-skill
description: Create, continue, or revise fiction projects—especially novels and serialized stories—when genre, prose style, POV, pacing, chapter planning, or long-form continuity need explicit control.
---

# Novel Writer

按用户要求选择创作规模。短篇可直接交付正文；需要整本、连载或长期改稿时，维护 `novel.yaml` 的创作配置和 `state/state.json` 的已成立事实。

## 选择工作模式

- **短篇正文**：按 [references/workflow.md](references/workflow.md) 的轻量流程写作；用户没有要求项目文件时，直接交付正文。
- **新建项目或整本小说**：先读 [references/workflow.md](references/workflow.md) 与 [references/planning-preflight.md](references/planning-preflight.md)；要求完整成书时还须读 [references/full-book-workflow.md](references/full-book-workflow.md)，按章推进并通过完成校验。
- **续写章节**：先读 [references/context-assembly.md](references/context-assembly.md) 装配上下文，再读 [references/chapter-cards.md](references/chapter-cards.md)、[references/continuity-state.md](references/continuity-state.md) 与 [references/handoff-continuity.md](references/handoff-continuity.md)，用 `scripts/handoff_report.py` 查看下一章必须承接的压力。
- **重写旧章节**：读 [references/continuity-state.md](references/continuity-state.md)，用 `scripts/state_rebuild.py` 得到旧章之前的事实快照；重写后核对、重放后续事务。
- **定义或调整文风**：读 [references/style-system.md](references/style-system.md)。把文风拆成可描述的参数，不把某个作者姓名当作文风配置本身；可用 `scripts/style_profile.py` 从定稿章节或样章提取可复核画像。
- **选择或混合题材**：读 [references/genre-system.md](references/genre-system.md)。只加载当前题材真正需要的约束；章卡可用 `payoff` 记录类型回报，`scripts/promise_report.py` 跟踪连续延后。
- **改稿/审稿**：先按 [references/post-draft-review.md](references/post-draft-review.md) 做只读的写后审查（`scripts/review_chapter.py`、`scripts/style_report.py`），再读 [references/revision-quality.md](references/revision-quality.md)，先修剧情和场景，再修语言。

## 配置优先级

发生冲突时按以下优先级处理：

1. 用户本轮明确要求。
2. 已确认的正文事实和用户手工修改。
3. 项目 `novel.yaml` 与 `state/state.json`。
4. 当前章节控制卡。
5. 题材与文风 reference。

不要为了套模板覆盖已经成立的人物设定、时间线或用户手工修改。

## 长篇写作原则

每章动笔前，先确认本章结束时会发生什么**状态变化**。至少明确主冲突、推进的剧情线、人物关系变化、需要触碰的伏笔以及章末牵引。没有状态变化的场景通常应压缩、合并或承担更明确的角色功能。

有隐藏真相的项目，把已确定的作者真相和知情边界记在 `state.revelations`；章卡列出本章触碰或揭示的条目。正文只能按当前视角与场景证据释放信息，写完后才把真正揭示的内容提交为读者已知。

正文只写角色当下能够感知、推断或误解的内容。解释性背景优先拆进动作、选择、对话、环境和后果中，避免用旁白代替戏剧过程。

正文完成后先用 `scripts/review_chapter.py` 做只读审查，修掉 `BLOCK` 项，再用 `scripts/style_report.py` 查看文风偏移。场景因果、POV/知识边界、角色行为和类型承诺仍须人工核对，脚本不能证明文学质量；完整顺序见 [references/post-draft-review.md](references/post-draft-review.md)。核对后按最终正文生成事务 JSON，用 `scripts/state_commit.py` 更新状态；提交前核对事务只写正文真实发生的变化。每章运行 `scripts/project_check.py`；整本交付前运行 `scripts/project_check.py --complete`，并人工核对结构、人物弧和类型承诺。

每章事务可用 `handoff.carry_over` 记录下一章必须承接、且仍在 `plot_threads` 或 `foreshadowing` 中活跃的条目；`scripts/handoff_report.py` 只读报告显式承接、活跃压力与长期未推进项，`project_check.py` 会核对章卡承诺是否落入事务。

项目化写正文前，整本创作运行 `scripts/project_check.py <project> --preflight book`，连载创作运行 `--preflight serial`。缺项先补计划；`build_context.py` 也会检查即将写的章节。一次性短篇正文仍走轻量流程。命令失败时按 [失败恢复](references/failure-recovery.md) 处理，旧章改稿后的重放冲突见该文与 [连续性与状态事务](references/continuity-state.md)。

## 项目文件约定

推荐小说项目结构：

```text
novel-project/
├── novel.yaml
├── outline/
│   ├── master.md
│   └── volumes/
├── characters/
├── world/
├── chapters/
├── control-cards/
└── state/
    ├── initial.json
    ├── state.json
    └── transactions/
```

`state/initial.json` 和逐章事务可重放出当前状态。Markdown 设定、人物卡和总结用于阅读与创作；发现冲突时先根据正文与用户说明确定事实，再同步修正状态和受影响的事务。新建项目的公开字段、错误级别与 `schema_version` 见 [项目契约](references/project-contract.md)。

## 写作交付

用户只要求正文时，直接交付正文。用户要求项目化创作时，写入章节、控制卡和状态事务；要求整本时，交付实际章节数、字数与未解决问题的核对结果。
