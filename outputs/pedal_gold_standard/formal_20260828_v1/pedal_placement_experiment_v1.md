# 踏板符号位置策略实验报告 v1（snap vs exact）

> 日期：2026-08-29。代码：`p4_multivoice_score.py --pedal-placement {snap,exact}`。产物：40 片段 `p4_exact.musicxml`。

## 1. 动机

评测 v1 显示踏板 start F1 0.41 / stop F1 0.22（rule，参考=演奏层 297 区间）。诊断发现：

- `find_nearest_note` 实际取"目标位置之后第一个音符"（非最近），踏板事件系统性偏晚；
- 长音/休止期间无音符，start/stop 被吸附到很远的音符，多个区间的同位置事件被 music21 合并；
- 结果：rule 输出 279 start / 279 stop，但仅 133/75 个与演奏层对齐（≤0.25 QL）。

对比：系统检测的 CC64 区间本身与参考几乎一致（模拟显示精确输出可达 start F1 0.92 / stop F1 0.92）。

## 2. 方法

新增 `--pedal-placement exact`：跳过 `attach_pedals`（音符吸附），在 MusicXML 写出后用 `insert_exact_pedals` 在 CC64 区间边界的精确位置插入 `<direction><pedal/><offset/></direction>`；同位置 stop+start 合并为 `change`。

配套修复：评测 `parse_pedals` 改用 `(measure-1)×bar_ql + offset` 解析位置（原用音符累加 cursor，多声部 backup 下偏差约 0.25 QL）。

## 3. 结果（40 片段，片段宏平均，参考=演奏层）

| 管线 | 踏板 start F1 | 踏板 stop F1 | 踏板事件 |
|---|---|---|---|
| p4_rule (snap) | 0.408 | 0.220 | 571 |
| p4_learned (snap) | 0.362 | 0.231 | 533 |
| **p4_exact** | **0.818** | **0.850** | ~560 |

- start F1 提升约 2 倍（0.408 → 0.818），stop F1 提升约 4 倍（0.220 → 0.850）。
- 时值一致率不变（0.435，踏板符号位置不影响音符时值）。

## 4. 结论

1. 踏板事件对齐的主要障碍是**符号位置策略**（吸附），而非区间检测：系统检测区间与演奏层一致率已达 92%。
2. exact 模式保留演奏层真实时序，符合"把演奏踏板动作写入谱面"的忠实性目标，同时兼容 MusicXML 标准（`<offset>`）。
3. 剩余误差主要来自切片窗口边界（跨窗口区间起点被截断）与区间检测精度。
4. 论文表述建议：踏板事件对齐（start/stop F1）从 0.41/0.22 提升至 0.82/0.85，归因于从"音符吸附"到"精确时序"的符号位置策略；该改进不影响时值一致性评测。

## 5. 复现

```bash
python audio2score/scripts/p4_multivoice_score.py --midi <seg>/performance_segment.mid \
  --out <seg>/p4_exact.musicxml --pedal-placement exact --max-voices 12 --divisors 8,4,3
```
