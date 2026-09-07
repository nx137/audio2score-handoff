# Phase 2A 构建执行指令 v1（本地 AI 执行）

状态：定稿（2026-09-07）。前置文档：`docs/trial8_phase2_expansion_plan.md`（Phase 2 总规格）、
`docs/trial8_phase2A_selection.md`（对齐质量核查 + 五段选段裁定，含证据与局限）。
角色：主控裁定与裁决；**本地 AI 只做验证运行**；用户（标注者 A）做 F 行抽样复核。

## 0. 前置确认

1. 工作区代码 ≥ `f11d6d60`（P0 measure 粒度过滤修复）；最新远端含本执行指令所在 commit。
2. 全池扫描产物已入库：`outputs/pedal_expansion/score_pedal_scan.csv`（235 首 / 64 首含 `<pedal>`）。
3. 五段对齐文件已在 `data/alignments/`（清单见 §2 表），已在主控侧通过空隙分析（A/B 级）。

## 1. 目标

构建 5 个 pedal 富集扩样段（Phase 2A），产出与 40 段金标准**同构**的段目录
（events.csv 30 列、reference_pedals.csv、reference_score.musicxml、segment_metadata.json 等），
但**输出到新根目录** `outputs/pedal_expansion/segments_v1/`，**不得触碰/污染**
`outputs/pedal_gold_standard/formal_20260828_v1/`（冻结档案）。

## 2. 五段输入定义

| # | 段（建议 sid） | ASAP 曲目目录 | performance（对齐源文件） | 窗口约束（主控裁定） |
|---|---|---|---|---|
| 1 | Chopin_Ballades_3_* | data/ASAP/Chopin/Ballades/3/ | Ko11M（`data/alignments/Chopin__Ballades__3__Ko11M.csv`，备选 LinPeng06M/Tan02） | 无空隙约束；窗口须覆盖 pedal 富集区（全曲 240 对/190 小节，任选密集段） |
| 2 | Liszt_Concert_Etude_S145_2_* | data/ASAP/Liszt/Concert_Etude_S145/2/ | Lu03M（`.../Liszt__Concert_Etude_S145__2__Lu03M.csv`，备选 Tario06M/Lo02/ZhangX03） | 无空隙约束；pedal 210 对/113 小节 |
| 3 | Rachmaninoff_Preludes_op_32_10_* | data/ASAP/Rachmaninoff/Preludes_op_32/10/ | Floril03（唯一 perf，`.../Rachmaninoff__Preludes_op_32__10__Floril03.csv`） | 短曲 span 240 QL；建议覆盖 pedal 连续区（m18 起 21 小节） |
| 4 | Chopin_Barcarolle_* | data/ASAP/Chopin/Barcarolle/ | Rozanski07M（`.../Chopin__Barcarolle__Rozanski07M.csv`，9 perf 均可用） | **窗口避开曲尾 QL>600**（空隙 @635.7–675.2，9 perf 一致） |
| 5 | Ravel_Miroirs_4_Alborada_del_gracioso_* | data/ASAP/Ravel/Miroirs/4_Alborada_del_gracioso/ | Chan02（`.../Ravel__Miroirs__4_Alborada_del_gracioso__Chan02.csv`，10 perf 均可用） | **窗口定原谱 m55–78（QL 165–243）**；必须避开空隙 @245.0–285.5（m78–92）。m82/85/89/91 四个 pedal 无对齐锚，不参与 ③ 判读 |

注：* = start_measure+1（段内首个 measure 编号，沿用 GS 命名惯例：sid 数字 = 起始 measure 序号）。

## 3. 执行步骤

### S1 窗口与段参数准备
按 GS 惯例（select_gold_standard.py 的 best_window / selection.json 结构）为 5 段生成
`outputs/pedal_expansion/selection_phase2A.json`：
- 每段含 `row`（composer/title/midi_performance/midi_score/xml_score 路径，对齐 ASAP 实际目录）、
  `start_measure`/`end_measure`、`bar_ql`、`time_sig`、`tempo_bpm`（从该曲 score/perf 实测）；
- 窗口须满足 §2 表约束，且每段窗口内含 **≥8 对完整 pedal（start+stop）**
  （例外：裁定 #P2A-1——Miroirs/4 豁免降为 **≥3 对**，见 trial8_phase2A_selection.md §8）；
- 窗口大小参考 GS 段（事件量 ~100–300 为佳，允许 ±）；
- 选窗后**必须验证**：窗口 QL 区间与对齐空隙（§2 表）不重叠（Miroirs/4 与 Barcarolle 硬约束）。

