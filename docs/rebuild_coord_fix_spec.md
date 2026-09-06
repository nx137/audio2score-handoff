# rebuild_segment_reference.py 坐标 bug 修复规格（P0）

- 日期：2026-09-06 | 状态：待本地 AI 实施 | 主控裁决依据：trial8_A_reviewer_exec.md 裁决 #4

## 1. 根因（已定论）

`tools/rebuild_segment_reference.py` 内从 score measure 推导 QL 位置的多处逻辑使用
**均匀 bar_ql 外推**（假定全曲同拍号：measure N 起点 = (N-1) x bar_ql），而 score 窗口
（map_score_window / alignment）使用**全曲谱面按真实拍号逐小节累计的 QL**。

对混合拍号乐曲两者必然错位。实证（Ravel Une Barque）：
- 全曲 139 小节：2/4 x65、3/4 x46、4/4 x25、1/4 x1、5/4 x2
- m.72 真实起点 = 176.0 QL（累计）；均匀外推 (72-1)x2 = 142
- 窗口 score_start_ql = 176.875（正确，≈176.0）；pedal_events 给 m.72 pedal position_ql = 142.01875（错）
- 过滤 score_start_ql <= p.position_ql < score_end_ql → 142 落不进 [176.875,179.16) → pedal 全丢 → reference_pedals 空

## 2. 修复要求

统一坐标系 = **全曲 xml_score 按真实拍号累计的 measure 起点表**：
- 输入：该段 manifest 的 xml_score（data/ASAP/.../xml_score.musicxml，全曲）
- 算法：m.1 起点 = 0；逐 measure 读 `<attributes><time><beats>/<beat-type>`（无则继承前一拍号），
  起点累加 `beats * 4 / beat-type`（QL 单位 = 四分音符）
- 该表用于：pedal_events 的 pedal position_ql、measure_index_range、fmt_beat 的 measure 编号、
  以及任何 score measure <-> QL 换算
- 不得再用「(measure_index) x bar_ql」形式的均匀外推；bar_ql 只作为该小节的单拍 QL 换算辅助

## 3. 实施与验证（本地 AI）

1. 改 `tools/rebuild_segment_reference.py`（建议先本地分支，diff 提交主控审阅后再入库）
2. **单段单元验证（通过才继续）**：
   - Ravel：pedal_events 应产出 m.72 的 2 个 `<pedal>`，position_ql 落在真实 m.72 区间 [176.0,180.0) 内，
     reference_pedals 非空且与谱面一致（注意：Ravel 窗口仅覆盖 m.72 部分，只有窗口内的 pedal 应入库）
   - Liszt_9_67：按真实拍号累计重新核对 m.15 stop / m.20 start 与窗口关系，修正此前的 0 起算结论
   - Chopin（回归）：修复后应保持原有 3 条（1797/1800/1806）不变或仅边界微调（±1 QL 内），不得破坏
3. 全 40 段重跑 rebuild → 输出汇总表：每段 reference_pedals 行数 vs 窗口内全曲 `<pedal>` 数（应相等）
4. events.csv ③ 列重算 → 重新统计 8 段 F 行（与裁决 #2/#3 前对照，报告变化）
5. 重新生成 trial8 F/U/H/E 复核清单 → 上报新分布
6. verify_handoff：若产物在 CHECKSUMS.sha256 注册，改动后须同步并保持全匹配

## 4. 红线

- 先本地分支修复 + 验证，diff 与验证报告交主控审阅后再决定入库
- 不触碰 evals/（冻结证据）与冻结模型；不伪造哈希
- 任何与上述预期不符（如 Chopin 回归破坏）→ 停下报告
