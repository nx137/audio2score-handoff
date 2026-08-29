# 踏板金标准评测报告 v2（formal_20260828_v1，含 p4_fused 融合管线）

> 金标准：40 片段 / 4672 事件（annotation_report_v1.md）。评测：`tools/evaluate_gold_standard.py`。
> v2 相对 v1 新增 `p4_fused`：候选评分融合 LightGBM 概率与规则先验（fuse-alpha=0.75，25% 模型 + 75% 规则）。

## 1. 总体指标（片段宏平均）

| 管线 | 时值一致率 | 踏板 start F1 | 踏板 stop F1 | 踏板事件 |
|---|---|---|---|---|
| p4_rule | 0.435 | 0.408 | 0.220 | 571 |
| p4_learned | 0.343 | 0.362 | 0.231 | 533 |
| **p4_fused** | **0.429** | 0.382 | 0.218 | 560 |
| p4_no_pedal | 0.435 | 0.025 | 0.025 | 0 |

候选可实现性：62.6%

## 2. 分层时值一致率（40 片段聚合）

| 管线 | 有参考时值 | 无参考时值 | notation-shortening |
|---|---|---|---|
| p4_rule | 0.193 | 0.797 | 0.002 |
| p4_learned | 0.269 | 0.440 | 0.210 |
| p4_fused | 0.263 | 0.681 | 0.122 |

## 3. 语义错配

- acoustic=yes & score=none：3334（71%）；perf=change & score=none：864（18%）
- 三层语义系统性错配：notation-shortening 1775 行 / pedal-only 1479 行 / independent-voice 136 行。

## 4. 解读

- **learned 负结果的根因**：42% 事件（1984/4672）无参考时值，其金标准标注规则（取 ≥ 按键时值的最短候选）与 rule 评分同构；learned 在有参考时值场景优于 rule（0.269 vs 0.193），但被无参考场景（0.440 vs 0.797）拖累。
- **p4_fused（α=0.75）**：整体一致率 0.429 接近 rule（0.435，差 0.6pp；learned 原本差 9.2pp）；无参考场景修复至 0.681（learned 仅 0.440）；有参考场景保留模型优势 0.263 vs rule 0.193；notation-shortening 保留 0.122（rule 仅 0.002）。
- 融合未整体超越纯规则：无参考事件的标注规则结构性偏向启发式，模型信息主要贡献于有参考与踏板延音记谱场景。
- 踏板事件 F1（start 0.36–0.41 / stop 0.22–0.23）：fused 处于 rule/learned 之间，无显著恶化；stop 仍受记谱惯例（谱面 stop 极少）限制。
- 复现：`python tools/evaluate_gold_standard.py --out .../evaluation/gold_standard_eval_v2.json`
