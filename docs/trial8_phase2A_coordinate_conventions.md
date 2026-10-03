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
报告落在 `outputs/pedal_expansion/evaluation/`，随 Phase 2A 标注前快照入库（见 `docs/trial8_phase2A_snapshot_exec.md`）。
实测（2026-10-02，五个 Phase 2A 段）：本轮它覆盖的是**全部 783 行复核表**（F 组 687 行），结果是
`mismatch=0 / no_mark_at_all=0 / spurious_none=0 / outside_window=0 / f_group_split=0`，五个段的 slice 小节号与声明窗口逐一相等；
687 行 F 中 542 行的记号**正好落在 onset 上**、145 行落在 0.25 QL 容差内（不在 onset 正上）；另有 6 行
`reference_onset_ql` 为空（Ballades 1、S145/2 1、op32/10 3、Miroirs/4 1），第 3 列按构造只能是 `none`，无法自动复核，
已列入人工读谱核查。

`tools/phase2a_audit_extraction.py`：同样从原始 ASAP 全谱零共享复算，但以**抽样后的 209 行**为对账对象——按 `row_no`
连接 `events.csv` 的 `reference_onset_ql`、定位小节、在窗口记号里取最近条目，与记录的 `published_score_pedal` 逐行比较；
同时核对 `reference_pedals.csv` 与全谱记号的位置一致性。窗口成员规则见 §7。

## 7. 窗口成员规则（`reference_pedals.csv` 的边界口径）

`reference_pedals.csv` 只含**自身小节落在窗口内**（序数 `score_start_measure-1 .. score_end_measure-1`）的 pedal 记号，
不是"QL 闭区间"。差别只在窗口右边界：窗口之后那一小节的**首拍**记号，其 QL 位置与窗口右边界完全相同（小节内偏移 0），
按闭区间会被算进来，但它属于**相邻段**。

实测（五个 Phase 2A 段，2026-10-02 对 ASAP 全谱复算）：

| 段 | 窗口内记号 | `reference_pedals.csv` 行数 | 被排除的右边界记号 |
| --- | --- | --- | --- |
| `Chopin_Ballades_3_55` | 78 | 78 | LH `stop` @294.0（下一小节原生 m.99 首拍） |
| `Chopin_Barcarolle_1` | 39 | 39 | LH `start` @66.0（原生 m.12 首拍） |
| `Liszt_Concert_Etude_S145_2_1` | 156 | 156 | 无 |
| `Rachmaninoff_Preludes_op_32_10_24` | 25 | 25 | LH `change` @128.0（原生 m.32 首拍） |
| `Ravel_Miroirs_4_Alborada_del_gracioso_25` | 7 | 7 | LH `stop` @246.0（原生 m.79 首拍） |

`tools/phase2a_audit_extraction.py` 早期版本按闭区间统计，于是打印 79/78、40/39、26/25、8/7（S145/2 为 156/156），
看起来像"提取丢了一条记号"。修正后（提交 `cbd7a19`）：窗口成员按小节归属判定，边界记号单独列为 `edge mark`，
并额外核对 `reference_pedals.csv` 中是否存在落在右边界上的行（五个段均为 0）。第 3 列判定不受影响：
第 3 列按 `PEDAL_MATCH_QL = 0.25` 取最近条目，边界记号属于相邻段，本就不在窗口内。

E 阶段推论：**任何窗口/切片统计都必须按小节归属判定，不得用 QL 闭区间**；否则每个窗口都可能多算至多 1 条来自相邻窗口的记号。

## 8. score 侧 onset 的覆盖（第 3 列能问到谱面的行占多少）

`events.csv` 的 `reference_onset_ql` 是**对齐产生的 score 侧 onset**。没有它，第 3 列按构造只能是 `none`，
两份独立审计工具都会跳过该行。实测（2026-10-02，五个 Phase 2A 段，`tools/phase2a_list_unlocated_rows.py`）：

| 段 | `events.csv` 行数 | 无 score 侧 onset（全量） | 其中落在复核表内 |
| --- | --- | --- | --- |
| `Chopin_Ballades_3_55` | 770 | 111 | 1（row_no 669） |
| `Chopin_Barcarolle_1` | 278 | 45 | 0 |
| `Liszt_Concert_Etude_S145_2_1` | 1555 | 588 | 1（row_no 1142） |
| `Rachmaninoff_Preludes_op_32_10_24` | 1168 | 862 | 3（row_no 37 / 962 / 1054） |
| `Ravel_Miroirs_4_Alborada_del_gracioso_25` | 798 | 278 | 1（row_no 798） |
| 合计 | 4569 | 1884 | 6 |

- **复核表只是 `events.csv` 的子集**（783 / 4569）。任何"多少行如何如何"的数字都必须先说清是哪个口径；
  与两份审计工具可比的是**复核表口径**（本表最后一列）。
- 复核表内只有这 6 行没有 score 侧 onset，与 `tools/phase2a_audit_score_pedal.py` 的
  `no_reference_onset_ql` 示例逐段一致（1 / 0 / 1 / 3 / 1）——两条独立路径互相印证。
