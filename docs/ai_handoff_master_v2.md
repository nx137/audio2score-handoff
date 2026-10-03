# 主控 AI 交接总纲 v2（持久化版）

> 建档 2026-10-03（第二轮主控）。仓库：`nx137/audio2score-handoff`（public）。
> **建档原因**：v1 交接文档（§0–§12，标题「【项目交接】钢琴 WAV→乐谱（P4 记谱层）研究 · 全数据集踏板重标注」）
> 只存在于用户与上一任主控的**聊天记录**里，**从未入库**。本轮实测确认：全库 110 个 `.md`
> （含 15 个中文名文件）中，特征串「本地端仅做验证」「交接纪律复述」「全数据集踏板重标注」命中 **0**。
> 本文档是 v1 的**入库替代版**，并在 §12–§14 追加本轮核实记录、决策锁与勘误。
>
> ⚠️ **凭据不入库**：v1 §2 的 GitHub PAT 已按安全惯例**从本文档移除**，凭据一律由用户在会话中提供。
> （实测：`NEXT_AI_CONTEXT.md` 与 `outputs/pedal_gold_standard/formal_20260828_v1/project_review_v1.md`
> 中的 `github_pat_...` 均为**省略号占位符**，非真实 token，公开库无凭据泄漏。）

---

## 0. 角色与铁律（最重要）

- 你是**主控 AI**：唯一有 GitHub 写权限、唯一负责编写/修改全部代码与文档的角色。
- 另有「**本地 AI**」运行在用户的 Windows 机器上：**无写权限、不做任何决策**。
  用户自己把指令转给本地 AI，再把输出原样贴回。
- **铁律（用户反复强调，不可违背）**：
  1. **「本地端仅做验证，所有的代码由你来修改」** —— 主控直接改代码 / 写文档 / 提交；
     本地 AI **只跑命令、原样回贴**。绝不让本地 AI「分析一下」「你决定」「顺手修一下」。
  2. 主控**直接 push 到 GitHub**；本地 AI 用 `git pull --ff-only` 同步。
  3. 指令必须**机械化、可复制**：完整命令 + 明确预期输出形状 + 「原样贴回」。
  4. **需要抉择时先向用户确认**，以 A/B/C 选项 + 各自代价的形式呈现。
  5. 交付方式：用户常说「**给出本地 ai 的提示词**」→ 输出一段可直接复制转发的提示词块。
  6. 主控**没有跨会话记忆**：凭据每次新会话需用户重新提供，**不要反复索要**。
  7. 严谨优先：结论必须有**源码级或实测级证据**（行号 / hash / 交叉工具闭合）；
     不确定就写「未验证」，禁止推测性陈述冒充事实。

## 1. 项目目标与论文红线

把**钢琴独奏 WAV** 经音频转录前端转为含 **CC64（延音踏板）** 的 MIDI，再由 P3/P4 后端转为
MusicXML 与可视化五线谱（SVG）。研究核心是 **P4 记谱层**：显式多声部、结构化时值、跨小节 tie、
候选级学习排序、**踏板感知解码**。最终交付 1 篇 SCI 三区论文 + 1 套可复现开源系统。

- **可以说**：已完成严格 CC64 配对消融；当前参考谱一致性**未显示可检出的 CC64 正向增益**；
  performance MIDI 的 CC64 与出版谱 pedal 标注之间存在**语义 / 粒度错配**。
- **不可以说**：系统已实现高保真踏板记谱；P4-L 全面优于规则评分；本结果证明端到端 WAV 转录更好。
- 不要把本项目 MIDI→MusicXML 的结论写成**端到端音频转录**结论。

**当前主攻子任务**：③ `published_score_pedal` 列的**全数据集重标注**（含补谱源）。

## 2. 仓库与凭据处理

- 仓库：`nx137/audio2score-handoff`（public），默认分支 `main`。
- 凭据：fine-grained PAT（login `nx137`，contents 写权限），**由用户在会话中提供**，不入库。
  提交走 **GitHub Contents API**（`PUT /repos/nx137/audio2score-handoff/contents/<path>`，
  需带 `sha` 做更新、`branch: main`）。写文件后**同批**更新 `CHECKSUMS.sha256`。
- ⚠️ 判断「某文件是否在库」**必须直接抓 `raw.githubusercontent.com/.../main/<path>`**；
  GitHub commits.atom 源可能返回陈旧缓存（曾漏掉整个 Phase-2A 提交链）。
- 截至 2026-10-03（第二轮主控接手时）远端 HEAD：`1daa98fa37307f8fdac41b62f4374670536ca593`。

## 3. 已完成进度（均有库内证据）

### 3.1 主线实验（已冻结，勿动）

| 项目 | 位置 | 状态 |
| --- | --- | --- |
| B 阶段证据 | `evals/B/` | 完成 |
| C 冻结参考谱评测 | `evals/C/frozen_test_20260817/` | 完成，**勿覆盖** |
| C 严格 CC64 配对消融 | `evals/C/pedal_ablation_frozen_20260818/` | 完成，**勿覆盖** |

- C 阶段只读 `data/asap_piece_manifest.csv` 中 `split == test` 的 **120 条演奏 / 31 个作品**，
  复用 `data/alignments/` 的外部对齐。**不得**用 test 结果调参 / 重训 / 反推对齐。
- 消融：P4-R / P4-R-NP / P4-L / P4-L-NP 共 **480/480 completed**，0 failures；
  P4-L 与 P4-L-NP 模型回退为 0；无踏板 XML 内 pedal 为 0/240。
- 冻结候选级 LightGBM 双哈希（**必须校验**）：
  - `audio2score/models/p4_asap_cross_piece_v1.txt`：
    `31f58cf9bc022a686eedc60ed9af6c621eac69ba4569cccf24147bdd4877b666`
  - `audio2score/models/p4_asap_cross_piece_v1.json`：
    `7dbeadb4fd5549de5e984444d0c77921ad8b3dbdaa44e6798279fcec342c6fe6`
