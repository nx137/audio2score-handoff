# trial8 标注者 A 复核执行说明（128 行抽样复核，F/U/H/E）

- 生成时间：2026-09-06（北京时间）
- 执行者：**标注者 A = 本地 AI**（受控角色，防自证偏差约束见 §6）
- 监督：主控（nx137）抽验 ≥10% 的 F 行并终审
- 任务：对 8 份复核清单共 **128 行**逐行复核，输出判定与证据，**不自行做阶段判定**
- 协议依据：`docs/trial8_annotator_A_prompt.md`（v1.3）；清单 = `docs/trial8_v13_review_exec.md` 的产物

## 0. 输入与输出

- 输入清单（已入库或本地）：`outputs/pedal_gold_standard/formal_20260828_v1/iaa/trial_A/review/trial8_A_review_<sid>.csv`（8 份，128 行）
- 配套材料（同段目录下）：`events.csv`（30 列）、`reference_score.musicxml`（谱面，含 `<pedal>` 标记）、
  `pedal_intervals.csv`（CC64 演奏踏板区间）、`reference_pedals.csv`、`review_guide.md`
- 输出（**新增**，不修改清单）：`.../iaa/trial_A/review/trial8_A_result_<sid>.csv`（8 份）+ 汇总上报

## 1. 清单构成与分组

| 组 | 行数 | 含义 | 复核动作 |
|---|---|---|---|
| F | 84（Ravel 34 / Chopin 50） | ③ published_score_pedal 被坐标修复改动 | 对照谱面 `<pedal>` 验证修复后 ③ 正确（**本轮核心**） |
| U | 34 | ① 或 ② = uncertain | 数值/CC64 重判，尽量定值 |
| H | 6 | review_priority = high | ④⑤⑥ 完整性复核 |
| E | 4 | reference_tie_start=1 或 tie/换踩 | 边界行 ③ 与 tie 结构协调性 |

四组零重叠 → 每行只有一个复核动作，无歧义。

## 2. 坐标体系（必读）与关键锚点

**两套坐标，不可混用**：

- `onset_ql` / `onset_location` = **performance 坐标**（演奏 MIDI 的小节号，如 Chopin m.254–257）
- `reference_onset_ql` = **score 坐标**（谱面小节编号体系，如 Chopin m.595–608）
- **③ `published_score_pedal` 是 score 侧值，与谱面 `<pedal>` 比对必须用 `reference_onset_ql`**，
  禁止用 `onset_location` 直接比谱面小节号（两者编号体系不同，Chopin 实测差 ~340 小节）。

score 坐标换算（按谱面拍号；QL 单位 = 四分音符）：
- Chopin（3/4 拍）：每小节 3 QL → `reference_onset_ql / 3` = score measure
- 其他段：按该段谱面拍号结构换算；拿不准就用仓库内 score 解析工具定位 `<pedal>` 的 score QL 区间

谱面 `<pedal>` 标记实测（reference_score.musicxml）：

- Bach_Prelude_bwv_846_2：**0**（谱面无踏板 → F=0，自洽）
- Ravel_Miroirs_3_Une_Barque_181：**2**，均在 **measure 72**（start + stop）；该谱面片段仅含 m.72 一个小节
- Chopin_Scherzos_20_254：**5**，在 measure **599**(stop)、**600**(start+stop)、**601**(start)、**602**(stop)

**Chopin 实证（修复正确的判定锚）**：`reference_pedals.csv`（score 侧谱面踏板事件表）含 3 条：
`1797.0 -> m.600 change`、`1800.0 -> m.601 change`、`1806.0 -> m.603 stop`。
修复后 ③ 非 none 行（F 组 7 行 + 非 F 行）的 `reference_onset_ql` 恰为 1797 / 1800 / 1806，
与 reference_pedals **逐条对应**。

**③ 的判读锚 = `reference_pedals.csv`**（其 event_type 原样决定 ③；`reference_score.musicxml` 的
`<pedal>` 仅作交叉参考，不作直接判据）。

score measure 换算注意：measure N 的起点 QL = (N-1) x bar_ql，即 `reference_onset_ql / bar_ql + 1`
才是 measure 编号（如 1800/3+1 = m.601，不是 m.600）。

**第一层自检（执行前必做）**：
1. 统计 84 个 F 行修复后 ③ 的分布（none / start / change / stop / uncertain）；
2. 对每个非 none 行，换算 `reference_onset_ql` → score measure，与谱面 `<pedal>` measure 比对：
   命中 → 正确；不命中（悬空）→ **停下报告该行**；
3. 同时检查谱面 `<pedal>` 标记是否有"无任何事件承接"的（谱面有 pedal 但 score 坐标窗口内无事件）→ 报告。
4. **专项核查（Ravel）**：Ravel 谱面片段仅含 m.72（1 小节、2 个 pedal），但 events 139 行 ③ 全 = none。
   复核前必须先查清：m.72 的两个 `<pedal>` 在 score 坐标（reference_onset_ql）的确切位置，
   其时刻附近是否有事件承接、这些事件 ③ 应为何值。若 m.72 pedal 悬空（无事件承接）→ 属
   segment score 窗口/坐标修复遗留问题，**停下专项报告，不进入逐行复核**。

## 3. F 组复核（84 行）——本轮核心

判据：`published_score_pedal` = 该事件时刻**出版谱**上的踏板动作状态：
`start`（此处开始踩）/ `change`（同一踩踏内谱面换踩，如 `*`）/ `stop`（此处松开）/ `none`（无动作）。

对每个 F 行（行内含 event_id、onset_location、reference_onset_ql、修复后 ③ 现值、baseline 旧 ③）：

