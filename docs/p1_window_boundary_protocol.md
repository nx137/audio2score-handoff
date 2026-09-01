# P1 窗口边界协议（Window Boundary Protocol）

> 范围：踏板 F1 评测的窗口边界处理协议（40 片段 / 297 CC64 区间实测）
> 数据来源：tools/analyze_window_boundaries.py（只读分析，2026-08）
> 状态：定稿

---

## 1. 背景

- 金标准 40 片段由完整演奏切片而来，片段窗口为 `[start_ql, end_ql]`。
- CC64 区间可能跨越窗口边界：窗口前已踩下、窗口后仍延音。
- 评测四口径（unclipped / inwindow / visible / clipped）对边界事件处理不同，
  导致同一系统在不同口径下 F1 不同。本文档定义统一协议。

---

## 2. 边界事件实测统计（2026-08）

| 类别 | 数量 | 占比 | 说明 |
|---|---|---|---|
| fully_inside | 239 | 80.5% | start 与 end 均在窗口内 |
| cross_start | 30 | 10.1% | 窗口前踩下，窗口内释放 |
| cross_end | 27 | 9.1% | 窗口内踩下，窗口后释放 |
| cross_both | 1 | 0.3% | 跨全窗（覆盖整个窗口） |
| **合计** | **297** | 100% | = 演奏参考 start/stop 总数 |

→ 边界事件约占 19.5%，但**均匀分散**（Top 片段仅 1~2 个 cross 事件），
无边界主导的片段。

---

## 3. 四口径定义（实现复刻）

### 3.1 参考事件构造（`_ref_events`）

| protocol | starts | stops | 语义 |
|---|---|---|---|
| unclipped | 全部区间的原始 start_ql | 全部区间的原始 end_ql | v1-v3 历史口径 |
| inwindow（默认） | 仅窗口内可见的 start | 仅窗口内可见的 stop | 严格公平：只评窗口内发生的事件 |
| visible | inwindow + 跨窗区间在窗口起点的 start | 仅窗口内释放的 stop | 全片段视角：系统确实渲染了跨窗 start |
| clipped | 全部区间的 clipped_start_ql | 全部区间的 clipped_end_ql | 位置裁剪到窗口，惩罚性最强 |

### 3.2 实测参考/输出计数（40 片段汇总）

| 来源 | starts | stops |
|---|---|---|
| unclipped 参考 | 297 | 297 |
| inwindow 参考 | 266 | 269 |
| visible 参考 | 297 | 269 |
| clipped 参考 | 297 | 297 |
| **p4_rule 输出** | **292** | **292** |

### 3.3 协议敏感性（相对 inwindow 的参考计数增量）

| protocol | start_delta | stop_delta |
|---|---|---|
| unclipped | +31 | +28 |
| visible | +31 | +0 |
| clipped | +31 | +28 |

解释：
- 31 = 30 个 cross_start + 1 个 cross_both（窗口前踩下、系统在窗口内渲染的 start）。
- 28 = 27 个 cross_end + 1 个 cross_both（窗口后释放、系统在窗口末尾渲染的 stop）。
- **inwindow 与 visible 仅 start 侧差 31 个**：visible 承认跨窗 start 为参考（系统确实
  渲染了它），stop 侧两者一致（窗口后释放均不给伪参考）。
- p4_rule 输出 292 介于 inwindow 参考（266/269）与全量参考（297）之间：
  系统渲染了 31 个跨窗 start（≈visible 参考）但受吸附影响有少量偏差。

---

## 4. 协议规则

**R1. 主报告用 `inwindow`**：严格公平——只评窗口内明确发生的事件，跨窗事件既
不惩罚也不奖励；默认口径，论文主数字。

**R2. 补充报告用 `visible`**：全片段视角——跨窗 start 补参考（系统确实渲染了它），
start F1 更接近整曲表现；stop 侧保持严格。论文推荐双口径：`inwindow` + `visible`。

**R3. `clipped` / `unclipped` 仅作敏感性附录**：clipped 惩罚性最强（精确裁剪位置 vs
系统吸附位置），unclipped 为历史口径（含窗口外事件，v1-v3 遗留）。

**R4. 跨窗 start（窗口前踩下）**：系统应渲染窗口起点的 start——`attach_pedals`
将区间吸附到窗口内第一个音符即为此行为；`visible` 口径补对应参考。

**R5. 窗口后释放的 stop**：**不给伪参考**（窗口外不可见），避免系统因吸附位置
被错误惩罚；`clipped` 例外（裁剪到窗口终点，用于敏感性对比）。

**R6. retake 规范化与窗口无关**：`sanitize_pedal_retakes` 在同一小节内合并相邻
stop/start 为 change，不依赖窗口边界。

**R7. 精确评测用 `--pedal-placement exact`**：消除音符吸附误差（start F1
0.408→0.822、stop F1 0.220→0.854 的修复即源于此）；exact 模式与 `visible` 口径
组合可最接近整曲真实踏板表现。

---

## 5. 论文引用建议

1. 主数字：`inwindow` 口径（踏板 F1 容差 0.25 QL）。
2. 稳健性表：四口径 F1 并列（evaluate_gold_standard.py 已输出 protocol_sensitivity）。
3. 边界统计（第 2 节）作为方法学附录：证明边界影响 ~19.5% 区间、均匀分散、
   无片段主导，inwindow 与 visible 仅差跨窗 start。

---

## 6. 复现

```
python tools/analyze_window_boundaries.py
python tools/evaluate_gold_standard.py --pedal-ref inwindow
python tools/evaluate_gold_standard.py --pedal-ref visible
```

数据：outputs/pedal_gold_standard/formal_20260828_v1/evaluation/window_boundary_analysis.json

关联：R7 对应 commit（exact 踏板修复，P1 问题二）；`--pedal-ref` 实现于
tools/evaluate_gold_standard.py `_ref_events`。