- P4-L − P4-L-NP 差异（95% CI）：note F1 −0.00099 [−0.00210, 0.00006]；
  duration −0.00171 [−0.00417, 0.00092]；tie −0.00053 [−0.00505, 0.00349]；
  voice −0.00066 [−0.00185, 0.00039]。

### 3.2 Trial-8 金标准 **40 段**（唯一「全量」口径，D1=A）

- 目录：`outputs/pedal_gold_standard/formal_20260828_v1/`，**641 文件 / 40 段**；
  coordinate-fix 重建提交 `2e1ba411f1`。
- 一级子目录实测 **43 个** = 40 段 + `_alignments/`(40 文件) + `evaluation/` + `iaa/`；
  每个段目录固定 **14 件**产物（`candidate_options.csv`、`events.csv`、`p4_exact.musicxml`、
  `p4_fused.musicxml`、`p4_learned.musicxml`、`p4_no_pedal.musicxml`、`p4_rule.musicxml`、
  `pedal_intervals.csv`、`performance_segment.mid`、`reference_events.csv`、`reference_pedals.csv`、
  `reference_score.musicxml`、`review_guide.md`、`segment_metadata.json`）。
- 作曲家分布：Bach 5 / Beethoven 7 / Chopin 6 / Haydn 3 / Liszt 3 / Mozart 2 /
  Schubert 5 / Schumann 3 / Scriabin 2 / 其他 4。
- **40/40 带 `coordinate_fix`**，`method` 全为 `alignment-mapped-score-window`（本轮实测）。
- Trial-8 的 8 段全部落在这 40 段内（如 `Chopin_Scherzos_20_254`、`Ravel_Miroirs_3_Une_Barque_181`）。
- 旧金标准 `pilot_20260820_v2`（130 文件）在库，**只作历史留档，不参与重标注**。

### 3.3 Phase 2A **5 段扩样**（方法泛化验证，已完成）

- 目录：`outputs/pedal_expansion/segments_v1/`（67 文件）；材料提交 `950db2f6`，锚定提交 `8feb0301f7`。
- 5 段 = `Chopin_Ballades_3_55` / `Chopin_Barcarolle_1` / `Liszt_Concert_Etude_S145_2_1` /
  `Rachmaninoff_Preludes_op_32_10_24` / `Ravel_Miroirs_4_Alborada_del_gracioso_25`。
- **5/5 都不在 40 段金标准内**（本轮实测确认）→ 独立泛化验证，**单独报告，不并入全量统计口径**。
- 双工具审计全绿；跨工具硬闭合：窗口内 `reference_pedals.csv` 行数 = 独立复算 =
  **78 / 39 / 156 / 25 / 7**；F 组计数 **196 / 74 / 375 / 38 / 4，合计 687**。
- 重跑后 **5 段 `published_score_pedal_changed = 0`**；`mapping_method` 均为 `strict`。
- `events.csv` 行数：770 / 278 / 1555 / 1168 / 798，**合计 4569**。
- 抽样参数：`seed=20260907` / `frac=0.30` / `min_per_seg=10`。

### 3.4 材料与产物清点（含旧记录勘误）

- `outputs/pedal_expansion/` 全树 **158 件**（根 2 + `evaluation/` 2 + `review/` 87 + `segments_v1/` 67）。
  - `review/` 87 = 根 6 + `rendered/` 63 + `sampled/` 18（有效 15 + 失效 3，**同目录改名**
    后缀 `.invalid_v2_perfdomain`）。
  - `segments_v1/` 67 = `_alignments/` 5 + 5×12 + `build_log.json` + `evaluation/` 1。
- **旧记录 3 处错误（已复核，勿沿用）**：
  1. 远端**没有** `review/_quarantine_invalid_v2/`（是改名不是隔离）。
  2. 远端**没有** `rendered/_render_reproducibility/`（9 张复现副本平铺在 `rendered/`）。
  3. `tools/append_checksums.py` **不在库里**（`tools/` 实测 31 件，无此文件）。
     若要用它，先由主控正式入库并锚定；否则由主控直算写入 CHECKSUMS。

### 3.5 锚定（CHECKSUMS）与校验

- `CHECKSUMS.sha256`：**分块追加**长成、**不排序**。实测 **4229 条目 / 4235 行**；
  空行位于第 4017 / 4019 / 4025 / 4027 / 4029 行（尾部旧区段 5 个空行）+ 文件末换行。
- **锚定写入纪律**：写入前对已有条目抽样逐字节自检，写入后读回校验。
  本轮实测：24 条代表条目（17 docs + 5 根 + 2 冻结模型）**24/24 PASS**。
- **哈希口径**（`tools/verify_handoff.py::digest()`，源码级）：
  - `TEXT_EXTS` 白名单（`.txt .csv .py .md .json .sha256 .sh .tex .musicxml .xml .yml .yaml
    .toml .rst .log .cfg .ini .gitignore .gitattributes .html .css`）→
    `open("r", encoding="utf-8", errors="replace")` 读（universal newline）+ `encode("utf-8")` 哈希；
  - 白名单外 → 裸字节 `read_bytes()`（`.png/.pdf/.svg/.mid/.mpos/.ipynb` 等）。
  - **已原生支持二进制，无需改一行代码。**
- `check_checksums()` 逐行 `split("  ", 1)`；成功打印
  `[通过] CHECKSUMS.sha256：{total} 个关键文件全部匹配`。
  另有 `check_required()`（REQUIRED **19** 项）、`check_models()`（冻结模型双哈希）、
  `check_manifest()`（120 演奏 / 31 作品）、`check_ablation()`（480 completed，四管线各 120）。
- **无任何 EXCLUDE/SKIP 规则 —— 清单本身就是权威范围。**
- 根目录文件若被改动，用 `python fixchecksumsline_endings.py` **原地按原行序重算**（不排序），
  再跑 `python tools/verify_handoff.py` 直到全绿。
  （源码级确认：该脚本 `read_text().splitlines()` → 逐行重算 → `"\n".join(out) + "\n"` 写回，
  保留空行与原有行序；且 `#` 开头行会被两个工具跳过。）
