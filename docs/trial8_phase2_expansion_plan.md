# Phase 2 执行规格：pedal 富集扩样 + Liszt TE9 重新对齐

状态：草案（2026-09-06，主控起草）
决策记录：
- 用户拍板「先扩样再上全量」：trial8 试点证据偏窄（③ 可判仅 Chopin 单段），
  先补抽含 `<pedal>` 的段扩大 F 组验证，再投入整个数据集重标注。
- 用户拍板「Liszt_Transcendental_Etudes_9_67 尝试重新对齐」：成功则纳入，
  仍失败则按止损线排除并记录。

---

## 1. 现状事实（2026-09-06 云端核验）

| # | 事实 | 证据 |
|---|------|------|
| 1 | 40 段金标准中谱面含 `<pedal>` 的仅 3 段 | 逐段扫描 reference_score.musicxml：Chopin_Scherzos_20_254 = 5 标签（小节 599–602）、Ravel_Miroirs_3_Une_Barque_181 = 2（m.72）、Liszt_TE9_67 = 1（元素序 m.15）；其余 37 段 = 0 |
| 2 | 40 段是「作曲家均衡 + 质量分」抽样产物，未对 pedal 富集 | tools/select_gold_standard.py：stratified_pool → 每作曲家 ≥1 → score 填充至 40（seed=20260828） |
| 3 | Liszt TE9 ADIG07 对齐数据缺陷 | 261 events 中 unmatched=256、labeled=1（segment_metadata.json）；_alignments CSV 中 onset_ql 8.25→145.75 空 137.5 QL |
| 4 | (n)ASAP 官方对该曲目音符级对齐亦不可靠 | CPJKU/asap-dataset（v2.1）metadata.csv：ADIG07 robust_note_alignment=0.0（官方人工检视标记），TE9 三 performance 全为 0 |
| 5 | 现行对齐后端 = beat 标注分段线性插值 + 同音高唯一匹配 | audio2score/scripts/asap_alignment.py（pretty_midi 实现），非音符级 DTW |
| 6 | 现成音符级对齐工具可用 | parangonar 3.3.2（PyPI，Apache-2.0）：DualDTWNoteMatcher（默认/SOTA）、AutomaticNoteMatcher（(n)ASAP v2.0 官方所用）、TheGlueNoteMatcher（神经网络，容忍大 mismatch）；partitura ≥1.6 解析 |
| 7 | 全池扫描器已入库 | tools/scan_pedal_in_scores.py（commit 51b79d01），待本地执行 |

**结构性推论**：③ 列（published_score_pedal）判读的证据厚度 = 谱面含 `<pedal>`
的段数 × 每段命中行数。不扩样则 F 组只剩 Chopin 单段 50 行——不足以支撑
「整数据集重标注」的方法可信度论证。扩样是 Phase 2 的前提。

---

## 2. Phase 2A：pedal 富集扩样

目标：把 F 组可判证据从「1 段 50 行」提升到「≥3 段含 pedal 谱面、可判行
≥100」，且覆盖 ≥2 位浪漫派/印象派作曲家。

### 2.1 全池扫描（本地 AI 执行——验证运行）
```
python tools/scan_pedal_in_scores.py \
    --asap-root data/ASAP \
    --out outputs/pedal_expansion/score_pedal_scan.csv
```
产出：data/ASAP 全部 222 首 xml_score 的 pedal_starts/stops/changes、
所在小节清单。回报主控候选清单。

### 2.2 候选过滤（主控据扫描结果裁定）
- 硬性条件：谱面含 ≥1 对 start+stop（即 pedal 区间完整）；
- 优先级：浪漫派/印象派（Chopin、Liszt、Ravel、Debussy、Schubert、Schumann、
  Scriabin、Rachmaninoff、Brahms）> 其他；
- 排除：5 个 pilot 曲目（select_gold_standard.PILOT_PIECE_KEYS）；
- 排除已知缺陷条目（如 Liszt TE9 ADIG07 重对齐未成功前不重复入样）。

### 2.3 选段与构建（本地 AI 执行，复用既有工具链）
- 选段：复用 build_pedal_gold_standard 的 best_window / stratified_pool 逻辑，
  但样本池限定为含 pedal 曲目；窗口需覆盖 ≥1 个 pedal 小节；
