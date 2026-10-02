# Phase 2A 标注前快照入库执行卡（本地 AI 执行）

**目的**：把 Phase 2A 的**标注者开工前基线**整体入库——分段产物、复核工作表、抽样表（含填写版）、渲染谱面、
两份独立审计报告——使"标注者拿到的到底是什么"在仓库里可复核、可比对。人工复核填写后的 CSV **另行提交**，
因此本快照就是人工判定的 diff 基线。

## 0 前提

- 执行前先 `git pull --ff-only`；此时远端 HEAD 应为本执行卡自身的提交（其父提交为 `77dd3cd2`）。
- 入库内容**全部由工具生成**，不得手工编辑任何文件。
- 本卡是 Phase 2A 迄今**唯一一次允许的写操作**（`git add / commit / push`）；除此之外不改任何文件。

## 1 只读清点（先贴回，再提交）

```bat
python -c "import subprocess,collections;o=[l for l in subprocess.run(['git','ls-files','--others','--exclude-standard'],capture_output=True,text=True).stdout.splitlines() if l.strip()];c=collections.Counter('/'.join(l.split('/')[:3]) for l in o);[print(k,v) for k,v in sorted(c.items())];print('TOTAL',len(o))"
```

预期（分目录计数）：

| 目录 | 文件数 | 说明 |
| --- | --- | --- |
| `outputs/pedal_expansion/segments_v1` | 约 67 | 5 段 × 12 件 + `_alignments/` 5 个对齐 csv + `build_log.json` + `evaluation/segment_reference_rebuild.json` |
| `outputs/pedal_expansion/review` | 约 86 | 5 复核表 + 5 抽样表 + 5 manifest + 5 工作表 + 3 个隔离 `.invalid_v2_perfdomain` + `rendered/` 62 件 + `phase2a_extraction_audit.json` |
| `outputs/pedal_expansion/evaluation` | 1 | `phase2a_score_pedal_audit.json` |

```bat
python -c "import csv,glob,os;[print(os.path.basename(f), sum(1 for _ in csv.DictReader(open(f,encoding='utf-8-sig')))) for f in sorted(glob.glob('outputs/pedal_expansion/review/phase2A_A_review_*.csv')) if '_sample' not in f]"
```

预期：`Chopin_Ballades_3_55 249`、`Chopin_Barcarolle_1 85`、`Liszt_Concert_Etude_S145_2_1 383`、
`Rachmaninoff_Preludes_op_32_10_24 45`、`Ravel_Miroirs_4_Alborada_del_gracioso_25 21`，合计 **783**（= 第二份审计报告的 `TOTAL rows=783`）。

```bat
python -c "import csv,glob,os;[print(os.path.basename(f),[(r['row_no'],r['onset_location'],r['hand'],r['pitch'],r['published_score_pedal']) for r in csv.DictReader(open(f,encoding='utf-8-sig')) if not (r.get('reference_onset_ql') or '').strip()]) for f in sorted(glob.glob('outputs/pedal_expansion/review/phase2A_A_review_*.csv')) if '_sample' not in f]"
```

预期：共 **6** 行 `reference_onset_ql` 为空（Ballades 1、Barcarolle 0、S145/2 1、op32/10 3、Miroirs/4 1）。
这 6 行在 score 侧没有 onset，第 3 列按构造只能是 `none`、**无法自动复核**，需人工读渲染谱确认该处没有 pedal 记号；
把行号与 `onset_location` 抄给复核者。

## 2 提交并推送（唯一一次写操作）

```bat
git add outputs/pedal_expansion/segments_v1 outputs/pedal_expansion/review outputs/pedal_expansion/evaluation
git diff --cached --shortstat
git commit -m "snapshot(phase2A): pre-annotator baseline (segments_v1, review, evaluation)" -m "Freezes what annotator A is given before the 209-row review: five segment outputs (12 artifacts each, alignment copies, build_log, reference rebuild log), the full 17-column review sheets (783 rows), the 209-row stratified samples with manifests, the score-domain worksheets, the 62 rendered files (per-segment PDF, per-page PNG/SVG, probe artifacts) and both independent audit reports." -m "Content is tool-generated, no hand edits. The FILLED review sheets are committed separately after the review, so this commit is the diff base for the human judgements." -m "The do-not-commit note in tools/phase2a_audit_score_pedal.py and in docs/trial8_phase2A_coordinate_conventions.md section 6 is superseded by this snapshot decision."
git log --oneline -3
git push origin main
git status --porcelain
```

预期：`git diff --cached --shortstat` 约 150 个文件；`git push` 成功；推送后 `git status --porcelain` **为空**。

## 3 红线

- 只允许 `git add` 上述三个目录；**不要** `git add -A`，不要动 `data/`、`tools/`、`docs/`、`evals/`。
- 若 `git push` 要求凭据或失败：立即停、原样贴回，不要改用其它方式（凭据由主控处理）。
- 不手工编辑任何入库文件；两份审计 JSON 保持工具原样输出。
- 提交后贴回：`git diff --cached --shortstat`、`git log --oneline -3`、`git push` 输出、`git status --porcelain`。
