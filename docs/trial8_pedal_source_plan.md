# ③ 谱源补全方案（pedal-source plan）v0.1

> 建档 2026-10-03（主控）。依据：`docs/trial8_score_source_pedal_audit.md`（40 段谱源实测）、
> `outputs/pedal_expansion/score_pedal_scan.csv`（235 个 ASAP 谱的 `<pedal>` 扫描）。
> 决议：**D6 = 补谱源**（2026-10-03）：为 ③ 列补上真实存在的谱面踏板记号层。

## 1. 实测：40 段金标准分成两类

| 类 | 段数 | 判定 | 处置 |
| --- | --- | --- | --- |
| **A 类** | 14 | 该作品的 ASAP 谱**本来就含** `<pedal>`，只是金标准当前窗口没覆盖到 | 用**现有工具链**加 pedal-rich 新段（与 Phase 2A 同款流程）；**不改**金标准既有 40 段的窗口与产物 |
| **B 类** | 26 | 该作品的 ASAP 谱**完全无** `<pedal>` | 走 §3 外部补谱协议（需新工具 + 人工取谱 + 许可留档） |

### A 类逐段（作品谱记号数 / 含记号小节数）

| 金标准段 | ASAP 谱 | 记号数 | 含记号小节 |
| --- | --- | --- | --- |
| `Beethoven_Piano_Sonatas_29-2_31` | `Beethoven/Piano_Sonatas/29-2` | 4 | 4 |
| `Chopin_Etudes_op_10_1_51` | `Chopin/Etudes_op_10/1` | 5 | 5 |
| `Chopin_Etudes_op_10_5_79` | `Chopin/Etudes_op_10/5` | 13 | 10 |
| `Chopin_Etudes_op_25_12_2` | `Chopin/Etudes_op_25/12` | 1 | 1 |
| `Chopin_Scherzos_20_254` | `Chopin/Scherzos/20` | 420 | 235 |
| `Chopin_Sonata_3_4th_109` | `Chopin/Sonata_3/4th` | 14 | 13 |
| `Liszt_Transcendental_Etudes_10_71` | `Liszt/Transcendental_Etudes/10` | 10 | 5 |
| `Liszt_Transcendental_Etudes_9_67` | `Liszt/Transcendental_Etudes/9` | 102 | 43 |
| `Prokofiev_Toccata_197` | `Prokofiev/Toccata` | 1 | 1 |
| `Ravel_Miroirs_3_Une_Barque_181` | `Ravel/Miroirs/3_Une_Barque` | 279 | 131 |
| `Schubert_Impromptu_op.90_D.899_3_54` | `Schubert/Impromptu_op.90_D.899/3` | 1 | 1 |
| `Schumann_Kreisleriana_7_32` | `Schumann/Kreisleriana/7` | 2 | 2 |
| `Scriabin_Etudes_op_8_11_29` | `Scriabin/Etudes_op_8/11` | 2 | 1 |
| `Scriabin_Sonatas_5_315` | `Scriabin/Sonatas/5` | 17 | 14 |

### B 类逐段（需外部谱源）

| 金标准段 |
| --- |
| `Bach_Fugue_bwv_848_55` |
| `Bach_Fugue_bwv_884_23` |
| `Bach_Prelude_bwv_846_2` |
| `Bach_Prelude_bwv_854_34` |
| `Bach_Prelude_bwv_860_7` |
| `Beethoven_Piano_Sonatas_16-1_73` |
| `Beethoven_Piano_Sonatas_17-1_107` |
| `Beethoven_Piano_Sonatas_23-1_291` |
| `Beethoven_Piano_Sonatas_26-3_96` |
| `Beethoven_Piano_Sonatas_27-1_80` |
| `Beethoven_Piano_Sonatas_4-1_51` |
| `Chopin_Etudes_op_10_12_114` |
| `Chopin_Etudes_op_10_4_64` |
| `Haydn_Keyboard_Sonatas_31-1_40` |
| `Haydn_Keyboard_Sonatas_32-1_28` |
| `Haydn_Keyboard_Sonatas_6-1_18` |
| `Liszt_Gran_Etudes_de_Paganini_6_Theme_and_Variations_147` |
| `Mozart_Piano_Sonatas_12-3_113` |
| `Mozart_Piano_Sonatas_8-1_44` |
| `Rachmaninoff_Preludes_op_23_6_50` |
| `Schubert_Impromptu_op.90_D.899_1_155` |
| `Schubert_Impromptu_op.90_D.899_2_133` |
| `Schubert_Impromptu_op142_1_125` |
| `Schubert_Wanderer_fantasie_1189` |
| `Schumann_Kreisleriana_5_56` |
| `Schumann_Toccata_134` |

