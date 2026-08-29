# 给下一位 AI / Codex 的接手上下文

## 任务目标

将钢琴 WAV 经音频转录前端转为含 CC64 的 MIDI，再由 P3/P4 后端转为 MusicXML 与可视化五线谱。当前研究重点是 **P4：显式多声部、结构化时值、跨小节 tie、候选级学习排序与踏板感知解码**。不要把本项目的 MIDI->MusicXML 结论误写为端到端音频转录结论。

## 可信的完成状态

1. P4 的多声部导出、同声部无重叠约束、跨小节 tie-chain、导出后 accidental/tie 修复、pedal retake 规范化均已实现并回归。
2. 候选级 LightGBM 冻结模型位于 `audio2score/models/p4_asap_cross_piece_v1.{txt,json}`；必须校验：
   - `.txt` SHA-256：`31f58cf9bc022a686eedc60ed9af6c621eac69ba4569cccf24147bdd4877b666`
   - `.json` SHA-256：`7dbeadb4fd5549de5e984444d0c77921ad8b3dbdaa44e6798279fcec342c6fe6`
3. B 阶段证据在 `evals/B/`；C 阶段参考谱冻结评测在 `evals/C/frozen_test_20260817/`；严格 CC64 配对消融在 `evals/C/pedal_ablation_frozen_20260818/`。
4. C 踏板消融：120 performances、31 pieces、P4-R/P4-R-NP/P4-L/P4-L-NP 共 480/480 completed；0 failures；P4-L 与 P4-L-NP 的模型回退为 0；无踏板 XML 内 pedal 为 0/240。

## 关键入口与约束

| 文件 | 作用 |
|---|---|
| `audio2score/scripts/p4_multivoice_score.py` | P4 主导出入口。`--candidate-model` 启用冻结 LightGBM；`--no-pedal` 严格在解码前禁用 CC64 且不输出 pedal。 |
| `audio2score/scripts/structured_duration_decoder.py` | 生成 key-release / pedal-acoustic 等时值候选并做全局结构化解码。 |
| `audio2score/scripts/voice_assignment.py` | voice 事件、硬约束与验证。 |
| `audio2score/scripts/score_metrics.py` | 相对参考谱指标：pitch/onset/note/duration/tie/voice/pedal。 |
| `audio2score/scripts/run_c_stage_asap_eval.py` | C 冻结 P3/P4-R/P4-L 评测运行器。 |
| `audio2score/scripts/run_c_pedal_ablation.py` | 严格 P4 有/无踏板配对运行器。 |
| `audio2score/scripts/reconcile_midi_xml.py` | MIDI/导出 MusicXML 的 tie-chain 合并后逐音对账。 |

## 已冻结的实验边界

C 阶段只读 `data/asap_piece_manifest.csv` 中 `split == test` 的 120 条演奏，并复用 `data/alignments/` 的外部对齐。不得使用 test 结果调参、重训模型，或用系统输出反推对齐。若要新实验：

- 新建带日期的 `evals/C/<new_experiment>/`；
- 明确配置、模型哈希、随机种子与数据 manifest；
- 不覆盖既有 `evals/C/frozen_test_20260817/` 与 `evals/C/pedal_ablation_frozen_20260818/`；
- 不修改这些目录中的 `config.json`、`commands.log`、`manifest/`、`models/`、`pieces/`、`summary/`。

## 关键研究结论与措辞边界

- P4-R 有无 CC64：note F1、duration、tie、voice 的逐曲宏平均完全一致。
- P4-L − P4-L-NP：note F1 −0.00099，95% CI [−0.00210, 0.00006]；duration −0.00171，[−0.00417, 0.00092]；tie −0.00053，[−0.00505, 0.00349]；voice −0.00066，[−0.00185, 0.00039]。
- 可以说：已完成严格 CC64 配对消融；当前参考谱一致性未显示可检出的 CC64 正向增益；performance MIDI CC64 与出版谱 pedal 标注存在语义/粒度错配。
- 不可以说：系统已经实现高保真踏板记谱；P4-L 全面优于规则评分；本结果证明端到端 WAV 转录更好。

## 建议的下一步优先级

1. 构建 30--50 片段的人工踏板金标准，区分声学延音、演奏踏板动作、出版谱 pedal，并定义 retake/change、半踏、编辑性省略规则。
2. 在该金标准上评测 pedal event、延音时值与可读性；不要继续只报告全局平均 pedal F1。
3. 若继续模型工作，只在 train/valid 上进行候选特征或排序改进，保留作品隔离；重新冻结后才可碰 test。
4. 准备论文时，清晰分开候选级排序、B 导出忠实性、C 参考谱一致性和端到端前端误差四类证据。

## 常见陷阱

