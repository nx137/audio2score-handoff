# 踏板金标准评测报告 v1（formal_20260828_v1）

> 金标准：40 片段 / 4672 事件（annotation_report_v1.md）。评测：`tools/evaluate_gold_standard.py`。

## 1. 总体指标

| 管线 | 时值一致率 | 踏板 start F1 | 踏板 stop F1 | 踏板事件 |
|---|---|---|---|---|
| p4_rule | 0.435 | 0.408 | 0.220 | 571 |
| p4_learned | 0.343 | 0.362 | 0.231 | 533 |
| p4_no_pedal | 0.435 | 0.025 | 0.025 | 0 |

候选可实现性：62.6%

## 2. 语义错配

- acoustic=yes & score=none：3334（71%）；perf=change & score=none：864（18%）
- 三层语义系统性错配：notation-shortening 1775 行 / pedal-only 1479 行 / independent-voice 136 行。

## 3. 解读

- **rule（43.5%）> learned（34.3%）**：LightGBM 候选模型未带来正向增益，与 CC64 消融（pedal F1≈0.002）一致；论文采用叙事 A，learned 不作为宣称增益。
- 踏板事件 F1 偏低（start 0.36–0.41 / stop 0.22–0.23）：系统将演奏踏板写入谱面的忠实性中等，stop 尤弱，如实报告。
- no_pedal 时值一致率与 rule 相同：踏板特征未改变时值输出。
- 复现：`python tools/evaluate_gold_standard.py`
