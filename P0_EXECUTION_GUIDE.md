# P0 修复执行手册（本地 AI 操作指南）

> 版本：v1（2026-09-01）
> 范围：P0 级四项修复的**执行验证**。代码已由主控修改并推送（commit `e6d72b9` → `c717a63` → `515a3a3`），你只需要按本手册运行命令、收集结果、回报。
> 对应代码：`audio2score/scripts/structured_duration_decoder.py`（P0-1）、`tools/p0_error_attribution.py`（P0-2/3/4）。

## 0. 角色与铁律（最重要，违反即失败）

0. **每次验证会话开始时，必须先从 GitHub 强制拉取并覆盖本地**（命令见第 1.5 节），
   确保与远端 `main` 完全一致；**严禁使用上一次会话遗留的陈旧本地文件**。
1. 你**只执行**本手册给出的命令，**不修改**任何代码、数据、文档。
2. 任何命令失败（退出码非 0 / 报错 / 结果异常）：**原样记录完整错误**（命令、退出码、stderr 最后 50 行、现象），按第 9 节模板回报主控。**严禁自行"修复"或绕过**。
3. 每一步成功后输出一行 `[步骤 N 完成]`。
4. push 前检查：**不得**把任何 token、密钥、`/tmp` 路径写进仓库。
5. 全量重建（步骤 1b）耗时长，可分段执行（`--range 0-9`、`10-19`……），但必须**全部完成**才算通过。

## 1. 环境准备

```bash
cd <仓库根目录>          # 含 audio2score/ tools/ outputs/ 的目录
# 先执行 1.5 节强制同步，再安装依赖
pip install pretty_midi music21 lightgbm
```

依赖缺一不可；`lightgbm` 用于 p4_learned/fused 管线。

## 1.5 强制同步（每次验证会话开始时必做，第 1 步）

```bash
cd <仓库根目录>
git fetch origin main
git status --porcelain     # 先查看本地状态
git reset --hard origin/main   # 强制用远端覆盖本地所有已跟踪文件
```

**规则**：
- `git status --porcelain` 若显示**任何**未提交/未推送的改动，**不要 reset**，原样记录并报告主控（可能上一次产物未 push 完成），等主控指示。
- 若 status 干净（无输出），执行 `git reset --hard origin/main`，然后确认：
  ```bash
  git log --oneline -1      # 应显示 44a0616 或更新的远端 commit
  git status --porcelain    # 应为空（干净工作区）
  ```
- 之后的所有命令都基于这份与远端一致的代码；每次会话（即使只隔几分钟）都要重新执行本同步。

## 2. 步骤 0：复现 P1.5 基线（只读）

```bash
python tools/verify_handoff.py
python tools/evaluate_gold_standard.py \
  --out outputs/pedal_gold_standard/formal_20260828_v1/evaluation/gold_standard_eval_v5.json \
  --bootstrap 200
```

**验收标准**（与 P1.5 报告一致）：
- p4_rule：dur@0.05 = 0.435，dur@0.25 = 0.742，dur@1.0 = 0.848
- p4_learned：dur@0.05 = 0.295，dur@0.25 = 0.707
- p4_exact：start F1 宏 0.889 / stop F1 宏 0.967（inwindow）

数字对不上 = 环境/数据有问题，**停止并回报**。

## 3. 步骤 1：P0-1 声部感知合法性验证

### 1a. 单片段 smoke（确认新代码生效且不崩）

```bash
A2S_EXTEND_CANDIDATES=1 python audio2score/scripts/p4_multivoice_score.py \
  --midi outputs/pedal_gold_standard/formal_20260828_v1/Chopin_Scherzos_20_254/performance_segment.mid \
  --out /tmp/p0_rule_on.musicxml --max-voices 12

A2S_VOICE_REASSIGN=0 A2S_EXTEND_CANDIDATES=1 python audio2score/scripts/p4_multivoice_score.py \
  --midi outputs/pedal_gold_standard/formal_20260828_v1/Chopin_Scherzos_20_254/performance_segment.mid \
  --out /tmp/p0_rule_off.musicxml --max-voices 12
```

