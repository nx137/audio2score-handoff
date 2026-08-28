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
