# 写后审查与人工核对

正文完成后、提交状态事务之前做写后审查。审查分两类：脚本能复现的确定性问题，和只能由作者判断的读感问题。脚本只负责前者并给出位置，不能证明文学质量。

## 命令

```bash
python3 scripts/review_chapter.py /path/to/novel              # 审查 current_chapter + 1
python3 scripts/review_chapter.py /path/to/novel --chapter 12 # 审查指定章节
python3 scripts/style_report.py /path/to/novel --chapter 12   # 只看文风画像与偏移
python3 scripts/review_chapter.py /path/to/novel --style      # 审查后附文风报告
```

`review_chapter.py` 是只读命令，不修改正文、状态或事务。报告含级别、文件/行号、命中依据和修订方向：

- `BLOCK`：可以复现的结构问题，例如空正文、残留占位内容、明显截断、括号或引号未闭合、章卡必填项未填。提交事务前必须处理。
- `NOTE`：字数偏低、重复开头/结尾、命中禁用表达、知识边界提示、文风偏移等，只提供证据，不单独决定能否提交。

退出码约定：有 `BLOCK` 返回 1，只有 `NOTE` 返回 0，输入错误（例如找不到正文）返回 2。

`style_report.py` 把本章的句长、段落长度、对话比例和重复开头/结尾，与最近已定稿章节的合并样本对照。报告会写明取样范围、指标定义和阈值；样本不足时明确写“无基线”，不虚构结论。偏移只是提示，不用单一分数替代审稿。

## 三层核对顺序

1. **确定性问题**：先运行 `review_chapter.py`，修掉所有 `BLOCK`。
2. **场景与因果**：每个场景是否有目标、阻力、选择和后果；本章事件是否由人物选择、外部压力或既有事实推动。
3. **POV 与知识边界**：正文是否只写了视角角色当下能感知、推断或误解的内容；`state.revelations` 中 `reader_known: false` 的作者真相是否被提前写成读者已知；视角角色是否只使用了 `known_by` 允许的信息。
4. **角色行为**：行为是否由当时掌握的信息、欲望、恐惧、关系和现实限制共同决定，而不是为了剧情方便。
5. **类型承诺**：总纲、阶段纲和章卡承诺的推进是否在本章真正发生；悬疑的信息控制、言情的关系变化能否追到具体章节。
6. **文风**：用 `style_report.py` 查看偏移，结合 `novel.yaml` 的参数和本章用途判断是否需要修改。

第 2–6 项必须人工判断。脚本的 `NOTE` 只帮助定位，不代替通读。

## 交给事务

核对完成后，按最终正文更新章卡与状态事务：只把正文里真实发生的变化写进事务，然后运行：

```bash
python3 scripts/state_commit.py <project>/state/state.json <project>/state/transactions/chapter-NNNN.json
python3 scripts/project_check.py <project>
```

顺序固定为：写正文 → 审查/修订 → 核对实际变化 → 提交事务 → 项目检查。