### 附：ASAP pedal 富集池（天然候选池）

- 扫描 235 个 ASAP 谱，**64 个含 `<pedal>`**：Chopin 21 / Liszt 14 / Beethoven 13 / Schumann 5 / Ravel 4 /
  Scriabin 2 / Brahms 1 / Debussy 1 / Prokofiev 1 / Rachmaninoff 1 / Schubert 1。
- Phase 2A 已用其中 5 个（`Chopin/Ballades/3`、`Chopin/Barcarolle`、`Liszt/Concert_Etude_S145/2`、
  `Rachmaninoff/Preludes_op.32/10`、`Ravel/Miroirs/4_Alborada_del_gracioso`）；**尚未使用约 60 个**。
- 这是把 ③ 证据面做厚的主要来源，且**零外部依赖、零许可风险**。

## 2. A 类执行（现有工具，零外部数据）

流程与 Phase 2A 一致，只对新段操作：
`phase2a_window_scan.py` → 定窗 → `build_formal_segments.py` → `rebuild_segment_reference.py` →
`prefill_events.py` / `annotate_events.py`（六列）→ `phase2a_audit_extraction.py` +
`phase2a_audit_score_pedal.py`（双审计）→ `phase2a_sample_review.py` + 渲染 → 抽样人工复核 → 判定。

硬约束：

- **不得修改**金标准既有 40 段的窗口与已锚定产物（保持可复现与哈希稳定）；
- 新段产物进入新目录，并同批锚定 CHECKSUMS；
- 判定口径沿用 2A：F 组 + `reviewer_confirm` 确认率 ≥ 95%%。

## 3. B 类外部补谱协议（v0.1，待 pilot 校准）

1. **来源与许可**：优先 **CC0 / CC-BY 的 MuseScore 公开谱**（可直接导出 MusicXML，无 OMR 误差）；
   次选 **IMSLP 公版版**（PDF，需 OMR 或人工录入）。每首必须记录 `source_url`、许可、编者/版次、
   下载日期、sha256。
2. **入库位置**：`data/scores_external/<Composer>/<Piece>/source.musicxml`（或 `.mscz`），同目录写
   `SOURCE.md`；**不覆盖**任何既有谱或 `reference_score.musicxml`。
3. **小节对齐**：外部谱与我们 `reference_score.musicxml` 的小节编号/反复/弱起可能不同 →
   必须产出 `measure_map.csv`（`external_measure` ↔ `our_score_measure`），人工抽查 ≥3 处核对。
4. **踏板层提取**：只取外部谱的 `<pedal>` 事件 → `reference_pedals_ext.csv`
   （`hand / position_ql / position_location / event_type / source`），位置按
   `measure_start + cursor + <offset>/divisions` 换算（与既有口径一致，`<offset>` 必须应用）。
5. **合并与重生成**：③ 取值改为「ext 层优先、ASAP 层兜底」；重跑 S4/S5 与双审计；
   **旧产物全部保留**（不覆盖）。
6. **验收**：每首必须有 (i) 记号数、(ii) 小节映射抽查记录、(iii) 渲染对比图、(iv) 双审计 JSON。

## 4. 分阶段

- **P0（已备）**：A 类 14 段清单、B 类 26 段清单、富集池 64 个谱。
- **P1（pilot，3 首）**：`Beethoven_Piano_Sonatas_16-1`、`Mozart_Piano_Sonatas_12-3`、
  `Schubert_Wanderer_fantasie_1189`（古典/浪漫各半，均公版，IMSLP 与 MuseScore 均有条目）→
  走通 §3 全流程并校准协议。
- **P2（批量）**：B 类其余 23 首，按作曲家风控（每批 ≤5 首，批后锚定）。
- **P3**：A 类扩样（从富集池取样，与 2A 同款）。

## 5. 待定决策

- **D7**：A 类新段的目录与命名（建议 `outputs/pedal_expansion/segments_v2/`）与规模（是否把富集池做满）。
- **D8**：B 类若某首确实找不到合格谱源（许可或质量不达标），该段 ③ 记为
  `not-notated-in-source` 并留档，**不允许悄悄留空**。
- **D9**：③ 合并后的列策略（保留 `reference_pedals.csv` 与 `reference_pedals_ext.csv` 双份，
  另加合并列 `published_score_pedal_merged`）。

## 6. 版本记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-10-03 | v0.1 | 建档（主控）：A/B 两类分类与逐段清单、富集池统计、A 类现有流程、B 类外部补谱协议、P0-P3 分期、D7-D9 待定。 |
