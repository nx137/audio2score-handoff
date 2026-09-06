# rebuild_segment_reference.py 坐标 bug 修复规格（P0 · 裁决 #6 定稿版）

- 日期：2026-09-06 | 状态：单段三锚验证已通过（裁决 #6），待 40 段全量重跑
- 主控裁决依据：trial8_A_reviewer_exec.md 裁决 #4（原始诊断）、#5（根因修正）、
  #6（Liszt_9_67 定性 + 放行全量；以最新为准）

## 1. 根因

### 1.1 已排除：裁决 #4 的「均匀 bar_ql 外推」诊断与代码实际不符

`score_measure_starts`（逐 measure 元素累加 bar_ql，含 X1/X2/X3 等全部元素）与
`pedal_events`（位置 = measure 起点 + 音符游标 + direction offset）**已是真实累计**。
142.01875 按真实累计表反查属 m.59（m.59 起点 = 142.0），此前归 m.72 是反查口径错误。

### 1.2 真正根因：pedal 过滤用了音符对齐窗口边界，而非 measure 边界

`map_score_window` 返回的 score_start_ql / score_end_ql 对齐到窗口内最早/最晚参考音符；
`measure_index_range` 已将其换算为 measure 元素范围 first/last（0 起算索引），
但 pedal 过滤仍直接使用音符对齐 QL 边界 → measure 开头/结尾的 pedal 被排除。

受影响段（同因）：Ravel（m.72 的 3 个 pedal 176.0/176.05/179.99375 全被 [176.875,179.16) 排除）、
Liszt_9_67（number 15 的 stop@106.0 被 [106.967,113.677) 排除）等。

## 2. 修复要求（裁决 #5 定，本地 AI 采用实现 B，单段已验证）

reference_pedals 过滤区间按 **measure 粒度**：

- 过滤区间 = `[starts[first], starts[last+1])`（last+1 越界则取 +inf）
  - starts = 全曲真实累计 measure 起点表（`score_measure_starts`，含全部 measure 元素）
  - first/last = `measure_index_range` 输出的 0 起算 measure 元素索引
- **禁止**用音符对齐 score_start_ql / score_end_ql 直接过滤 pedal

## 3. 实施与验证

### 3.1 单段单元验证（已完成 · 裁决 #6 认可 · 全部通过）

- **Ravel**：窗口 = 元素序 72（= number 72，无 X 偏移），measure 区间 [176.0, 180.0)
  → reference_pedals = **3 条**（start@176.0、stop@176.05、stop@179.99375）✅
- **Chopin**：窗口 = 序 595–608 → reference_pedals = **3 条**（1797/1800/1806 锚不变，±0）回归 ✅
- **Liszt_9_67**：窗口 = 元素序 18–19（1 起算）= **number 15–16**（全曲含 X1–X3 三个补充
  小节，序数与 number 偏移 3），measure 区间 [102.0, 114.0)；number 15 含
  `<pedal type="stop"/>`（direction 音符游标定位 = 106.0）→ reference_pedals = **1 条
  （stop@106.0）** ✅
  - 裁决 #3 的「窗口外/待查」与裁决 #5、旧规格 §3 的「保持空」预期**作废**
    （基于音符对齐边界的误判）。

### 3.2 待办：40 段全量重跑 + 上报

1. 全 40 段重跑 rebuild → 汇总表：每段 reference_pedals 行数 vs 窗口 measure 范围内
   全曲 `<pedal>` 数（应相等；区分「窗口内真无 pedal」与「有 pedal 未入库」）
2. Chopin 补查：m.599 / m.602 谱面 pedal 的 pedal_events 位置与解析情况，说明为何修复后
   仍 3 条（规范化合并 / 窗口外 / 未解析），确认非修复遗漏
3. events.csv ③ 列重算 → 重新统计 8 段 F 行（与裁决 #2/#3 前对照，报告变化）
4. 重新生成 trial8 F/U/H/E 复核清单 → 上报新分布（清单入库等主控指示）
5. verify_handoff：若产物在 CHECKSUMS.sha256 注册，改动后须同步并保持全匹配

## 4. 独立问题（不阻塞本修复，另案处理）

### 4.1 Liszt_9_67 alignment 0/85

events.csv `reference_onset_ql` 0/85 全空：rebuild **只读不写**该列
（`recompute_score_pedal_column` 仅改 published_score_pedal）；原始 build 对该段未写入
（candidate_stats unmatched 256/261）。后续专项：补写 reference_onset_ql / 修复匹配。

### 4.2 Liszt_9_67 ③ 全 none 的双重成因

(a) reference_pedals 曾被窗口边界误滤为空 —— 本修复解决（将 = 1 条）；
(b) events 无 reference_onset_ql → ③ 重算仍全 none —— 需 4.1 解决后才正确。
上报时须注明 (b)，避免将修复误判为无效。

## 5. 红线

- 修复先在分支 codex/coord-fix-rebuild；diff 与验证报告交主控审阅后再决定入库
- 不触碰 evals/（冻结证据）与冻结模型；不伪造哈希
- 任何与上述预期不符（Chopin 回归破坏、Ravel 非 3 条、Liszt 非 1 条）→ 停下报告
