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
- 支持悬疑、惊悚、言情、奇幻、仙侠、科幻、历史、都市等题材，也允许组合。
- 改稿时按结构、人物、对话、描写、语言和连续性的顺序检查。

## 使用

把本仓库作为 Agent Skill 使用；在支持 Skill 加载机制的环境中，可将目录安装、复制或链接到对应的 skills 目录。调用示例：

```text
Use $novel-writer-skill to create a 60-chapter urban mystery novel with a restrained tone,
third-person limited POV, high dialogue density, and low exposition density.
```

初始化小说项目：

```bash
python3 scripts/init_novel.py /path/to/my-novel --title "小说名"
```

生成下一章上下文包：

```bash
python3 scripts/build_context.py /path/to/my-novel \
  --compact-state \
  --output /tmp/chapter-context.md
```

每章完成后可提交状态事务：

```bash
python3 scripts/state_commit.py /path/to/my-novel/state/state.json /path/to/my-novel/state/transactions/chapter-0001.json
python3 scripts/project_check.py /path/to/my-novel
```

整本完成后运行 `python3 scripts/project_check.py /path/to/my-novel --complete`。重写旧章用 `scripts/state_rebuild.py` 从 `state/initial.json` 和事务日志重建状态；具体步骤见 [完整成书流程](references/full-book-workflow.md) 与 [连续性事务](references/continuity-state.md)。

校验器按汉字逐字、英文逐词计数，不计标点和空行。项目 YAML 使用常见的缩进映射、列表和标量；当前标准库解析器不支持锚点、标签和多行块标量。

详细流程见 [SKILL.md](SKILL.md)。
