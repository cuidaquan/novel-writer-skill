# 章节上下文装配

续写时，上下文应足够支撑当前章节，同时避免把整本小说重新加载。默认以 `state/state.json` 的 `current_chapter + 1` 作为目标章节。

## 文件命名

推荐使用可排序的编号文件名：

```text
chapters/chapter-0001.md
control-cards/chapter-0001.yaml
outline/volumes/volume-01.md
characters/<character-id>.yaml
world/<topic>.md
```

章节和控制卡也兼容 `chapter-1.*`、`0001.*`、`1.*`。人物文件按 ID 精确选择；世界观条目允许 `world/` 下的相对路径。

## 自动装配

项目化续写时，优先在章卡 `context.characters` 和 `context.world` 中列出本章资料，`viewpoint` 对应的人物卡会自动加入。章卡完成后运行：

```bash
python3 scripts/build_context.py /path/to/novel \
  --compact-state \
  --max-chars 30000 \
  --output /tmp/chapter-context.md
```

上下文生成前会做本章写前检查：总纲中的故事承诺与结局方向、POV 人物资料、章卡目标/阻力/变化和引用资料须已填写。整本或连载项目还应先按 [写前规划与验收](planning-preflight.md) 检查对应范围。

脚本会按固定顺序收集：

1. `novel.yaml`
2. `state/state.json`
3. 总纲与当前卷纲（若存在）
4. 当前章节控制卡
5. 最近三章正文（可用 `--recent` 调整）
6. 章卡引用和命令行追加的人物与世界观条目
7. 当前题材已有的专门指导，以及 `style.modules` 和章卡 `style_modules` 选中的场景指导

输出文件是临时上下文，不是新的事实源。正文、配置和 `state/state.json` 仍是权威来源；原文件变化后应重新生成，不继续使用旧包。

`--compact-state` 分三层：本章人物与资料、章卡引用的剧情线/伏笔/真相、`handoff.carry_over` 保完整；其余活跃条目降为 `active_pressure` 摘要（`kind/id/status/last_touched_chapter`），默认最多 40 条，用 `--active-limit` 调整；超出上限的只计数，清单写出省略摘要并提示用 `handoff_report.py` 看全量。重要旧事实若被省略，应回看完整状态或资料源。`--max-chars` 超限时不加 `--fit` 会失败并列出最大的来源；加 `--fit` 会依次把活跃摘要降到 20/10/5/0 条、把时间线/备注降到 10/5/2/0、再从旧到新丢弃近期章节，并在清单里记录裁剪内容。修改旧章时可用 `--state` 指向 `state_rebuild.py --through` 生成的历史快照。

需要观测锚点时加 `--style-anchor`（`--anchor-recent` 控制取样章数）：它从已定稿章节提取一段简短的可观察指标，作为低优先级来源加入上下文；样本不足时清单写“unavailable”。

隐藏真相在精简视图中只按章卡 `revelations.touch`、`revelations.reveal` 纳入。`truth` 是作者信息；`reader_known: false` 不能被叙述成读者已经确认的事实。人物能否据此行动还要看 `known_by`。生成器会把这条边界写入上下文清单，但正文和事务仍须人工核对。

## 选择人物与世界观

只加入会直接影响本章行为、信息边界或冲突的条目。人物通常包括 POV 角色、同场关键角色和本章会改变关系状态的角色。世界观通常包括当前地点、正在使用的制度/能力规则和本章冲突依赖的技术或物件规则。

脚本只为“下一章”生成上下文。重写旧章节时，当前 `state.json` 可能已经包含后续事实，必须先人工确定回滚或重建边界，再装配改稿上下文。
