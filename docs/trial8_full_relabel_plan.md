# Trial-8 全数据集重标注执行方案（草案 v0.1）

> 建档：2026-10-03（主控）｜状态：**草案**，待 §5 决策项 D1-D5 锁定后升 v1.0。
> 已完成的两条链：Trial-8 8 段（`outputs/pedal_gold_standard/formal_20260828_v1/`，coordinate-fix 重建，
> commit `2e1ba411f1`）＋ Phase 2A 5 段扩样（`outputs/pedal_expansion/segments_v1/`，材料 commit `950db2f6`，
> 锚定 commit `8feb0301f7`）。
> 目的：把「客观基准 + 抽样人工复核」从试标/扩样推广到全数据集，产出一份**坐标一致、口径一致、
> 可复现**的踏板六列重标注，支撑论文记谱层（P4）结论与开源复现。
> 本方案只固化**口径与节奏**，**不复制命令**——各步的现行命令以对应 exec 文档为准，避免两处漂移。

## 1. 不变式（任何段都不得偏离）

- **I1 坐标双轨**：`onset_location`（performance 域，按该段 performance `bar_ql` 均分）与 `score m.`
  （乐谱自身小节编号）**不得混用**。谱面定位一律走 score 侧：`events.csv` 的 `reference_onset_ql`
  ＋ `measure_starts` 惯例 ＋ `segment_metadata.json` 的 `score_start_measure` 锁定切片起点；
  `segment_metadata.json` 必须带 `coordinate_fix: alignment-mapped-score-window`。
- **I2 窗口成员判定**：精确 QL 半开区间 `starts[first] <= ql < starts[last+1]`（源码级口径，O1 已关闭）。
- **I3 踏板归一**：同一 `(hand, position)` 的成对 stop+start 归一为 `change`；位置 =
  `measure_start + cursor + <offset>/divisions`，其中 `<offset>` **必须应用**。故
  `reference_pedals.csv` 行数 ≠ 原始 mark 数。
- **I4 两套容差不得混用**：③ 的判定容差 `PEDAL_MATCH_QL = 0.25`（取最近 reference 条目，距离 ≤0.25 QL
  则采用其类型，否则 `none`）；工作表的「列出」容差 `--tol = 0.5` 只影响展示列，**不是判定容差**。
- **I5 听辨口径**：材料为 `performance_segment.mid`（MIDI 渲染，CC64 生效）；WAV 不进入标注材料集；
  首标与重标对称。
- **I6 隔离**：标注者 A / B 全程隔离，产物分目录，隔离期结束前不互看；不覆盖既有只读档案。

## 2. 工序骨架（每段一遍；S = 段目录）

| 步 | 名称 | 产出 / 验收要点 |
| --- | --- | --- |
| S1 | 窗口扫描与选择 | 段清单 + 每段 performance/score 窗口；写入 selection JSON |
| S2 | 分段构建 | `segments_v1/<sid>/` 十二件产物齐备（`events.csv` / `reference_*.csv` / `pedal_intervals.csv` / `p4_*.musicxml` / `performance_segment.mid` / `segment_metadata.json` / `build_log.json` 等）；`strict` 为主的 mapping_method 记录可查 |
| S3 | reference 重建（coordinate fix） | `reference_score.musicxml` 与 `reference_pedals.csv` 按 score 坐标重算；`segment_metadata.json` 写入 `coordinate_fix` |
| S4 | 客观六列生成 | prefill + annotate 规则值（②=CC64 区间、③=MusicXML 解析＋score 映射、①=数值判据、④⑤⑥=规则） |
| S5 | 双工具审计 | `phase2a_audit_extraction.py` 与 `phase2a_audit_score_pedal.py` 两份 JSON **全绿**；F 组计数与抽样 manifest 的 `n_F` **逐段相等** |
| S6 | 分层抽样 + 渲染 | 每段 worksheet（含 `score m.` 定位列）＋填写版 CSV ＋实现抽查表 manifest ＋渲染谱 PDF/PNG/SVG（MuseScore 3 路线） |
| S7 | 人工抽样复核 | 只判 ③ 列；`ok` / `incorrect`（`incorrect` 必须写实际记号类型与所在小节） |
| S8 | 判定与放行 | 确认率达标 → 结论 A；同类行系统性 `incorrect` → 结论 B（停止扩张、回到坐标/规则排查） |
| S9 | 锚定与留档 | 产物入库同批锚定 CHECKSUMS ＋ `verify_handoff.py` 全绿 |

## 3. 抽样与判定口径

