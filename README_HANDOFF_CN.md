# 钢琴音频转可视化五线谱：可复现交接包

**交接版本：2026-08-19**  
**项目状态：P4 多声部记谱、冻结候选模型、B/C 阶段评测与严格 CC64 消融均已完成；论文级踏板人工金标准尚未开展。**

本目录是可整体复制的项目快照。它包含可执行源码、冻结模型、ASAP 的项目所需 MIDI/MusicXML 数据与对齐、冻结评测证据、成果报告、样例以及自动检查脚本。请在解压后的根目录运行，所有新生成文件写入 `outputs/` 或新的日期目录，**不得覆盖 `evals/` 中的冻结证据**。

## 从这里开始

1. 阅读 `environment/INSTALL.md`，建立后端 Python 环境。
2. 执行 `python tools/verify_handoff.py`，确认文件、模型和证据记录完整。
3. 执行 `bash tools/run_smoke_tests.sh`，运行单元测试和最小导出。
4. 让下一位 AI 先通读 `NEXT_AI_CONTEXT.md`；它给出了代码入口、结论边界和不可触碰的冻结资产。

## 目录一览

| 目录 / 文件 | 用途 | 是否必需 |
|---|---|---|
| `audio2score/scripts/` | MIDI->MusicXML、渲染、对账、训练、B/C 评测源码与测试 | 是 |
| `audio2score/models/` | 冻结 LightGBM 模型和哈希说明 | 是 |
| `audio2score/samples/` | 小型 MIDI/MusicXML smoke 样例 | 是 |
| `frontend/` | WAV->MIDI 前端源码、CPU 权重、短 WAV 样例 | 如需端到端 WAV 输入则是 |
| `data/ASAP/` | ASAP 所需 MIDI/MusicXML、标注；不含原始音频 | 复现 C 阶段/再训练时是 |
| `data/alignments/` | 冻结评测所复用的外部对齐 CSV | 复现 C 阶段时是 |
| `data/asap_piece_manifest.csv` | 作品隔离 split 清单 | 是 |
| `data/batch_summary.csv` | 对齐索引和批处理记录 | 复现 C 阶段时是 |
| `evals/B/`、`evals/C/` | 已冻结的 B/C 实验原始证据 | 是；只读 |
| `results/` | 已交付报告、协议和乐谱示例 | 是 |
| `environment/` | 依赖清单与安装说明 | 是 |
| `tools/` | 验收、smoke、相对路径 WAV->MIDI 脚本 | 是 |
| `MANIFEST.md`、`CHECKSUMS.sha256` | 资产清单与完整性校验 | 是 |

## 最小运行示例

```bash
mkdir -p outputs
python audio2score/scripts/p4_multivoice_score.py \
  --midi audio2score/samples/test_performance.mid \
  --out outputs/example.musicxml \
  --candidate-model audio2score/models/p4_asap_cross_piece_v1 \
  --max-voices 12 --divisors 8,4,3

python audio2score/scripts/render_score.py \
  --musicxml outputs/example.musicxml --out-svg outputs/example.svg
```

完整端到端 WAV->MIDI->MusicXML：先按 `environment/INSTALL.md` 安装前端环境，再执行：

```bash
python tools/transcribe_wav.py --wav frontend/test_piano.wav --out outputs/from_wav.mid
python audio2score/scripts/p4_multivoice_score.py \
  --midi outputs/from_wav.mid --out outputs/from_wav.musicxml \
  --candidate-model audio2score/models/p4_asap_cross_piece_v1 --max-voices 12
```

## 冻结结论（不可改写为更强主张）

- C 阶段严格 CC64 消融覆盖 **120 个演奏、31 首作品、4 条管线、480/480 完成组合**；失败数为 0。
- 无踏板条件在解码前传入空 CC64 区间，并审计到 **0/240 无踏板 XML 含 `<pedal>`**；P4-L 没有 LightGBM 回退。
- P4-R 与 P4-R-NP 在 note F1、时值、tie、voice 上完全一致；P4-L 相对 P4-L-NP 的主指标差异的 95% 配对 bootstrap 区间均跨越 0。
- 因此，当前证据不支持“CC64 对相对参考谱一致性存在可检出的正向增益”；pedal F1 约 0.002，不能宣称高质量踏板记谱。

详见 `results/reports/C阶段_冻结踏板消融实验报告_20260818.pdf` 和 `NEXT_AI_CONTEXT.md`。

## 许可与使用边界

`data/ASAP/` 随附上游 `LICENSE.md`；其说明为 **CC BY-NC-SA 4.0**，仅应在该许可范围内使用与再分发。ASAP 原始音频不在本包内；如需按上游说明关联 MAESTRO 音频，请自行获取并遵守其许可。前端权重及历史推理代码的具体再分发边界尚未在本项目中独立核验，发布前应复核来源许可。更多内容见 `LICENSES_AND_DATA_NOTICES.md`。