**验收**：
- 两条命令 rc=0；
- 用 `diff <(grep -o '<duration>[0-9]*</duration>' /tmp/p0_rule_on.musicxml) <(grep -o '<duration>[0-9]*</duration>' /tmp/p0_rule_off.musicxml) | head` 能看到**时值差异**（P0-1 生效）；若完全无差异，说明迁移未触发，回报现象。
- 无 `ValueError` / `RuntimeError`。

### 1b. 全量重建（40 片段 × 5 管线；voice reassign 默认开启）

```bash
A2S_EXTEND_CANDIDATES=1 python tools/p1_5_extend.py --range 0-39
```

可分段：`--range 0-9`、`--range 10-19`、`--range 20-29`、`--range 30-39`（脚本幂等，可续传）。
**验收**：每片段 5 条管线（rule/learned/fused/exact/no_pedal）均打印 `ok`，无 `RuntimeError`。

### 1c. 评测 v6（P0-1 后的全量结果）

```bash
python tools/evaluate_gold_standard.py \
  --out outputs/pedal_gold_standard/formal_20260828_v1/evaluation/gold_standard_eval_v6.json
```

### 1d. 对比 v5 → v6（P0-1 效果）

读取两个 JSON 的 `summary.pipes`，逐管线列出：
| 管线 | dur@0.05 (v5/v6) | dur@0.25 (v5/v6) | dur@1.0 (v5/v6) | startF1宏 (v5/v6) | stopF1宏 (v5/v6) |

**特别注意**：
- p4_exact 的踏板 F1 **不得回归**（start 宏 0.889 / stop 宏 0.967 附近）；
- 任何管线出现 `dur@0.05` 大幅下降（>0.05）都要在回报中高亮。

## 4. 步骤 2：P0-2 无匹配输出归因

```bash
python tools/p0_error_attribution.py \
  --out outputs/pedal_gold_standard/formal_20260828_v1/evaluation/p0_error_attribution.json
```

**验收**：生成 `p0_error_attribution.json` 与 `.md`。
回报 `summary.unmatched_by_reason`（hand_mismatch / pitch_missing / onset_shift × 各管线），
并列出 hand_mismatch 非零的片段（`segments[*].<pipe>.reasons.hand_mismatch > 0`）。

## 5. 步骤 3：P0-3 learned 误差分解

- 读取 `p0_error_attribution.md` 第 3 节：各 review_class 的 @0.25 时值一致率（rule / learned / fused）。
- 原样回报该表。
- 若主控要求新数据重训（非 ASAP-train），等待主控补充命令，**不要自行下载/训练**。

## 6. 步骤 4：P0-4 三层归因

- 读取 `p0_error_attribution.md` 第 2 节：精确可达率 / oracle@0.25 / 不可达缺口按 review_class。
- 按以下模板回报：
  - 生成层：精确可达率（%），缺口 = 1 − 可达率
  - 排序/DP 层：oracle@0.25 − 实际 @0.25（rule 管线）
  - 结构层：hand_mismatch 计数 + 不可达且无 tie 的延音事件（从归因 md 中摘录）

## 7. 步骤 5：收尾（提交与推送）

```bash
git add -A
git status --short          # 人工检查：不应出现任何 token/密钥/tmp 文件
git commit -m "P0: 执行结果(v6评测+归因报告)"
git push
```

> push 凭据：使用本机已配置的 GitHub 凭据；若无，请在命令前设置
> `GITHUB_TOKEN` 环境变量（由用户提供），并**不要**把它写进任何文件或 commit message。

## 8. 步骤 6：不执行项

- 不修改 `NEXT_AI_CONTEXT.md` / `CHECKSUMS.sha256`（主控更新）。
- 不重训任何模型。
- 不删除/移动任何文件。

## 9. 回报模板（每个步骤一条，失败必填错误段）

```markdown
【步骤 N】状态：完成 / 失败
- 命令：<实际执行的命令>
- 退出码：<0 或具体值>
- 关键输出：<核心数字/日志摘要>
- 指标表：<如适用>
- 错误（仅失败时）：<stderr 最后 50 行 + 你的观察>
```

回报务必**完整、逐字**（尤其错误信息），主控据此决定下一步。