- 分层抽样沿用 2A 参数（5 段实测一致）：`seed=20260907`、`frac=0.30`、`min_per_seg=10`；
  `n_target = max(min_per_seg, int(frac * n_F + 0.5))`（**半进舍入**，非 Python `round`），
  `n_F <= min_per_seg` 时全取（`full_take=true`）。
- 每条 manifest 必含：`n_F / n_target / full_take / seed / frac / min_per_seg / strata_drawn / rows`。
- **硬校验（跨工具闭合）**：manifest 的 `n_F` 必须等于审计工具独立算出的 F 组计数
  （2A 5 段实测 196 / 74 / 375 / 38 / 4，合计 687，逐段相等）。
- 抽样必覆盖：③ ∈ {start, change, stop} 的 F 组全体、`review_priority=high`、`uncertain`、
  跨小节 tie / 换踩边界行。
- **放行口径**：确认率 = `reviewer_confirm=ok` 行数 / 抽样行数 ≥ 95% → 结论 A（该批可用）；
  否则结论 B。禁止用"重标 vs 首标全量一致率"替代本口径。
- **表外确认项不进 verdicts 文件**（`phase2a_fill_review.py` 会以 `row_no not in this sheet` 拒绝）：
  无 score 侧 onset 的行、带 `<offset>` 的记号对，单独留档复核。

## 4. 结构性事实：无 score 侧 onset 的行

- 2A 5 段实测：全量 `events.csv` 中 **1884 / 4569 ≈ 41%** 的行无 score 侧 onset，且跨段极不均
  （S145/2 588/1555、op32/10 862/1168、Miroirs 278/798、Ballades 111/770、Barcarolle 45/278）；
  这些行的最近距离 >1.0 QL 者占 75%，即其在输入对齐里本就不存在。
- 这类行第 3 列按构造只能是 `none`，且**两份审计工具都不检查它们**。
- 因此全量阶段必须**单列「该行有无 score 侧坐标」**，并把"无坐标"行单独统计、单独口径，
  **不得混入 F 组确认率**。

## 5. 待锁定决策项

- **D1 全量段清单**：以 `MANIFEST.md`（120 演奏 / 31 作品）与 `outputs/pedal_expansion/selection_phase2A.json`
  为候选源，锁定"全数据集"具体包含哪些段、去重后段数、与已完成 13 段（Trial-8 8 ＋ 2A 5）的交集。
  **未锁定前不批量建段。**
- **D2 重建范围**：全量段是否一律走 `rebuild_segment_reference.py` 重算 ③；
  `scan_segment_coordinate_mismatch.py` 的输出作为受影响清单。
- **D3 抽样比例**：是否沿用 `frac=0.30`，或对受影响段提高、对零改动段降低。
- **D4 人工规模**：保持"抽样复核"而不回到全量人工听判（方法学依据见
  `docs/trial8_annotator_A_prompt.md` §1.3）。
- **D5 锚定范围**：本次只锚 Phase-2A 链；全仓 `6977` 个文件中仍有 `2750` 个未锚
  （`evals` 1901、`outputs` 765、`results` 64、`frontend` 12、`data` 6、`audio2score` 2 等），
  是否在放行前补齐。

## 6. 提交与留档节奏

- 每段/每批：**产物 commit 与 CHECKSUMS 锚定同批**；已锚文件被改动后，用
  `python fixchecksumsline_endings.py` 原地刷新，再跑 `python tools/verify_handoff.py` 直至全绿。
- commit message 前缀沿用 `feat(phase2A):` / `fix(phase2A):` / `docs(phase2A):` / `chore(checksums):`；
  全量阶段前缀待 D1 定名。
- 每段必须留存的证据：`build_log.json`、`segment_metadata.json`（含 `coordinate_fix`）、两份审计 JSON、
  抽样 manifest；若做人工抽样，另存 worksheet / 填写表 / 判定文件与判定报告。

## 7. 已可引用的证据（不重算）

- 2A 双工具全绿：`outputs/pedal_expansion/review/phase2a_extraction_audit.json`、
  `outputs/pedal_expansion/evaluation/phase2a_score_pedal_audit.json`。
- 5 段窗口内 `reference_pedals` 行数与独立复算逐段相等（78 / 39 / 156 / 25 / 7）。
- 重跑后 5 段 `published_score_pedal_changed = 0`；mapping_method 均为 `strict`。

## 8. 版本记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-10-03 | v0.1 | 建档（主控）：不变式 I1-I6、工序骨架 S1-S9、抽样与判定口径、结构性事实（无 score 侧 onset 行）、决策项 D1-D5、留档节奏。命令以各 exec 文档为准，不在本方案内复制。 |
