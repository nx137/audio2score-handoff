# Phase 2A 选段裁定 + 对齐质量核查报告

状态：定稿（2026-09-07，主控裁定落盘）
前置决策：
- 用户拍板「先扩样再上全量」：trial8 试点 F 组证据偏窄（③ 可判仅 Chopin 单段 50 行），先补抽含 `<pedal>` 段扩大验证，再投入整个数据集重标注。
- 用户拍板「Liszt TE9 ADIG07 尝试重新对齐」（Phase 2B，本报告不含其执行细节，见 plan §3）。
- 用户拍板「扩样选段 = 五首最全」：Chopin/Ballades/3 + Liszt/Concert_Etude_S145/2 + Rachmaninoff/Preludes_op_32/10 + Chopin/Barcarolle + Ravel/Miroirs/4_Alborada_del_gracioso。

## 1. 对齐质量核查方法（双重判据）

1. 官方 (n)ASAP metadata.csv `robust_note_alignment`（1066 rows，官方人工检视标记）。
2. 项目自有 external alignment（`data/alignments/*.csv`，1036 文件，7 列：
   `hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql`）空隙分析：
   - rows = 匹配行数；maxgap = reference_onset_ql 排序后最大相邻差；span = onset_ql 跨度；g20 = gap>20 QL 段数。
   - 失败模式标定：Liszt TE9 ADIG07 = 151 行 / maxgap 115.33 / 4 处 gap>20。

## 2. 反直觉证据（重要方法论结论）

| 曲目 | 官方 robust | 项目 alignment | 结论 |
|---|---|---|---|
| Schumann/Arabeske | 1.0（2/2） | **失败**：82/81 行、137.75 QL 空隙×3 | 官方标记**不可**作为选段依据 |
| Liszt/Concert_Etude_S145/2 | 0（0/4） | **优良**：2191–2363 行、0 大空隙 | 淘汰决策须以**项目空隙分析**为准 |
| Rachmaninoff/Preludes_op_32/10 | 0（0/2） | **优良**：610 行、maxgap 18 | 同上 |

**推论：凡选段必须跑项目 alignment 空隙分析；官方 robust 仅作提示，不直接决定可用性。**

## 3. 核查分层结果

### A 级（0 大空隙，直接可用）
| 曲目 | perf 数 | 对齐行数 | maxgap | span | g20 |
|---|---|---|---|---|---|
| Chopin/Scherzos/31 | 12 | 5233–5410 | 11.0 | 2331 | 0 |
| Chopin/Ballades/1 | 17 | 3700–4200 | 7–9.5 | 1452 | 0 |
| Chopin/Ballades/3 | 3 | 3527–3852 | 7.0 | 720 | 0 |
| Liszt/Concert_Etude_S145/2 | 4 | 2191–2363 | 11.5–19.5 | 550 | 0 |
| Rachmaninoff/Preludes_op_32/10 | 1 (Floril03) | 610 | 18.0 | 240 | 0 |

### B 级（1 处空隙，窗口可规避）
| 曲目 | perf 数 | 对齐行数 | 空隙位置 | 备注 |
|---|---|---|---|---|
| Chopin/Barcarolle | 9 | 2519–2757 | @635.7–675.2（曲尾） | 窗口选曲尾前 pedal 区即可 |
| Ravel/Miroirs/4_Alborada | 10 | 1452–1674 | @245.0–285.5（m78–m92） | 见 §5 局限 |

### C 级（淘汰）
| 曲目 | 证据 |
|---|---|
| Schumann/Arabeske | 82/81 行 + 137.75 QL×3（TE9 同款失败） |
| Liszt/Sonata | 3590–3799 行但 **21–23 处 gap>20**、maxgap 222–266 |
| Liszt/Mephisto_Waltz | 3–4 处 gap>20、maxgap 46.25、系统失败区@718–764（13 perf 一致） |
| Liszt/Transcendental_Etudes/4 | 行数仅 426–455（覆盖严重不足） |
| Liszt/Transcendental_Etudes/9 | 已知（裁决 #10），151/141/133 行 + 115+ QL 空隙×4–6 |
| Liszt/Hungarian_Rhapsodies/6 | 31–91.5 QL 空隙×1（Ye04 达 91.5） |

## 4. 选段裁定与窗口约束（五首）

| 曲目 | performance 候选 | 对齐证据 | 窗口约束 |
|---|---|---|---|
| Chopin/Ballades/3 | Ko11M / LinPeng06M / Tan02 | 0 空隙 | 无（pedal 遍布 190 小节） |
| Liszt/Concert_Etude_S145/2 | Lu03M / Tario06M / Lo02 / ZhangX03 | 0 大空隙 | 无 |
| Rachmaninoff/Preludes_op_32/10 | Floril03（唯一 perf） | maxgap 18 | 短曲（span 240）可覆盖大段 |
| Chopin/Barcarolle | 9 perf 任意 | 1 空隙@曲尾 | **窗口避开 QL>600 区** |
| Ravel/Miroirs/4 | Chan02 等 10 perf | 1 空隙@245–285.5 | **窗口定 m55–78（QL 165–243），避开空隙** |

## 5. 已知局限（入档，论文 negative-case 素材）

1. **Miroirs/4 空隙与 pedal 区系统性重叠**（10 perf 空隙位置一致 @245–285.5）：
   pedal m82(start@255)/m85(stop@264)/m89(start@276)/m91(stop@282) 落空隙内、无 performance 对齐锚 → 这 4 个标记**不参与 ③ 判读**；
   可用 pedal 区 = m58/62/70/75/78（QL 183–243），窗口建议 m55–78。印象派谱面 pedal 本就稀疏，F 可判行预计少于浪漫派曲目。
2. **Barcarolle 曲尾空隙**：对齐后端在曲尾渐弱段失效（9 perf 一致 @635–675），不影响中段窗口。
3. **官方 robust 标记与项目 alignment 的不一致**（§2）——论文方法部分可引为"选段需以数据自有对齐质量为准"的证据。

## 6. 产物入库（Phase 2A 已入库产物）

- `outputs/pedal_expansion/score_pedal_scan.csv`：ASAP 235 首 `<pedal>` 扫描（64 首含 pedal）——已入库（commit 见本报告同批）。
- `docs/trial8_phase2A_selection.md`：本报告。

## 7. 下一步

1. Phase 2A 构建执行：本地 AI 按本报告 §4 选段与窗口约束跑 build 流水线（五段），产出六列标注 + F 组复核清单。
2. 用户（标注者 A）对新段 F 行抽样复核（≥30% 或每段 ≥10 行）。
3. 收敛后按 phase2 plan §2.5 判定（F 组确认率 ≥95% 放行全量重标注）。
4. Phase 2B（Liszt TE9 parangonar 重对齐）可与 2A 并行推进。
