# 踏板金标准标注规则 v1.1（收紧版）

> 基线：`outputs/pedal_gold_standard/pilot_20260820_v2/ANNOTATION_GUIDE.md`。
> 本文件在其基础上**收紧定义、补齐三处缺口**（半踏、编辑性省略、retake 阈值校准），并给出**自动预填规则**。
> 适用范围：先用于 `Chopin_Etudes_op_25_10_15` 与 `Liszt_Mephisto_Waltz_222` 两个 pilot 校准。

## 0. 总原则（不变）

每个 `events.csv` 行回答的问题是：**这个演奏事件，在出版谱里最应该怎样记？**
不是"系统现在写成了什么"，也不是"演奏者实际踩了什么"。

只允许修改最右侧六个空列：`acoustic_sustain`、`performance_pedal_action`、`published_score_pedal`、`notation_decision`、`review_class`、`review_note`。左侧 20 列一律不动。

## 1. 三类语义的精确定义（必须先区分清楚）

| 列 | 回答的问题 | 信息来源 | 本质 |
|---|---|---|---|
| `acoustic_sustain` | 手指离键后，这个音**声音上**是否仍明显延续？ | `pedal_extension_ql`、`acoustic_duration_ql` | 声音物理事实 |
| `performance_pedal_action` | 这个音符发生时，演奏者右脚**实际上**在做什么？ | `pedal_intervals.csv`（CC64 区间） | 演奏行为事实 |
| `published_score_pedal` | 出版谱在这个位置**写了**什么踏板记号？ | `reference_pedals.csv` | 乐谱语义（事实记录，不做评价） |

三层彼此独立、可能互相矛盾。**矛盾是预期的，不是错误**——正是论文要呈现的语义错配证据。不要强行协调三层。

## 2. 自动预填规则（本 pilot 的前三列已按此预填）

### 2.1 acoustic_sustain（允许值：yes / no / uncertain）

令 `pe = pedal_extension_ql`（= acoustic_duration_ql - key_duration_ql）：

- 事件落在片段边界区（见 2.4）→ `uncertain`
- `pe > 0.25` → `yes`
- `pe <= 0.25` → `no`（手指基本承担了延音，踏板延长可忽略）

### 2.2 performance_pedal_action（允许值：hold / change / release / none / uncertain）

对照 `pedal_intervals.csv`，规则按优先级：

1. 边界区事件 → `uncertain`
2. 音符位于某 CC64 区间内部：
   - 距区间结束 > 0.25 ql → `hold`
   - 距区间结束 <= 0.25 ql，且该区间 `retake_gap_ql < 0.25`（快速再踩）→ `change`
   - 距区间结束 <= 0.25 ql，无快速再踩 → `release`
3. 音符落在区间之间的空隙：
   - 空隙 `retake_gap_ql < 0.25` 且音符贴近释放点 → `change`
   - 音符贴近释放点、空隙 >= 0.25 → `release`
   - 音符贴近下一次踩下点 → `change`
4. 附近无任何 CC64 区间 → `none`

### 2.3 published_score_pedal（允许值：start / change / stop / none / uncertain）

- 若 `reference_pedals.csv` 为空 → 全部 `none`（本 pilot 的 Chopin 片段即此情况）
- 否则取距离音符 onset 最近的踏板记号：距离 <= 0.25 ql → 填该记号的 `event_type`（start/change/stop）；无记号在 0.25 内 → `none`

### 2.4 边界区定义（三列都填 uncertain 的情形）

- `onset_ql < seg_start + 0.25` 或 `onset_ql > seg_end - 0.25`
- 本 pilot 实测：Chopin 边界区 = [56.0, 56.25] U [71.75, 72.0]，共 6 个事件；Liszt 边界区 = [884.0, 884.25] U [899.75, 900.0]，共 5 个事件。

## 3. 半踏（half-pedal）规则【新增】

- **H1（数据现状）**：当前 `pedal_intervals.csv` 只含 CC64 起止区间，**无深度值**，无法客观判定半踏。因此 pilot v2 阶段**不新增 half-pedal 类目**；`performance_pedal_action` 仍按 2.2 用区间判定。
- **H2（标注行为）**：若标注者凭听感或谱面（如谱上标 half pedal / una corda 类提示）怀疑某处为半踏，在 `review_note` 中记录 `possible half-pedal at <位置>`，`performance_pedal_action` 不因此改值（通常仍为 hold）。
- **H3（校准决策）**：pilot 完成后统计 H2 记录数量。若半踏频繁出现，再决策是否扩展数据模型（给 `pedal_intervals.csv` 增加 CC64 深度列，需修改 `tools/build_pedal_gold_standard.py` 并重新生成）。该决策同时写入论文 limitations。

## 4. 编辑性省略（editorial omission）规则【新增】

- **E1（事实记录）**：`published_score_pedal` 是乐谱事实——谱上没写就是 `none`。**不要替乐谱补写**，即使演奏层有大量 retake。
- **E2（记谱惯例）**：`notation_decision` 遵循谱面惯例：快速 retake（`retake_gap_ql < 0.25`）在出版谱中通常不逐个标注。**优先选择可读的短时值 + pedal 记号承担延音**，不把每次 retake 强行写进谱面。
- **E3（矛盾处置）**：当演奏层（大量 retake）与谱面层（无标记）不一致时，如实分层记录，`review_class` 选 `notation-shortening` 或 `pedal-only`，并在 `review_note` 注明 `performance retake vs score none (editorial omission)`。**这类行是论文的关键证据，优先保证其 review_note 质量。**

## 5. retake 阈值校准规则【新增】

- **R1（实测基线）**：两个 pilot 片段共 17 个 `retake_gap_ql`：min=0.039，median=0.081，max=0.198，**全部 < 0.25**。当前阈值 0.25 在本 pilot 内**无临界冲突**，暂维持。
- **R2（临界区记录）**：若后续片段出现 `retake_gap_ql` 落在 [0.20, 0.30] 的临界值，标注者在 `review_note` 记录 `retake threshold check: <值>`，用于最终定阈值。
- **R3（裁剪区间）**：片段首尾被裁剪的区间（`clipped_start_ql` / `clipped_end_ql` 与真实值不同）一律不参与阈值判定，其事件走边界区 `uncertain`。

## 6. 标注纪律

1. 只改最后六列；不确定就填 `uncertain` + 在 note 里说明原因，**不要猜**。
2. `notation_decision` 优先选 `candidate_durations` 中的值；候选均不合适才写显式 QL。
3. 完成标准：六列无空值（`review_note` 鼓励填但允许空）；`uncertain` 比例 < 20%；每个片段至少 10 行 `review_note` 给出具体理由。
4. 禁止：修改任何左侧列；覆盖 `evals/`、`audio2score/models/`；把预填结果当"答案"直接采用而不复核（预填是**起点**，不是金标准）。

## 7. 附录：预填算法复现要点

预填由三列规则（2.1-2.3）+ 边界区（2.4）确定，输入为 `events.csv`、`pedal_intervals.csv`、`reference_pedals.csv`、`segment_metadata.json`（start_ql/end_ql）。若本地 events.csv 与仓库版本行数不一致，可用本算法在本地重算，避免手工粘贴。
