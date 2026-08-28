# B 阶段评测协议：踏板感知钢琴 MIDI→乐谱系统

> **版本**：v1.0（冻结版）  
> **冻结日期**：2026-08-16  
> **适用范围**：P3 单声部基线、P4 规则评分、P4 LightGBM 候选评分三种 MIDI→MusicXML 系统；候选模型跨曲泛化评估；后续 C/D 阶段全部主结果、消融与人工评测。  
> **本协议目的**：把“候选排序提升”“MusicXML 导出正确”“谱面更可读”拆成不同层次、用不同证据验证，避免用某一层的好结果替代另一层的结论。

---

## 1. 研究问题、比较对象与可作出的结论

| 编号 | 研究问题 | 比较对象 | 允许得出的结论 | 不允许替代的结论 |
|---|---|---|---|---|
| RQ1 | 学习评分是否改善合法时值候选的排序？ | P4-LightGBM vs P4-rule | 未见作品上的候选级排序改善 | 不直接等价于整谱可读性改善 |
| RQ2 | 多声部、结构化时值解码是否能稳定导出正确的 MusicXML？ | P4-rule / P4-LightGBM | 导出层不增删音、tie/小节/渲染结构合法 | 不等价于相对于参考谱的音乐学最优记谱 |
| RQ3 | P4 相比稳定单声部记谱是否改善参考谱一致性与谱面质量？ | P3 vs P4-rule vs P4-LightGBM | 在有参考谱、同一输入和同一评测容差下的系统级改进 | 不把 P3 回归集结果当作未见作品泛化结果 |
| RQ4 | 踏板信息是否带来可感知的记谱收益？ | 后续 C 阶段踏板消融 vs 保留踏板 | 只在配对消融、同一曲目和盲评条件下成立 | 不用“输出了 pedal 元素”替代踏板质量结论 |

**解释原则**：P4-LightGBM 只重排已满足硬约束的离散候选。任何候选级 ROC-AUC、AP 或 Top-1 改进，只能说明排序器更接近参考时值；最终 MusicXML 质量还必须由系统级指标和人工盲评独立证明。

---

## 2. 冻结对象与版本追溯

### 2.1 软件与固定参数

| 项目 | 冻结值 |
|---|---|
| P3 导出器 | `audio2score/scripts/midi_to_score.py` |
| P4 导出器 | `audio2score/scripts/p4_multivoice_score.py` |
| P4 解码器 | `audio2score/scripts/structured_duration_decoder.py` |
| 对账器 | `audio2score/scripts/reconcile_midi_xml.py` |
| 渲染器 | `audio2score/scripts/render_score.py`（Verovio） |
| 候选评测器 | `audio2score/scripts/evaluate_candidate_model.py` |
| 量化网格 | `divisors=8,4,3` |
| 起音容差 | `0.125 QL`（一个三十二分音符） |
| 时值容差 | `0.25 QL`（一个十六分音符） |
| P4 最大声部数 | `max_voices=12` |
| 正式候选模型前缀 | `audio2score/models/p4_asap_cross_piece_v1` |
| P4 模型文件 SHA-256 | `.txt`: `31f58cf9bc022a686eedc60ed9af6c621eac69ba4569cccf24147bdd4877b666`；`.json`: `7dbeadb4fd5549de5e984444d0c77921ad8b3dbdaa44e6798279fcec342c6fe6` |

每次正式运行必须记录：脚本版本、完整命令、输入 MIDI 的 SHA-256、manifest 的 SHA-256、模型 SHA-256、运行日期、依赖版本、stderr、退出状态。任何其中一项变化都形成新的实验运行，而不能覆盖旧结果。

### 2.2 冻结管线

| 系统 ID | 名称 | 命令语义 | 学习模型 | 主要作用 |
|---|---|---|---|---|
| `P3` | 单声部稳定基线 | P3 的量化、分手、同手下一起音截断与 MusicXML 导出 | 无 | 验证多声部结构化解码的增益 |
| `P4-R` | P4 规则评分 | 显式多声部 + 踏板感知候选 + 小节级 DP | 规则 `candidate_probability()` | 验证结构化建模本身 |
| `P4-L` | P4 LightGBM | 与 P4-R 相同硬约束与候选集 | `p4_asap_cross_piece_v1` | 验证候选学习排序的额外增益 |

**硬约束声明**：三个 P4 相关系统均必须满足同一 hand + voice 的异起音事件不重叠、同起点 chord 成员时值一致、跨小节 tie 完整、每小节不超拍。模型不可绕过这些约束。

---

## 3. 数据集、隔离与用途

### 3.1 ASAP 作品级主实验集

