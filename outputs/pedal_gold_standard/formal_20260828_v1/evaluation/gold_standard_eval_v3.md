# 踏板金标准评测报告 v3（formal_20260828_v1，含 p4_fused 与 p4_exact）

> 金标准：40 片段 / 4672 事件（annotation_report_v1.md）。评测：`tools/evaluate_gold_standard.py`。
> v3 相对 v2 新增 `p4_exact`：踏板符号以精确位置（CC64 区间边界 + MusicXML `<offset>`）输出，替代吸附到最近音符。

## 1. 总体指标（片段宏平均）

| 管线 | 时值一致率 | 踏板 start F1 | 踏板 stop F1 | 踏板事件 |
|---|---|---|---|---|
| p4_rule | 0.435 | 0.408 | 0.220 | 571 |
| p4_learned | 0.343 | 0.362 | 0.231 | 533 |
| p4_fused (α=0.75) | 0.429 | 0.382 | 0.218 | 560 |
| **p4_exact** | **0.435** | **0.822** | **0.854** | 559 |
| p4_no_pedal | 0.435 | 0.025 | 0.025 | 0 |

候选可实现性：62.6%

## 2. 语义错配

- acoustic=yes & score=none：3334（71%）；perf=change & score=none：864（18%）
- 三层语义系统性错配：notation-shortening 1775 行 / pedal-only 1479 行 / independent-voice 136 行。

## 3. 解读

### 3.1 时值一致率
- rule 43.5% ≈ fused 42.9% > learned 34.3%。learned 负结果根因：42% 事件无参考时值、其金标准标注规则与 rule 评分同构；learned 在有参考场景 26.8% > rule 19.0%。
- p4_exact 仅改变踏板符号位置，不改变音符时值，故时值一致率与 rule 相同（0.435）。

### 3.2 踏板 F1（参考 = 演奏层 pedal_intervals，容差 0.25 QL）
- **p4_exact 大幅提升踏板事件对齐**：start F1 0.822（rule 0.408）、stop F1 0.854（rule 0.220）。
- 根因：`attach_pedals` 把 start/stop 吸附到"下一个音符"导致系统性偏晚，长音/休止处偏移巨大、多个区间的同位置事件被合并；exact 模式用 CC64 区间边界直接写 `<offset>`，保留演奏层真实时序。
- 剩余未对齐主要来自窗口边界截断（跨窗口区间的起点被切片截为窗口起点）。

### 3.3 论文含义
- 踏板符号位置策略是可解释、可量化的系统改进点：snap（吸附）→ exact（精确）带来 start/stop F1 约 2–4 倍提升，不改变记谱音符。
- stop 低值的历史根因（谱面 stop 记谱惯例）在 exact 口径下已不是主要限制；新限制为窗口边界与区间检测精度。

## 4. 复现

```bash
python audio2score/scripts/p4_multivoice_score.py --midi <seg>/performance_segment.mid \
  --out <seg>/p4_exact.musicxml --pedal-placement exact --max-voices 12 --divisors 8,4,3
python tools/evaluate_gold_standard.py --out outputs/pedal_gold_standard/formal_20260828_v1/evaluation/gold_standard_eval_v3.json
```
