# 章节控制卡

章节控制卡用于动笔前确定本章的功能。它不是正文提纲的逐句剧本，只记录必须成立的变化和约束。

推荐字段：

```yaml
chapter: 12
title: 暂定标题
viewpoint: lin-zhou
target_words: 3200
goal: 主角必须拿到账本，但不能暴露真实身份
conflict: 对手提前封锁仓库
context:
  characters: [lin-zhou, chen-yu]
  world: [locations/old-warehouse]
scenes:
  - 潜入仓库
  - 搭档发现主角隐瞒信息
change:
  plot: 主线从“怀疑”推进到“得到可验证证据”
  character: 主角第一次主动欺骗搭档
  relationship: 搭档信任下降
threads:
  advance: [main-case]
  touch: [missing-brother]
foreshadowing:
  plant: [f-014]
  pay_off: []
revelations:
  touch: [r-014]
  reveal: []
style_modules: [suspense]
required_facts:
  - 仓库停电发生在 23:10 之后
forbidden:
  - 不让反派直接自曝计划
ending:
  mode: reversal
  hook: 账本最后一页被人撕走
```

## 生成规则

控制卡至少回答四个问题：

1. 本章主角想完成什么？
2. 什么力量阻止他？
3. 到章末，什么事实、关系或选择发生了不可忽略的变化？
4. 为什么读者会继续读下一章？

整本项目还要分配每章 `target_words`，并用 `viewpoint`、`context.characters`、`context.world` 指定本章视角和必要资料。`scenes` 只写关键场景，不逐句锁死正文。实际结果可以偏离计划，但最终状态事务须按正文填写。

有隐藏真相时，`revelations.touch` 指本章需要掌握但尚不揭晓的作者信息，`revelations.reveal` 指本章在正文中明确告知读者的信息。`project_check.py` 会核对计划揭示是否在同章事务中标为读者已知；若写作结果改变，应先按正文修订章卡，再提交事务。`style_modules` 只列本章需要的场景技法。

如果无法回答第 3 个问题，先检查该章是否只是重复信息、过渡或无后果的展示。

## 写作中的偏离

正文出现比控制卡更自然的结果时，可以偏离控制卡，但要满足人物动机和既有事实。章节完成后，以最终正文为准更新状态，不强行把文本改回原计划。