| 条目 | 冻结内容 |
|---|---|
| 清单 | `tmp/asap_cross_piece/asap_piece_manifest.csv` |
| 数据版本 | ASAP 数据目录记录的 commit：`afc815c75c42e83a79c03feb6da8a35e77d4c6b8` |
| 纳入条件 | 有有效 `score_and_performance_aligned` 标记、有效逐拍映射、performance MIDI/score MIDI/reference MusicXML 均存在 |
| 排除 | 1,067 条元数据记录中，31 条不满足上述完整对齐条件的演奏不纳入 |
| 划分键 | `piece_key = composer + "\x1f" + title` |
| 划分函数 | 对 `piece_key` 的 SHA-256 前 8 个十六进制字符取模：0–69=train、70–84=validation、85–99=test |
| 演奏 / 作品规模 | 1,036 条演奏 / 221 首作品 |
| train | 694 条演奏 / 159 首作品 |
| validation | 222 条演奏 / 31 首作品 |
| test | 120 条演奏 / 31 首作品 |

同一 `(composer, title)` 的所有演奏必须在同一集合。训练调参只能使用 train；阈值、设计选择和人工规则只能在 validation 确定；test 仅用于最终一次锁定报告。若重训模型、扩大候选集或修改打标逻辑，必须重新生成独立运行目录，不能复用旧 test 表。

### 3.2 P3 三曲生产回归集

| 曲目 | 用途 | 允许的结论 |
|---|---|---|
| 莫扎特 K.4 | 导出正确性、MusicXML tie、渲染回归 | 生产管线稳定性 |
| 斯卡拉蒂 K.79 | 多声部/chord 联合时值与布局压力回归 | 结构硬约束稳定性 |
| 舒伯特 D.979 | 踏板延长与 pedal retake 回归 | 踏板序列化稳定性 |

该集是人工验收回归集，不参与 ASAP 训练、验证或测试，也不作为跨作品泛化主结果。其固定通过条件为：P4 输入事件与 XML tie 合并事件数量一致；0 多写、0 漏写、0 音高错误、0 小节超拍；XML 可解析；Verovio 成功输出 SVG/PNG；`ties_left_open=0`。

### 3.3 候选标注的有效样本定义

只有演奏事件与参考 MusicXML 事件可可靠匹配、且参考时值唯一落在候选集内时，候选行才可被写为 `label=1/0`。以下情况必须保留空标签，而不是伪负例：

- 演奏/参考事件无法唯一对应；
- 参考时值不在候选集；
- 多个候选同样接近参考时值；
- 对齐或参考谱缺失。

候选覆盖率是主指标的一部分；低覆盖率时，不得只报告已标注样本上的分类指标而声称“整体记谱正确”。

---

## 4. 既有候选模型正式结果的封存口径

### 4.1 唯一承认的正式结果目录

候选模型正式结果唯一对应：

```text
tmp/asap_cross_piece/full_streaming_eval_deduplicated/
```

其 `evaluation_metrics.json` 与正式模型资产完全一致。测试集结果为：模型 ROC-AUC `0.868960`、AP `0.857762`、候选事件 Top-1 `0.738746`；规则评分 Top-1 `0.625078`。这是候选级未见作品结果，不能直接写成整谱质量提升。

### 4.2 去重定义

去重的目标是：同一参考事件映射出的重复正候选不能多次计入训练/测试。`duplicate_positive_manifest.csv` 记录 25 条演奏、共 27 条冗余正例删除。去重后每个 split 中 `positive_candidates == labeled_events`。

### 4.3 历史目录处理

以下目录不作为正式引文或论文表格来源：

- `full_streaming_eval_dedup/`：名称含“dedup”，但内容与去重前 `full_streaming_eval/` 相同；
- `full_run/chunks/*/batch_summary.csv`：部分 chunk 汇总保留了去重前计数；
- `pilot_*`：仅为 9 条演奏的闭环试运行，不是正式主实验。

正式候选表统计只读取顶层 `tmp/asap_cross_piece/full_run/batch_summary.csv` 与 `full_streaming_eval_deduplicated/evaluation_metrics.json`；后续新运行应在新的不可覆盖目录生成完整清单、汇总与模型资产。

---

## 5. 客观指标

### 5.1 层级 A：候选级排序（ASAP，有可靠标签时）

| 指标 | 定义 | 报告方式 |
|---|---|---|
| 候选覆盖率 | 可靠且参考时值在候选集内的事件数 / 已对齐演奏事件数 | 每 split、每作品；同时报告未匹配、参考时值不在候选集、歧义三类缺口 |
| ROC-AUC | 标注候选的二分类排序质量 | validation 与 test；模型和规则并列 |
| Average Precision | 正候选稀疏时的排序质量 | validation 与 test；模型和规则并列 |
| Event Top-1 | 每个 `candidate_event_id` 中唯一最高分候选是否为正 | validation 与 test；模型和规则并列 |
| 逐作品离散度 | 每首作品分别计算 Top-1 与覆盖率 | 中位数、IQR、均值；不能只报微平均 |