- **E 阶段的含义**：全量重标时，没有 score 侧 onset 的行第 3 列只能是 `none`，此类行在 `events.csv` 里占
  1884 / 4569 ≈ 41%；"读谱复核第 3 列"这条验证路径对它们**不适用**。成因（窗口外 / 对齐未覆盖 / 其他）
  尚未定论，**D 阶段设计判定口径前必须先查清**，否则会把"无可问"误当成"判错"。

## 9. 开放项（E 阶段前必须关闭）

以下两项**不在** 209 行抽样的覆盖内，也**不被**任何自动审计作为判定对象，故显式登记，不得默认已关闭。

- **O1｜Miroirs/4 那一对带 `<offset>` 位移的 pedal 记号**（已核实到小节级）：切片
  `reference_score.musicxml`（小节号 35..78）里，`<pedal>` 元素实际落在 **m.58 / m.62 / m.70 / m.75 / m.78**
  五个小节共 8 枚；其中 **m.70 内有 4 枚** —— cursor 0.0 `start`、cursor 1.5 `stop`、
  cursor 2.5 `start`（`<offset> = -512`，divisions = 1024/四分音符 ⇒ −0.5 QL，绝对 221.0）、
  cursor 3.0 `stop`（`<offset> = +512` ⇒ +0.5 QL，绝对 222.5，落在 m.70 / m.71 小节线之后 0.5 QL）。
  关闭方式：人工读渲染谱第 36–37 小节（从切片首小节数起）确认记号位置，并确认提取层是按 `<offset>`
  位移定位、而非只用 `measure_start + cursor`。
- **O2｜全量 `events.csv` 中 1884 / 4569 行（41%）`reference_onset_ql` 为空**：复核表 783 行中仅 6 行属该类
  （1/0/1/3/1，均 `in_review_sheet = yes`、`in_sample = no`）；这 6 行第 3 列按构造只能是 `none`，
  因此任何以第 3 列为对象的自动核对在这 6 行上都不构成判定。关闭方式：D 阶段定判定口径前，用
  `events.csv` 的 `onset_ql` 与 S2 对齐文件的 performance onset 集合求交，给出成因分类
  （窗口外 / 对齐未覆盖 / 其他）及是否影响判定的结论。

## 10. 已知缺陷：`reference_pedals.csv` 的 `position_location` 小节号

**结论**：该列的小节号按**均匀网格**计算（`floor(position_ql / score_bar_ql) + 1`）。当曲目小节长度不统一
（变拍号）时，它与谱面文件自身的小节编号不一致。**QL 数值本身正确**，不受影响。

**核实方式**（2026-10-02，主控直读已入库的 5 份 `reference_score.musicxml`，不依赖任何重算）：
对每段列出"谱面文件里物理含有 `<pedal>` 元素的小节号"，与该列的 `m.<n>` 比对。

| 段 | 谱面文件中有 `<pedal>` 的小节（真值） | 该列 `m.<n>` 落在真值之外的量 | 判定 |
|----|------------------------------------|---------------------------|------|
| Ballades/3 | 52, 53, …, 98（40 个小节） | 0 / 78 | 一致 |
| Barcarolle | 1 … 11 | 0 / 39 | 一致 |
| op.32/10 | 18 … 31 | 25 / 25 整体 +1 | **非缺陷**：该谱首小节编号为 `0`，`m.<n>` 是序数而文件号 = 序数 − 1（见 §3） |
| S145/2 | 3–26, 29–33, 39–68, 72–76, 80–81 | 19 / 156 | **同一现象的疑似例**（其中含连续 5 小节整段，不能由跨小节线位移解释）；待 E 阶段逐行定案 |
| Miroirs/4 | **58, 62, 70, 75, 78** | 7 / 7（全部偏 +4/+5） | **确认缺陷** |

Miroirs/4 逐行对照（`position_ql` → 真值小节 / 该列写的）：183.0 → 58 / 62；195.5 → 62 / 66；
219.0、220.5、221.0 → 70 / 74；222.5 → 70（跨线）/ 75；234.0 → 75 / 79。

**影响面**：
- 全部工具以 QL 为主键，**不受影响**；两份自动审计与本次快照核验的一致性结论也不受影响
  （它们与本节用的是同一套网格口径）。
- 标注者用的工作表是**另一套、正确的**谱面小节号：`annotatorA_worksheet_score_*.txt` 的 `score m.<n>` 列
  已对 209 行抽样逐行与谱面文件自身的 `<pedal>` 内容核对（206 行吻合、3 行为合法 `(none)`、0 处不一致），
  故**标注材料不受本缺陷影响**。
- 受影响的只有"人读该列时的定位"，以及任何直接引用该列文本的下游产物。

**处置**：该列的生成代码应在 E 阶段（全量重标）前改为按谱面文件自身的小节编号（或按逐小节累加的
非均匀网格）输出；**已入库的 5 段产物不为修此列而重跑**——重跑会连带刷新 `reference_events.csv`
等文件、使两份审计报告与本次快照失效，代价大于收益（如要重跑，须由用户明确指示）。
