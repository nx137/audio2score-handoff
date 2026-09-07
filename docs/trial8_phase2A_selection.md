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


---

## 8. 执行裁定（2026-09-07，本地 AI S1 实测触发，主控裁定）

**裁定 #P2A-1：Miroirs/4 豁免「窗口内 ≥8 对完整 pedal」硬约束，降为 ≥3 对，保留该段。**

触发事实（本地 AI 实测与主控扫描一致）：避空隙窗口 m55–78（QL 165–243）内完整 pedal 对仅 **3 对**
（m58 start / m62 stop / m70 两对跨 m71 / m75 start，m78 边缘）。该窗口已是「避开 245.0–285.5 空隙」
前提下 pedal 最密集区，无可调整空间（曲尾带 m195–229 被空隙 @635–675 破坏不可用）。

裁定理由：
1. 用户拍板五首组合含 Ravel/Miroirs/4（印象派面）；
2. 该段角色 = Ravel 风格覆盖 + negative case（谱面 pedal 稀疏 + 空隙与 pedal 区重叠的系统性证据），
   而非 F 可判行主贡献段；
3. Phase 2A 汇总目标（≥3 段含 pedal 谱面、可判行 ≥100、覆盖 ≥2 位浪漫派/印象派作曲家）由
   Ballades/3 + Concert_S145/2 + op.32/10 + Barcarolle 四段保证（Barcarolle 候选窗口 31 对、
   op.32/10 9 对、Ballades/3 与 S145/2 远超 8）；
4. 不凑数原则：Miroirs/4 F 可判行如实偏低（预计 10–30），复核时有多少核多少；
   若构建后 F 行 <10，则该段豁免「每段 ≥10 行」抽样门槛，按全部 F 行复核。

约束更新：Miroirs/4 段「窗口内含 ≥3 对完整 pedal（start+stop）」；其余 4 段维持 ≥8 对。


**裁定 #P2A-2：混合拍号段 uniform bar_ql 窗口偏差——接受（GS 既定近似），加边缘规避约束，不改代码。**

触发（本地 AI S1 实测）：S145/2 窗口 uniform [24,120) vs score 真实 measure 累计 [24,135)
（尾部差 15 QL ≈ 4 小节）；Miroirs/4 uniform [162,234) vs [174,246)（平移 12 QL）。

主控取证结论：
1. **坐标系双轨为 GS 既定设计**（rebuild_coord_fix_spec.md P0 权威记录）：Segment 的
   start_ql/end_ql/bar_ql/time_sig 属 **performance-MIDI 坐标**（uniform）；score 侧窗口由
   alignment 映射为真实 measure（如 GS Une Barque：perf measure 180–183 映射到 score
   measure 72，metadata 有 score_start_ql/score_start_measure 与 coordinate_fix=
   alignment-mapped-score-window 记录）。本地 AI 用 score 真实累计衡量 perf uniform 窗口
   属坐标系混比，偏差方向性成立但基准错配。
2. **GS 先例**：40 段含混合拍号段（Une Barque）以同机制构建并全量验收通过（裁决 #7），
   P0 修复仅限 reference 侧（measure 粒度过滤），未改 build 侧——build 侧 uniform 是
   有意的近似设计。
3. **容差**：候选窗口裁剪自带 ±16 QL 缓冲（NEXT_AI_CONTEXT 记录"已验证窗口内输出与全曲
   一致"）。S145/2 偏差 15 QL、Miroirs 12 QL 均 < 16 QL，在容差内但偏大（贴近上限）。
4. **影响边界**：perf 窗口偏差影响 P3/P4 候选生成范围（评测用）；金标准六列标注
   （events.csv ③ 判读）坐标权威在 rebuild 侧（alignment 映射 + measure 粒度过滤），
   不受 perf 切窗偏差直接影响。

