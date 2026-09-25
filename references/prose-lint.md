# 套路扫描（prose lint）

可配置的 advisory 扫描，用来发现重复用词、句式套路与标点习惯。它不阻断提交，规则默认不启用。

## 运行

```bash
python3 scripts/prose_lint.py /path/to/novel --chapter 12
python3 scripts/prose_lint.py /path/to/novel --all --default-rules
python3 scripts/prose_lint.py /path/to/novel --rules /path/to/rules.json
```

- 默认扫描 `current_chapter + 1`；`--all` 扫描所有已提交章节。
- 规则来源：项目 `checks/prose-rules.json`（存在时自动使用）→ `--rules` 指定文件 → `--default-rules` 内置词表。都没有时报告“no rules configured”并退出 0。
- 全部命中都是 NOTE，带文件、行号与命中片段；退出码只有 0（成功）与 2（输入错误），没有阻断码。

## 规则文件

```json
{
  "words": ["仿佛", "似乎", "宛如", "不禁"],
  "patterns": [
    {"id": "abstract-summary", "regex": "他感到(很|十分)?(愤怒|悲伤|难过)", "note": "用抽象情绪总结代替动作"}
  ],
  "punctuation_per_100": {"…": 4.0, "！": 3.0}
}
```

- `words`：字面词表，逐词统计出现次数与所在行。
- `patterns`：正则列表，`id` 用于报告，`note` 作为修订方向；非法正则在加载时报错（退出 2）。
- `punctuation_per_100`：标点每百字频率上限，超过才提示。

## 边界

- 词表与文化、题材强相关，默认不启用；只有显式 `--default-rules` 才加载一份保守内置词表。
- 扫描只提供证据，不判断是否为“AI 味”，也不替代审稿；阻断仍由 `review_chapter.py` 的 BLOCK 项负责。
- 规则文件是项目配置，不是新的真相源。
