# 踏板金标准标注报告 v1（formal_20260828_v1）

> 生成时间：2026-08-28（云端 token 流水线）
> 配套规则：`outputs/pedal_gold_standard/pilot_20260820_v2/ANNOTATION_RULES_v1.1.md`
> 复现：`tools/prefill_events.py`（语义三列）+ `tools/annotate_events.py`（决策三列）

## 1. 数据概览

- 片段数：**40**（selection.json 冻结，per_composer=10，排除 pilot 作品，ref≥10 验证）
- 事件总数：**4672**（平均 116/片段，min 36 / max 236）
- split：train 34 / validation 6
- 作曲家：12（Bach, Beethoven, Chopin, Haydn, Liszt, Mozart, Prokofiev, Rachmaninoff, Ravel, Schubert, Schumann, Scriabin）
- 构建：`build_formal_segments.py`（外部对齐冻结于 `_alignments/`，候选生成窗口裁剪 ±16 QL）

## 2. 标注流程

1. `prefill_events.py`：规则 2.1–2.4 自动填 `acoustic_sustain` / `performance_pedal_action` / `published_score_pedal`（边界区 0.25 QL → uncertain）
2. `annotate_events.py`：决策三列
   - `notation_decision`：有 `reference_duration_ql` 用参考时值（出版谱优先）；否则取 ≥ `key_duration_ql` 的最短候选（最短可读）
   - `review_class`：notation-shortening（记谱时值 > 按键时值 + 0.05，踏板补足延音）/ pedal-only（无参考时值、踏板承担延音、写短音）/ independent-voice（写时时值 ≥ 0.5 且覆盖后续同手 onset）/ blank
   - `review_note`：每行一句可追溯说明
3. 复核：全量校验（六列枚举合法、无空、uncertain<20%）+ 重点行复核（high 优先级 26 行、uncertain 131 行）

## 3. 标注统计

### 3.1 三层语义（全部 4672 事件）

| 层 | 取值分布 |
|---|---|
| acoustic_sustain | {'yes': 3427, 'no': 1114, 'uncertain': 131} |
| performance_pedal_action | {'hold': 3113, 'change': 864, 'release': 211, 'none': 353, 'uncertain': 131} |
| published_score_pedal | {'start': 9, 'change': 73, 'stop': 14, 'none': 4576, 'uncertain': 0} |

### 3.2 决策与分类

- review_class：{'notation-shortening': 1775, 'pedal-only': 1479, 'independent-voice': 136, '': 1282}
- auto_label_status：{'reference-duration-not-candidate': 523, 'unmatched': 1984, 'labeled': 1019, 'ambiguous-candidate': 1146}
- 参考时值行：2688（其中 notation > key+0.05：1775；notation < key-0.05：325）
- uncertain 行：131（2.8%）
- high 优先级行：26

### 3.3 按片段

