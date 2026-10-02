# Phase 2A 坐标约定记录（score 侧）

适用范围：Phase 2A 各产物里 QL 数字的含义、小节编号以哪一套为准、以及**不得乱序重跑**的操作约束。
证据来源：对 5 个 Phase 2A 段与 `data/ASAP/**/xml_score.musicxml`、`data/alignments/**` 的独立核验（提交 `fb2ed135`）。

## 1. 两个坐标域

- `onset_ql` / `onset_location` / `bar_ql`：**performance 域**（均匀速度，perf bar_ql，如 4.0）。
- `reference_onset_ql` / `reference_pedals.position_ql` / 所有 `score_*` 字段：**score 域**。
  两者数值区间可能重叠，混用会得到"看似合理但错误"的小节定位（worksheet v1/v2 的失效根因）。

## 2. score QL 是"标称网格 QL"，不是物理谱面时间

网格 = 首个 `<part>` 每个小节按 `4*beats/beat-type` 累加，**每小节都记满一个标称小节**；因此比标称值短的首小节（起拍小节）也被记满一整小节。

- `Rachmaninoff/Preludes_op_32/10`：谱面首小节 `number="0"`，实际发声长度为 **1.0 QL**，网格按 4.0 计。
- `data/alignments/Rachmaninoff__Preludes_op_32__10__Floril03.csv` 的 271 个不同 `reference_onset_ql`
  取值，**271/271 与该谱面 XML 的网格起点集完全吻合**；只与物理（实际发声）起点集吻合 266/271。
- 该曲原生第 26 小节起点处的 pedal 记号记录为 `104.0`（网格起点），而非 `101.0`（物理起点）。

推论：对齐 → `reference_pedals` → `events.csv` 第 3 列 → 标注工作表**共用同一基准**，所以小节归属按构造是精确的；
但这些数值**不可与报告物理谱面时间的外部工具直接比较**。E 阶段全量重标时，任何含起拍小节的曲目都适用同一条。

## 3. 小节编号

- `segment_metadata.json` 的 `score_start_measure` / `score_end_measure` 是**1-based 序数**（小节序号，index+1）。
- 谱面文件自身的 `number` 属性才是记谱软件里显示的小节号；仅当文件首小节编号为 1 时二者相等。
- op.32/10 首小节编号为 `0`，故其原生编号 = 序数 − 1（窗口序数 9..32 ≡ 原生 8..31）。
- `annotatorA_worksheet_score_*.txt` 表头打印序数窗口，行内打印原生编号，二者同时可见。

## 4. 同一时刻的多枚 pedal 记号

同一位置的记号归一为：仅 `start` → start；仅 `stop` → stop；同位置 `stop`+`start`（换踩，谱面呈现为
`start; stop; start` 或 `stop; start`）→ change。
少数行正好压在系统边界上（记号落在相邻小节内、距离 ≤ 0.5 QL）：工作表的"该小节记号"栏显示 `(none)`，
同时把邻近记号列在 `nearest reference_pedals` 栏，按 `barline-crossing` 处理，不计错。

## 5. 顺序约束（不得违反）

`tools/build_formal_segments.py` 写出的 reference 产物仍是**修复前**的语义（按 performance 域小节号切片）。
任何重跑 build 之后，**必须紧接着重跑 `tools/rebuild_segment_reference.py`**；否则
`reference_score.musicxml` / `reference_pedals.csv` / `events.csv` 会静默退回错误的坐标域，
Phase 2A 的全部复核材料（工作表、抽样表、报告）随之失效。

## 6. 独立复核工具

`tools/phase2a_audit_score_pedal.py`：用与 prefill/rebuild 零共享的代码路径，从原始 ASAP 谱面重算第 3 列与小节归属，
并与复核表逐行对账（row_no 连接、第 3 列一致性、切片-窗口小节一致性、窗口包含、记号对账、F 组一致性）。
报告为工作产物，不入库。