- 根目录 **10 个**被跟踪文件：`.gitattributes`、`.gitignore`、`CHECKSUMS.sha256`、
  `LICENSES_AND_DATA_NOTICES.md`、`MANIFEST.md`、`NEXT_AI_CONTEXT.md`、`P0_EXECUTION_GUIDE.md`、
  `README.md`、`README_HANDOFF_CN.md`、`fixchecksumsline_endings.py`。
  （CHECKSUMS 里只收录其中 5 个；`README.md`、`.gitattributes`、`.gitignore`、
  `fixchecksumsline_endings.py`、`CHECKSUMS.sha256`（自身不可自锚）在根但**未列入**。）
- 其他计数：`tools/` 跟踪 **31** 个文件；`docs/` **17** 件。
- **全仓未锚情况**：6980 blob 中锚定 4229，**未锚 2751 件 / 约 2.05 GiB**：
  `evals` 1901 件 / 1994.5 MiB、`outputs` 765 件 / 59.3 MiB、`results` 64 件 / 32.1 MiB、
  `data` 6 件 / 2.0 MiB、`frontend` 12 件 / 2.0 MiB、`audio2score` 2 件 / 0.2 MiB、
  根 `CHECKSUMS.sha256` 1 件（自身）→ 见 **D5**。

### 3.6 ③ 列谱源可得性审计（决定性发现）

权威档案：`docs/trial8_score_source_pedal_audit.md`（v1.0）、`docs/trial8_pedal_source_plan.md`（v0.1）。

- **两个层级必须分清（v1 交接文档此处混淆，见 §13 勘误③）**：
  - **窗口层**（40 段 `reference_score.musicxml`）：合计仅 **8 处 `<pedal`**、
    `reference_pedals.csv` 合计 **7 行**；**37/40 段为 0**，有痕迹的仅 3 段
    （`Chopin_Scherzos_20_254` 5 处 / 3 行、`Ravel_Miroirs_3_Une_Barque_181` 2 处 / 3 行、另 1 段 1 处 / 1 行）。
  - **作品层**（ASAP 谱源 `data/ASAP/**/xml_score.musicxml`，共 235 个）：
    40 段所属作品中 **14 个含 `<pedal>`（A 类）/ 26 个不含（B 类）**。
- 40 段 `events.csv` 的 ③ 现状：**4672 行中仅 14 行非 `none`**，全部在 `Chopin_Scherzos_20_254`
  （change 11 / stop 3），其余 39 段 ③ 全 `none`。
- 修复前基线（父提交 `6696617b`）在 2 段上有 84 行非 none（Miroirs_3 34 + Scherzos_20 50）——
  那 84 行实为**坐标错位把 performance 侧取值泄漏进 ③**（假非空），修复后清回 `none` 是**正确**行为。
- **口径纠正**：`docs/trial8_annotator_A_prompt.md` §1.2 里「其余 6 段 ③ 首标值本就正确」
  必须更正为「**两侧皆空（源未记谱）**」。
- **③ 的权威记录在 `iaa/trial_A/review/` 那批清单里**（含 `baseline_published_score_pedal` 列）。
- **40 段 A/B 分类**（本轮已用 `outputs/pedal_expansion/score_pedal_scan.csv` 独立复算，逐段吻合）：
  - **A 类 14 段**（该作品的 ASAP 谱本来就含 `<pedal>`，只是当前窗口没覆盖到）：逐段记号数
    `Chopin/Scherzos/20` 420、`Ravel/Miroirs/3` 279、`Liszt/Transcendental/9` 102、
    `Scriabin/Sonatas/5` 17、`Chopin/Sonata_3/4th` 14、`Etudes_op_10/5` 13、`Transcendental/10` 10、
    `Etudes_op_10/1` 5、`Beethoven/29-2` 4、`Kreisleriana/7` 2、`Scriabin/Etudes_op_8/11` 2、
    `Etudes_op_25/12`、`Prokofiev/Toccata`、`Schubert/Impromptu_op.90_D.899/3` 各 1。
    → **换窗 / 加 pedal-rich 新段即可，零外部数据、零许可风险。**
    ⚠️ **A 类里只有 7 段记号数 ≥10**，其余 7 段仅 1–5 处，换窗后 F 组无统计意义。
  - **B 类 26 段**（ASAP 谱完全无记号：Bach 5 / Beethoven 6 / Chopin 2 / Haydn 3 /
    Liszt Paganini 1 / Mozart 2 / Rachmaninoff 1 / Schubert 4 / Schumann 2）
    → **只有这 26 段需要外部补谱。**
- **ASAP pedal 富集池**：235 谱中 **64 个含 `<pedal>`**
  （Chopin 21 / Liszt 14 / Beethoven 13 / Schumann 5 / Ravel 4 / Scriabin 2 /
  Brahms 1 / Debussy 1 / Prokofiev 1 / Rachmaninoff 1 / Schubert 1），总记号 7290 处。
  2A 用掉 5 个、A 类占 14 个 → **剩余未用 45 个**（Chopin 14 / Beethoven 12 / Liszt 11 /
  Schumann 4 / Ravel 2 / Brahms 1 / Debussy 1），其中 9 个记号 <5 处 → **高价值剩余 ≈36 个**。
  池内最富：`Liszt_Mephisto_Waltz` 685、`Liszt_Sonata` 519、`Chopin_Scherzos_31` 479、
  `Chopin_Ballades_1` 465、`Liszt_Transcendental_Etudes_4` 426。

## 4. 决策登记表（**权威**）

