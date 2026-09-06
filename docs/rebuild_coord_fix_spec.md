# rebuild_segment_reference.py 坐标 bug 修复规格（P0 · 裁决 #5 修正版）

- 日期：2026-09-06 | 状态：根因已按裁决 #5 修正，待本地 AI 实施
- 主控裁决依据：trial8_A_reviewer_exec.md 裁决 #4（原始诊断）与裁决 #5（根因修正，以 #5 为准）

## 1. 根因

### 1.1 已排除：裁决 #4 的「均匀 bar_ql 外推」诊断与代码实际不符

本地 AI 实施前单段验证（Ravel Une Barque，分支 codex/coord-fix-rebuild，未改码）实测：

| 项 | #4 预期（应修复） | 代码实际 | 结论 |
|---|---|---|---|
| score_measure_starts m.72 起点 | = 142（均匀外推 (72-1)x2） | **= 176.0** | 已是真实拍号累计 |
| pedal_events m.72 pedal | position_ql = 142.01875（错） | **176.0 (start) / 176.05 (stop)** | 已是正确坐标 |
| measure → QL 推导 | 均匀外推 | 逐 measure 读 `<time>` 累加 | 无此 bug |

- 142.01875 的归属：按真实累计表反查，142.01875 属 **m.59**（m.59 起点 = 142.0），不是 m.72。
  此前把 142.01875 记为 m.72 属**反查口径错误**（int(position_ql//2)+1 的均匀反查对混合拍号段无效）。
- 结论：rebuild 侧 pedal_events / score_measure_starts **不需要**「改成真实累计」——它们已是。

### 1.2 真正根因：reference_pedals 的 pedal 过滤用了音符对齐窗口边界，而非 measure 边界

reference_pedals 为空的直接原因 = 过滤式用了 `map_score_window` 的音符对齐 QL 边界：

- score_start_ql = **176.875**（m.72 内第 0.875 QL 处才出现第一个参考音符，非小节起点）
- score_end_ql = **179.16**（最晚参考音符附近，非小节终点）
- 过滤式 `score_start_ql <= p.position_ql < score_end_ql` 逐条排除 m.72 的 **3 个 pedal**：
  - start @ 176.0 → < 176.875（窗口左侧）→ 排除
  - stop @ 176.05 → < 176.875（窗口左侧）→ 排除
  - stop @ 179.99375 → >= 179.16（窗口右侧）→ 排除
- 结果：reference_pedals 空（「窗口 measure 范围内有 pedal 但被边界误滤」）。

窗口的 measure 范围标注 [score_start_measure, score_end_measure] = [72, 72] 是**正确**的；
问题只在 pedal 过滤时未把窗口换算成 measure 边界。

## 2. 修复要求（裁决 #5）

reference_pedals 及一切「score 片段窗口内 pedal 提取」的过滤区间，一律按 **measure 粒度**：

- 锚 = 窗口 measure 范围 [score_start_measure, score_end_measure]（已有且正确，不改）
- 过滤区间 = [MeasureStart(score_start_measure), MeasureStart(score_end_measure + 1))
  - MeasureStart(N)：m.1 起点 = 0；逐 measure 读 `<attributes><time><beats>/<beat-type>`
    （无则继承前一拍号），起点累加 `beats * 4 / beat-type`（QL 单位 = 四分音符）
- 实现（择一，依代码结构定，须过 §3 验证）：
  - A. 过滤前把窗口 QL 边界 floor/ceil 到所属 measure 边界；
  - B. 按窗口 measure 范围 + 真实累计表直接重算过滤区间，不再用 score_start_ql/score_end_ql 过滤 pedal。
- **禁止**再用音符对齐的 score_start_ql / score_end_ql 直接过滤 pedal（现行 bug 的根源）。
- Ravel 校验算例：m.72 = 4/4，真实区间 [176.0, 180.0)；修复后 reference_pedals 应 = 3 条：
  start@176.0、stop@176.05、stop@179.99375（179.99375 属 m.72，在 m.73 起点 180.0 之前，应入库）。

## 3. 实施与验证（本地 AI）

1. 改 `tools/rebuild_segment_reference.py`（reference_pedals / map_score_window 的 pedal 过滤逻辑；
   分支 codex/coord-fix-rebuild；diff 与验证报告交主控审阅后再入库）
2. **单段单元验证（通过才继续）**：
   - Ravel：reference_pedals 非空且 = 3 条（176.0 / 176.05 / 179.99375），与 pedal_events、
     谱面 `<pedal>` 一一对应；
   - Liszt_9_67：窗口 measure 范围 m.18–19 → measure 粒度区间内确无 pedal → reference_pedals
     应保持空（③=none 正确性复验）；另查 0/85 行无 reference_onset_ql（rebuild 是否写该列）；
   - Chopin（回归）：reference_pedals = 窗口 measure 范围内全量 pedal——1797 / 1800 / 1806
     锚不变（±1 QL）；若 m.599 / m.602 的 pedal 亦在窗口内则补全为 5 条并上报
     （③ 非 none 行数相应变化，需重判）
3. 全 40 段重跑 rebuild → 汇总表：每段 reference_pedals 行数 vs 窗口 measure 范围内全曲
   `<pedal>` 数（按 §2 口径应相等；区分「窗口内真无 pedal」与「有 pedal 未入库」）
4. events.csv ③ 列重算 → 重新统计 8 段 F 行（与裁决 #2/#3 前对照，报告变化）
5. 重新生成 trial8 F/U/H/E 复核清单 → 上报新分布
6. verify_handoff：若产物在 CHECKSUMS.sha256 注册，改动后须同步并保持全匹配

## 4. 红线

- 先本地分支修复 + 验证，diff 与验证报告交主控审阅后再决定入库
- 不触碰 evals/（冻结证据）与冻结模型；不伪造哈希
- 任何与上述预期不符（Chopin 回归破坏、Ravel 仍空、Liszt_9_67 误变非空）→ 停下报告
