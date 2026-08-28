# 交接资产清单

**快照日期：2026-08-19**。本清单描述交接包根目录中实际包含的资产；`CHECKSUMS.sha256` 对关键入口、模型、配置、汇总与报告提供逐文件 SHA-256。

## A. 运行必需资产

| 路径 | 内容 | 用途 | 状态 |
|---|---|---|---|
| `audio2score/scripts/` | 26 个 Python 源文件（含 4 个测试） | 记谱、评测、训练和渲染 | 必需 |
| `audio2score/models/p4_asap_cross_piece_v1.txt` | 冻结 LightGBM Booster | P4-L 候选级评分 | 必需 |
| `audio2score/models/p4_asap_cross_piece_v1.json` | 特征顺序元数据 | 与 Booster 匹配 | 必需 |
| `audio2score/samples/` | 最小 MIDI/MusicXML 示例 | 本地 smoke | 必需 |
| `environment/requirements-backend.txt` | 后端 Python 依赖 | 安装记谱、评测、渲染环境 | 必需 |
| `environment/INSTALL.md` | 安装与运行步骤 | 新机器启动 | 必需 |
| `tools/verify_handoff.py` | 只读完整性检查 | 新机器到货验收 | 必需 |
| `tools/run_smoke_tests.sh` | 单元测试与单样例回归 | 新机器功能验收 | 必需 |

## B. 端到端 WAV 输入资产

| 路径 | 内容 | 用途 | 状态 |
|---|---|---|---|
| `frontend/piano_transcription/` | 历史音频转录推理源码与约 172 MB CPU 权重 | WAV -> MIDI | 端到端运行必需 |
| `frontend/test_piano.wav` | 短音频样例 | 前端人工验证 | 可选 |
| `environment/requirements-frontend.txt` | 前端独立依赖 | 单独虚拟环境安装 | 端到端运行必需 |
| `tools/transcribe_wav.py` | 相对路径前端命令 | 避免旧机器绝对路径 | 端到端运行必需 |

未包含 Windows 专用 Python/FFmpeg 二进制分发包：它们不是跨平台运行的必要条件，且会造成重复体积。请在新机器上通过系统包管理器或官方渠道安装 FFmpeg（如需要）。

## C. 数据与评测复现资产

| 路径 | 内容 | 用途 | 状态 |
|---|---|---|---|
| `data/ASAP/` | ASAP 的项目所需 MIDI、MusicXML、标注、元数据；无音频、无 Git 元数据 | 候选监督与 C 阶段参考 | 复现评测必需 |
| `data/asap_piece_manifest.csv` | 作品隔离 train/valid/test 清单 | 冻结 test 选择 | 必需 |
| `data/alignments/` | 外部对齐 CSV（1036 个） | C 阶段对齐索引 | 复现 C 阶段必需 |
| `data/batch_summary.csv` | 对齐批处理与 test 对齐索引 | C 运行器输入 | 复现 C 阶段必需 |
| `evals/B/` | 两次 B 阶段 regression gate 原始证据 | 历史可追溯性 | 必需，只读 |
| `evals/C/frozen_test_20260817/` | 冻结 P3/P4-R/P4-L 参考谱评测证据 | 历史可追溯性 | 必需，只读 |
| `evals/C/pedal_ablation_frozen_20260818/` | 480 条严格 CC64 消融记录、XML、指标、日志和汇总 | 历史可追溯性 | 必需，只读 |

## D. 成果与研究文档

`results/reports/` 包含 B 阶段协议、盲评材料和闭环验收记录、两份 C 阶段 PDF/LaTeX 实验报告、项目计划书及领域调研；`results/examples/` 包含 M0/P3/P4 样例的 MIDI、MusicXML、SVG/PNG 和验证说明。它们不是运行后端所必需，但属于项目成果和论文证据，应一并保存。

## E. 有意未纳入的内容

| 类别 | 原因 | 处理建议 |
|---|---|---|
| Python `__pycache__`、旧运行输出、临时 render/chunk/candidate 缓存 | 可再生成，且不构成证据 | 不迁移 |
| ASAP `.git/` 元数据 | 上游历史非运行必要，显著增加体积 | 如需上游版本历史，从原始仓库重新克隆 |
| 原始 MAESTRO/ASAP 音频 | ASAP 快照本身不分发；本项目 C 阶段基于 MIDI/参考谱 | 根据上游指引和许可自行获取 |
| Windows 专用 Python/FFmpeg 安装包 | 与新机器 OS 强绑定、可官方安装 | 按目标系统重新安装 |
| 旧机器绝对路径与任何秘密 | 不可移植，也不应转交 | 使用相对路径；本包不含凭证 |

## F. 固定模型哈希

| 文件 | SHA-256 |
|---|---|
| `audio2score/models/p4_asap_cross_piece_v1.txt` | `31f58cf9bc022a686eedc60ed9af6c621eac69ba4569cccf24147bdd4877b666` |
| `audio2score/models/p4_asap_cross_piece_v1.json` | `7dbeadb4fd5549de5e984444d0c77921ad8b3dbdaa44e6798279fcec342c6fe6` |

完整性检查命令：`python tools/verify_handoff.py`。
