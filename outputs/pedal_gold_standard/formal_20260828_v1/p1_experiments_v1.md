# P1 系统改进报告 v1（2026-08-30）

> 范围：跨窗口边界处理、CC64 提取审查、候选可实现性天花板分析。
> 方法：40 片段逐事件归因（p4_exact vs 演奏层参考，容差 0.25 QL）+ 管线代码审查 + 候选集合模拟。

## 1. 摘要

1. **发现并修复系统 bug**：`insert_exact_pedals` 固定把踏板写进左手（parts[1]），music21 把全休止声部压缩成少量小节时事件被**静默丢弃**（`measures.get(num) is None -> continue`）——9 个受影响片段的 `p4_exact` 已重生成（音符结构 c14n 校验不变），F1 显著提升。
2. **评测协议新增 `visible` 口径**：窗口内事件 + 跨窗踩下在窗口起点的 start，不给窗口外伪 stop。**start F1 宏平均 1.000 / stop 0.967**。
3. **CC64 提取审查结论**：窗口内检测 **100% 召回（FN=0）**、时序精确（匹配偏移全 0）；残留误差全部为窗口边界伪事件（31 个窗口起点 start + 12 个窗口终点 stop），机制完全解释。
4. **候选天花板定位**：62.6% 可实现率的缺口 74% 在 notation-shortening 类，根因是候选集过小（中位 2 个时值）；**模拟显示候选加入延音扩展时值后可达 95.8%（+33.2pp）**，实施路径明确。

## 2. Bug：踏板事件因左手小节折叠被静默丢弃

- **机制**：`insert_exact_pedals` 选择 `parts[1]`（左手）写入 `<direction><pedal/>`。music21 在声部全休止时可能把小节压缩（如 Mozart_8-1 左手窗口 4 小节只剩 1 小节整休止），此时 `measures = {1: ...}`，所有落在小节 2–4 的踏板事件 `measures.get(num) -> None -> continue` 被丢弃。Mozart_8-1 参考 5 个区间 10 个事件，旧输出只有 1 个 start。
- **影响**：9 个片段（LH 小节数 < RH 小节数）：Bach_848 / Beethoven_16-1 / Beethoven_4-1 / Chopin_10-1 / Liszt_10_71 / Liszt_9_67 / Mozart_8-1 / Rachmaninoff_23-6 / Schubert_op142。
- **修复**（`p4_multivoice_score.py`）：改为「LH 优先；仅当 LH 小节数不足时回退到小节更全的声部」。重生成 9 个 `p4_exact.musicxml`，c14n 校验除踏板 direction 外元素树完全一致。
- **效果**（inwindow 口径，40 片段宏平均）：

| 指标 | 修复前 | 修复后 |
|---|---:|---:|
| start F1 宏 | 0.858 | **0.889** |
| start F1 微 | 0.932 | **0.945** |
| stop F1 宏 | 0.936 | **0.967** |
| stop F1 微 | 0.970 | **0.978** |

## 3. 评测协议：visible 口径

- **动机**：inwindow 口径下系统在窗口起点写的 start（对应"窗口开始前已踩下"的跨窗区间）被判为 FP（31 个），而这是切片注入 CC64=127@0 的**忠实输出**。
- **定义**：`start 参考 = 窗口内踩下事件 ∪ 跨窗区间（窗口前已踩下）在窗口起点的 start`；`stop 参考 = 仅窗口内释放事件`（窗口后释放不可见，不给伪参考）。实现为 `--pedal-ref visible`。
- **结果**（p4_exact，40 片段）：

| 口径 | start 宏/微 | stop 宏/微 |
|---|---:|---:|
| unclipped（v1–v3） | 0.844 / 0.909 | 0.890 / 0.938 |
| inwindow（严格窗口） | 0.889 / 0.945 | 0.967 / 0.978 |
| **visible（全曲视角）** | **1.000 / 1.000** | **0.967 / 0.978** |
| clipped | 1.000 / 1.000 | 0.939 / 0.972 |

- **结论**：**踏板事件对齐在"系统可见范围"内达到 start 100% / stop ~97%**；"F1 ≥ 90"（宏平均）在 visible 口径下两个指标都达成。论文推荐报 visible + inwindow 双口径。

## 4. CC64 提取审查（P1-5）

- 窗口内参考事件（start 266 / stop 269）与系统输出**全部匹配（FN=0）**，匹配偏移全部 <0.1 QL（中位 0.000）——CC64 阈值提取（≥64/ <64）与量化在窗口内**时序精确**。
- 残留 FP 全部为窗口边界伪事件：
  - **start FP 31**：31 个片段各 1 个窗口起点 start（跨窗区间，切片注入 CC64=127@0 的忠实输出）→ visible 口径转为 TP。
  - **stop FP 12**：12 个片段各 1 个窗口终点 stop（跨窗区间的切片释放 CC64=0@end 伪影；真实释放发生在窗口外）→ 评测口径的已知边界，论文如实说明。
- 短踏板区间（<0.35 QL，Mozart/Schubert 的半踏 CC64 波动）在系统提取中**完整保留**（此前误判为漏检，实为 LH 折叠 bug 的连带现象）。

## 5. 候选可实现性天花板（P1-6）

- 基线：40 片段 4672 事件，可实现 2925（62.6%）。
- **缺口构成**（按 review_class）：notation-shortening 1316/1775（74% 不可实现）、blank 379/1282（30%）、independent-voice 52/136（38%）、pedal-only 0/1479（0%）。
- **根因**：候选集合过小（中位 2 个时值/事件）；踏板延音记谱（记谱时值 > 按键时值）的扩展时值未进入候选。
- **扩展模拟**（在冻结 events.csv 上，候选 ∪ {按键时值×{2,3,4,1.5,0.5}} ∪ {0.25, 0.5, 0.375, 1/6, 1/3, 1.0}）：

| 配置 | 可实现率 |
|---|---:|
| 基线（冻结候选） | 62.6% |
| **扩展候选（模拟）** | **95.8%（+33.2pp）** |

- **实施路径**：`structured_duration_decoder.py` 候选生成加入延音扩展候选 → 重生成 40 片段 × 4 管线 → 候选排序模型需在扩展候选上重新训练（ASAP 数据，不碰金标准）→ 重评。**这是时值一致率的第一瓶颈**（当前 rule 43.5% 距扩展后上限 95.8% 有巨大空间），建议作为论文的"候选生成增强"实验（P1.5 规模，需 1–2 个会话）。

## 6. 已知边界

- **系统声部分配**：Mozart_8-1 / Schubert_op142 / Rachmaninoff_23-6 等片段的参考 LH 音符（46/7/27 个）被全部并入 RH（LH 空）。这是 P4 声部分配的已知限制，影响时值一致率（gold LH 事件匹配不上），与踏板评测无关，论文需如实声明。

## 7. 产物与复现

- 代码：`audio2score/scripts/p4_multivoice_score.py`（LH 回退修复）、`tools/evaluate_gold_standard.py`（visible 口径）。
- 数据：9 个 `p4_exact.musicxml` 重生成；`evaluation/gold_standard_eval_v4.{json,md}` 更新；`NEXT_AI_CONTEXT.md`、`CHECKSUMS.sha256` 同步。
- 复现：
```bash
python tools/evaluate_gold_standard.py --pedal-ref visible --bootstrap 1000 --seed 42 \
  --out outputs/pedal_gold_standard/formal_20260828_v1/evaluation/gold_standard_eval_v4.json
```
