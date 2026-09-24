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

项目化续写时，可在控制卡完成后运行：

```bash
python3 scripts/build_context.py /path/to/novel \
  --character lin-zhou \
  --character chen-yu \
  --world locations/old-warehouse \
  --output /tmp/chapter-context.md
```

脚本会按固定顺序收集：

1. `novel.yaml`
2. `state/state.json`
3. 总纲与当前卷纲（若存在）
4. 当前章节控制卡
5. 最近三章正文（可用 `--recent` 调整）
6. 显式指定的人物与世界观条目

输出文件是临时上下文，不是新的事实源。正文、配置和 `state/state.json` 仍是权威来源；原文件变化后应重新生成，不继续使用旧包。

## 选择人物与世界观

只加入会直接影响本章行为、信息边界或冲突的条目。人物通常包括 POV 角色、同场关键角色和本章会改变关系状态的角色。世界观通常包括当前地点、正在使用的制度/能力规则和本章冲突依赖的技术或物件规则。

脚本只为“下一章”生成上下文。重写旧章节时，当前 `state.json` 可能已经包含后续事实，必须先人工确定回滚或重建边界，再装配改稿上下文。