- 构建：build_formal_segments → rebuild_segment_reference.py（P0 修复后
  measure 粒度过滤）→ 六列自动标注（② CC64 规则映射、③ MusicXML `<pedal>`
  解析+坐标映射、① 数值判据、④⑤⑥ 规则复核——trial8 v1.3 流程）；
- 产物进 outputs/pedal_gold_standard/formal_20260828_v1/ 之外的新目录
  （如 phase2_expansion/），不动既有 40 段冻结档案。

### 2.4 F 组人工复核（用户，标注者 A）
- 对新段 ③ 判读命中行（published_score_pedal 非 none）抽样复核；
- 抽样 ≥30% 或每段 ≥10 行，对照 reference_score.musicxml；
- 复核记录复用 trial8 review CSV 格式。

### 2.5 判定标准（收敛后放行全量）
- F 组确认率 ≥95% 且无系统性修订；
- 若出现系统性修订 → 按 trial8 模式：主控裁决根因 → 修代码/规格 → 重跑 →
  复核，直到收敛。

---

## 3. Phase 2B：Liszt TE9 ADIG07 重新对齐

### 3.1 输入（整曲，非切段）
- score：data/ASAP/Liszt/Transcendental_Etudes/9/xml_score.musicxml
- performance：data/ASAP/Liszt/Transcendental_Etudes/9/ADIG07.mid
- （对照）官方：CPJKU/asap-dataset v2.1 同名目录 note_alignment.tsv / .match

### 3.2 方案（按序尝试，前一方案匹配覆盖率达标即停）
- A. parangonar `DualDTWNoteMatcher`（默认推荐）
  score = partitura 加载 xml（force_ids、merge_parts、unfold repeats 视情况）；
  perf = load_performance_midi；process_ornaments=True；
- B. parangonar `TheGlueNoteMatcher`（A 大面积失败时兜底，容忍版本差异）；
- C. 官方 (n)ASAP v2.1 note_alignment.tsv 对照（官方标 robust=0，仅作失败
  模式对照，不直接作为成功依据）。

### 3.3 注入（成功后）
- 对齐（score note ↔ performance note）→ 换算到项目坐标系：
  转成 _alignments CSV 同构格式（hand,pitch,onset_ql,reference_part,
  reference_voice,reference_pitch,reference_onset_ql）；
- 重建该段 reference_pedals.csv 与 events.csv 的 ③ 列参考锚；
- 与裁决 #10 铁证交叉核对：performance 中 pitch 100 反复 ×80 与 LH 低音
  39–58 必须落到 score 对应小节（真实位置在 number 14/X1 一带），不得再落
  空隙/伪窗口。

### 3.4 止损线（待拍板）
- 若 A+B 的匹配覆盖率（matched/261）仍低于阈值 → 正式排除 Liszt TE9 出
  F 组，在论文与数据说明中记录为 negative case（对齐工具链在高度自由速度
  慢板上的已知失效），不补写、不伪造。
- 建议阈值：matched < 50%（130/261）即排除；≥50% 则进入人工抽样核对。

---

## 4. 与「整个数据集重标注」的衔接

Phase 2 收敛后（F 组确认率达标），即启动既定目标——按 v1.3 修复后方法
对全数据集（40 段 + Phase 2 新段，乃至 manifest 全量可重建段）重标注：

1. 流水线全量重跑（② CC64 全域映射 / ③ pedal 解析+坐标 / ① 数值判据）；
2. 全量质检：alignment 质量检查（Liszt 类缺陷自动标记）→ ③ 与谱面 `<pedal>`
   逐段对账 → ② 与 CC64 事件流对账；
3. 分层抽样人工复核（段 × 事件类型）；
4. trial8 8 段 + Phase 2 新段作为回归基线：重跑结果应与复核记录一致
   （除已修复坐标项）。

---

## 5. 待拍板项

- P1. 扩样段数（建议 6–10 段，见问题）
- P2. Liszt 止损线阈值（建议 matched<50% 排除）
- P3. 是否引入 (n)ASAP v2.1 官方 note alignment 作为全量对照源