裁定：
- **不改 build 代码**（超出 Phase 2 授权；GS 同机制已验收）；接受偏差继续构建；
- **新增 S1 选窗边缘规避约束**：窗口首尾各留 ≥2 小节（≈ 8 QL）内不得含 pedal 事件
  （防窗口边缘偏差吃掉 pedal 样本）。若 S145/2/Miroirs/4 现选窗口不满足，向里收缩窗口
  或微调 measure 范围后重新验证；
- S6 质检回报须附 uniform-real 偏差实测值（perf 窗口 QL vs 该段 alignment 映射的
  score 窗口 QL），供主控最终判断产物边界。

约束更新：S1 在「≥8/≥3 对 pedal」与「空隙规避」之外，追加「窗口边缘 ≥2 小节无 pedal」。

**裁定 #P2A-3：豁免 S145/2 与 Barcarolle 的「窗口边缘 ≥2 小节无 pedal」约束（#P2A-2 部分撤销），
以「窗口边界不截断 pedal 对」承接；保留两段。**

触发（本地 AI S1 实测回报，2026-09-07）：S145/2（210 对/113 小节 ≈1.9 对/小节）、
Barcarolle（246 对/107 小节 ≈2.3 对/小节）pedal 近乎连续（几乎每小节都有 pedal 活动），
#P2A-2 新增的「窗口首尾各 ≥2 小节无 pedal」**结构性不可满足** → 两段 0 可行窗口；
本地 AI 停报请求裁决（三选一：豁免 / 换段 / 放宽）。主控上报用户后，用户拍板
「豁免边缘约束（推荐）」方案 1。

裁定理由：
1. pedal 连续密集正是两段入选 F 组的根本原因（pedal 富集 + Liszt/Chopin 风格覆盖）；
   F 组须覆盖「pedal 连续密集」这一全量重标注最困难场景——若只选 pedal 稀疏段，
   等于人为规避困难场景、引入选择偏差，验证结论无法外推（呼应用户定位：
   扩样段是验证工具，最终目标是全数据集重标注）；
2. #P2A-2 边缘约束的本意 = 窗口边界判定干净 + 为 uniform 坐标偏差（S145/2 差 15 QL）
   留缓冲；其形式（≥2 小节无 pedal）对 pedal 连续密集段不可满足，但目的可由
   「边界不截断 pedal 对」+ slice 自带 ±16 QL 缓冲承接；
3. 与 #P2A-1（Miroirs/4 约束 8 对→3 对）同性质：约束按段特征适配，不搞一刀切。

裁定：
- 豁免范围**仅限** S145/2 与 Barcarolle；Ballades/3、op32/10、Miroirs/4 已有可行窗口，
  维持 #P2A-2 原约束（边缘 ≥2 小节无 pedal）不变；
- S145/2 与 Barcarolle 的替代质量判据：
  a) 首选：窗口 start/end 不落在任何 pedal 对 (down, up) 区间内（不截断 pedal 对）；
  b) 若 a) 扫描后仍 0 可行窗口：允许边界截断 pedal 对，但截断行须标记 uncertain 走
     ① 人工复核、不计入 ③ 自动判定；此降级路径须先回报主控、确认后再定窗；
- 其余约束不变：两段仍须「窗口内 ≥8 对完整 pedal」+ 空隙规避（Barcarolle 窗口避开
  QL>600）；S145/2 uniform 偏差 15 QL < ±16 QL slice 缓冲，接受（#P2A-2 已裁定）；
- 降级门槛：豁免后若某段 F 可判行仍过低（<10），按 #P2A-1 同款处理——F 行全量复核、
  不硬凑段数（五首组合是上限而非下限）。

约束更新（S1 生效）：
- Ballades/3、op32/10、Miroirs/4：「≥8/≥3 对 pedal」+ 空隙规避 + 窗口边缘 ≥2 小节无 pedal；
- S145/2、Barcarolle：「≥8 对 pedal」+ 空隙规避 + 窗口边界不截断 pedal 对
  （若不可行 → 允许截断 + 截断行走 ① 复核，回报主控确认后定窗）。
