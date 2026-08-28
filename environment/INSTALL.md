# 在新电脑安装与启动

## 0. 前置条件

建议 Linux、macOS 或 Windows + WSL2；至少预留 **12 GB 可用磁盘**（本交接包解压、临时输出及评测会同时占用空间），内存 8 GB 以上。后端推荐 Python 3.10--3.12；历史音频前端建议单独使用 Python 3.9 或 3.10。以下命令均从交接包根目录执行。

不需要、也不应复制旧电脑的环境变量、令牌或任何凭证。本包不包含此类内容。

## 1. 后端（MIDI -> MusicXML / 评测）

```bash
python3 -m venv .venv-backend
# Linux/macOS
source .venv-backend/bin/activate
# Windows PowerShell: .venv-backend\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r environment/requirements-backend.txt
```

可选：如需从命令行调用外部 Verovio 而不是 Python 包，请自行安装 Verovio CLI；本项目的 `render_score.py` 使用 Python `verovio` 包即可。生成或编辑中文 LaTex 报告时另行安装 TeX Live/XeLaTeX + CTeX。

## 2. 音频前端（WAV -> MIDI）

这是历史高分辨率带踏板钢琴转录前端，权重和推理源码在 `frontend/piano_transcription/`。它与后端分开建环境，避免旧版深度学习依赖污染记谱与评测环境：

```bash
python3.10 -m venv .venv-frontend
source .venv-frontend/bin/activate
python -m pip install --upgrade pip
python -m pip install -r environment/requirements-frontend.txt
```

CPU 推理可用，但较慢；若安装的 PyTorch 与本机硬件不匹配，请按 PyTorch 官方说明安装对应版本。`tools/transcribe_wav.py` 使用相对路径定位本包权重，不依赖旧电脑的绝对路径。

## 3. 快速验收

先激活后端环境，再运行：

```bash
python tools/verify_handoff.py
bash tools/run_smoke_tests.sh
```

验收会检查关键资产、冻结模型 SHA-256、C 阶段证据计数，并执行后端单元测试和一条 MIDI -> MusicXML 导出。它不会重跑 120 演奏的冻结评测，也不会写入 `evals/`。

## 4. 常用命令

规则 P4：

```bash
python audio2score/scripts/p4_multivoice_score.py \
  --midi audio2score/samples/test_performance.mid \
  --out outputs/p4_rule.musicxml --max-voices 12 --divisors 8,4,3
```

冻结 LightGBM P4：

```bash
python audio2score/scripts/p4_multivoice_score.py \
  --midi audio2score/samples/test_performance.mid \
  --out outputs/p4_learned.musicxml \
  --candidate-model audio2score/models/p4_asap_cross_piece_v1 \
  --max-voices 12 --divisors 8,4,3
```

严格无踏板消融条件：在上面 P4 命令末尾加 `--no-pedal`。这会在解码前屏蔽 CC64，不是导出后删除 XML 标签。

渲染：

```bash
python audio2score/scripts/render_score.py \
  --musicxml outputs/p4_learned.musicxml --out-svg outputs/p4_learned.svg
```

完整冻结评测是高耗时、高磁盘占用操作；只有在明确建立新实验目录、且不覆盖历史证据时才运行。详见 `NEXT_AI_CONTEXT.md`。
