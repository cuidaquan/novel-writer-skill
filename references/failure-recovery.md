# 失败恢复

脚本在失败时尽量给出下一步。以下按症状列出最短恢复路径，`<project>` 换成项目路径。

## 缺章卡或正文

症状：`project_check.py` 报 `chapter N has no control card` 或 `control card N has no chapter body`；`build_context.py` 报 `Control card for chapter N not found`。

恢复：补齐对应文件，命名用 `control-cards/chapter-NNNN.yaml` 与 `chapters/chapter-NNNN.md`；已提交章节不能缺正文。补齐后重跑 `project_check.py`。

## 事务错误

症状：`state_commit.py` 报 `invalid transaction: ...` 或 `transaction would produce invalid state: ...`。

恢复：错误不会写入状态或事务。按提示修正事务 JSON 后重新提交。常见原因：`expected_chapter`/`chapter` 不匹配、重复时间线 id、揭示时间与章卡不符。

## 事务与状态不一致

症状：`project_check.py` 报 `state/state.json differs from replayed transactions`。

恢复：先审阅旧章改动与后续事务，再预览重放结果，确认无误后写回：

```bash
python3 scripts/state_rebuild.py <project> --output /tmp/rebuilt.json
python3 scripts/state_rebuild.py <project> --write
python3 scripts/project_check.py <project>
```

## 中断写入

症状：事务文件已存在，但 `state.current_chapter` 没有前进；`project_check.py` 报 `state.current_chapter=N but transaction count=M`。

原因：`state_commit.py` 先写事务日志（真相源）再写 `state.json`（派生快照）。若第二步中断，日志完整而快照落后。恢复：

```bash
python3 scripts/state_rebuild.py <project> --write
python3 scripts/project_check.py <project>
```

不要为了迁就落后的快照而手工删除事务文件。

## 上下文超预算

症状：`build_context.py --max-chars` 报 `largest sources: ...`。

恢复：减少 `--recent`、保持 `--compact-state`，或加 `--fit`；`--fit` 会先缩短时间线/备注尾部，再从旧到新丢弃近期章节。清单里的 `Compact view omitted` 与 `Trimmed for --max-chars` 说明省略了什么。

## 旧章改稿后的重放冲突

见 [连续性与状态事务](continuity-state.md) 的“重写旧章”。原则：先确认 `state/initial.json` 是可信的第 0 章快照，逐章核对受影响的事务，再重放写回。

## 项目文件无法解析

症状：`read_yaml`/`read_json` 报错。

恢复：检查 JSON 根节点是对象、YAML 使用空格缩进；当前解析器不支持锚点、标签和多行块标量。修正文件后重试。