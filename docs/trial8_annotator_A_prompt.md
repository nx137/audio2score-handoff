# Trial-8 金标准重标试标 · 标注者 A 复核提示词

> 建档日期：2026-09-03（v1.3：客观驱动 + 抽样人工复核）
> 材料版本：`outputs/pedal_gold_standard/formal_20260828_v1/` 修复版（2026-09-02 coordinate-fix 重建）
> 依赖 commit：`2e1ba411f1`（fix(gs): rebuild 40 score-side reference artifacts with correct perf-QL->score-QL mapping）
> 用途：以客观数据驱动六列标注（CC64 物理记录、MusicXML 解析、数值判据、规则推导），人工仅抽样复核关键行，
>       检验坐标修复后 ③ 列重生成值的正确性，为「其余 32 段采用修复版 ③ + 同款复核」或「修复排查/重标」提供依据。
> 隔离红线：标注者 A 与标注者 B 全程隔离；本文件及 A 的复核产物在隔离期结束前不得共享给 B，反之亦然。

---

## 1. 背景与动机

### 1.1 坐标修复（2026-09-02）
构建层存在坐标系 bug（perf-QL → score-QL 映射错误），已于 2026-09-02 修复并上线：
- commit `2e1ba411f1` 重建 40 段 score-side reference 产物，映射改为正确的 perf-QL → score-QL；
- `segment_metadata.json` 新增 `coordinate_fix` 标记；
- 乐谱侧坐标字段统一为 `score_time_signature` / `score_bar_ql` / `score_start_ql` / `score_end_ql`；
- `reference_pedals.csv` 按乐谱 QL 重建；修复工具同时重算受错位影响的 `events.csv` 标注列。

### 1.2 受影响范围（B 阶段实测，2026-09-03）
对 8 段抽样段逐段比对 baseline-1（首标）与 baseline-2（修复版）的 ③ 列，结果：
| 段 | ③ 改动行 / 总行 | 说明 |
|---|---|---|
| Ravel_Miroirs_3_Une_Barque_181 | 34 / 139 | 修复改动 |
| Chopin_Scherzos_20_254 | 50 / 236 | 修复改动 |
| 其余 6 段 | 0 | 两档一致 |

即坐标 bug 只影响存在踏板-音符边界错位的 2 段；其余段 ③ 首标值本就正确。

### 1.3 方法学依据（六列无需全量人工听判）
本项目演奏 MIDI（`performance_segment.mid`）源自 ASAP（继承自 MAESTRO），其 CC64 控制器事件由
Yamaha Disklavier 高精度物理捕获，是**客观演奏记录**而非估计。学术界的踏板真值标注同样采用物理测量
（如 QMUL Chopin 踏板数据集用专用传感器追踪踏板移动、MAESTRO v3 作为 sustain-pedal transcription
公开基准）。据此确定六列的判定来源：
- ② `performance_pedal_action`：由 `pedal_intervals.csv`（CC64 区间）规则映射，**无需听辨**；
- ③ `published_score_pedal`：由 `reference_score.musicxml` 的 `<pedal>` 元素解析 + score 坐标映射，
  **程序可精确完成**；
- ① `acoustic_sustain`：数值判据（acoustic_duration_ql − key_duration_ql > 0.25 QL），听音仅辅助
  区分踏板延音与自然混响；
- ④ `notation_decision` / ⑤ `review_class` / ⑥ `review_note`：基于前三列与参考时值的规则推导。
因此试标从「全量盲标 6 列」改为「客观基准 + 抽样人工复核」，与首标方法论（规则预填 + 重点复核）一致。

### 1.4 试标策略（v1.3）
- 客观基准确认：修复版 `events.csv` 六列 = 修复坐标下 prefill/annotate 规则重生成值（baseline-2）；
- 复核清单：仅对关键行抽样人工复核（③ 修复改动行 + uncertain + high + 边界歧义行）；
- 判定：复核接受率与修复改动行确认率达标 → 修复可信，32 段采用修复版 ③ 与同款规则值；
  出现系统性修订 → 进入修复排查。

---

## 2. 三档概念与客观基准

### 2.1 档位定义
- **首标档 baseline-1**：修复前（commit `6696617b`，`2e1ba411` 的父提交）的标注值。只读审计参照，不得改动。
- **修复档 baseline-2**：修复工具在正确坐标下重生成的当前值（= 客观基准）。本试标以它为复核对象。
- 复核产物 = 标注者 A 对清单行的接受/修订结果。

### 2.2 客观值来源
| 列 | 来源 | 复核方式 |
|---|---|---|
| ② | `pedal_intervals.csv` CC64 区间规则（区间内 hold、端点 release、retake≤0.25 QL 并入延续、区间外 none） | 对照区间表确认 |
| ③ | `reference_score.musicxml` `<pedal>` 解析 + score 坐标映射（start/change/stop/none） | 看谱确认 |
| ① | acoustic−key 差值 > 0.25 QL → yes / ≤0.25 → no；两可 → uncertain | 数值 + 听音辅助 |
| ④⑤⑥ | 参考时值 + 分类规则 | 规则复核 |

---

## 3. 复核清单生成（执行方：本地 AI）