- `--no-pedal` 不可替换为导出后删除 XML pedal 标签；那不是严格消融。
- 指定 `--candidate-model` 却无法加载时，验证/评测应失败，不可安静回退为规则评分。
- MusicXML tie 对账必须将 tie-chain 合并；不要把跨小节拆分记作“多写音”。
- 历史运行曾因磁盘不足中断。完整证据很大；新实验开始前确认至少 12 GB 空闲空间。
- 旧脚本或历史 config 中可能保留旧机器绝对路径；新运行必须改为本包根目录下的相对路径。当前 `tools/transcribe_wav.py` 已做到这一点。


## 踏板金标准（2026-08-28 正式版）

- 正式金标准：`outputs/pedal_gold_standard/formal_20260828_v1/`，40 片段 / 4672 事件 / 12 作曲家（train 34 / validation 6）；`selection.json` 冻结（per_composer=10、ref≥10、排除 pilot 作品）。
- 管线：`select_gold_standard.py` → `validate_selection.py` → `precompute_alignments.py`（外部对齐冻结 `_alignments/`）→ `build_formal_segments.py --index N [--skip-render]`（候选生成窗口裁剪 ±16 QL，已验证窗口内输出与全曲一致）→ `prefill_events.py`（语义三列）→ `annotate_events.py`（决策三列）→ `evaluate_gold_standard.py`。
- 标注：六列全填；uncertain 131/4672（2.8%）；review_class：notation-shortening 1775 / pedal-only 1479 / independent-voice 136 / blank 1282；报告 `annotation_report_v1.md`。
- 评测 v1（`evaluation/gold_standard_eval_v1.{json,md}`）：rule 43.5% > learned 34.3%；踏板 start F1 0.36–0.41 / stop F1 0.22–0.23；语义错配 acoustic-yes&score-none 3334、perf-change&score-none 864。
- 评测 v2 + 融合实验（2026-08-29，`evaluation/gold_standard_eval_v2.{json,md}`、`fusion_experiment_v1.md`）：learned 负结果根因=42% 事件无参考时值、其标注规则与 rule 同构；learned 在有参考场景 26.8% > rule 19.0%。新增 `--fuse-alpha`（模型概率+规则先验线性融合，α=0.75）：p4_fused 一致率 42.9% 接近 rule，有参考 26.2% 保留模型优势、无参考 68.4% 大幅修复。40 片段 `p4_fused.musicxml` 已入库。
- 已知注意：
  1. `p4_learned` 必须在装有 `lightgbm` 的环境生成（缺包会静默回退规则评分，曾导致 rule/learned 结果相同）。
  2. 评测/报告输出必须写在 `outputs/` 内（sparse-checkout cone）；`results/` 不在 cone，git 不会跟踪。
  3. 并行构建有 `build_log.json` 写竞争风险（按 index 去重），慢片段可串行重跑补录。
- 待办：inter-annotator agreement 未做（论文声明"规则预填+专家复核"）；SVG 渲染可后补；token（github_pat_... 过期 2026-09-27）用完后请 revoke。

- 评测 v3 + 踏板位置实验（2026-08-29，`evaluation/gold_standard_eval_v3.{json,md}`、`pedal_placement_experiment_v1.md`）：新增 `--pedal-placement exact`（CC64 区间边界直接写 `<offset>`，替代吸附到最近音符）。踏板 start F1 0.408→0.818、stop F1 0.220→0.850（参考=演奏层）；时值一致率不变。根因：`find_nearest_note` 取下一音符导致系统性偏晚；exact 模式保留演奏层真实时序。40 片段 `p4_exact.musicxml` 已入库。

- 评测 v4 + 协议修正（2026-08-30，`evaluation/gold_standard_eval_v4.{json,md}`）：评测脚本升级——踏板参考三口径 `--pedal-ref {unclipped,inwindow,clipped}`（默认 inwindow：只评窗口内可见事件，v1–v3 的未裁剪口径含约 50 个窗口外假象事件）；1:1 贪心匹配（原 `any()` 可重复计数）；`change` 双计 start+stop；新增微平均、bootstrap 95% CI（seed=42, n=1000）、分级时值（0.05/0.25/1.0 QL + 中位绝对误差）。
- 推荐口径 inwindow：**p4_exact start 宏 0.858（CI [0.791,0.917]）/ 微 0.932；stop 宏 0.936（CI [0.875,0.983]）/ 微 0.970**（参考=演奏层，容差 0.25 QL）。unclipped 口径回归：微平均 0.896/0.926 与手工复算一致，宏 stop 0.854 同 v3、start 0.814（v3 0.822，差异来自贪心匹配）。
- 分级时值（宏平均）：@0.05 0.435 / @0.25 0.742 / @1.0 0.848 / 中位|err| 0.094（rule=exact=no_pedal）；p4_fused 中位 0.062、@0.25 0.749；p4_learned @1.0 0.853。**时值误差集中在 0.05–0.25 QL 微差，非整倍数错误**。
- 含义：协议修正后 stop 已 >0.9；start 宏平均 0.858（微 0.932）的残余缺口来自窗口内 CC64 量化偏移（~0.25–0.5 QL）与少量漏检（见 project_review_v1.md 的 P1-5）。论文应报 inwindow + 双聚合口径。
