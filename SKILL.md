---
name: novel-writer-skill
description: Create, continue, or revise fiction projects—especially novels and serialized stories—when genre, prose style, POV, pacing, chapter planning, or long-form continuity need explicit control.
---

# Novel Writer

把小说当作一个持续演化的项目，而不是一次性的长 Prompt。优先维护“创作配置”和“故事事实”两类信息：`novel.yaml` 决定题材、文风、视角和节奏；`state/state.json` 记录已经在正文中成立的事实。

## 选择工作模式

- **新建小说**：先读取 [references/workflow.md](references/workflow.md) 的初始化流程。需要实际创建项目目录时，优先运行 `scripts/init_novel.py`，再按用户要求补充设定。
- **续写章节**：先读 `novel.yaml`、`state/state.json`、当前卷纲/章纲和最近 1–3 章；再读 [references/chapter-cards.md](references/chapter-cards.md) 与 [references/continuity-state.md](references/continuity-state.md)。
- **定义或调整文风**：读 [references/style-system.md](references/style-system.md)。把文风拆成可描述的参数，不把某个作者姓名当作文风配置本身。
- **选择或混合题材**：读 [references/genre-system.md](references/genre-system.md)。只加载当前题材真正需要的约束。
- **改稿/审稿**：读 [references/revision-quality.md](references/revision-quality.md)，先修剧情和场景，再修语言。

## 配置优先级

发生冲突时按以下优先级处理：

1. 用户本轮明确要求。
2. 项目 `novel.yaml`。
3. 当前章节控制卡。
4. 题材与文风 reference。
5. 本 Skill 的默认建议。

不要为了套模板覆盖已经成立的人物设定、时间线或用户手工修改。

## 长篇写作原则

每章动笔前，先确认本章结束时会发生什么**状态变化**。至少明确主冲突、推进的剧情线、人物关系变化、需要触碰的伏笔以及章末牵引。没有状态变化的场景通常应压缩、合并或承担更明确的角色功能。

正文只写角色当下能够感知、推断或误解的内容。解释性背景优先拆进动作、选择、对话、环境和后果中，避免用旁白代替戏剧过程。

章节写完后再更新状态。不要在正文尚未稳定时提前修改事实源；需要回写时生成事务 JSON，并使用 `scripts/state_commit.py` 原子地更新 `state/state.json`。提交后运行 `scripts/state_check.py`。

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
    ├── state.json
    └── transactions/
```

`state/state.json` 是结构化事实源。Markdown 设定、人物卡和总结用于阅读与创作，不应与事实源悄悄分叉；发现冲突时先根据正文与用户明确说明确定哪一边是真实状态，再同步修正。

## 写作交付

用户只要求正文时，直接交付正文，不展示内部检查清单。用户要求项目化创作时，把章节、控制卡和状态事务写入对应文件，并说明本章实际推进了哪些剧情事实。
