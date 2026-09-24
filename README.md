# novel-writer-skill

面向 Codex 的长篇小说创作 Skill。它把题材、文风、POV、节奏等创作参数与人物、伏笔、剧情线、时间线等连续性事实分开管理，适合从开书到多章节续写的项目化创作。

## 能做什么

- 用 `novel.yaml` 定义主类型、混合类型、叙事视角、语气、句式、对话密度、描写密度、节奏与禁用表达。
- 用章节控制卡明确每章的目标、冲突、状态变化、伏笔和章末牵引。
- 用 `state/state.json` 保存长篇连续性事实，并通过事务脚本逐章提交。
- 支持悬疑、惊悚、言情、奇幻、仙侠、科幻、历史、都市等题材，也允许组合。
- 改稿时按结构、人物、对话、描写、语言和连续性的顺序检查。

## 使用

把本仓库作为 Codex Skill 使用，或将目录复制/链接到 Codex skills 目录。可直接调用：

```text
Use $novel-writer-skill to create a 60-chapter urban mystery novel with a restrained tone,
third-person limited POV, high dialogue density, and low exposition density.
```

初始化小说项目：

```bash
python3 scripts/init_novel.py /path/to/my-novel --title "小说名"
```

每章完成后可提交状态事务：

```bash
python3 scripts/state_commit.py /path/to/my-novel/state/state.json transaction.json
python3 scripts/state_check.py /path/to/my-novel/state/state.json
```

详细流程见 [SKILL.md](SKILL.md)。
