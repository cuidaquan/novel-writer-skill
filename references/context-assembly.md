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

脚本会按固定顺序收集：

1. `novel.yaml`
2. `state/state.json`
3. 总纲与当前卷纲（若存在）
4. 当前章节控制卡
5. 最近三章正文（可用 `--recent` 调整）
6. 章卡引用和命令行追加的人物与世界观条目

输出文件是临时上下文，不是新的事实源。正文、配置和 `state/state.json` 仍是权威来源；原文件变化后应重新生成，不继续使用旧包。

`--compact-state` 只纳入本章人物、相关关系、未结束剧情线/伏笔及最近 20 条时间线和备注；重要旧事实若被省略，应回看完整状态或资料源。`--max-chars` 只检查大小，超限会失败，不会静默截断。修改旧章时可用 `--state` 指向 `state_rebuild.py --through` 生成的历史快照。

## 选择人物与世界观

只加入会直接影响本章行为、信息边界或冲突的条目。人物通常包括 POV 角色、同场关键角色和本章会改变关系状态的角色。世界观通常包括当前地点、正在使用的制度/能力规则和本章冲突依赖的技术或物件规则。

脚本只为“下一章”生成上下文。重写旧章节时，当前 `state.json` 可能已经包含后续事实，必须先人工确定回滚或重建边界，再装配改稿上下文。
