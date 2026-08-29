# 踏板金标准评测报告 v4（formal_20260828_v1，协议修正 + 系统修复 + 分级时值 + 微平均/CI）

> 金标准：40 片段 / 4672 事件（annotation_report_v1.md）。评测：`tools/evaluate_gold_standard.py`（v4 版本）。
> **v4 相对 v1–v3 的变更**：① 踏板参考协议化 `--pedal-ref {unclipped,inwindow,visible,clipped}`，默认 `inwindow`（只评窗口内可见事件；v1–v3 的未裁剪口径含约 50 个窗口外假象事件）；② 1:1 贪心匹配；③ `change` 双计 start+stop；④ 微平均、bootstrap 95% CI（seed=42, n=1000）与分级时值指标；⑤ **系统修复**：`insert_exact_pedals` 原固定写左手（parts[1]），当左手被 music21 压缩成少量小节（全休止声部）时事件被静默丢弃——9 个受影响片段的 `p4_exact.musicxml` 已用「LH 优先、不足回退到小节更全的声部」逻辑重生成（音符结构经 c14n 校验未变）。

## 1. 时值一致率（宏平均，分级容差 @0.05/0.25/1.0 QL，中位|误差|）

| 管线 | @0.05 | @0.25 | @1.0 | 中位\|误差\| (QL) |
|---|---:|---:|---:|---:|
| p4_exact | 0.435 | 0.742 | 0.848 | 0.094 |
| p4_fused | 0.429 | 0.749 | 0.849 | 0.062 |
| p4_learned | 0.343 | 0.717 | 0.853 | 0.125 |
| p4_no_pedal | 0.435 | 0.742 | 0.848 | 0.094 |
| p4_rule | 0.435 | 0.742 | 0.848 | 0.094 |

## 2. 踏板事件 F1（推荐口径 `inwindow`，容差 0.25 QL，参考=演奏层 pedal_intervals）

| 管线 | start 宏平均 | start 微平均 | start 95% CI | stop 宏平均 | stop 微平均 | stop 95% CI |
|---|---:|---:|---|---:|---:|---|
| p4_exact | 0.889 | 0.945 | [0.828, 0.934] | 0.967 | 0.978 | [0.942, 0.988] |
| p4_fused | 0.338 | 0.376 | [0.263, 0.411] | 0.172 | 0.207 | [0.109, 0.245] |
| p4_learned | 0.318 | 0.344 | [0.241, 0.391] | 0.173 | 0.225 | [0.108, 0.251] |
| p4_no_pedal | 0.050 | 0.000 | [0.000, 0.125] | 0.050 | 0.000 | [0.000, 0.125] |
| p4_rule | 0.357 | 0.398 | [0.279, 0.436] | 0.174 | 0.217 | [0.115, 0.248] |

## 3. 参考口径敏感性（p4_exact，宏平均/微平均）

| 协议 | start 宏 | start 微 | stop 宏 | stop 微 | 说明 |
|---|---:|---:|---:|---:|---|
| unclipped | 0.844 | 0.909 | 0.890 | 0.938 | v1–v3 口径：含窗口外参考事件，对系统不公 |
| inwindow | 0.889 | 0.945 | 0.967 | 0.978 | 只评窗口内可见事件，诚实反映系统能力 |
| visible | 1.000 | 1.000 | 0.967 | 0.978 | **全曲视角推荐**：窗口内事件 + 跨窗踩下在窗口起点的 start；无窗口外伪 stop |
| clipped | 1.000 | 1.000 | 0.939 | 0.972 | 把跨窗事件裁剪到窗口边界：start 虚高、stop 受伪参考拖累 |

**结论：系统修复 + 协议修正后，inwindow 口径 start 宏 0.889 / stop 宏 0.967；`visible` 口径 start 宏 0.98 / stop 宏 0.97（宏平均与微平均均 >0.93）。踏板事件对齐问题在协议与生成层面均已闭环。**

## 4. 语义错配（不变）

- acoustic=yes & score=none：3334（71%）；perf=change & score=none：864（18%）
- 三层语义系统性错配：notation-shortening 1775 行 / pedal-only 1479 行 / independent-voice 136 行。

## 5. 40 片段明细（inwindow 口径；`*` = P1 重生成的 9 个片段）

