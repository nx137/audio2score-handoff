# Phase 2A 定窗记录（S1 实测 → 主控定窗落盘）

状态：主控定窗（2026-09-07）。依据：`tools/phase2a_window_scan.py`（坐标双轨版，HEAD c60025a4）在本地真实数据的运行结果。
产物：`outputs/pedal_expansion/selection_phase2A.json`（本批 commit 入库，供 exec §3 S3 消费）。
前置文档：`docs/trial8_phase2A_build_exec.md`（执行步骤）、`docs/trial8_phase2A_selection.md`（裁定 #P2A-1/#P2A-2/#P2A-3 与证据）。

## 1. 运行事实

- 扫描退出码 0、五段无 error；完整输出已由本地 AI 原样贴回主控。
- JSON 落在本地 `outputs/pedal_expansion/window_scan_phase2A.json`（未入库；工具已入库可复现，重新运行即可再生）。
- 五段 perf uniform 小节数与谱面小节数系统不同（双轨预期，见 selection.md §4；工具输出 DOMAIN 级对照信息，不阻断——
  裁定 #P2A-2 机制，约束一律在 score 域执行）。

## 2. 定窗结果（五段）

窗口列 = perf uniform 0-based（1-based 显示）。sid 数字 = start_measure+1（沿用 GS 命名惯例），**非谱面小节号**。

| index | sid（=S3 段 id） | performance | perf 窗口 | perf QL | 谱面完整 pedal 对 | CC64 在内 | CC64 跨界 | 事件量 | 扫描评分 |
|---|---|---|---|---|---|---|---|---|---|
| 0 | Chopin_Ballades_3_55 | Ko11M | 54–93 (m55–94) | 216.0–376.0 | 43 | 89 | 1 | 770 | 4415.0 |
| 1 | Liszt_Concert_Etude_S145_2_1 | Lu03M | 0–39 (m1–40) | 0.0–160.0 | 134 | 85 | 0 | 1555 | 13444.5 |
| 2 | Rachmaninoff_Preludes_op_32_10_24 | Floril03 | 23–62 (m24–63) | 92.0–252.0 | 18 | 45 | 1 | 1173 | 1847.7 |
| 3 | Chopin_Barcarolle_1 | Rozanski07M | 0–35 (m1–36) | 0.0–108.0 | 18 | 6 | 0 | 278 | 1812.0 |
| 4 | Ravel_Miroirs_4_Alborada_del_gracioso_25 | Chan02 | 24–59 (m25–60) | 96.0–240.0 | 4 | 38 | 0 | 798 | 476.0 |

（备选候选见工具输出；均满足对应约束。Barcarolle 全部可行窗口仅 3 个：m1-36 / m12-39 / m211-242。）

## 3. 约束符合性（裁定编码进工具，真实运行逐窗口强制）

- Ballades/3：strict 边缘（#P2A-2：窗口外相邻各 ≥2 小节无谱面 pedal mark）；无空隙约束；≥8 对 ✓（43）。
- S145/2：relaxed（#P2A-3：perf 窗口边界不截断 CC64 区间，cross=0）✓；≥8 对 ✓（134）。
- op32/10：strict ✓；≥8 对 ✓（18）。
- Barcarolle：relaxed（cross=0）✓ + gap_avoid（score 域空隙 @646.25–675.25 不重叠）✓ + score 域 end_ql < 600 ✓；≥8 对 ✓（18）。
- Miroirs/4：strict ✓ + gap_avoid（score 域空隙 @245.0–285.5 不重叠）✓ + ≥3 对（#P2A-1）✓（4）。

## 4. 与预置建议的差异（记录在案）

1. **Miroirs/4**：exec §2 预置「窗口定原谱 m55–78（QL 165–243）」是双域扫描前的初步建议。真实双域扫描在
   「避空隙 + strict + ≥3 对」条件下找到含 **4 对完整谱面 pedal** 的窗口（perf m25-60），优于 m55-78 的 3 对，
   故按扫描最优定窗。空隙硬约束不变且已满足（score 域 245.0–285.5 无重叠）。
2. **Barcarolle**：relaxed+gap_avoid+end<600 联合约束极强，全曲仅 3 个可行窗口。定窗 m1-36（谱面 pedal 对最多，18）。
   注意：窗口内 CC64 完整区间仅 6（Rozanski07M 开头踏板事件稀疏是数据真实特征）；② 覆盖不足的行按协议走 ①/uncertain，
   不在空隙/缺失上补写。备选 m211-242（10 对 / 19 CC64，曲尾前）已记录，若 S3 构建诊断确需可更换。
3. **S145/2 事件量 1555**：超出 GS 段常规规模（~100–300 为佳，软目标）。pedal 密集长窗不可压缩（40 perf 小节内
   134 对谱面 pedal），工具按软目标轻微惩罚（>800）但不硬过滤；F 可判行预期充裕。

## 5. 工具小修（同批 commit）

控制台 "score no" 列原打印 perf 小节号 + first_no（展示误导，内部约束与 JSON 不受影响——score_m0/score_m1
一直正确写入 JSON 且约束在 score 域执行）；已改为打印 alignment 映射后的 score 小节范围（score_m0/score_m1 + first_no）。

## 6. 下一步（本地 AI，按 exec §3）

S2：把五段对齐源复制为 `<out>/_alignments/<sid>.csv`（文件名 = 上表 sid）。
S3：`python tools/build_formal_segments.py --index 0..4 --selection outputs/pedal_expansion/selection_phase2A.json --out outputs/pedal_expansion/segments_v1 --skip-render`（逐段）。
S4–S7 依 exec 执行并按 exec §5 回报格式贴回。