### S2 对齐文件准备
将 §2 表 alignment 源文件复制到 `<out_root>/_alignments/<seg_id>.csv`（seg_id 命名同 GS，
见 build_formal_segments 内部 `composer_title_{start_measure+1}`），文件名与 selection 一致。

### S3 分段构建
```
python tools/build_formal_segments.py --index N --selection outputs/pedal_expansion/selection_phase2A.json \
    --out outputs/pedal_expansion/segments_v1 --skip-render
```
N = 0..4。逐段执行，记录每段 build_log 输出与耗时。

### S4 reference 重建（P0 measure 粒度逻辑）
```
python tools/rebuild_segment_reference.py --segment <sid_1> --segment <sid_2> ... --dry-run   # 先看 diff
python tools/rebuild_segment_reference.py --segment <sid_1> --segment <sid_2> ...            # 落盘
```
脚本已支持 `--base`（commit 18b2489d41，默认仍为 formal_20260828_v1、向后兼容）：
```
python tools/rebuild_segment_reference.py --base outputs/pedal_expansion/segments_v1 \
    --segment <sid_1> --segment <sid_2> ... --dry-run   # 先看 diff
python tools/rebuild_segment_reference.py --base outputs/pedal_expansion/segments_v1 \
    --segment <sid_1> --segment <sid_2> ...             # 落盘
```
注意：`--base` 必须指向含该段 `build_log.json` 的根（segments_v1 的 build_log 由
build_formal_segments --out 自动生成）；40 段历史重跑仍用默认值（不传 --base）。
不得把扩样段写进 40 段冻结根。

### S5 六列自动标注
```
python tools/prefill_events.py  outputs/pedal_expansion/segments_v1/<sid>/...   # 语义三列 ②③①
python tools/annotate_events.py outputs/pedal_expansion/segments_v1/<sid>/...   # 决策三列 ④⑤⑥
```
段目录逐个传入。若任一列出现无法自动判定的行，保留留空并记入回报（与 GS 首标口径一致：
空值硬约束仅 ①–④，⑤⑥ 留空合法，裁决 #1）。

### S6 质检与回报（重要——向主控回报以下每段数据）
1. events.csv 行数、30 列结构、BOM/编码与 GS 段一致；
2. 六列填充统计（各列 none/值分布）；③ published_score_pedal 非 none 的行数（= F 可判行）；
3. 窗口内 pedal 覆盖：reference_pedals.csv 行数、measure 范围、与谱面 `<pedal>` 对账（应一致，Miroirs/4 注明 m82–91 排除）；
4. 对齐质量快照：该段 alignment 的匹配行数与窗口内空隙（应无大空隙）；
5. 与 GS 段目录结构对比清单（同文件集、无多余产物）。

### S7 复核清单生成（用户后续抽样）
对每段按 trial8 review CSV 格式生成 F/U/H/E 分组清单（复用 f4ce86f5a0 的清单生成方式），
暂存 `outputs/pedal_expansion/review/`，不 commit 复核产物（合并原则：不 push 复核 CSV）。

## 4. 验证点（全部通过才回报“完成”）

- [ ] 五段 events.csv 六列全填（语义三列 0 人工；决策三列规则复核），结构同 GS；
- [ ] 窗口与空隙无重叠（Miroirs/4 硬约束：窗口 ⊆ QL 165–243；Barcarolle：QL 起点 <600）；
- [ ] 每段 F 可判行（③ 非 none）与 pedal 对数量级匹配，不出现异常 0；
- [ ] reference_score.musicxml 的 `<pedal>` 与 reference_pedals.csv 对账一致；
- [ ] 未触碰 formal_20260828_v1 任何文件（git status 确认）；
- [ ] 无伪造/补写（空隙上不插值、不硬凑）。

## 5. 回报格式（给主控）

按段给出：sid、事件行数、六列分布、F 可判行数、pedal 覆盖 measure、对齐快照、异常清单；
以及 selection_phase2A.json 内容摘要、S4 是否需脚本小改的结论、git status（应只见 segments_v1 新产物与
可能的小改脚本）。

## 6. 红线重申

不动 `evals/`、`outputs/pedal_gold_standard/formal_20260828_v1/`、`CHECKSUMS.sha256`；
不伪造哈希、不补写缺失锚点；异常即停回报主控；复核产物不 commit/push。
