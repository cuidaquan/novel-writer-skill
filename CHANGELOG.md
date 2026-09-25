# Changelog

版本对应 .doc/roadmap-v0.6-v1.0.md 的路线。公开字段契约见 [references/project-contract.md](references/project-contract.md)。

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