对 8 段 `events.csv`（修复版）按如下规则筛选，导出 `iaa/trial_A/review/trial8_A_review_<sid>.csv`
（含事件信息列 + baseline-2 六列值 + 筛选原因列）：
- **F 组**：③ 列 baseline-1 ≠ baseline-2 的行（Ravel 34 行、Chopin 50 行）——核心复核对象；
- **U 组**：① 或 ② 为 `uncertain` 的行；
- **H 组**：`review_priority` = high 的行；
- **E 组**：跨小节 tie（reference_tie_start/stop）或换踩歧义等边界行（标注者/助手按需补充）。
预期清单总量远小于 1133（约 100–200 行级），以本地 AI 实际筛出为准。

---

## 4. 标注者 A 复核说明

### 4.1 角色
你是复核者，不是全量盲标者。复核对象是修复版客观预填值，你的任务是逐行判断其正确性：
接受（OK）或修订（给出新值 + 理由）。

### 4.2 材料与工具
- 复核表：`outputs/pedal_gold_standard/formal_20260828_v1/iaa/trial_A/review/trial8_A_review_<sid>.csv`
- 听辨材料：`outputs/pedal_gold_standard/formal_20260828_v1/<sid>/performance_segment.mid`
  （片段目录平铺，无 segments/ 层；MuseScore 渲染，确认 CC64 生效）
- 谱面：同目录 `reference_score.musicxml`（MuseScore 打开）
- CC64 区间：同目录 `pedal_intervals.csv`；坐标：`segment_metadata.json`

### 4.3 复核流程
1. ②：查该行 onset 落在哪个 CC64 区间 → 对照预填值（hold/change/release/none）；
2. ③：看谱该事件对应位置有无踏板记号 → 对照预填值（start/change/stop/none）；
3. ①：核对数值判据，必要时听音确认（区分踏板延音与自然混响）；
4. ④⑤⑥：复核规则推导的合理性，重点看跨小节 tie 与换踩点；
5. 判定：OK 或修订（修订必须写理由）。全部完成前不查看 baseline-1。

### 4.4 判据速查
- 阈值：retake = 0.25 QL；BOUNDARY = 0.25 QL；≤0.25 QL 为容差噪声不改变判定。
- ① yes/no/uncertain；② hold/change/release/none/uncertain；③ start/change/stop/none/uncertain；
  ④ 记谱时值（以参考时值为准）；⑤ independent-voice/notation-shortening/pedal-only/留空；⑥ 自由文本。

### 4.5 隔离红线
不与标注者 B 共享任何材料/过程/结果；不读取 baseline-1 与 B 的材料；不打开 `evals/C/`；
全部产物写入新文件，禁止覆盖 events.csv 或首标只读档案。

### 4.6 交付物
- 复核结果：`trial8_A_review_<sid>.csv`（追加 A 的判定列 accept/revise 与修订值、理由）
- 复核日志：`trial8_A_review_log.md`（时间、片段、结论）

---

## 5. 判定标准（执行方：主控 + 本地 AI 统计）

- **F 组确认率** = A 接受修复值行数 / F 组总行数（84 行）。≥ 95% 且无系统性修订 → 修复可信。
- **整体接受率** = A 接受行 / 复核清单总行。
- **U/H/E 组修订模式**：修订若集中于某一类（如某类 uncertain 反复被改）→ 提示规则需调整。
- **结论 A（修复可信）**：F 组确认率 ≥95% 且无系统性模式 → 其余 32 段采用修复版 ③ 与同款规则值，
  仅对全库 uncertain/high 行执行与首标相同的复核工作流；无需全量重标。
- **结论 B（修复仍有问题）**：F 组确认率 <95% 或修订呈系统性 → 回到修复工具排查坐标映射，
  修复后重跑本流程；不直接进入 40 段全量人工重标（人工重标仅在修复工具无法收敛时作为后备）。
- 本判定不依赖「重标 vs 首标」全量一致率，而依赖「人工对客观基准的抽样确认率」——工作量与首标方法论对齐。

---

## 6. 附录

### 6.1 导出与复制注意
阈值符号（`> 0.25 QL`、`≤ 0.25 QL`）与枚举值必须逐字保留；导出/复制本文件后按 CHECKSUMS 流程复核哈希。

### 6.2 修订记录
| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-09-03 | v1.0 | 建档：coordinate-fix 后的 8 段试标提示词（标注者 A）；重算哈希并登记 CHECKSUMS。 |
| 2026-09-03 | v1.1 | 听音口径澄清：听辨材料为 `performance_segment.mid`（MIDI 播放器渲染），WAV 不进入标注材料集；修订 4.3 材料清单 / 4.5 阶段 1 / 4.9 停报条件；重算哈希并更新 CHECKSUMS。 |
| 2026-09-03 | v1.2 | 路径约定修正：材料包为 `formal_20260828_v1/<片段ID>/` 平铺（无 `segments/` 层）；iaa 共享材料统一于 `formal_20260828_v1/iaa/`（生成一次、只读共享，A/B 产出分目录隔离）；重算哈希并更新 CHECKSUMS。 |
| 2026-09-03 | v1.3 | 方法重构：客观驱动 + 抽样人工复核（B 阶段实测仅 2 段 ③ 受修复影响；② 用 CC64 物理记录、③ 用 MusicXML 解析，无需全量听判）；新增 1.3 方法学依据、复核清单流程与判定标准；重算哈希并更新 CHECKSUMS。 |

---

*v1.3 方法学依据：演奏 MIDI 的 CC64 为 Disklavier 物理捕获（MAESTRO/ASAP 谱系）；踏板真值标注在学术界采用物理测量（QMUL Chopin 数据集、MAESTRO v3 pedal-transcription 基准），故低层踏板状态不作人工听判。*
