# 连续性与状态事务

`state/state.json` 只保存“已经在故事中成立、后续章节需要记住”的事实。不要把所有设定都塞进去；静态世界观继续放在 `world/`，详细人物背景继续放在 `characters/`。

`state/initial.json` 是第 0 章的事实快照。初始化脚本会创建它；第一章提交前若补充初始状态，须同时更新 initial.json 与 state.json。此后事务日志是状态变化的历史，`state/state.json` 是重放得到的当前快照。

## 状态结构

模板包含：

- `project`：当前卷与当前章节。
- `characters`：会变化的角色状态，如地点、伤势、持有物、公开/私密知识。
- `relationships`：关系强度、公开状态或关键变化。
- `plot_threads`：主线/支线的当前状态、最近推进和未解决压力。
- `foreshadowing`：伏笔的埋设、激活、回收或放弃状态。
- `timeline`：会影响连续性的事件记录。
- `continuity_notes`：难以结构化但必须记住的约束。

## 事务格式

每章写一个 JSON 事务，例如：

```json
{
  "expected_chapter": 11,
  "chapter": 12,
  "chapter_title": "账本",
  "summary": "主角潜入仓库取得账本，但关键页已被撕走。",
  "character_updates": {
    "lin_zhou": {"location": "旧仓库", "injury": "left-palm-cut"}
  },
  "relationship_updates": {
    "lin_zhou__chen_yu": {"trust": "down", "note": "搭档发现主角有所隐瞒"}
  },
  "plot_thread_updates": {
    "main-case": {"status": "open", "last_progress": "获得账本残页"}
  },
  "foreshadowing_updates": {
    "f-014": {"status": "planted", "note": "最后一页缺失"}
  },
  "timeline_events": [
    {"id": "ch12-warehouse-blackout", "time": "23:10", "event": "仓库停电"}
  ],
  "continuity_notes_add": ["账本最后一页当前下落不明"]
}
```

`scripts/state_commit.py` 会检查当前状态、事务字段和候选状态，在通过校验后把事务保存为 `state/transactions/chapter-NNNN.json` 并更新 state.json。已有章节不能重复提交。

## 重写旧章

例如重写第 17 章：

```bash
python3 scripts/state_rebuild.py /path/to/novel --through 16 --output /tmp/before-17.json
python3 scripts/build_context.py /path/to/novel --chapter 17 --state /tmp/before-17.json --output /tmp/ch17-context.md
```

依据改后的正文修改 `state/transactions/chapter-0017.json`。逐章核对 18 章至当前章的正文与事务：改动可能让后续人物知识、伏笔或时间线失效，脚本只能验证结构，不能替作者判断剧情因果。核对后先预览重放结果，再写回当前状态：

```bash
python3 scripts/state_rebuild.py /path/to/novel --output /tmp/rebuilt.json
python3 scripts/state_rebuild.py /path/to/novel --write
python3 scripts/project_check.py /path/to/novel
```

v0.2 项目若没有 `state/initial.json`，须从可信的第 0 章备份恢复初始事实快照；不要把当前状态改成 0 章冒充初始状态。也可在确认旧备份后用 `state_rebuild.py --base <snapshot>` 预览重放。

## 何时记入状态

需要记：人物受伤、地点变化、得到/失去物品、知道了新信息、关系明显变化、剧情线推进、伏笔埋设/回收、会约束后续的时间事件。

通常不需要记：一次性环境描写、没有后果的情绪波动、已经在人物卡中稳定不变的背景资料。
