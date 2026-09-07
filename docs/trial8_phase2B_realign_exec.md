# Phase 2B 执行指令 v1：Liszt TE9 ADIG07 重新对齐（本地 AI 执行）

状态：定稿（2026-09-07）。前置：用户拍板「Liszt TE9 尝试重新对齐：成功则纳入，仍失败再排除」；
数据缺陷定性见裁决 #10 与 `docs/rebuild_coord_fix_spec.md` §4.2。
主控侧已核事实：官方 (n)ASAP robust_note_alignment TE9 三 performance 全 0（人工检视标记）；
项目自有对齐 ADIG07 = 151 行 / maxgap 115.33 / gap>20 四段（TE9 段 261 events 中 unmatched 256）。

## 1. 目标与验收

目标：用音符级对齐工具 parangonar（而非现行 beat 插值后端）重做
`Liszt/Transcendental_Etudes/9/ADIG07` 的 performance↔score 对齐，产出项目 7 列对齐 CSV
（hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql），
并交叉核对裁决 #10 铁证（pitch 100 反复 ×80 + LH 低音 39–58 必须落到 score 真实位置，
不得再落入空隙/伪窗口）。

验收（向主控回报后由主控裁定是否纳入）：
- 匹配覆盖率（matched 行数 / 261 事件）达标且无 >30 QL 空洞；
- 铁证交叉核对通过：真实位置落在 number 14/X1 一带的对应小节。

## 2. 输入

- score: `data/ASAP/Liszt/Transcendental_Etudes/9/xml_score.musicxml`
- performance: `data/ASAP/Liszt/Transcendental_Etudes/9/ADIG07.mid`
- performance 节拍标注（现用后端的输入）: `data/ASAP/Liszt/Transcendental_Etudes/9/ADIG07_annotations.txt`
- （对照，不直接作为成功依据）官方 (n)ASAP v2.1 `ADIG07_note_alignments/note_alignment.tsv`
  与 `ADIG07.match`——CPJKU/asap-dataset 仓库同名目录，官方标 robust=0，仅作失败模式对照。

## 3. 方案（按序尝试，前一方案达标即停并向主控回报）

### 方案 A：parangonar `DualDTWNoteMatcher`（默认）
```
pip install parangonar partitura   # parangonar 3.3.x；partitura >= 1.6
```
流程：
1. `partitura.load_musicxml(xml, force_note_ids=True)`（必要时 unfold repeats / merge parts，需与
   项目 reference score 事件口径对齐——reference_onset_ql 以项目现有 score QL 坐标系为准）；
2. `partitura.load_performance_midi(mid)`；`process_ornaments=True`；
3. `DualDTWNoteMatcher().match(score, performance)` → note alignment（score_id ↔ perf_id）；
4. 覆盖率 = 匹配的 perf 音符 / ADIG07 音符总数；同时统计匹配结果在 score 侧的 QL 覆盖空洞。

### 方案 B：`TheGlueNoteMatcher`（A 大面积失败时兜底）
同 3.1 输入，替换 matcher。容忍大 mismatch。

### 方案 C：官方 note_alignment.tsv 对照（仅分析）
拉官方 tsv，统计其自身覆盖率与空洞——用于判断“官方都做不好”是工具问题还是数据问题。

## 4. 坐标换算与注入（成功后才做，且须先报主控批准改 TE9 段）

1. 将 parangonar 匹配换算到项目 7 列格式：
   - perf 侧：`onset_ql` 沿用项目现有 performance 时间→QL 换算（asap_alignment.py 口径）；
   - score 侧：score note → `reference_onset_ql` 用项目现有 score 事件 QL（同 P0 修复后的真实累计口径）；
   - `hand/pitch`：perf note 的 pitch + 左右手拆分（split_hands 口径）。
2. 与裁决 #10 铁证交叉核对：pitch 100 反复 ×80、LH 低音 39–58 在重对齐结果中的
   reference_onset_ql 必须落在真实小节（number 14/X1 一带），而非 8.25→145.75 伪空隙。
3. 重建 TE9 段（`outputs/pedal_gold_standard/formal_20260828_v1/Liszt_Transcendental_Etudes_9_67/`）
   的 reference_pedals.csv 与 events ③ 列参考锚——**该步会改动 40 段冻结档案内的 TE9 段，
   必须先向主控申报（按裁决 #8/#9 先例做新裁决）再执行**，不得擅自覆盖。
4. 若重建，须同步更新规格与裁决记录（新裁决 #11+）。

## 5. 止损线（向主控回报，由主控裁定排除或继续）

- 方案 A+B 均无法达成：匹配覆盖 < 50%（约 130/261）或存在 >30 QL 空洞 → 建议正式排除
  Liszt TE9 出 F 组，记录为 negative case（对齐工具链在高度自由速度慢板上的已知失效），不补写、不伪造；
- 覆盖率在 50%–80% 灰区：向主控回报覆盖质量细节（空洞位置、错配模式），由主控人工裁定。

## 6. 产物与回报

产物（成功后）：`outputs/pedal_expansion/realign/liszt_te9_adig07_alignment.csv`（7 列）；
回报内容：方案 A/B/C 各自覆盖率与空洞、铁证核对表、官方对照、环境版本（parangonar/partitura）、
git status（应只见新增 realign 产物）。

## 7. 红线

TE9 段档案改动须先报批；不伪造、不在空隙上插值；官方 tsv 仅作对照不作成功依据；
异常即停回报。
