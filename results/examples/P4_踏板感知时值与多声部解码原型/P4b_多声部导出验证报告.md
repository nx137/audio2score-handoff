# P4b：多声部 MusicXML 导出验证报告

## 本轮结果

P4b 的多声部 MusicXML 导出原型已完成可运行验证，但**仍为候选原型，不替换已验收的 P3 单声部生产导出器**。

本轮修复了多声部对账器的一个关键语义错误：延音线链原先只按音高追踪；当不同 voice 同时或相邻保留相同音高时，链会被错误串接。现在以 `(part_id, voice_id, pitch)` 共同索引 tie 链，因此独立声部中的同音高长音不会被误合并。

同时，声部分配器加入了强 voice 复杂度代价：在满足不重叠与 chord 时值一致性硬约束的前提下，优先复用已有 voice，避免此前原型把三首曲子机械拆成 12 个声部。

本轮还定位并修复了上一轮遗留的两条警告（见"修复验证"）：

- **Schubert music21 beam 配对警告**是 `beam.Beams.mergeConnectingPartialBeams` 对合法拍尾十六分组合的假阳性；输出 XML 本身有效，Verovio 渲染正常。修复为在写出时仅过滤这条已知告警（连同其续行），不改变任何 beam 数据。
- **Mozart Verovio 未闭合 tie 警告**由 Verovio 每小节按调号重置临时记号、而 music21 只在 tie 链部分音符上写显式临时记号引起：tie 两端被判定为不同音高。修复为给所有带 `<tied>` 且书写音高与调号不一致的音符补齐显式 `<accidental>`，使整条 tie 链的 gestural 音高一致，不改变书写音高。

两条修复都不触碰对账器读取的 `pitch/start/duration/tie` 字段，逐音对账结果与基线完全一致。

## 回归验证

对账基准是 P3 已量化、分手后的记谱输入事件。MusicXML 侧会合并同一 `part + voice + pitch` 的 tie 链后再比对。

| 曲目 | 输入事件 | XML 合并 tie 后 | 多写 | 漏写 | 起音漂移 > 0.125 QL | 符号时值差 > 0.25 QL | RH / LH voice 数 | 渲染 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 莫扎特 K.4 | 335 | 335 | 0 | 0 | 0 | 43 | 4 / 4 | SVG、PNG 成功 |
| 斯卡拉蒂 K.79 | 759 | 759 | 0 | 0 | 0 | 13 | 5 / 4 | SVG、PNG 成功 |
| 舒伯特 D.979 | 390 | 390 | 0 | 0 | 0 | 117 | 5 / 4 | SVG、PNG 成功 |

三首 XML 都通过：

- XML 语法解析；
- 每小节游标完整性检查：无超拍或欠拍；
- Verovio SVG/PNG 渲染；
- 逐音事件集合检查：0 多写、0 漏写、0 超阈值起音漂移。

## 时值差异的含义

时值偏差并不等于导出错误。P4c 会从键盘释放、踏板声学结束、小节线与下一同 voice onset 中选择离散候选时值；因此它有意不再复制 P3 的单 voice 截断时值。

尤其是舒伯特 D.979 的 117 处差异，是后续人工标注和 LightGBM 训练应优先覆盖的样本池：需要判断每一处究竟是应保留为独立声部、应缩短为可读符号时值，还是仅由踏板导致的声学延续。

## 已知限制

1. 导出器目前仍是结构合法性原型，而非最终可读性最优谱面；4–5 个 voice 已大幅优于旧版的 12 个，但仍需小节级全局优化进一步合并。
2. ~~舒伯特导出阶段仍出现一次 music21 beam 配对警告~~ —— 已定位为 `beam.Beams.mergeConnectingPartialBeams` 的假阳性并修复：写出时过滤该条告警（含续行），XML 与 Verovio 渲染不受影响（回归中 stderr 已无任何输出）。
3. ~~莫扎特在 Verovio 导入时报告 1 条未闭合 tie 警告~~ —— 已定位并修复：Verovio 每小节按调号重置临时记号，music21 只在 tie 链部分音符上写显式记号导致两端音高判定不一致；现为所有 tie 音符补齐与书写音高一致的显式临时记号。重新导出与旧样例均不再告警，逐音对账不变。