| 编号 | 值 | 内容 | 锁定时间 |
| --- | --- | --- | --- |
| **D1** | **A** | 「全量重标注」= **金标准 40 段**。Phase 2A 5 段作为独立泛化验证单独报，不并入。（B = 45 段含 2A；C = 120 演奏全量；均已否决。） | 用户拍板 |
| **D2** | **A** | 全量 40 段跑 `rebuild_segment_reference.py --dry-run` 复核（**不写产物**）+ `scan_segment_coordinate_mismatch.py` 出受影响清单，两者留档。（B = 真跑全量重算；C = 只重算扫码命中段。） | 2026-10-03 |
| **D3** | **A** | 分层抽样一律沿用 `seed=20260907` / `frac=0.30` / `min_per_seg=10`。（B = 受影响 0.30 / 零改动 0；C = 受影响 0.50 / 零改动 0.10。）<br>注：40 段 F 组当前仅 14 行 → 抽样后人工量 ≈4 行，真正的人工量在 D6 补谱之后。 | 2026-10-03 |
| **D4** | — | 保持「**客观数据驱动 + 抽样复核 + 外部验证**」，**不回到全量人工听判**。（用户曾质疑「人耳对几毫秒差异不敏感」，已被说服；不再询问。）方法学依据见 `docs/trial8_annotator_A_prompt.md` §1.3。 | 已定 |
| **D5** | **B** | 放行前补锚 `outputs`(765) + `results`(64) + `data`(6) + `frontend`(12) + `audio2score`(2) ≈ 849 件 / 95.6 MiB；**`evals` 1901 件 / 1994.5 MiB 单独排期**。（A = 只锚新产物；C = 全补齐含 evals。）<br>动机：金标准 40 段当前仅 **1.6%** 受哈希保护、两份 C 冻结证据 1.4% / 1.0%，重标注基线无法事后举证未被覆盖。 | 2026-10-03 |
| **D6** | **补谱源** | 为 ③ 补上真实存在的谱面踏板记号层：A 类 14 段用现有工具链加 pedal-rich 新段；B 类 26 段走外部补谱协议。**不改金标准既有 40 段的窗口与已锚定产物。** | 2026-10-03 |
| **D7** | **A** | A 类扩样目录 = `outputs/pedal_expansion/segments_v2/`；**第一批做 A 类中记号数 ≥10 的 7 段**（Scherzos_20 / Miroirs_3 / Trans_9 / Scriabin_Sonatas_5 / Sonata_3_4th / op_10_5 / Trans_10），与 Phase 2A 同款流程。（B = 做满富集池剩余 36 段有效；C = v2 做 A 类 7 段 + v3 取富集池 top-10。） | 2026-10-03 |
| **D8** | 待定 | B 类若某首确实找不到合格谱源（许可或质量不达标），该段 ③ 记为 `not-notated-in-source` 并留档，**不允许悄悄留空**。留待 P1 pilot。 | — |
| **D9** | 待定 | ③ 合并后的列策略（保留 `reference_pedals.csv` 与 `reference_pedals_ext.csv` 双份，另加合并列 `published_score_pedal_merged`）。留待 P1 pilot。 | — |

## 5. 外部补谱协议分期（v0.1，待 pilot 校准）

- **P0（已备）**：A 类 14 段清单、B 类 26 段清单、富集池 64 个谱。
- **P1（pilot，3 首）**：`Beethoven_Piano_Sonatas_16-1`、`Mozart_Piano_Sonatas_12-3`、
  `Schubert_Wanderer_fantasie_1189`（古典 / 浪漫各半，均公版，IMSLP 与 MuseScore 均有条目）
  → 走通全流程并校准协议。
- **P2（批量）**：B 类其余 23 首，按作曲家风控（每批 ≤5 首，批后锚定）。
- **P3**：A 类扩样（从富集池取样，与 2A 同款流程）。

外部补谱硬性要求：优先 **CC0 / CC-BY 的 MuseScore 公开谱**（可直接导出 MusicXML，无 OMR 误差），
次选 **IMSLP 公版**（需 OMR / 人工录入）；每首记录 `source_url`、许可、编者 / 版次、下载日期、sha256；
入库 `data/scores_external/<composer>/<work>/source.musicxml` + 同目录 `SOURCE.md`；
必须产出 `measure_map.csv`（`external_measure` ↔ `our_score_measure`）并**人工抽查 ≥3 处**。

## 6. 不变式（I1–I6）——**指针**

口径权威实现见 `docs/trial8_full_relabel_plan.md` §1（I1 坐标双轨 / I2 窗口成员判定 /
I3 踏板归一 / I4 两套容差不得混用 / I5 听辨口径 / I6 隔离）与 `docs/trial8_phase2A_coordinate_conventions.md`。
**任何段都不得偏离。**

关键速记：
- **I1**：`onset_location`（如 `m.79 beat 3.375`）是 **performance 域**小节号
  （由 `_fmt_beat(onset_ql, segment.bar_ql)` 按 perf MIDI 的 `bar_ql` 均分法算出），
  **不是谱面小节号，不可拿去翻 PDF**。谱面定位一律走 score 侧：
  `events.csv` 的 `reference_onset_ql` + S4 的 `measure_starts` 惯例 +
  `segment_metadata.json` 的 `score_start_measure`。
- **I2**：精确 QL **半开区间** `starts[first] <= ql < starts[last+1]`。
- **I3**：同一 `(hand, position)` 的成对 stop+start 归一为 **`change`**；
  pedal 位置 = `measure_start + cursor + <offset>/divisions`，**`<offset>` 必须应用**
  （`audio2score/scripts/score_metrics.py::pedal_events()` 第 84–91 行）。
  → **`reference_pedals.csv` 行数 ≠ 原始 mark 数**。
  实测归一：Ballades raw 480→366、Barcarolle 455→455、S145/2 420→244、op32/10 48→36、Miroirs 20→20；
  窗口内 78 / 39 / 156 / 25 / 7。
- **I4**：判定容差 `PEDAL_MATCH_QL = 0.25`（③ 取最近 `reference_pedals` 条目，
  距离 ≤0.25 QL 则用其类型，**否则 `none`**）；列出容差 `--tol = 0.5` 只影响工作表展示列
  （`tools/phase2a_make_worksheet.py` 第 133–134 行；第 234 行 `if abs(p - ql) <= a.tol + EPS`，**闭区间**），
  **绝不是判定容差**。实测佐证：Ballades 工作表第 737 行 `stop d0.500(pos 236)` 被列出，
  同行 `published_score_pedal=start` 取的是 `d0.000` 那条。