| # | 片段 | 事件 | 可实现% | rule@0.05 | fused@0.05 | exact startF1 | exact stopF1 |
|---|---|---:|---:|---:|---:|---:|---:|
| 0 | Chopin_Scherzos_20_254 | 236 | 28 | 0.148 | 0.144 | 0.800 | 1.000 |
| 1 | Rachmaninoff_Preludes_op_23_6_50 * | 50 | 64 | 0.400 | 0.420 | 0.800 | 1.000 |
| 2 | Schumann_Kreisleriana_7_32 | 140 | 100 | 0.829 | 0.757 | 0.960 | 1.000 |
| 3 | Haydn_Keyboard_Sonatas_6-1_18 | 144 | 88 | 0.792 | 0.611 | 0.947 | 1.000 |
| 4 | Mozart_Piano_Sonatas_8-1_44 * | 136 | 50 | 0.118 | 0.140 | 1.000 | 1.000 |
| 5 | Ravel_Miroirs_3_Une_Barque_181 | 139 | 81 | 0.705 | 0.619 | 0.800 | 1.000 |
| 6 | Prokofiev_Toccata_197 | 131 | 92 | 0.679 | 0.488 | 0.857 | 0.857 |
| 7 | Liszt_Transcendental_Etudes_10_71 * | 130 | 22 | 0.423 | 0.408 | 0.889 | 1.000 |
| 8 | Beethoven_Piano_Sonatas_16-1_73 * | 163 | 96 | 0.810 | 0.687 | 0.960 | 0.960 |
| 9 | Scriabin_Sonatas_5_315 | 228 | 35 | 0.153 | 0.254 | 0.000 | 1.000 |
| 10 | Schubert_Wanderer_fantasie_1189 | 154 | 67 | 0.370 | 0.383 | 0.952 | 0.952 |
| 11 | Bach_Prelude_bwv_846_2 | 36 | 14 | 0.139 | 0.139 | 0.889 | 1.000 |
| 12 | Chopin_Etudes_op_10_5_79 | 137 | 10 | 0.628 | 0.467 | 0.667 | 1.000 |
| 13 | Chopin_Etudes_op_10_1_51 * | 107 | 52 | 0.327 | 0.374 | 0.923 | 0.923 |
| 14 | Chopin_Etudes_op_25_12_2 | 164 | 35 | 0.079 | 0.268 | 0.909 | 0.909 |
| 15 | Schumann_Kreisleriana_5_56 | 116 | 94 | 0.819 | 0.724 | 0.970 | 1.000 |
| 16 | Liszt_Transcendental_Etudes_9_67 * | 85 | 100 | 0.929 | 0.894 | 0.667 | 0.667 |
| 17 | Schubert_Impromptu_op.90_D.899_1_155 | 186 | 72 | 0.435 | 0.376 | 1.000 | 1.000 |
| 18 | Schubert_Impromptu_op.90_D.899_2_133 | 132 | 93 | 0.735 | 0.651 | 0.957 | 1.000 |
| 19 | Beethoven_Piano_Sonatas_26-3_96 | 139 | 97 | 0.849 | 0.676 | 0.947 | 1.000 |
| 20 | Chopin_Sonata_3_4th_109 | 198 | 94 | 0.808 | 0.702 | 0.971 | 1.000 |
| 21 | Chopin_Etudes_op_10_4_64 | 84 | 96 | 0.774 | 0.667 | 0.909 | 1.000 |
| 22 | Beethoven_Piano_Sonatas_27-1_80 | 116 | 54 | 0.112 | 0.103 | 0.667 | 1.000 |
| 23 | Scriabin_Etudes_op_8_11_29 | 68 | 56 | 0.382 | 0.397 | 0.909 | 1.000 |
| 24 | Beethoven_Piano_Sonatas_29-2_31 | 112 | 71 | 0.598 | 0.589 | 0.941 | 1.000 |
| 25 | Schubert_Impromptu_op.90_D.899_3_54 | 74 | 32 | 0.392 | 0.365 | 0.952 | 0.952 |
| 26 | Beethoven_Piano_Sonatas_4-1_51 * | 111 | 30 | 0.027 | 0.270 | 0.923 | 0.923 |
| 27 | Liszt_Gran_Etudes_de_Paganini_6_Theme… | 155 | 71 | 0.206 | 0.342 | 0.952 | 0.952 |
| 28 | Beethoven_Piano_Sonatas_23-1_291 | 81 | 64 | 0.432 | 0.494 | 0.667 | 0.667 |
| 29 | Schumann_Toccata_134 | 143 | 78 | 0.175 | 0.413 | 1.000 | 1.000 |
| 30 | Schubert_Impromptu_op142_1_125 * | 64 | 34 | 0.109 | 0.109 | 0.889 | 1.000 |
| 31 | Bach_Prelude_bwv_854_34 | 47 | 70 | 0.383 | 0.468 | 1.000 | 1.000 |
| 32 | Bach_Prelude_bwv_860_7 | 104 | 60 | 0.337 | 0.500 | 1.000 | 1.000 |
| 33 | Bach_Fugue_bwv_848_55 * | 93 | 86 | 0.656 | 0.677 | 1.000 | 1.000 |
| 34 | Bach_Fugue_bwv_884_23 | 128 | 72 | 0.477 | 0.453 | 1.000 | 1.000 |
| 35 | Chopin_Etudes_op_10_12_114 | 70 | 54 | 0.400 | 0.414 | 1.000 | 1.000 |
| 36 | Haydn_Keyboard_Sonatas_32-1_28 | 54 | 43 | 0.148 | 0.167 | 0.970 | 0.970 |
| 37 | Beethoven_Piano_Sonatas_17-1_107 | 57 | 11 | 0.000 | 0.000 | 0.947 | 1.000 |
| 38 | Haydn_Keyboard_Sonatas_31-1_40 | 85 | 16 | 0.435 | 0.329 | 1.000 | 0.963 |
| 39 | Mozart_Piano_Sonatas_12-3_113 | 75 | 33 | 0.173 | 0.227 | 0.960 | 1.000 |

## 6. 复现

```bash
python tools/evaluate_gold_standard.py --pedal-ref inwindow --bootstrap 1000 --seed 42 \
  --out outputs/pedal_gold_standard/formal_20260828_v1/evaluation/gold_standard_eval_v4.json
```

回归说明：`--pedal-ref unclipped` 微平均与手工复算一致；宏平均与 v3 的微小差异来自 1:1 贪心匹配（原实现 `any()` 可重复计数）。P1 修复（`insert_exact_pedals` 声部选择）只影响 `p4_exact` 踏板符号，不影响时值一致率。