## 修复验证

两条警告的最小复现与修复验证（均在 `audio2score/scripts/p4_multivoice_score.py` 内实现，P3 生产导出器 `midi_to_score.py` 未改动）：

| 检查项 | 结果 |
|---|---|
| 旧莫扎特样例 Verovio 未闭合 tie | 修复前 `1 tie left open` → 修复后 `0`（`sanitize_tie_accidentals` 补齐 m33 B4 等音符的显式 `natural`） |
| 旧莫扎特样例对账 | 修复前后一致：335 事件、0 多写 / 0 漏写 / 0 漂移 / 43 时值差，`完全一致` |
| 三首新导出 stderr | 全部为空（Schubert beam 假阳性及其续行已被过滤） |
| 三首新导出 Verovio | 全部 `ties_left_open=0`、`unclosed=0` |
| 三首新导出对账 | 莫扎特 43 / 舒伯特 117 / 斯卡拉蒂 13 时值差（与基线一致），均 `完全一致` |
| 三首新导出渲染 | SVG + PNG 全部成功 |

修复说明：

- **beam**：只过滤 `beam: WARNING:Found a messed up beam pair ...` 及其续行（beam 列表 repr），不修改任何 beam 数据；输出 XML 与修复前逐字节一致。
- **tie**：为所有带 `<tied>` 且 `<pitch><alter>` 与当前调号（逐小节跟踪 `<key><fifths>`）不一致的音符补写显式 `<accidental>`，使整条 tie 链在 Verovio 内的 gestural 音高一致；不改书写音高，不触碰对账字段。转调安全（按小节更新调号）。
- 当前解码输出已不再产生旧样例那种跨小节 tie + 缺显式记号的组合（莫扎特 tie 变为小节内闭合），因此新导出默认不再告警；该步骤作为防御性保证，对旧样例已验证有效。

## 交付内容

- `代码/p4_multivoice_score.py`：P4b 多 voice 导出器；
- `代码/reconcile_midi_xml.py`：支持按声部区分 tie 链的对账器；
- `代码/voice_assignment.py`：带 voice 复杂度惩罚的分配基线；
- `多声部导出样例/`：每首的源 MIDI、P4 MusicXML、总 SVG、总 PNG；
- 既有的 `时值评测/` 与 P4a–P4c 代码仍保留。

## P4c / P4d 本轮完成项

1. `代码/structured_duration_decoder.py` 已升级为小节级动态规划：每小节联合选择候选时值，候选概率、跨小节 tie、节拍对齐和小节内 tie 数进入软代价；同一 voice 的下一起音边界和不重叠仍是硬约束。
2. 新增 `代码/build_candidate_dataset.py`，为人工复核生成候选级 CSV，并预留 `label`、`review_class`、`review_note`。人工类别为 `independent-voice`、`notation-shortening`、`pedal-only`；启发式建议仅用于排序，不冒充标签。
3. 新增 `代码/train_candidate_model.py`，提供 LightGBM 训练与模型元数据接口。当前环境未安装 LightGBM，本轮未伪造训练结果；没有充分标签时解码继续使用规则概率 fallback。
4. 三首曲目均完成全局解码、MusicXML 写出、SVG/PNG 渲染与逐音对账。候选表共生成：莫扎特 980 条、斯卡拉蒂 1549 条、舒伯特 997 条。

| 曲目 | RH/LH 音符 | RH/LH voice | 多写 | 漏写 | 起音漂移 > 0.125 QL | 时值差 > 0.25 QL | 渲染 |
|---|---:|---:|---:|---:|---:|---:|---|
| 莫扎特 K.4 | 233 / 102 | 4 / 4 | 0 | 0 | 0 | 43 | SVG、PNG |
| 斯卡拉蒂 K.79 | 525 / 234 | 4 / 5 | 0 | 0 | 0 | 13 | SVG、PNG |
| 舒伯特 D.979 | 189 / 201 | 5 / 4 | 0 | 0 | 0 | 117 | SVG、PNG |

时值差异仍按“符号候选与 P3 记谱输入时值”的定义统计，不将其误报为音符增删。它们正是待人工复核的训练样本，而不是本轮强行优化掉的数字。