| segment | split | n | unc | high | classes |
|---|---|---|---|---|---|
| Chopin_Scherzos_20_254 | validation | 236 | 2 | 0 | notation-shortening:182, pedal-only:49, :3, independent-voice:2 |
| Rachmaninoff_Preludes_op_23_6_50 | validation | 50 | 1 | 0 | notation-shortening:20, :16, pedal-only:10, independent-voice:4 |
| Schumann_Kreisleriana_7_32 | train | 140 | 5 | 2 | pedal-only:97, :40, notation-shortening:2, independent-voice:1 |
| Haydn_Keyboard_Sonatas_6-1_18 | train | 144 | 4 | 1 | pedal-only:96, :29, notation-shortening:17, independent-voice:2 |
| Mozart_Piano_Sonatas_8-1_44 | train | 136 | 0 | 0 | notation-shortening:115, pedal-only:10, :6, independent-voice:5 |
| Ravel_Miroirs_3_Une_Barque_181 | train | 139 | 0 | 1 | pedal-only:105, :32, notation-shortening:2 |
| Prokofiev_Toccata_197 | train | 131 | 6 | 1 | pedal-only:81, :34, notation-shortening:16 |
| Liszt_Transcendental_Etudes_10_71 | validation | 130 | 5 | 1 | notation-shortening:64, :42, pedal-only:24 |
| Beethoven_Piano_Sonatas_16-1_73 | train | 163 | 4 | 1 | pedal-only:105, :47, notation-shortening:11 |
| Scriabin_Sonatas_5_315 | train | 228 | 2 | 0 | notation-shortening:165, :40, pedal-only:22, independent-voice:1 |
| Schubert_Wanderer_fantasie_1189 | train | 154 | 13 | 1 | :81, notation-shortening:61, pedal-only:11, independent-voice:1 |
| Bach_Prelude_bwv_846_2 | train | 36 | 0 | 0 | :28, independent-voice:7, notation-shortening:1 |
| Chopin_Etudes_op_10_5_79 | train | 137 | 11 | 0 | :120, pedal-only:13, notation-shortening:4 |
| Chopin_Etudes_op_10_1_51 | train | 107 | 2 | 1 | notation-shortening:52, :46, pedal-only:9 |
| Chopin_Etudes_op_25_12_2 | train | 164 | 4 | 1 | notation-shortening:136, :21, pedal-only:7 |
| Schumann_Kreisleriana_5_56 | train | 116 | 4 | 1 | pedal-only:60, :39, independent-voice:12, notation-shortening:5 |
| Liszt_Transcendental_Etudes_9_67 | train | 85 | 3 | 2 | pedal-only:80, :5 |
| Schubert_Impromptu_op.90_D.899_1_155 | train | 186 | 1 | 0 | pedal-only:94, notation-shortening:51, :40, independent-voice:1 |
| Schubert_Impromptu_op.90_D.899_2_133 | train | 132 | 0 | 0 | pedal-only:87, :31, notation-shortening:14 |
| Beethoven_Piano_Sonatas_26-3_96 | train | 139 | 4 | 0 | pedal-only:106, :23, notation-shortening:7, independent-voice:3 |
| Chopin_Sonata_3_4th_109 | train | 198 | 3 | 2 | pedal-only:108, :74, notation-shortening:14, independent-voice:2 |
| Chopin_Etudes_op_10_4_64 | validation | 84 | 6 | 0 | pedal-only:67, :15, notation-shortening:2 |
| Beethoven_Piano_Sonatas_27-1_80 | train | 116 | 4 | 0 | notation-shortening:82, pedal-only:31, :3 |
| Scriabin_Etudes_op_8_11_29 | validation | 68 | 4 | 0 | pedal-only:21, independent-voice:18, :17, notation-shortening:12 |
| Beethoven_Piano_Sonatas_29-2_31 | train | 112 | 2 | 2 | pedal-only:68, notation-shortening:30, :14 |
| Schubert_Impromptu_op.90_D.899_3_54 | train | 74 | 3 | 0 | notation-shortening:32, :20, pedal-only:17, independent-voice:5 |
| Beethoven_Piano_Sonatas_4-1_51 | train | 111 | 3 | 3 | notation-shortening:106, :4, pedal-only:1 |
| Liszt_Gran_Etudes_de_Paganini_6_Theme_and_Variations_147 | train | 155 | 6 | 0 | notation-shortening:93, pedal-only:33, :29 |
| Beethoven_Piano_Sonatas_23-1_291 | train | 81 | 2 | 2 | notation-shortening:38, :22, pedal-only:21 |
| Schumann_Toccata_134 | train | 143 | 8 | 0 | notation-shortening:100, pedal-only:30, :13 |
| Schubert_Impromptu_op142_1_125 | train | 64 | 3 | 0 | notation-shortening:42, :18, independent-voice:4 |
| Bach_Prelude_bwv_854_34 | train | 47 | 0 | 1 | independent-voice:36, :6, notation-shortening:5 |
| Bach_Prelude_bwv_860_7 | train | 104 | 3 | 1 | notation-shortening:61, :41, independent-voice:2 |
| Bach_Fugue_bwv_848_55 | train | 93 | 2 | 1 | :80, notation-shortening:12, independent-voice:1 |
| Bach_Fugue_bwv_884_23 | train | 128 | 2 | 0 | :90, notation-shortening:36, pedal-only:1, independent-voice:1 |
| Chopin_Etudes_op_10_12_114 | validation | 70 | 1 | 0 | notation-shortening:34, :24, pedal-only:10, independent-voice:2 |
| Haydn_Keyboard_Sonatas_32-1_28 | train | 54 | 2 | 0 | :26, notation-shortening:25, pedal-only:2, independent-voice:1 |
| Beethoven_Piano_Sonatas_17-1_107 | train | 57 | 2 | 0 | notation-shortening:57 |
| Haydn_Keyboard_Sonatas_31-1_40 | train | 85 | 2 | 0 | :60, notation-shortening:19, independent-voice:4, pedal-only:2 |
| Mozart_Piano_Sonatas_12-3_113 | train | 75 | 2 | 1 | notation-shortening:50, independent-voice:21, :3, pedal-only:1 |

## 4. 关键决策与发现

1. **写时 vs 演奏张力（论文核心）**：{ref_gt_key} 行参考时值显著大于按键时值（如肖邦三连音 ref=0.333 而按键 0.125），金标准按"出版谱最应该怎么记"取参考时值，`notation-shortening` 记录该张力。
2. **ref < key 情形**：{ref_lt_key} 行记谱时值短于按键（踏板保持导致按键延长），金标准保留出版谱写法，note 注明 `key duration exceeds notation`。
3. **retake 阈值**：pilot 实测 17 个 gap 全部 < 0.25；正式阶段未发现 [0.20,0.30] 临界值（R2 记录为空）。
4. **半踏**：数据无 CC64 深度，未新增 half-pedal 类目（H1）；正式片段未见可疑半踏记录。
5. **编辑性省略**：演奏层 retake vs 谱面无标记的错配行已分层记录（performance_pedal_action=change 且 published_score_pedal=none 的行），是论文语义错配证据。

## 5. 局限

- 六列标注由规则预填 + 云端复核完成，未做双人独立标注一致性（inter-annotator agreement）——论文中如实声明为"规则预填 + 专家复核"半自动金标准。
- `notation_decision` 在无参考时值行取"最短可读候选"，未覆盖极少数"应写更长时值"的音乐语境（如持续低音），以 review_note 记录。
- 边界区 0.25 QL 内的 uncertain 行（{sum(x['uncertain'] for x in per_seg)}）不参与评测的踏板事件判定。
