# 跨章交接与防漂移

长篇常见的问题不是状态没有记录，而是状态有记录、下一章却没抓住重点。交接契约把“下一章必须承接什么”写进每章事务，同时继续以 `state/state.json` 为唯一真相源。

## 交接契约

每章事务可选写 `handoff`：

```json
{
  "handoff": {
    "carry_over": ["main-case", "f-014"],
    "notes": ["证人的安全仍受威胁"]
  }
}
```

- `carry_over`：下一章必须处理、且在本章结束时仍活跃的 `plot_threads` 或 `foreshadowing` id。已解决或已放弃的条目不能列入。
- `notes`：难以结构化、但仍需承接的压力。

`handoff` 只引用现有条目，不复制它们的状态，因此不是第二套真相源。事务重放后，`state.handoff` 是唯一的当前交接状态；重写旧章后按 [连续性与状态事务](continuity-state.md) 重建即可。

## 查看交接与漂移

```bash
python3 scripts/handoff_report.py /path/to/novel --stale 5
```

只读报告包含三部分：

1. **显式承接**：最近一章事务写入的 `carry_over` 与 `notes`，并标出每个条目的类型、状态和最后推进章节。
2. **活跃压力**：从 `plot_threads`、`foreshadowing` 和 `relationships` 派生的未收束条目及最后推进章节。
3. **漂移提示**：连续 `--stale` 章（默认 5）没有推进的活跃条目，附最后推进章节。已记录原因并置为 `paused` 的条目单列，不计为漂移。

报告始终是提示：它不会把合理暂停判为情节错误，也不改变状态。

## 章卡承诺与事务

`project_check.py` 核对已提交章节的章卡承诺是否落到事务：

- `threads.advance` 中的剧情线必须出现在该章 `plot_thread_updates`；缺失是阻断错误。
- `foreshadowing.plant` 和 `foreshadowing.pay_off` 必须出现在 `foreshadowing_updates`；缺失是阻断错误。
- `revelations.reveal` 的读者揭示规则不变；`revelations.touch` 与 `threads.touch` 缺失只给提示。

如果正文结果与章卡不同，先按正文修订章卡与事务，再提交；不要为了满足计划而改回正文。