- **I5**：材料为 `performance_segment.mid`（MIDI 渲染，CC64 生效）；**WAV 不进入标注材料集**；首标与重标对称。
- **I6**：标注者 A / B 全程隔离，产物分目录，隔离期结束前不互看；**不得覆盖既有只读档案**
  （Trial-8 40 段、`pilot_20260820_v2`、`evals/C/*frozen*`）。

### 抽样与判定口径（沿用 2A，勿改）

- `n_target = max(min_per_seg, int(frac * n_F + 0.5))` —— **半进舍入 `int(x+0.5)`**，
  不是 Python `round`（`tools/phase2a_sample_review.py` 第 53–54 行 `round_half_up`）。
  ⚠️ 陷阱：S145/2 `0.30×375 = 112.5`，`round_half_up` = 113，而 `round(112.5)` = 112（银行家舍入）会少抽 1 行。
- `n_target = min(n_target, n_F)`；`full_take = n_F <= min_per_seg`。
- 第 121 行：`if full_take or len(rows) <= 3` 进**强制层**；分配见第 78–86 行 `allocate()`。
- 每条 manifest **必含 8 键**：`n_F / n_target / full_take / seed / frac / min_per_seg /
  strata_drawn / rows`。
- 抽样必覆盖：③ ∈ {start, change, stop} 的 F 组全体、`review_priority=high`、`uncertain`、
  跨小节 tie / 换踩边界行。
- **放行口径**：确认率 = `reviewer_confirm=ok` 行数 / 抽样行数 **≥ 95%** → 结论 A（该批可用）；
  否则结论 B（停止扩张，回到坐标 / 规则排查）。**禁止**用「重标 vs 首标全量一致率」替代本口径。
- **表外确认项不进 verdicts 文件**（`phase2a_fill_review.py` 会以 `row_no not in this sheet` 拒绝）。

### 结构性事实：无 score 侧 onset 的行

- 2A 5 段实测 **1884 / 4569 ≈ 41%** 的行无 score 侧 onset，跨段极不均
  （S145/2 588/1555、op32/10 862/1168、Miroirs 278/798、Ballades 111/770、Barcarolle 45/278）。
- **本轮新测**：40 段金标准 **1984 / 4672 ≈ 42.5%** 的行 `reference_onset_ql` 为空。
- 成因已查清（O2 关闭）：三元组 (hand,pitch,onset) 本可命中却没值 = **0 行**；
  未对齐 1789（95%）；(hand,pitch) 完全未出现 78；onset 早于对齐起点（全在 S145/2）17。
  按最近距离分层：≤0.005→0；≤0.25→53；≤0.5→215；≤1.0→203；**>1.0→1413（75%）**。
  → 这些行的 score 侧坐标**在输入对齐里本就不存在**，不是算法 bug。
- 这类行第 3 列按构造只能是 `none`，且**两份审计工具都不检查它们**。
- **全量阶段必须单列「该行有无 score 侧坐标」**，把「无坐标」行单独统计、单独口径，
  **不得混入 F 组确认率**。

### 边界记号闭环（E1 审计已复核，O1 关闭）

- 共 **4 个 edge marks**：Ballades LH stop pos=294 / idx=98 / num=99；
  Barcarolle LH start pos=66 / idx=11 / num=12；op32/10 LH change pos=128 / idx=32 / num=32；
  Miroirs LH stop pos=246 / idx=78 / num=79；**S145/2 无 edge mark**。
- 每段「reference rows sitting exactly on the right window edge」均 **0**。

## 7. 工具链速查（接口为权威，改动前先读源码）

| 工具 | 接口 / 语义 |
| --- | --- |
| `tools/build_formal_segments.py` | `--index N --selection <sel> --out <out> --skip-render`；seg_id = `composer_title_{start_measure+1}`；对齐文件从 `<out>/_alignments/<seg_id>.csv` 读入 |
| `tools/rebuild_segment_reference.py` | `--base <base> --segment <sid> …`（支持 `--dry-run`）；重建后旧 `reference_score.svg` 改名 `.stale` 防误导 |
| `tools/prefill_events.py` | 接段目录列表；**退出码 1 = 有改动已预填（非错误）** |
| `tools/annotate_events.py` | 接段目录列表；**退出码 1 = 已决定行数（非错误）** |
| `tools/phase2a_audit_extraction.py` | `--sampled … --segments …` |
| `tools/phase2a_audit_score_pedal.py` | `--segments … --review … --out …` |
| `tools/phase2a_make_worksheet.py` | `--sampled --segments [--tol] [--out-suffix]`；输出名模板（第 252 行）`annotatorA{out_suffix}_{sid}.txt`，默认 `--out-suffix _worksheet_score` |
| `tools/phase2a_sample_review.py` | 分层抽样，口径见 §6 |
| `tools/phase2a_fill_review.py` | `--csv <filled.csv> --verdicts <file> [--dry-run] [--check] [--overwrite]` |
| `tools/phase2a_window_scan.py` | 窗口扫描（S1） |
| `tools/scan_pedal_in_scores.py` | ASAP 谱 `<pedal>` 扫描（富集池 64 个的来源） |
| `tools/scan_segment_coordinate_mismatch.py` | 段级坐标错位扫描（D2 受影响清单） |
| `tools/verify_handoff.py` | 全库校验（§3.5） |
| `fixchecksumsline_endings.py`（根） | 按原行序原地重算 CHECKSUMS（不排序） |

- ⚠️ `tools/append_checksums.py` **不在库**（上一任主控本地有 5810 B 版本，
  接口 `--add-root --add-tree DIR... [--refresh-tree DIR...] [--label] [--dry-run]`，AST OK）
  → 若要用它，先由主控正式入库并锚定；否则由主控直算写入 CHECKSUMS。
