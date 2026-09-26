# 决策版本记录

立项讨论是多轮的，每一轮都可能改决策。没有记录就会出现这种问题：三个月后想问"尺度是在哪一轮定的、当时为什么这么定、连带改了什么"，谁也答不上来；想把某条决策退回去，又不知道会牵动哪些配置。

`history/log.jsonl` 是**追加型**事件日志：只增不改，因此不可能被静默覆盖。人读的台账由它渲染，不单独维护。

## 一、一条事件的字段

| 字段 | 内容 | 为什么必须有 |
| --- | --- | --- |
| `id` / `time` | `p003` / 时间 | 回退与引用的锚点 |
| `kind` | `premise`（决策轮）／`structure`（结构改动）／`text`（正文版） | 决策线与正文线同本日志，靠类型区分 |
| `author` | `agent` 或 `user` | 谁推动的这一轮 |
| `summary` | 一句话说明 | 台账上能直接读 |
| `input` | **作者的原话逐字** | 事后问"为什么"时唯一的答案 |
| `diff` | 字段级变更（含列表的增删） | 一眼看改了什么，不用读全文 |
| `propagated` | 连带改动的派生产物（`novel.yaml`、章卡…） | 决策与配置的依赖留痕 |
| `hashes` | 该轮 `premise.yaml`、`outline/brief.md`、`novel.yaml`、章卡、正文的哈希 | **没有哈希就无法证明"恢复出来的就是那一轮"** |
| `status` | `draft` / `locked` | 锁定后不许静默改 |
| `snapshot` | `history/snapshots/<id>/` | 那一轮的完整文件副本 |

## 二、五道锁

| 锁 | 机制 | 挡住什么 |
| --- | --- | --- |
| 1 追加日志 | 只写不改，人读台账由它渲染 | 记录被覆盖、被遗忘 |
| 2 每轮带哈希 | 工作副本与派生产物都算哈希 | 恢复出来的东西对不对，无法证明 |
| 3 `--verify` 接入门禁 | `brief_check.py` 与 `--preflight book --require-premise` 都会检查"改动是否没有对应轮次" | 手工改了配置，事后查不出来 |
| 4 锁定语义 | `locked` 之后任何改动必须显式新开一轮并写理由 | 悄悄把尺度改回去这类暗改 |
| 5 派生链 | `novel.yaml` 由 `--from-premise` 生成，`brief_check` 比对两者 | 出了配置违规却查不到是哪一轮引入的 |

## 三、命令

```bash
python3 scripts/premise_log.py <项目> --list                 # 列出所有轮次
python3 scripts/premise_log.py <项目> --show p003            # 打印那一轮的决策与上下文
python3 scripts/premise_log.py <项目> --diff p002 p003       # 只看变更、连带影响与作者原话
python3 scripts/premise_log.py <项目> --verify               # 工作副本是否等于最新一轮（漂移则退 1）
python3 scripts/premise_log.py <项目> --restore p003         # 默认只打印回退计划
python3 scripts/premise_log.py <项目> --restore p003 --apply # 真正写回，并重跑校验
```

## 四、回退语义

`--restore` 会先把**当前**状态记成一条 `<id>-pre-restore`（回退前的安全网），再写回目标轮次的文件，然后追加一条 `<id>-restored` 作为**新基线**——这样 `--verify` 与 `brief_check` 又会和工作副本一致。回退不是撤销历史，而是"在历史后面追加一次回到某轮的操作"。

`--apply` 之后自动跑 `brief_check`：不通过就明确告诉你"回退不干净"，别在这种情况下接着写。

三种回退粒度：

| 场景 | 做法 | 注意 |
| --- | --- | --- |
| 只退决策 | `--restore p00N --apply`（只覆盖 `premise.yaml` / `brief.md`） | 如果决策影响配置，还要重新生成 `novel.yaml` |
| 决策 + 配置 | 先 `--restore`，再 `init_novel.py <项目> --force --from-premise premise.yaml` | `brief_check` 会核对两者一致 |
| 正文版本 | `kind: text` 的轮次快照含 `chapters/`，可用 git 或快照目录回退 | 正文回退后必须重跑 `review_chapter.py` 与 `project_check.py` |

## 五、样例

```jsonl
{"id":"p001","kind":"premise","author":"agent","summary":"初始提案（14 组）","input":"一句话需求","diff":{"created":true},"status":"draft","hashes":{"premise.yaml":"c7dbe749","novel.yaml":"209df03d"}}
{"id":"p002","kind":"premise","author":"agent","summary":"尺度升到 frank","input":"小说尺度可以再大一些","diff":{"intimacy.tier":{"from":"sensual","to":"frank"}},"propagated":["novel.yaml 已同步"],"status":"draft"}
{"id":"p003","kind":"structure","author":"user","summary":"拆章 10→11，新增小院一场","input":"可以再进一步 / 都要吧","diff":{"length.target_chapters":{"from":10,"to":11},"agent_added":{"added":["第 6/7 章由一章拆成两章，新增西厢小院一场戏"],"removed":[]}},"status":"draft"}
{"id":"p004","kind":"premise","author":"agent","summary":"确认锁定","input":"就按这版","diff":{},"status":"locked"}
```

回看时：

```
$ python3 scripts/premise_log.py . --diff p001 p002
## Changed fields (1)
- intimacy.tier: 'sensual' → 'frank'
## Why (recorded inputs)
- p002 (agent): 小说尺度可以再大一些
```

## 六、和正文版本的关系

决策线与正文线共用一本日志，靠 `kind` 区分：

- `premise` / `structure`：`premise.yaml` 是当前决策，快照含 `premise.yaml`、`brief.md`、`novel.yaml`；
- `text`：记录某一版正文（章数、合并 md5、字节数，快照含 `chapters/`）。

这样"这一版正文基于哪一轮决策"可以一句话查到；反过来，某条决策引起的正文返工也能顺着日志回溯到作者的原话。

> 如果项目同时纳入 git，两者互补：git 管文件内容的历史，本日志管**决策与理由**的历史（git 记不住"为什么"）。日志里的哈希可以与 git 对象互证。