主表以 test 为最终结果，validation 仅用于开发记录。对于每个系统，以作品为单位进行 1,000 次 bootstrap，报告均值差的 95% percentile CI；无法计算时明确标为“样本不足”。

### 5.2 层级 B：MIDI→MusicXML 导出完整性（所有输入均可评）

导出前事件由**同配置**的 P3 或 P4 解码器重放得到，XML 侧用 `(part_id, voice_id, pitch)` 合并 tie 链。该层评估的是导出层是否忠实实现既定解码，而非解码器是否接近原始演奏。

| 指标 | 合格判据 / 含义 |
|---|---|
| XML 真实事件数 | 与同配置解码输入事件数并列报告 |
| Extra / Missing | XML 侧凭空多写 / 漏写的事件数；正式回归要求均为 0 |
| Onset drift | 超过 `0.125 QL` 的同音高配对起音偏移数 |
| Duration drift | 超过 `0.25 QL` 的同音高配对时值偏移数 |
| Voice overlap | 同一 `(hand, voice)` 的异起音重叠事件对数；P4 必须为 0 |
| Overfull measure | 小节中任一 voice 或导出游标超过标称小节时值的计数；必须为 0 |
| Tie completeness | 孤立 stop、未闭合 start、跨 voice 串接的 tie 链计数；必须为 0 |
| XML parse success | MusicXML 解析是否成功 |
| Render success | Verovio 是否成功生成至少一页 SVG 与 PNG |
| Layout warnings | `ties_left_open`、`unclosed`、beam/layout 警告的分项计数；布局警告单列，不与导出失败混为一谈 |

### 5.3 层级 C：相对参考谱的系统级记谱质量（有可靠参考谱时）

该层使用参考 MusicXML 和可靠的演奏–乐谱对齐，不用原始 MIDI note-off 直接惩罚踏板造成的声学延长。

| 指标 | 匹配 / 容差 | 说明 |
|---|---|---|
| Pitch P/R/F1 | 同音高、经参考对齐的符号事件 | 衡量音高事件集合 |
| Onset P/R/F1 | 起音误差 ≤ `0.125 QL` | 与层级 B 的“导出漂移”不同，此处对象是参考谱 |
| Duration accuracy | 匹配事件的时值误差 ≤ `0.25 QL` 的比例 | 同时报 MAE/中位绝对误差 |
| Note P/R/F1 | 音高、起音、时值同时满足容差 | 主系统级音符指标 |
| Tie-chain accuracy | 参考跨小节持续事件的链是否完整、边界是否正确 | 仅在可可靠映射的 tie 样本报告 |
| Voice consistency | 参考 voice 可可靠映射时的声部一致率；否则报告为空 | 不把启发式手/voice 编号强行当真值 |
| Pedal start/change/stop | 踏板事件 P/R/F1 与位置绝对误差 | 仅在有踏板真值时报告；change 与同位置 stop/start 按等价规则处理 |

系统级主表必须按**作品宏平均**与**所有事件微平均**同时报告。若二者方向不同，正文优先解释宏平均，因为它避免少数长曲支配结果。

### 5.4 层级 D：音频端到端（后续扩展）

WAV→MIDI 前端与 MIDI→MusicXML 后端分别报告，禁止把前端 AMT 错误归因于记谱器：

1. 音频→MIDI：pitch/onset/offset/pedal 指标；
2. MIDI→MusicXML：按本协议层级 B/C；
3. WAV→MusicXML：以同一参考谱评估总效应；
4. 误差传播：按 AMT 错误类型（谐波误检、漏检、onset、offset、pedal）分层报告记谱错误变化。

---

## 6. 统一输出目录与运行记录契约

每次实验在 `evals/B/<run_id>/` 下独立创建，不覆盖历史运行：

```text
evals/B/<run_id>/
  manifest/manifest.csv
  manifest/manifest.sha256
  config.json
  environment.txt
  commands.log
  models/p4_asap_cross_piece_v1.txt
  models/p4_asap_cross_piece_v1.json
  models/checksums.sha256
  pieces/<piece_id>/<pipeline>/
    output.musicxml
    export.stderr.log
    reconcile.json
    render/
    render.stderr.log
    render_qa.json
    metrics.json
  summary/piece_summary.csv
  summary/metrics_summary.json
  summary/baseline_comparison.md
```

