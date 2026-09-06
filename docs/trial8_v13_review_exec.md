# trial8 v1.3 复核清单生成 —— 本地 AI 执行指令

- 生成时间：2026-09-06（北京时间）
- 执行者：本地 AI（持有仓库 clone 的环境）
- 任务性质：**一次性执行指令**。产出 = 8 份复核清单 CSV + 自检报告。
  本指令不要求、也不允许修改任何金标准数据。
- 协议依据：`docs/trial8_annotator_A_prompt.md`（v1.3，CHECKSUMS.sha256 登记哈希 `1e27e60cba57ee769be93f2137d40ca939feb3c38e0423c4017bda1b0fc25c46`）

## 0. 对齐远端（目标：与 origin/main 一致）

```bash
cd <仓库根目录>
git status                 # 确认无未提交改动；有未提交改动先处理，不要 reset 丢弃
git fetch origin
git reset --hard origin/main
git rev-parse HEAD         # 应为远端最新（含本指令文档 docs/trial8_v13_review_exec.md 的 commit）
git log --oneline -3
```

## 1. 完整性校验（verify gate，不过则停）

```bash
python tools/verify_handoff.py
```

- 期望：`CHECKSUMS.sha256` 全部 **4041 条有效条目**逐一匹配，无 mismatch。
- 若报 mismatch：先 `git status` 确认工作树干净；检查 `core.autocrlf` / `.gitattributes`
  是否改写行尾（verify 对文本做 universal-newline 归一化，行尾一般不构成差异）。
- **禁止**为通过校验而修改 `CHECKSUMS.sha256` 或任何被校验文件。仍失败 → 停下报告原始输出。

## 2. 通读协议

通读 `docs/trial8_annotator_A_prompt.md`（v1.3），确认六列判据、阈值（retake / BOUNDARY = 0.25 QL）、
路径约定。本指令与协议冲突处以协议为准，并报告差异。

## 3. 数据自检（8 段）

GS = `outputs/pedal_gold_standard/formal_20260828_v1`

| 片段 sid | 期望事件数（数据行数） |
|---|---|
| Bach_Prelude_bwv_846_2 | 36 |
| Haydn_Keyboard_Sonatas_6-1_18 | 144 |
| Beethoven_Piano_Sonatas_16-1_73 | 163 |
| Ravel_Miroirs_3_Une_Barque_181 | 139 |
| Prokofiev_Toccata_197 | 131 |
| Chopin_Scherzos_20_254 | 236 |
| Schubert_Wanderer_fantasie_1189 | 154 |
| Liszt_Transcendental_Etudes_10_71 | 130 |
| **合计** | **1133** |

对每段逐一执行：

1. `$GS/<sid>/events.csv` 存在，数据行数 = 期望事件数（不含表头）。
2. **空值检查仅针对前四列** `acoustic_sustain, performance_pedal_action,
   published_score_pedal, notation_decision`（须无空单元格）；`review_class` / `review_note`
   按协议允许合法留空（见文末「裁决记录」）。前四列若出现空值 → 记录 (row, col) 报告，
   不要自行填值。
3. **baseline 差异门（自检）**：取坐标修复前首标档 `6696617b66` 的同路径 events.csv：

   ```bash
   git show 6696617b66:$GS/<sid>/events.csv > /tmp/baseline_<sid>.csv
   ```

   以 `event_id` 对齐（若无法唯一对齐，回退按 (hand, pitch, onset_ql)），比较
   `published_score_pedal`（③ 列）：
   - **预期**：仅 `Ravel_Miroirs_3_Une_Barque_181`（34 行）与
     `Chopin_Scherzos_20_254`（50 行）有差异；其余 6 段 **0 差异**。
   - 实测不符 → **停下报告**（这是已确认的 B 阶段基准；不符说明基线或工作树有问题，不要继续）。

## 4. 生成四组复核清单

对每段选行（并集去重；行身份 = `event_id`），依据**当前工作树**的 events.csv：

| 组 | 选取规则 |
|---|---|
| F | `published_score_pedal` 与 baseline-1（6696617b66）不同的行 |
| U | `acoustic_sustain` 或 `performance_pedal_action` 为 `uncertain` 的行 |
| H | `review_priority` 为 `high` 的行 |
| E | `reference_tie_start` == 1，或 `review_note` 含 `tie` / `换踩` 的行 |

输出文件：`$GS/iaa/trial_A/review/trial8_A_review_<sid>.csv`
（目录不存在则 `mkdir -p`，即新建 `iaa/trial_A/review/`）。

CSV 列（UTF-8；数值原样保留，不要四舍五入）：

```
segment_id,row_no,event_id,hand,pitch,onset_ql,onset_location,groups,
acoustic_sustain,performance_pedal_action,published_score_pedal,
notation_decision,review_class,review_note,baseline_published_score_pedal,
review_priority,reference_tie_start
```

- `row_no`：events.csv 中的数据行号（表头为 0，第一数据行 = 1）
- `groups`：命中的组以 `|` 连接，如 `F|U`
- `baseline_published_score_pedal`：仅 F 行填 baseline-1 的 ③ 列值，其余行留空

## 5. 上报（打印即可）

- 每段：清单行数 + F / U / H / E 各自计数（并说明重叠，如 F∩H 行数）
- 8 段合计清单行数（预期**显著小于 1133**；参考：F 合计应为 84 = Ravel 34 + Chopin 50）
- 自检结论：baseline 差异门是否通过；六列空值情况（若有）
- 完成后列出 8 个清单文件路径，等待下一步指示（不要自行判定、不要自行入库）

## 红线（违反即视为执行失败）

1. 只允许在 `$GS/iaa/trial_A/review/` 下**新增** CSV；不得修改/删除任何现有文件。
2. **不 commit、不 push** —— 产物先留本地并上报，入库另行决定。
3. 不触碰 `evals/`（冻结证据）、`CHECKSUMS.sha256`、任何 `events.csv` / `*.musicxml` /
   `*.mid` / `reference_*` / `pedal_intervals.csv`。
4. `git show` 等只读命令可用；需要写 git 对象时停止并询问。
5. 任何与预期不符（verify 失败、差异门不符、列缺失或命名不同、行数不符）→
   停下报告原始输出，不要自行发挥或“修正”数据。


## 裁决记录

### 2026-09-06 主控裁决 #1：`review_class` 留空 = 合法（A 方案）
- 背景：本地 AI 自检发现 8 段 events.csv 存在空值，且 100% 集中在 `review_class`（⑤）一列：
  Bach 28 / Haydn 29 / Beethoven 47 / Ravel 32 / Prokofiev 34 / Chopin 3 / Schubert 81 / Liszt 42；
  其余五列（①-④、⑥ review_note）全部完整有值。
- 裁决：按 v1.3 协议，⑤ `review_class` 枚举含"留空"（复核分类标记，仅需特别复核的行赋值，
  常规行为默认留空态），故**留空为合法状态，不视为数据丢失或损坏，不填值、不报错**。
  ⑥ `review_note` 同理允许留空。
- 空值硬约束仅适用于 ①-④（`acoustic_sustain`, `performance_pedal_action`,
  `published_score_pedal`, `notation_decision`）四列，本指令 §3.2 已相应修正。
- 后续执行：继续生成 F/U/H/E 复核清单并上报（本地 AI 报告中的方案 A）。
