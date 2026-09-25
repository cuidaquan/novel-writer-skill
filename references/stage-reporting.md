# 长篇进度与阶段报告

三个只读命令，用来在长篇中途看清进度、派生视图与阶段复盘。它们都不修改 state、正文或事务，也不新建真值文件。

## 进度与预算

```bash
python3 scripts/progress_report.py /path/to/novel
```

输出：已提交章节 / 计划章节、已写字数 / 目标字数与百分比、每章均速、剩余章节、按当前均速的预计完稿字数、低于目标 80% 的章节数、逐章计划与实际，以及未收束条目计数（剧情线、伏笔、读者未知真相、仍延后的承诺）。

数字来自 `novel.yaml`、章卡与正文；改稿后重新运行即可，没有缓存。

## 派生状态视图

```bash
python3 scripts/state_view.py /path/to/novel --write /tmp/state-view.md
python3 scripts/state_view.py /path/to/novel --check /tmp/state-view.md
```

视图从 `state/state.json` 与事务日志渲染人物、关系、剧情线、伏笔、真相、时间线、交接与备注。文件头明确写“由 state 派生，不是真相源；冲突以 state、正文和事务为准”。`--check` 重新渲染并与现有文件比较：不一致退出 1 并提示重新生成。**不要把它当第二份真相源**，它只是便于通读的派生文档。

`revelations.truth` 是作者信息，视图会原样列出；不要把其中的真相写进正文。

## 阶段复盘

```bash
python3 scripts/stage_review.py /path/to/novel --stale 5 --deferred-streak 3 --recent 5
```

按顺序运行 `progress_report.py`、`handoff_report.py`、`promise_report.py`、`style_profile.py`，把输出拼成一份报告，每段标明来源脚本。子命令的 advisory 退出（例如风格样本不足）不会让复盘失败；输入错误返回 2。聚合器不复制任何状态逻辑。

## 题材模块提示

`build_context.py` 的清单会写一行 `Genre modules:`，列出有专门指导的题材，以及没有模块、走通用路径的题材。没有模块不是错误，只是让“正走通用路径”变得可见。