1. 解析 `reference_score.musicxml`，列出全部 `<pedal>` 标记及其 score measure，换算为 score QL 位置；
2. 用该行的 **`reference_onset_ql`（score 坐标）** 与 pedal 的 score QL 位置比对：
   - 不命中任何 pedal 动作 QL → 修复后 ③ 应为 **none**；
   - 命中 `<pedal type="start|stop">` 的 score QL → ③ 应 = start / stop；
   - `change` 依协议判据（同一区间内谱面换踩记号）；
3. 判定：
   - `confirmed`：修复后 ③ 与 score 坐标判读一致；
   - `revised`：不一致 → 给出建议新值 + **可复核证据**（score measure/`<pedal type=...>` 原文）；
4. `evidence` 列必须写 score 坐标依据（换算后 measure + `<pedal type=...>` 原文），
   不许写"与 events.csv 一致"或引用 performance 小节号作判据。

## 4. U 组复核（34 行）

- ① acoustic_sustain = uncertain 的行：重算数值判据
  `acoustic_duration_ql − key_duration_ql`（阈值 0.25 QL，且是否覆盖后续同手 onset）→
  可定 yes/no 则 revised 定值，真歧义才保留 uncertain 并说明；
- ② performance_pedal_action = uncertain 的行：查 `pedal_intervals.csv`（CC64 区间）与事件 onset 的包含关系，
  按协议规则映射定值（v1.3 后 ② 本应 0 人工，出现 uncertain 需给出解释，如区间边界歧义）。

## 5. H 组（6 行）与 E 组（4 行）

- H：复核 ④ notation_decision（是否与 ③/① 联动一致）、⑤ review_class、⑥ review_note 的恰当性；
  有问题 → revised 并说明；无问题 → confirmed。
- E：tie 边界行（reference_tie_start=1 或 note 含 tie/换踩）——核对 ③ 在该处的取值与 tie/换踩结构协调性。

## 6. 防自证偏差约束（本地 AI 扮演 A 时强制）

1. F 行判据**只允许来自谱面解析**（§3.1–3.2），禁止以"events.csv 现值/旧值"作为判据；
2. 每个 revised 必须带谱面坐标证据；每个 confirmed 的 evidence 也应尽量带坐标；
3. **禁止批量同判**：不许"因为修复脚本说对就对"；逐行独立判读；
4. 输出后自检一遍：确认表中 confirmed 的 F 行，其修复后 ③ 与谱面 pedal 标记坐标是否真的一致。

## 7. 输出 schema（trial8_A_result_<sid>.csv，UTF-8）

```
segment_id,event_id,group,decision,revised_col,revised_value,evidence,note
```

- `group`：F / U / H / E（该行所属组）
- `decision`：confirmed / revised
- `revised_col`、`revised_value`：仅 revised 行填（如 `published_score_pedal`, `none`；`acoustic_sustain`, `yes`）
- `evidence`：谱面坐标 / `<pedal type=...>` 原文 / CC64 区间号
- `note`：补充说明（可空）

## 8. 汇总上报（打印即可）

1. 每段：清单行数 → confirmed / revised 计数
2. **F 组确认率 = F-confirmed / 84**（全局口径）
3. 系统性修订分析：按 evidence 模式聚类 revised 行，报告是否存在"同模式反复出现"（如同一小节区域全部被 revised）
4. 84 个 F 行修复后 ③ 的分布表（§2 自检结果复述）
5. 完成后报告 8 个 result 文件路径，等待下一步指示

**注意**：判定（F 确认率 ≥95% 且无系统性修订 → 32 段重做 ③ vs 全量重标）由主控在 D 阶段做出，
A **不自行判定、不自行入库**。

## 红线

1. 只允许在 `.../iaa/trial_A/review/` 下**新增** `trial8_A_result_*.csv`；不修改清单、events.csv 或任何现有文件。
2. 不 commit、不 push（先上报）。
3. 不触碰 evals/、CHECKSUMS.sha256、*.musicxml / *.mid / reference_* / pedal_intervals.csv。
4. 任何与预期不符（§2 分布异常、谱面解析失败、列缺失）→ 停下报告原始输出。

## 裁决记录（续）

### 2026-09-06 主控裁决 #2：Ravel reference_pedals 空 = 真 bug；F 组判定剔除 Ravel；③ 锚 = reference_pedals
- 取证（云端 + 本地 AI 专项）：
  - Ravel 谱面片段仅 m.72 一节，含 2 个 `<pedal>`（start + stop）；`reference_pedals.csv` **为空**
    （仅表头 46B）。对照：Bach 谱面真无 pedal 时同样为空，Chopin 谱面 5 个 `<pedal>` 生成 3 条
    reference_pedals —— Ravel 属「谱面有 pedal 但解析/入库丢失」。
  - Ravel events 139 行 ③ 全 = none；仅 27/139 行有 reference_onset_ql（落在 score m.72 窗口），
    112 行无 score 坐标；score 窗口仅 m.72 一节（score_start_measure = score_end_measure = 72）。
- 裁决：
  1. Ravel 的谱面 pedal 解析 / score 窗口构建存在缺陷（坐标修复 `2e1ba411` 的遗留问题）。
  2. **Ravel F 组 34 行不可用于 trial8 F 组判定**——其「全 none」是 pedal 输入缺失所致，不是谱面确认。
  3. ③ 判读锚 = `reference_pedals.csv`（event_type 原样），MusicXML `<pedal>` 仅交叉参考。
  4. Chopin 50 行按 reference_pedals 对齐继续复核（非 none 行应逐条命中 1797/1800/1806）。
  5. 新增全局取证：扫描 40 段 `reference_pedals.csv` 行数 vs 谱面 `<pedal>` 数，找出全部
     「谱面有 pedal 但 reference_pedals 空」的段（区分真无 pedal），上报后再定修复方案。
