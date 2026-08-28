# Pilot 标注交接说明（给电脑端 AI / Codex / Claude Code）

## 1. 任务

在 **2 个 pilot 片段** 上完成 `events.csv` 的六列标注，用于校准踏板金标准规则：

- `outputs/pedal_gold_standard/pilot_20260820_v2/Chopin_Etudes_op_25_10_15/`
- `outputs/pedal_gold_standard/pilot_20260820_v2/Liszt_Mephisto_Waltz_222/`

**只标这两个。** 其余三个片段（Balakirev / Rachmaninoff / Beethoven）与旧目录 `pilot_20260820` 一律不动。

## 2. 第一步：拉取最新代码，确认预填已就位

预填文件、规则文档与建议文件已由 AI 直接推入本仓库。执行：

```bash
git pull
```

确认以下内容就位：

| 文件 | 检查点 |
|---|---|
| `Chopin_Etudes_op_25_10_15/events.csv` | 341 行（含表头），前三列已预填 |
| `Liszt_Mephisto_Waltz_222/events.csv` | 260 行（含表头），前三列已预填 |
| 各片段目录下 `notation_suggestions.csv` | 存在，含 event_id / 建议时值 / confidence / 理由 |
| `pilot_20260820_v2/ANNOTATION_RULES_v1.1.md` | 存在（本目录） |
| `pilot_20260820_v2/PILOT_ANNOTATION_HANDOFF.md` | 存在（本文件） |

> 若你本地对 `events.csv` 已有未推送的标注修改，**先备份再 pull**；git 会提示冲突，按备份内容处理。

预填状态：前三列已按规则填好；`notation_decision` / `review_class` / `review_note` 留空，待标注。

## 3. 第二步：阅读规则

必须通读两份文档后再动手：

1. `outputs/pedal_gold_standard/pilot_20260820_v2/ANNOTATION_GUIDE.md`（基础指南）
2. 本目录 `ANNOTATION_RULES_v1.1.md`（收紧版，半踏/编辑性省略/retake 校准的最终定义）

## 4. 第三步：逐行标注（重点 = 复核 + 裁决）

对每一行：

1. **复核前三列**：预填值是否合理？拿不准的看 `_work/candidates.csv` 和 `pedal_intervals.csv` 原始数据；**重点复核所有 `uncertain` 行**：
   - Chopin：6 行（边界区 [56.0,56.25] U [71.75,72.0]）
   - Liszt：5 行（边界区 [884.0,884.25] U [899.75,900.0]）
2. **填写 `notation_decision`**：先看 `notation_suggestions_<片段>.csv` 的建议（含 confidence 与理由），再决定：
   - 候选中有接近 `reference_duration_ql` 的 → 优先选它（Chopin 大量 `labeled` 行，参考时值 0.333 三连音）
   - 音短但踏板延长明显（`pedal_extension_ql > 0.25`）→ 保留短时值，延长交给 pedal（`pedal-only`），**不要强行 tie 或拉长**
   - 候选都不合适 → 写显式 QL
3. **填写 `review_class`**：`independent-voice` / `notation-shortening` / `pedal-only` / `other` / 留空
4. **填写 `review_note`**：简短理由。**下列行必须写 note**：
   - 所有 `uncertain` 行
   - 所有 `review_class` 非空的行
   - 所有演奏层 retake 与谱面无标记矛盾的行（写 `performance retake vs score none (editorial omission)`）

**对照谱面**：打开同目录 `p4_rule.svg`、`p4_learned.svg`、`p4_no_pedal.svg`、`reference_score.svg` 交叉验证记谱合理性。`reference_score.musicxml` / `reference_events.csv` 可查参考时值与 tie。

## 5. 禁止事项（红线）

- 不修改任何左侧 20 列
- 不触碰 `evals/`（尤其 `evals/C/`）、`audio2score/models/` 冻结模型
- 不改动其余 3 个 pilot 片段、不删旧目录 `pilot_20260820`（是否清理另行决策）
- 不使用 `split == test` 的 120 条演奏做任何训练/调参
- 不把 `notation_suggestions` 直接当答案复制——它是建议，不是金标准

## 6. 完成标准与回报

完成条件：两片段六列无空值；`uncertain` 比例 < 20%（预填基线：Chopin 6/340、Liszt 5/259）；每个片段至少 10 行 `review_note`。

完成后向用户回报一份**简短标注报告**（约 10 行）：
1. 两片段各自：总行数、`acoustic_sustain` 的 yes/no/uncertain 计数、`performance_pedal_action` 各值计数、`published_score_pedal` 各值计数
2. `notation_decision` 中：用了候选值 vs 显式值的行数
3. `review_class` 分布
4. `uncertain` 行的最终处置说明（改成了什么、为什么）
5. 标注过程中**拿不准的规则问题清单**（用于校准，逐条列出）
6. 发现的预填错误（若有）

## 7. 完成后推回 GitHub

在项目根目录执行（按实际 git 状态调整）：

```bash
git add outputs/pedal_gold_standard/pilot_20260820_v2/Chopin_Etudes_op_25_10_15/events.csv
git add outputs/pedal_gold_standard/pilot_20260820_v2/Liszt_Mephisto_Waltz_222/events.csv
git commit -m "annotate pilot v2: Chopin + Liszt (six columns) per rules v1.1"
git push
```

> 注意：仓库当前包含 `.venv-backend/`（21612 个文件）与 `tools/__pycache__/`，属于误推。建议另行处理（见第 8 节），不要混入本次提交。

## 8. 仓库卫生（建议但非本次必须）

- 将 `.venv-backend/`、`__pycache__/` 加入 `.gitignore`，并 `git rm -r --cached .venv-backend tools/__pycache__` 后提交，避免仓库继续膨胀。
- 旧 pilot 目录 `outputs/pedal_gold_standard/pilot_20260820`（v1）是否删除，待校准后与 v2 对比再决定，本次不动。