`config.json` 至少包含：系统 ID、输入类型、量化网格、容差、P4 最大声部数、模型前缀与 SHA-256、manifest 路径/SHA-256、数据版本、随机种子、运行命令。`commands.log` 逐行记录每条实际执行的命令及退出码；失败条目不得从汇总中静默消失，而要在 `piece_summary.csv` 标为失败并写入原因。

建议的统一基线命名：

```text
P3        = midi_to_score.py
P4-R      = p4_multivoice_score.py（无 --candidate-model）
P4-L      = p4_multivoice_score.py（--candidate-model p4_asap_cross_piece_v1）
```

---

## 7. 人工可读性盲评方案（D 阶段执行，B 阶段冻结）

### 7.1 片段与条件

- 至少 30 个片段，优先从未见作品 test 集抽取；每首作品最多 2 个片段，避免长曲主导；
- 每片段 2–8 小节，包含至少一种目标现象：踏板延长、retake、持续低音与旋律并存、跨小节 tie、复节奏或和弦；
- 对同一输入生成 P3、P4-R、P4-L 版本；评分界面不显示系统名、文件名、生成顺序或模型信息；
- 所有候选谱统一版面宽度、字号、纸张和渲染器；必要时裁为相同小节范围；
- 片段顺序与系统版本顺序独立随机化；每位评审的顺序不同；
- 评审前用 3 个不纳入统计的练习片段统一评分理解。

### 7.2 评审者与量表

目标为 3–5 名具备钢琴演奏或教学经验的评审者；记录音乐训练年限、是否熟悉 MusicXML/制谱软件，但不在主结果中展示个人身份。

每项使用 1–5 分 Likert 量表（1=明显不可接受，3=可用但需修改，5=自然且可直接使用）：

1. 节奏与时值可读性；
2. 声部组织清晰度；
3. 持续音与 tie 的合理性；
4. 踏板符号/换踏板点的合理性；
5. 视觉整洁度；
6. 整体可演奏性。

同时记录一个主观优选：在同一片段的盲化版本中选择“最愿意用于排练的一版”；允许“无差别/均不合格”。开放文本只用于错误类型归纳，不直接作为定量结论。

### 7.3 统计与报告

- 主分析单位为“片段×评审者”，同时按片段聚合展示；
- 对配对版本使用 Wilcoxon signed-rank 检验，并报告 Hodges–Lehmann 位置差与 95% CI；
- 多个量表维度的 p 值采用 Holm 校正；
- 报告每项的中位数、IQR、有效样本数与优选比例；
- 以 Krippendorff’s alpha（有序量表）或加权一致性系数报告评审一致性；
- 若评审者数不足 3 或 alpha 偏低，结论降级为探索性描述，不宣称强主观优势。

---

## 8. B 阶段验收标准与后续任务边界

### 8.1 B 阶段完成条件

1. 本协议版本冻结，任何变更以 `v1.1+` 新文件记录；
2. 三个系统 ID、固定参数、正式模型校验和与数据隔离规则可由第三方复现；
3. 候选级正式结果只引用去重后的正式目录，历史歧义已明确排除；
4. 建立统一基线运行器，能够对单曲依次完成导出、对账、渲染、结构化 QA 与 `metrics.json`；
5. 建立批量汇总，输出按 `piece × pipeline × split` 的明细与按作品宏平均汇总；
6. 在 P3 三曲回归集完成一次自动化闭环，并全部通过其固定回归条件；
7. 人工盲评材料模板、随机化表和数据字典准备完成，但不在 B 阶段提前收集主观结果。

### 8.2 阶段边界

- **B 阶段不做**：重新训练新模型、改变候选集、使用 test 调参、以人工评分替代客观质量、把三曲回归集包装为泛化性能；
- **C 阶段做**：正式主实验、踏板/多声部/学习评分/全局 DP 消融、逐曲分布与置信区间；
- **D 阶段做**：执行已冻结的盲评、生成论文级谱例与图表；
- **E 阶段做**：整理可复现实验包、论文表格、方法与实验文字。

---

## 9. 实施优先级

1. 实现 `run_piece`：将 P3 / P4-R / P4-L 的导出、对账、渲染和日志编排为单曲运行；
2. 实现 `render_qa`：将 XML 解析、小节超拍、tie、Verovio 状态和警告结构化；
3. 实现 `batch_eval`：读取冻结 manifest，写逐曲明细与聚合表；
4. 实现参考谱 `score_metrics`：区分“导出忠实性”和“相对参考谱质量”；
5. 用 P3 三曲执行闭环验收后，再启动 ASAP 未见作品系统级主实验。

这份协议选择先保证证据链的边界清晰，再追求表格数量。乐谱系统最容易出现“指标都很好，谱却不对”的错觉；这里专门把那条捷径堵上。
