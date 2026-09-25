# 文风配置系统

文风用可观察参数表达。不要只写“高级”“有文学感”“像某某作者”，这些标签难以稳定执行。

推荐在 `novel.yaml` 中使用以下维度：

```yaml
style:
  tone: restrained
  pov_distance: close
  sentence_length: short-to-medium
  rhythm: fast
  dialogue_density: high
  exposition_density: low
  description_density: medium
  sensory_detail: medium
  interiority: indirect
  metaphor_density: low
  humor: low
  violence: concrete
  ending_mode: hook
  forbidden:
    - 空泛哲理总结
    - 连续排比
    - 解释已经由动作表现出的情绪
  modules: []
```

## 参数含义

- `tone`：冷峻、温暖、轻快、压抑、荒诞、克制等整体语气。
- `pov_distance`：`close` 更贴近角色即时感受；`medium` 允许有限概括；`distant` 更适合史诗或群像。
- `sentence_length`：控制主要句长和阅读速度，不要求每句一致。
- `rhythm`：决定段落推进速度、停顿频率和场景切换密度。
- `dialogue_density`：决定对话在场景中的占比。
- `exposition_density`：控制直接说明背景设定的程度。
- `description_density`：控制环境、外貌、动作细节的篇幅。
- `interiority`：`direct` 可直接写心理；`indirect` 主要通过动作、感官和选择表现。
- `metaphor_density`：控制比喻频率，默认不宜过高。
- `ending_mode`：常用 `hook`、`reversal`、`emotional-beat`、`resolution`。

## 场景覆盖

可在章节控制卡里用 `style_override` 临时覆盖局部参数（只影响本章，不动 `novel.yaml`）。例如战斗场景写 `sentence_length: short`、`description_density: low`、`violence: concrete`；情感场景可提高 `interiority` 与停顿。但用户没有要求时不要改变整本小说的基调。`style_report.py` 会识别声明：与覆盖一致的偏移标为 `style-override`，不再当作漂移。

需要额外的场景技法时，在 `style.modules` 设全书常用模块，或在章卡 `style_modules` 设本章模块；上下文生成器只加载选中的文件。当前可选 [suspense](style-modules/suspense.md) 与 [intimacy](style-modules/intimacy.md)。模块是对场景的补充，优先服从本书的参数和用户要求。

## 从样章提取风格

用户提供样章时，只提取可观察特征：句长分布、段落长度、对话比例、叙事距离、常用感官、动作/心理比例、比喻频率、场景进入方式、结尾方式和明确禁忌。把结果写成参数配置，再用新内容验证；不要复制样章中的独特措辞、句子或标志性表达。

## 生成风格画像

```bash
python3 scripts/style_profile.py /path/to/novel --recent 5
python3 scripts/style_profile.py /path/to/novel --sample /path/to/sample.md
```

画像只报告可观察指标（句长、段落长度、对话比例、重复开头/结尾），并给出 `style.sentence_length` 与 `style.dialogue_density` 的建议取值；样本不足时明确写 INSUFFICIENT，不虚构结论。它只存聚合数字，不把样章句子存成模仿模板。`tone`、`pov_distance`、`interiority` 等判断性字段仍由作者确认后再写入 `novel.yaml`。

续写时可加 `build_context.py --style-anchor`（`--anchor-recent` 控制取样章数），把一段简短的观测锚点放进上下文；它是可选的低优先级信息，不挤掉必要事实，也不替代 `novel.yaml`。

`style_report.py` 还会把本章的开场/结尾签名与近期定稿章对照（`## Cross-chapter patterns`），提示“连续多章同类开场或悬念句”。这也是提示：重复是否成立由作者判断，章节内重复与跨章重复分开列出。
