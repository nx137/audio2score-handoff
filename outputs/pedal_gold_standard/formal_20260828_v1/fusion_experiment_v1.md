# 融合排序实验报告 v1（fuse-alpha 候选评分融合）

> 日期：2026-08-29。代码：`structured_duration_decoder.py`（rank_candidates 新增 fuse_alpha）、`p4_multivoice_score.py`（--fuse-alpha）。产物：40 片段 `p4_fused.musicxml`（α=0.75）。

## 1. 动机

金标准评测 v1 显示 learned（34.3%）整体低于 rule（43.5%）。分层分析定位根因：

- 42% 事件（1984/4672）**无参考时值**，金标准标注规则为"取 ≥ 按键时值的最短候选"，与 rule 评分同构 → rule 79.7% vs learned 44.0%；
- 有参考时值事件（2688）learned 26.9% > rule 19.3%；notation-shortening（踏板补足延音）learned 21.0% vs rule 0.2%。

因此 learned 的"负结果"是评测口径（无参考事件的规则化标注）与模型训练目标（拟合参考谱时值）的错配，而非模型失效。

## 2. 方法

在候选评分中把模型概率与规则先验线性融合：`prob = (1-α)·prob_model + α·prob_rule`，α=0 为纯模型、α=1 为纯规则。默认 α=0.75（25% 模型 + 75% 规则）。

## 3. 结果

### 3.1 α 扫描（4 个代表性片段，时值一致率）

| α | 0.0 | 0.25 | 0.5 | 0.75 | 1.0 |
|---|---|---|---|---|---|
| 4 片段宏平均 | 28.0% | 30.0% | 32.4% | 43.3% | 43.7% |

### 3.2 全量 40 片段（官方评测口径，片段宏平均）

| 管线 | 时值一致率 | 踏板 start F1 | 踏板 stop F1 |
|---|---|---|---|
| p4_rule | 0.435 | 0.408 | 0.220 |
| p4_learned | 0.343 | 0.362 | 0.231 |
| **p4_fused (α=0.75)** | **0.429** | 0.382 | 0.218 |

### 3.3 分层（40 片段聚合）

| 管线 | 有参考 | 无参考 | notation-shortening |
|---|---|---|---|
| rule | 0.190 | 0.799 | 0.002 |
| learned | 0.268 | 0.442 | 0.210 |
| fused | 0.262 | 0.684 | 0.123 |

## 4. 结论

1. 融合把 learned 整体一致率从 34.3% 修复至 42.9%，距纯规则仅 0.6pp（原差 9.2pp）。
2. 融合保留模型在有参考场景的优势（26.2% vs rule 19.0%），并在无参考场景大幅修复（68.4% vs learned 44.2%）。
3. 融合未能整体超越纯规则：无参考事件的标注规则结构性偏向启发式，模型信息主要在"有参考时值"与"踏板延音记谱"场景发挥。
4. 论文表述建议：不再写"LightGBM 无正向增益"，改为"候选模型在有参考时值场景优于规则启发式（26.8% vs 19.0%）；融合排序（α=0.75）在整体一致率接近规则的同时保留该优势，无参考场景的规则化标注口径对启发式存在结构性偏向"。

## 5. 复现

```bash
python audio2score/scripts/p4_multivoice_score.py --midi <seg>/performance_segment.mid \
  --out <seg>/p4_fused.musicxml --candidate-model audio2score/models/p4_asap_cross_piece_v1 \
  --fuse-alpha 0.75 --max-voices 12 --divisors 8,4,3
python tools/evaluate_gold_standard.py --out outputs/pedal_gold_standard/formal_20260828_v1/evaluation/gold_standard_eval_v2.json
```