- **S2 对齐文件**（落 `<out>/_alignments/`，字节）：`Chopin_Ballades_3_55.csv` 137140、
  `Chopin_Barcarolle_1.csv` 91650、`Liszt_Concert_Etude_S145_2_1.csv` 84417、
  `Rachmaninoff_Preludes_op_32_10_24.csv` 21760、`Ravel_Miroirs_4_Alborada_del_gracioso_25.csv` 55980。
- **S4 重建日志（重跑后）** n_score_events / n_score_pedals / published_score_pedal_changed：
  Ballades 739/78/0；Barcarolle 265/39/0；S145/2 1461/156/0；op32/10 1152/25/0；Miroirs 842/7/0。
- **5 段窗口参数**：

| 段 | perf→score 对 | score 窗口 | 拍号 | perf 窗口 | bar_ql | score_bar_ql | score_start_ql | score_end_ql | perf_start_ql | perf_end_ql |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ballades/3 | 210→240 | m52–98 | [6,8] | m55–94 | 4.0 | 3.0 | 154.0 | 292.5 | 216.0 | 376.0 |
| S145/2 | 78→210 | m2–81 | [6,8] | m1–40 | 4.0 | 3.0 | 4.5 | 265.5 | 0.0 | 160.0 |
| op32/10 | 138→24 | m9–32 | [4,4] | m24–63 | 4.0 | 4.0 | 35.0 | 124.333333 | 92.0 | 252.0 |
| Barcarolle | 370→207 | m1–11 | [12,8] | m1–36 | 3.0 | 6.0 | 0.0 | 64.7 | 0.0 | 108.0 |
| Miroirs/4 | 168→10 | m35–78 | [6,8] | m25–60 | 4.0 | 3.0 | 108.5 | 245.0 | 96.0 | 240.0 |

## 8. 本地运行环境

