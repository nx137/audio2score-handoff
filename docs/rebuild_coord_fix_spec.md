# rebuild_segment_reference.py 坐标 bug 修复规格（P0 · 裁决 #7 定稿版）

- 日期：2026-09-06 | 状态：修复完成（代码合入 main、40 段全量验证通过）；入库集 = 2 个 reference_pedals.csv（裁决 #8）
- 主控裁决依据：trial8_A_reviewer_exec.md 裁决 #4（原始诊断）、#5（根因修正）、
  #6（Liszt_9_67 定性 + 放行全量）、#7（Ravel ③=0 正确性 + 批准入库；以最新为准）

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
Liszt_9_67（number 15 的 stop@106.0 被 [106.967,113.677) 排除）。

## 2. 修复（已实施并合入 main）

reference_pedals 过滤区间按 **measure 粒度**：

- 过滤区间 = `[starts[first], starts[last+1])`（last+1 越界则取 +inf）
  - starts = 全曲真实累计 measure 起点表（`score_measure_starts`，含全部 measure 元素）
  - first/last = `measure_index_range` 输出的 0 起算 measure 元素索引
- 已合入：tools/rebuild_segment_reference.py（原 314 行过滤，单行逻辑替换为三行）

## 3. 验证结果（已完成）

### 3.1 单段三锚（裁决 #6，通过）
- Ravel：窗口 = 序 72（number 72），[176.0, 180.0) → **3 条**（start@176.0、stop@176.05、
  stop@179.99375）
- Chopin：窗口 = 序 595–608 → **3 条**（1797/1800/1806 锚不变，±0）
- Liszt_9_67：窗口 = 元素序 18–19（= number 15–16，全曲含 X1–X3 偏移 3），[102.0, 114.0)
  → **1 条**（stop@106.0，number 15 内第 4 QL）

### 3.2 40 段全量（裁决 #7，通过）
- 40/40 rebuilt，无 D 类异常；汇总表「窗口内 pedal 数 == reference_pedals 行数」全 YES
- A 修复受益：Ravel（0→3）、Liszt_9_67（0→1）
- B 不变且 >0：Chopin（3→3，锚 ±0；窗口内 pedal_events 即 3 条，非修复遗漏；
  谱面 5 `<pedal>` 中 2 个未成独立事件属 pedal_events 解析/规范化环节，记为观察项）
- C 前 0 后 0：其余 37 段（窗口 measure 内真无 pedal）

## 4. 已澄清的语义与独立问题

### 4.1 Ravel ③ 全 none = 正确结果（裁决 #7），非坐标错位 bug

③ 判读语义 = **动作命中**（事件 reference_onset_ql 恰好命中 pedal 动作 QL 才标
start/change/stop；判据见 trial8_A_reviewer_exec.md §3）。云端实证：
- Ravel events 27 行有 reference_onset_ql（min 176.875、max 179.160），到 3 条 pedal
  的最短距离全部 ≥ 0.825 QL（0 行 ≤ PEDAL_MATCH_QL=0.25）；
- m.72 谱面 pedal 动作（176.0 start + 176.05 stop 在首个演奏音符前、179.99375 stop 在
  最后音符后）与演奏事件**无时刻交集** → ③ 全 none 正确。
- 早期规格「③ 非 none 由 0 变 >0」预期作废。reference_pedals 修复验证以
  「== 窗口内 pedal 数」为准，独立于 ③ 匹配。
- Ravel 在 trial8 F 组维持「无 ③ 非 none 行可判」：理由更新 = 谱面/演奏客观无交集
  （裁决 #2 剔除结论不变，论据修正）。

### 4.2 Liszt_9_67 alignment 0/85（独立问题，另案）

events.csv `reference_onset_ql` 0/85 全空：rebuild **只读不写**该列
（`recompute_score_pedal_column` 仅改 published_score_pedal）；原始 build 对该段未写入。
后续专项：补写 reference_onset_ql / 修复匹配。修复后 Liszt ③ 仍全 none 属此因，非修复无效。

### 4.3 Chopin 谱面 5 `<pedal>` vs pedal_events 3 条（观察项）

m.599/m.602 的 `<pedal>` 未形成独立窗口事件（相邻 start 合并 / position 归并 / 规范化）。
不影响 F 组判定（锚 1797/1800/1806 精确对齐、50/50 confirmed），留待后续核查。

## 5. 入库（裁决 #8 修正：纯 git，无 CHECKSUMS 同步）

- 核查（裁决 #8 云端核实）：CHECKSUMS.sha256（4046 行）中 formal_20260828_v1 下**仅
  iaa/ 10 个文件**（IAA_ANNOTATION_GUIDE + 8 张 iaa_*.csv + iaa_sample_manifest.csv）；
  40 段 reference_pedals / reference_events / segment_metadata / events / reference_score
  等派生产物**均非 CHECKSUMS 注册文件**（CHECKSUMS 只锁定不可重建资产：ASAP 原始数据
  data 3884 条、evals 33、人工标注 iaa），由 git 版本管理。
- 入库方式 = **纯 git 提交产物本身**；不更新 CHECKSUMS.sha256；不影响 verify。
- 本次入库集 = **2 个文件**：Ravel_Miroirs_3_Une_Barque_181 / Liszt_Transcendental_Etudes_9_67
  的 reference_pedals.csv（语义变更 0→3、0→1）。40 段 metadata 仅 applied_at 时间戳变
  （无语义，不入库）；events（psp_changed 全段=0）/ reference_events / reference_score
  无变更（不入库）。
- 观察项：reference_pedals.csv 的 position_location 列用 fmt_beat 均匀 bar_ql 反查，
  混合拍号段（Ravel）显示 measure 可能不准——position_ql 为判读锚不受影响，留待核对。

## 6. 红线

- 不触碰 evals/（冻结证据）与冻结模型；不伪造哈希
- 任何 verify 失配或哈希清单异常 → 停下报告
