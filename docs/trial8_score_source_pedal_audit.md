# 金标准 40 段 · 谱源踏板记号可得性审计

> 建档 2026-10-03（主控）｜方法：只读公开仓库内容（GitHub API / raw），主控实算，可复现。
> 目的：在把「客观基准 + 抽样复核」推广到全数据集（D1 = A，40 段）之前，先确认
> ③ `published_score_pedal` 到底有没有可复核内容。

## 1. 实测结论

1. **40 段的谱面记号几乎不存在**：40 段 `reference_score.musicxml` 合计出现 `<pedal` **8 处**、
   `reference_pedals.csv` 合计 **7 行**；其中 **37/40 段为 0 处 / 0 行**。有痕迹的仅 3 段：
   `Chopin_Scherzos_20_254`（5 处 / 3 行）、`Ravel_Miroirs_3_Une_Barque_181`（2 处 / 3 行）、
   另有 1 段 1 处 / 1 行。
2. **原因是上游谱源本身未记谱，不是坐标或管线缺陷**。抽查金标准曲目的上游
   `data/ASAP/**/xml_score.musicxml`：`Beethoven/Piano_Sonatas/16-1` 0 处、
   `Haydn/Keyboard_Sonatas/6-1` 0 处、`Mozart/Piano_Sonatas/12-3` 0 处、
   `Schubert/Impromptu_op.90_D.899/1|2|4` 各 0 处、`/3` 1 处。
3. **对照：Phase 2A 五段的谱源确实带记号**——`Chopin/Ballades/3` **480**、
   `Liszt/Concert_Etude_S145/2` **420**、`Ravel/Miroirs/4_Alborada_del_gracioso` **20**，
   与 2A 记录的原始 mark 数 480 / 420 / 20 **逐一吻合**。⇒ ③ 的唯一来源就是
   `data/ASAP/**/xml_score.musicxml`，不存在第二个谱源。
4. **40 段 `events.csv` 的 ③ 现状**：4672 行中仅 **14 行**非 `none`（全部在 `Chopin_Scherzos_20_254`：
   change 11 / stop 3），其余 39 段 ③ 全 `none`。② 侧充足：`hold` 3113 / `change` 864 /
   `release` 211 / `none` 353 / `uncertain` 131；`review_priority`：high 26 / medium 3506 / normal 1140；
   `auto_label_status`：unmatched 1984 / ambiguous-candidate 1146 / labeled 1019 /
   reference-duration-not-candidate 523。

## 2. 口径纠正（对既有文档的更正）

`docs/trial8_annotator_A_prompt.md` §1.2 记有「Ravel_Miroirs_3 34/139、Chopin_Scherzos_20 50/236 改动，
其余 6 段 0 改动」，并据以推出「其余段 ③ 首标值本就正确」。实测（对修复前父提交 `6696617b`）：

- `Chopin_Scherzos_20_254` ③ 非 `none` **50** 行（全 `change`）；`Ravel_Miroirs_3_Une_Barque_181`
  ③ 非 `none` **34** 行（start 9 / change 11 / stop 14）；`Schubert_Wanderer_fantasie_1189` **0** 行。
- 两段谱面真记号只有 **5 处与 2 处**，故基线-1 的 ③ 不可能是谱面来源，只能是
  **坐标错位把 performance 侧取值泄漏进 ③**（即被修复的那个 bug 的症状）；修复后清回 `none` 是**正确**行为。
- 因此 §1.2 的推理应更正为：**其余段两侧皆空（源未记谱），"0 改动" ≠ "本就正确"**。
  同理 `outputs/pedal_gold_standard/formal_20260828_v1/iaa/trial_A/review/trial8_A_review_*.csv`
  中 6 段的 `baseline_published_score_pedal` 列为空，不代表首标已正确。

## 3. 对全数据集方案的影响

- 2A 的「F 组（③ 命中行）抽样复核」口径**不能**直接套用到 40 段：40 段 F 组当前 ≈ 14 行（仅 1 段）。
- 40 段的客观基准主轴只能落在 **②（CC64 物理记录，内容充足）** 与 **①（数值判据）** 上；
  ③ 的方向需先定（决策项 **D6**）。
- ② 与 ① 不依赖谱面记号，不受本审计影响。

## 4. 复现口径（只读，任意人可重跑）

- 段清单：`outputs/pedal_gold_standard/formal_20260828_v1/*/events.csv`（40 段 / 4672 行）
- 记号计数：对同目录 `reference_score.musicxml` 计 `<pedal` 出现次数；参考行数取 `reference_pedals.csv` 行数
- 上游谱源：`data/ASAP/<Composer>/<Piece>/.../xml_score.musicxml`（共 235 个）
- 基线对照：`git show 6696617b:outputs/pedal_gold_standard/formal_20260828_v1/<seg>/events.csv`

## 5. 版本记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-10-03 | v1.0 | 建档（主控）：40 段谱源踏板记号可得性实测、口径纠正、对全数据集方案的影响、D6 决策入口。 |
