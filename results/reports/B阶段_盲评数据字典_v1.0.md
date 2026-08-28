# B 阶段盲评数据字典 v1.0

> 与 `B阶段_人工盲评材料模板_v1.0.md` 配套使用。所有系统身份映射均属于受控数据；评审可见表单只能使用 `display_code`。

## A. 片段抽样表 `segment_manifest.csv`

| 字段 | 类型 | 允许值／格式 | 含义 |
|---|---|---|---|
| `segment_id` | string | `SEG-001` 起的唯一 ID | 正式评测片段唯一标识 |
| `piece_key` | string | `composer\x1ftitle` | 与 ASAP 作品隔离一致的曲目键 |
| `split` | enum | `test` | 来源数据集划分；盲评正式片段必须为 test |
| `performance_id` | string | 数据集原始 ID | 输入演奏标识 |
| `start_measure` | integer | ≥ 1 | 片段起始小节号 |
| `end_measure` | integer | ≥ `start_measure` | 片段结束小节号，且总长度为 2–8 小节 |
| `measure_count` | integer | 2–8 | 裁切后小节数 |
| `target_phenomena` | string | 分号分隔枚举 | `pedal_extension;retake;sustain_melody;cross_bar_tie;polyrhythm;chord` 的非空子集 |
| `selection_rationale` | string | 简短文本 | 说明选中该段的结构现象，不得包含系统结果 |
| `included` | boolean | `0/1` | 是否纳入正式样本 |

## B. 盲化随机化表 `randomization_private.csv`

| 字段 | 类型 | 允许值／格式 | 含义 |
|---|---|---|---|
| `reviewer_id` | string | `R01`… | 匿名评审者 ID |
| `display_order` | integer | 从 1 连续编号 | 该评审者看到的顺序 |
| `segment_id` | string | 外键至 `segment_manifest.csv` | 片段 ID |
| `display_code` | string | 如 `A17` | 评审可见的匿名版本 ID |
| `system_id_private` | enum | `P3/P4-R/P4-L` | 受控映射，不得暴露给评审者 |
| `rendered_asset_private` | string | 本地受控路径 | 实际图片或 PDF 资产路径 |
| `asset_sha256` | string | 64 位十六进制 | 资产完整性校验和 |
| `is_practice` | boolean | `0/1` | 是否为练习样本；练习样本不纳入主统计 |
| `random_seed_id` | string | 运行 ID | 关联固定随机种子及其生成脚本 |

## C. 逐谱评分表 `ratings_blinded.csv`

| 字段 | 类型 | 允许值／格式 | 含义 |
|---|---|---|---|
| `reviewer_id` | string | 外键 | 匿名评审者 |
| `display_order` | integer | 外键 | 展示顺序 |
| `segment_id` | string | 外键 | 片段 |
| `display_code` | string | 外键 | 匿名版本 |
| `rhythm_readability` | integer | 1–5 | 节奏与时值可读性 |
| `voice_clarity` | integer | 1–5 | 声部组织清晰度 |
| `tie_reasonableness` | integer | 1–5 | 持续音与 tie 合理性 |
| `pedal_reasonableness` | integer | 1–5 | 踏板／换踏板点合理性 |
| `visual_neatness` | integer | 1–5 | 视觉整洁度 |
| `playability` | integer | 1–5 | 整体可演奏性 |
| `free_text` | string | 可为空 | 错误类型或意见，仅质性归纳 |
| `completed_at_utc` | ISO-8601 | 时间戳 | 完成时间；不得用于推断系统身份 |

缺失评分使用空值，不使用 `0`、`NA` 或文本占位符；统计时逐维度报告有效样本数。

## D. 片段偏好表 `preferences_blinded.csv`

| 字段 | 类型 | 允许值／格式 | 含义 |
|---|---|---|---|
| `reviewer_id` | string | 外键 | 匿名评审者 |
| `segment_id` | string | 外键 | 片段 |
| `preferred_display_code` | string | 同片段的展示代码或空 | 最愿用于排练的版本；无差别／均不合格时为空 |
| `preference_type` | enum | `single_choice/no_difference/all_unacceptable` | 偏好类别 |
| `preference_note` | string | 可为空 | 可选理由；只做质性归纳 |

## E. 评审者背景表 `reviewer_background_private.csv`

| 字段 | 类型 | 允许值／格式 | 含义 |
|---|---|---|---|
| `reviewer_id` | string | 外键 | 与评分表关联的匿名 ID |
| `piano_training_years` | number | ≥ 0 | 钢琴演奏／教学训练年数 |
| `role_category` | enum | `teacher/student/performer/other` | 粗粒度角色，不写个人身份 |
| `musicxml_familiarity` | integer | 1–5 | 对 MusicXML／制谱软件熟悉度 |
| `consent_recorded` | boolean | `0/1` | 知情说明是否已记录 |

## F. 脱盲与报告规则

1. 数据录入、完整性检查与缺失值审计在不读取 `system_id_private` 的条件下进行。
2. 仅在预先定义的清洗规则执行完毕后，将 `randomization_private.csv` 合并入分析数据。
3. 报告必须同时给出片段×评审者与按片段聚合的样本量；不得把同片段三个版本当作独立曲目。
4. 任何漏盲、资产替换、随机化重做或样本排除，都要新建运行 ID、保留原始表并在论文补充材料说明。