- 仓库路径：`D:\keyan\handoff_build\`；Shell：**Windows PowerShell**，每条命令单独执行。
- 中文 Windows 控制台**有时乱码**；工具输出里的 `pedal\_expansion`、`**sample`、`row\_no`
  是渲染丢失下划线 / 通配符所致，**不是数据问题**。
- **MuseScore 3.3.4 为 Microsoft Store（MSIX）版**：
  `C:\Program Files\WindowsApps\64051MuseScoreBVBA.MuseScoreNotationSoftware_3.3.4.0_x64__pz631wrhsw9tj\bin\MuseScore3.exe`；
  **无 MuseScore 4**。**`verovio` 未安装** → 渲染一律走 MuseScore 3 路线。
- **PowerShell 坑**：`find /c /v ""` 会报 `FIND: Parameter format not correct` →
  改用 `@(git diff --cached --name-only).Count`；多语句命令曾报 `Unexpected token '$cs'` →
  每条命令显式分隔、逐条执行。
- git 提交由**主控用 API 完成**；本地只做 `git pull --ff-only` 与只读核验。

## 9. 工序骨架 S1–S9（每段一遍）

| 步 | 名称 | 验收要点 |
| --- | --- | --- |
| S1 | 窗口扫描与选择 | 段清单 + 每段 perf / score 窗口 → 写入 selection JSON |
| S2 | 分段构建 | 12 件产物齐备；`mapping_method`（`strict` 为主）可查 |
| S3 | reference 重建（coordinate fix） | 按 score 坐标重算；`segment_metadata.json` 写 `coordinate_fix` |
| S4 | 客观六列生成 | ②=CC64 区间、③=MusicXML 解析＋score 映射、①=数值判据、④⑤⑥=规则 |
| S5 | 双工具审计 | 两份 JSON 全绿；F 组计数 = manifest `n_F` 逐段相等 |
| S6 | 分层抽样 + 渲染 | worksheet（含 `score m.` 定位列）+ 填写版 CSV + manifest + PDF/PNG/SVG |
| S7 | 人工抽样复核 | 只判 ③；`ok` / `incorrect`（incorrect 必须写实际记号类型与所在小节） |
| S8 | 判定与放行 | 确认率 ≥95% → 结论 A；同类行系统性 incorrect → 结论 B |
| S9 | 锚定与留档 | 产物入库**同批**锚定 CHECKSUMS；`verify_handoff.py` 全绿 |

**每段必须留存**：`build_log.json`、`segment_metadata.json`（含 `coordinate_fix`）、
两份审计 JSON、抽样 manifest；若做人工抽样，另存 worksheet / 填写表 / 判定文件与判定报告。

**commit message 前缀**：`feat(phase2A):` / `fix(phase2A):` / `docs(phase2A):` / `chore(checksums):`；
全量阶段用 `feat(relabel):` / `fix(relabel):` / `docs(relabel):`。

## 10. 常见坑（血泪清单）

1. **`onset_location` ≠ 谱面小节号**。拿它翻 PDF 一定错（I1）。
2. **`round` vs `round_half_up`**：抽样是 `int(x+0.5)`，用 `round` 会少抽行。
3. **0.25 判定容差 vs 0.5 列出容差**不可混用（I4）。
4. **`reference_pedals.csv` 行数 ≠ 原始 mark 数**（stop+start 归并为 change，且 `<offset>` 要应用）（I3）。
5. **约 41–43% 的行没有 score 侧坐标**，这是数据结构的固有事实，不是 bug；必须单列口径。
6. **`prefill_events.py` / `annotate_events.py` 退出码 1 是正常状态**，不是失败。
7. 表外行塞进 verdicts 会被 `phase2a_fill_review.py` 拒绝。
8. `--no-pedal` 不可用「导出后删 XML pedal 标签」替代；那不是严格消融。
9. 指定 `--candidate-model` 但无法加载时，验证 / 评测**必须失败**，
   **不可安静回退为规则评分**。
10. MusicXML tie 对账必须**先合并 tie-chain**，跨小节拆分不算「多写音」。
11. 完整证据很大：**新实验前确认 ≥12 GB 空闲磁盘**（历史上曾因磁盘不足中断）。
12. 旧脚本 / 历史 config 可能保留旧机器绝对路径，新运行必须用**包根目录相对路径**。
13. 不得覆盖：`evals/C/frozen_test_20260817/`、`evals/C/pedal_ablation_frozen_20260818/`、
    金标准 40 段、`pilot_20260820_v2`，以及各自 `config.json` / `commands.log` /
    `manifest/` / `models/` / `pieces/` / `summary/`。
14. **锚定只加哈希、不改文件**，因此把只读冻结档案纳入 CHECKSUMS **不违反 I6**。
15. **判断「文件是否在库」走 raw.githubusercontent，不走 commits.atom**（陈旧缓存）。
16. **`rebuild_segment_reference.py --dry-run` 曾非完全只读**。逐段产物确实不写（第 328–330 行提前返回），
    但 `main()` 第 431–433 行**无条件覆盖** `BASE/evaluation/segment_reference_rebuild.json`。
    该文件是 40 段 S3 重建的**唯一在库记录**（含 `published_score_pedal_changed`，**合计 96** =
    `Chopin_Scherzos_20_254` **50** + `Ravel_Miroirs_3_Une_Barque_181` **34** +
    `Liszt_Transcendental_Etudes_9_67` **12**；与 `docs/trial8_score_source_pedal_audit.md` 的 50/34 吻合）。
    裸跑 `--dry-run` 会**覆盖并丢失这份证据**（dry-run 记录不含 `n_score_events` / `n_score_pedals` /
    `published_score_pedal_changed`），且因该文件已锚定而让 `verify_handoff.py` 失败。
    **2026-10-03 已由主控修复**：dry-run 改写到 `evaluation/segment_reference_rebuild.dryrun.json`。
17. **`raw.githubusercontent.com` 在写入后可能服务陈旧缓存**。实测：刚 push 的
    `docs/trial8_full_relabel_plan.md` 经 raw 读回仍是**旧版本**（7805 B / 旧摘要），
    而 Contents API 与 git tree 的 blob sha 已一致（`3eb49f6473e7`）。
    → 判断「刚写入的内容」用 **Contents API 或 git tree/blobs API**；批量校验下载内容时用
    **git blob SHA-1**（`sha1(b"blob <len>\\0" + data)`）与 tree 比对，可彻底排除 CDN 陈旧。
18. **Contents API 对 > 1 MB 的文件返回 `encoding: "none"` / `content: ""`**。用它做逐字节自检会产生
    **假阴性**（实测：`data/ASAP/Liszt/Transcendental_Etudes/10/xml_score.musicxml` 2,293,388 B）。
    → 大文件自检一律走 raw 或 git blobs API。
19. **`.gitattributes` 覆盖缺口 → Windows 检出把裸字节口径的文件写成 CRLF，本地 `verify_handoff.py` 必失败。**
    实测（2026-10-03）：`eol=lf` 只覆盖 14 个扩展名、`binary` 只覆盖 12 个；
    **`*.ipynb` / `*.aux` / `*.out` / `*.mpos` / `*.invalid_v2_perfdomain` 以及 `.gitattributes` / `.gitignore`
    两边都不在**（当初的 `<无扩展名>` 统计其实就是这两个 dotfile）。这些文件在 `verify_handoff.digest()` 下走
    **裸字节**口径——注意 `Path(".gitignore").suffix == ""`，所以 TEXT_EXTS 里的 `.gitignore` /
    `.gitattributes` 两项**永远不会命中，是死成员**。一旦被 autocrlf 换成 CRLF，摘要立刻失配。
    **已修复**：`.gitattributes` 补齐上述扩展名与两个 dotfile 的 `text eol=lf`（14 个高风险文件的 blob
    实测全为 LF，故此改动**不改变任何已有 blob**）。本地侧根治：`git config core.autocrlf false` + 强制重新检出。
20. **`tools/verify_handoff.py::check_checksums()` 把失败清单截断在 20 条**（`"\n  ".join(bad[:20])`）。
    看不到全量清单时**必须改用 `tools/diagnose_checksums.py`**（不截断 + ASCII 转义 + 成因分类 + `--basename-hints`）。
    实测教训：本地一条命令报 20 条，真实是 **23 条**，差额被截断吃掉。
21. **中文 Windows 控制台会把中文路径渲染成乱码**（`C\u9636\u6bb5_...` 显示为 `C\ufffd\u05b6...`）。
    **不要据乱码反推路径名**——实测曾把 `results/reports/C阶段_冻结ASAP测试_实验报告_20260818.aux`
    误猜成 `导出ASAP消融`。一律让工具输出 **ASCII 转义**。

## 11. 论文措辞红线

见 §1。另：不要把本项目 MIDI→MusicXML 结论写成端到端音频转录结论。
③ 的现状是「**参考谱一致性未显示可检出的 CC64 正向增益**」，不是「踏板记谱已高保真实现」。

## 12. 本轮（2026-10-03 第二轮）核实记录

**远端 HEAD 实测** = `1daa98fa37307f8fdac41b62f4374670536ca593`（与 v1 交接文档一致）。

**逐条复核一致（17 项）**：HEAD、CHECKSUMS 条目 4229、尾部 5 空行（行 4017/4019/4025/4027/4029）、
冻结模型双哈希（逐字节相等）、40/40 `coordinate_fix.method`、
③ 列 4672 行 / 14 行非 none（全在 `Chopin_Scherzos_20_254`：change 11 / stop 3）、
A 类 14 / B 类 26、富集池 235 中含 pedal 64（逐作曲家分布全等）、
`review/` 87 件、`segments_v1/` 67 件、`formal_20260828_v1/` 641 文件、
根目录 10 件、`tools/` 31 件、三处「旧记录错误」全部复核为「不存在」、
`tools/append_checksums.py` 不存在、24 条锚定条目逐字节自检 24/24 PASS、
金标准 40 段 5/5 与 2A 5 段互不相交。

**A 类逐段记号数**已用 `score_pedal_scan.csv` 独立复算，与 `trial8_pedal_source_plan.md` 逐行吻合。

**锚定覆盖率实测（D5 的动机）**：`segments_v1/` 100%、`tools/` 100%、`docs/` 100%、
`data/` 99.8%；**金标准 40 段 10/641 = 1.6%**、`evals/C/frozen_test` 10/731 = 1.4%、
`evals/C/pedal_ablation_frozen` 10/971 = 1.0%、`pilot_20260820_v2` **0/130 = 0%**。
→ **全量重标注的基线此前无哈希保护**，这是 D5 = B 的直接依据。

**D5 = B 已执行（2026-10-03）**：补锚 `outputs`(765) + `results`(64) + `data`(6) + `frontend`(12) +
`audio2score`(2) = **849 件 / 95.6 MiB**，全部通过 **git-blob-SHA1** 校验（0 陈旧 / 0 失败）；
CHECKSUMS 由 **4230 → 5079** 条目（657,666 B），写入后 45 条抽样复核 0 不匹配。
**金标准 40 段与两份 C 冻结证据现已纳入哈希范围。** 剩余未锚 **1902 件**
（`evals` 1901 + 根 `CHECKSUMS.sha256` 自身 1），按 D5 = B 单独排期。

**本地首次全量校验（2026-10-03）**：`verify_handoff.py` 的 4 项前置检查**全通过**
（必需资产 19 项、冻结模型双哈希、test manifest 120/31、CC64 配对证据 480 completed 四管线各 120），
仅 `CHECKSUMS` 项失败。根因**不在 CHECKSUMS 记录本身**——远端逐条核实，被报出的路径全部
「在清单内且与远端内容一致」。真实成因是**本地工作树偏离 HEAD**：
① **12 条已暂存、从未推送的 `git mv`**（`rendered/miroirs4-*` 9 件 → `_render_reproducibility/`；
`sampled/*.invalid_v2_perfdomain` 3 件 → `_quarantine_invalid_v2/`）→ 原路径本地缺失（用户裁决 **B：本地丢弃**）；
② **14 个文件被 Windows 检出写成 CRLF**（详见坑 19）。预期失配 **23 条**（12 缺失 + 11 摘要）。
另有未跟踪残留：`tools/append_checksums.py`（用户裁决 **B：不入库**）与一个 `$null` 文件
（PowerShell 把 `> $null` 当成了文件名，属垃圾，可删）。

## 13. 对 v1 交接文档的勘误（4 条）

1. **`docs/` 实为 17 件，不是 16 件**。v1 §3.5 写「原 14 件 + 新增 2 件 = 16」；
   实测 17，新增的是 **3 件**（`trial8_full_relabel_plan.md`、`trial8_score_source_pedal_audit.md`、
   `trial8_pedal_source_plan.md`），14 + 3 = 17。
2. **`outputs/pedal_expansion/` 的字节数不可跨环境比**。v1 §3.4 写 `38,475,735 B`，
   git 内实测 **`37,993,259 B`**（件数 158 一致，差 482,476 B）。最可能是上一任主控在
   **本地 CRLF 检出**的工作树上量的。→ 口径只记**件数**（或记 git blob 字节数）。
3. **v1 §3.6 把两个层级混为一谈**。v1 写「37/40 段金标准的乐谱源本身不带任何踏板记号
   （上游 ASAP 谱同样是 0 处）；另 3 段（即 2A 那三首）谱源有 480 / 420 / 20 处」。
   权威口径是**两个层级**：窗口层 37/40 段为 0（共 8 处 / 7 行，3 段有痕迹）；
   作品层 14 个作品含 pedal（A 类）/ 26 个不含（B 类）。
   **且 480 / 420 / 20 是 Phase 2A 那 5 段里三首的原始 mark 数，与 40 段无关**。
4. **补注**：`formal_20260828_v1/` 一级子目录实为 **43 个** = 40 段 + `_alignments/`(40 文件)
   + `evaluation/` + `iaa/`（文件数 641 与 v1 一致）。

## 14. 下一步（按序）

1. 本地 AI 同步：`git pull --ff-only` → 回报 `git log -1` → `python tools/verify_handoff.py` 全绿。
2. **D5 = B**：主控补锚 `outputs` + `results` + `data` + `frontend` + `audio2score`（≈849 件）。
3. **D2 = A**：本地只读跑 `rebuild_segment_reference.py --dry-run`（40 段）+
   `scan_segment_coordinate_mismatch.py`，产出留档。
4. **P1 pilot（3 首外部补谱）**：`Beethoven_Piano_Sonatas_16-1`、`Mozart_Piano_Sonatas_12-3`、
   `Schubert_Wanderer_fantasie_1189` → `data/scores_external/<composer>/<work>/` + `measure_map.csv`。
5. **D7 = A**：建 `outputs/pedal_expansion/segments_v2/`，先做 A 类记号 ≥10 的 7 段（零外部依赖）。
6. 每批产物**同批锚定** CHECKSUMS；提交后让本地 AI 复跑 `verify_handoff.py`。

## 15. 版本记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-10-03 | v2.0 | 建档（第二轮主控）：v1 聊天版交接文档入库替代；本轮远端核实 17 项一致 + 4 条勘误 + 锚定覆盖率实测；D2/D3/D5/D7 决策锁定（均 = A、A、B、A）。 |
| 2026-10-03 | v2.1 | D5 = B 执行完成（CHECKSUMS 4230 → 5079，补锚 849 件，git-blob-SHA1 全通过）；修复 `rebuild_segment_reference.py --dry-run` 的非只读副作用（保住 96 处 ③ 变更的在库记录）；补 §10 坑 16/17/18。 |
| 2026-10-03 | v2.2 | 补 `.gitattributes` 覆盖缺口（根因：Windows 检出把裸字节口径文件写成 CRLF）；新增 `tools/diagnose_checksums.py`；补 §10 坑 19/20/21 与本地首次校验记录。 |
