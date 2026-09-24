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

可在章节控制卡里临时覆盖局部参数。例如战斗场景可把 `sentence_length` 调短、`description_density` 降低、`violence` 调为 `concrete`；情感场景可提高 `interiority` 与停顿，但用户没有要求时不要改变整本小说的基调。

## 从样章提取风格

用户提供样章时，只提取可观察特征：句长分布、段落长度、对话比例、叙事距离、常用感官、动作/心理比例、比喻频率、场景进入方式、结尾方式和明确禁忌。把结果写成参数配置，再用新内容验证；不要复制样章中的独特措辞、句子或标志性表达。
