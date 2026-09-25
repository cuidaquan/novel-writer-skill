# Changelog

版本对应 .doc/roadmap-v0.6-v1.0.md 的路线。公开字段契约见 [references/project-contract.md](references/project-contract.md)。

## 1.4.1
- 修正开场/结尾签名：说话标签（`我说，``她问我，``老板说：`）不再算作段落开头或结尾，否则中文对话密集的稿子会把 `我说，``她说，``我说，嗯。` 报成重复开头/重复结尾，而真正在变化的内容从未被比较。
- 修正对话行占比：除引号外，以说话标签开头的行也计为对话。此前不使用引号的对话体会被算成 0 对话，并据此建议错误的 `dialogue_density`。
- `progress_report.py`：计划章节全部写完时报告成稿总字数，不再输出会误导的“按均速预计”。
- 校准记录与已知限制同步更新。

## 1.4.0
- `prose_lint.py`：可配置的套路扫描（词表、正则句式、标点频率），全部为带行号的 NOTE，默认不启用规则，不阻断提交。
- 人物声音区分度：完成可行性评估后**暂缓**，结论与重新评估条件见 .doc/voice-prototype-evaluation.md。

## 1.3.0
- `progress_report.py`：进度、剩余章节、按均速的预计完稿与未收束条目计数。
- `state_view.py --write/--check`：由 state 渲染派生视图（明确标注非真相源），并检测派生文件是否陈旧。
- `stage_review.py`：聚合进度、交接、承诺与文风画像，各段标明来源脚本。
- `build_context.py` 清单标注题材模块的覆盖与缺口。

## 1.2.0
- 章卡字段责任分级与客观校验：`scenes`、`required_facts`、`forbidden`、`ending`、`title`、`style_override` 的结构由脚本校验，语义兑现明确为人工；章卡 `forbidden` 命中给出 NOTE。
- 章卡 `style_override`：声明本章局部文风覆盖，`style_report` 把与声明一致的偏移标为 `style-override` 而不是漂移。
- 文风校准：新增悬疑、言情、短句与中等句长样例及阈值行为记录；约 ±25% 的偏移列为已知漏报。
- 跨章公式：开场/结尾签名与近期定稿章对照，提示连续同类开场或悬念句。
- 词频、标点频率与字符型例比：`style_profile`/ `style_report` 输出观察值，不设阈值。

## 1.1.0
- 提交门禁：`state_commit.py` 重跑确定性审查，未放行的 BLOCK 拒绝写入；`--allow`/ `--reason` 带记录放行，`project_check.py` 复核已提交章节。
- 占位检测分级：硬标记阻断，`待定` 等歧义词只提示，避免误伤正常台词。
- 完结收口类型承诺：`payoff.id` 分组、`dropped` 显式放弃，`--complete` 列出仍延后的承诺。
- 上下文分层：引用与交接承诺保完整，其余活跃条目按上限摘要；`--active-limit` 与 `--fit` 逐级裁剪。

## 1.0.0
- 冻结新建项目契约：novel.yaml、章卡、状态、事务与审查输出的公开字段、错误级别和 schema_version。
- 增加契约与 Skill 路由回归测试，记录已知限制。
- 提供 VERSION、变更记录与发布说明。

## 0.9.0
- 从空目录可复现的单章、连载与整本演练；失败恢复指南。
- README 按工作模式给出最短命令路径；声明 Python 与平台支持。

## 0.8.0
- style_profile.py 风格画像；build_context.py --style-anchor。
- 章卡 payoff 类型回报与 promise_report.py；两种题材、两种文风与章卡覆盖的验收测试。

## 0.7.0
- handoff 交接契约；--compact-state 优先级、省略摘要与 --fit。
- project_check 核对章卡承诺；handoff_report.py 漂移提示；12 章长程样例。

## 0.6.0
- review_chapter.py 只读单章审查（BLOCK/NOTE、退出码分级）。
- style_report.py 文风偏移提示；写后审查文档与回归测试。
