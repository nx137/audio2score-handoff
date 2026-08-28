# 踏板金标准标注指南

## 总原则

你要回答的问题是：**这个演奏事件，在出版谱里最应该怎样记？** 不是“系统现在写成了什么”。

每个 `events.csv` 行代表一个量化后的演奏音符事件。不要改左侧信息列，只填写最右侧六个空列：

`acoustic_sustain`, `performance_pedal_action`, `published_score_pedal`, `notation_decision`, `review_class`, `review_note`

建议先标 `Chopin_Etudes_op_25_10_15` 和 `Liszt_Mephisto_Waltz_222` 两个目录，用来校准规则。

## 每列怎么填

### 1. acoustic_sustain

判断这个音是否因为踏板或共振，在手指离开琴键后仍然明显持续。

允许值：`yes`, `no`, `uncertain`

- 看 `pedal_extension_ql`。如果大于 `0.25`，通常填 `yes`。
- 如果 `key_duration_ql` 很短，但 `acoustic_duration_ql` 明显更长，也倾向 `yes`。
- 如果 `pedal_extension_ql` 接近 0，填 `no`。
- 如果事件发生在片段边界，无法确定前后关系，填 `uncertain`。

示例：

| key_duration_ql | acoustic_duration_ql | pedal_extension_ql | acoustic_sustain |
|---:|---:|---:|---|
| 0.125 | 1.2917 | 1.1667 | `yes` |
| 0.500 | 0.5000 | 0.0000 | `no` |
| 0.125 | 0.4167 | 0.2917 | `yes` |

### 2. performance_pedal_action

判断这个音符发生时，演奏者的 CC64 踏板正在做什么。

允许值：`hold`, `change`, `release`, `none`, `uncertain`

对照 `pedal_intervals.csv`：

- 音符落在某个 CC64 区间内部：`hold`
- 音符落在踏板释放点附近，且之后没有马上再踩：`release`
- 音符落在踏板释放并快速再踩的位置附近：`change`
- 附近没有任何 CC64 区间：`none`
- 片段边界或时间太接近：`uncertain`

快速再踩的判断：`retake_gap_ql` 很小，通常 `< 0.25`。

示例：

| pedal_intervals.csv 情况 | performance_pedal_action |
|---|---|
| 音符位于区间 302 内部 | `hold` |
| 音符接近某区间 end，且下一区间 gap 约 0.15 | `change` |
| 音符接近某区间 end，且后面没有紧接新区间 | `release` |
| 音符附近无 CC64 | `none` |

### 3. published_score_pedal

判断出版谱在这个音符位置有没有踏板记号，以及是什么类型。

允许值：`start`, `change`, `stop`, `none`, `uncertain`

对照 `reference_pedals.csv` 的 `position_location` 和 `event_type`。

- 位置接近且有 `start`：`start`
- 位置接近且有 `change`：`change`
- 位置接近且有 `stop`：`stop`
- 位置没有踏板记号：`none`
- 位置看不清或片段被切断：`uncertain`

如果 `reference_pedals.csv` 为空，大多数行应填 `none`。

### 4. notation_decision

这是核心判断：这个音符写多长？

先看 `candidate_durations` 列，再决定：

- 选择其中一个候选时值，例如 `0.125`、`0.333`、`0.500`。
- 如果候选都不合适，可以直接写一个具体 QL 数值，例如 `0.25`、`1.5`。
- 不确定时写 `uncertain`。

规则：

1. 如果 `reference_duration_ql` 有值，并且某个候选与它接近，优先选择这个候选。
2. 如果音很短但踏板延长明显，通常保留短时值，把延长交给踏板记号，不要强行写成 tie 或长音。
3. 如果长音必须和同一只手的后续旋律同时存在，才考虑选择长时值，并配 `review_class=independent-voice`。
4. 跨小节长音可以选择跨小节候选，由 MusicXML tie 表示；不要为了避开 tie 把音缩短。

### 5. review_class

解释 `notation_decision` 的理由。

允许值：

- `independent-voice`：这个音应当保留为独立声部，让它与同手其他音同时存在。
- `notation-shortening`：为了可读性，把实际声学延长缩短为更合理的符号时值。
- `pedal-only`：延长主要由踏板承担，谱面保留短音 + pedal 记号即可。
- `other`：以上都不是。
- 留空：普通、没有特殊争议的音。

### 6. review_note

写简短理由，例如：

- `acoustic sustain comes from CC64; keep short note + pedal`
- `reference score uses triplet`
- `bass note needs own voice while RH melody continues`
- `pedal releases here; do not tie across release`

## 实际示例

### 示例 A：Chopin LH pitch 41，m.17 beat 3.000

| 字段 | 值 |
|---|---|
| key_duration_ql | 0.125 |
| acoustic_duration_ql | 1.2917 |
| pedal_extension_ql | 1.1667 |
| candidate_durations | 0.125; 0.333 |
| reference_duration_ql | 0.333 |

一种合理标注：

```text
acoustic_sustain = yes
performance_pedal_action = hold
published_score_pedal = none
notation_decision = 0.333
review_class = notation-shortening
review_note = reference triplet duration; CC64 carries the longer acoustic sustain
```

### 示例 B：Liszt LH pitch 31，m.223 beat 1.000

| 字段 | 值 |
|---|---|
| key_duration_ql | 0.125 |
| acoustic_duration_ql | 1.4708 |
| pedal_extension_ql | 1.3458 |
| reference_pedals.csv | m.223 beat 1.000 start |

一种合理标注：

```text
acoustic_sustain = yes
performance_pedal_action = hold
published_score_pedal = start
notation_decision = 0.125
review_class = pedal-only
review_note = pedal starts here; keep short written note, do not notate acoustic length
```

## 推荐标注流程

1. 打开 `events.csv`。
2. 只看 `hand`, `pitch`, `onset_location`, `key_duration_ql`, `acoustic_duration_ql`, `pedal_extension_ql`, `candidate_durations`, `reference_duration_ql`。
3. 打开 `pedal_intervals.csv` 判断演奏踏板动作。
4. 打开 `reference_pedals.csv` 判断出版谱踏板标记。
5. 先填前三列，再根据候选时值决定 `notation_decision`。
6. 最后用 `review_class` 和 `review_note` 解释为什么。