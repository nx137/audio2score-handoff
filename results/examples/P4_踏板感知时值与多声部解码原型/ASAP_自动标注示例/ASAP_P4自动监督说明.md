# ASAP → P4 候选级自动监督

## 用途与边界

此流程将 **ASAP** 中的演奏 MIDI、参考 score MIDI、参考 MusicXML 与逐拍对齐标注连接起来，为 P4 的“候选记谱时值”生成可追溯的 `0/1` 标签。它服务于候选排序模型训练；**不会**替换结构约束，也不会直接替换已经验收的 P3 导出器。

ASAP 由 [`asap-dataset`](https://github.com/fosfrancesco/asap-dataset) 发布，仓库说明其含对齐的 MIDI/MusicXML 乐谱、演奏 MIDI 和逐拍注释；当前版本使用 **CC BY-NC-SA 4.0** 许可。训练、发布衍生成果前须满足非商业、署名、相同方式共享等要求，并引用 Foscarin et al. (ISMIR 2020)。

## 对齐链路

```text
演奏 MIDI note-on（秒）
  └─ ASAP performance_beats → midi_score_beats 分段线性映射
       └─ score MIDI：同音高、唯一、最近的 note-on
            └─ MusicXML：同音高、唯一、近邻的符号事件
                 └─ auto_label_candidates.py：候选时值唯一命中 → 1/0
```

`asap_alignment.py` 输出的外部对齐 CSV 具有下列固定列：

```text
hand,pitch,onset_ql,reference_part,reference_voice,reference_pitch,reference_onset_ql
```

其中 `onset_ql` 是当前 P4 量化后的演奏事件位置；参考端三元组加起音唯一定位 MusicXML 事件。因此真实演奏不再使用“同 QL 起音”的受控样例捷径。

## 保守拒绝规则

下列情形**不**写成标签，而是进入拒绝表或在自动标签表中保留空 `label`：

- ASAP 标记 `score_and_performance_aligned=false`；
- 事件落在逐拍映射范围外；
- 量化演奏事件无法唯一回接原始演奏 note-on；
- score MIDI 或 MusicXML 存在同音高起音歧义，或超过容差；
- 参考符号时值不在当前候选集中；
- 多个候选同时位于 `duration_tolerance` 内。

仅 `auto_label_status=labeled` 的事件可进入监督训练；对每个这样的 `candidate_event_id`，恰有一个 `label=1`，其余候选为 `label=0`。其它状态的 `label` 必须为空，训练读取器会跳过它们。

## 已完成的真实条目验证

示例条目是 ASAP 的 `Bach/Fugue/bwv_846/Shi05M.mid`。在 `score_note_tolerance_sec=0.08`、`xml_note_tolerance_ql=0.125` 下：

| 阶段 | 结果 |
|---|---:|
| 量化演奏事件 | 754 |
| 可靠外部对齐 | 728 |
| 对齐拒绝 | 26 |
| 候选行 | 2,691 |
| 可监督事件 | 109 |
| 正标签 | 109 |
| 负标签 | 280 |
| 空标签候选行 | 2,302 |

上表的“可监督事件”与正标签一一对应；大量“参考时值不在候选集”是当前 P4 候选集覆盖率问题的测量结果，不应被伪造为负例。

本目录保存了该验证的三份可检查产物：

- `bach_bwv846_shi05m_alignment.csv`：可靠外部对齐；
- `bach_bwv846_shi05m_alignment_rejected.csv`：带拒绝原因的事件；
- `bach_bwv846_shi05m_candidates_auto_labeled.csv`：候选级自动标签表。

## 可复现命令

在 `audio2score/scripts/` 目录下，假定 ASAP 已克隆或下载至 `<ASAP_ROOT>`：

```bash
python3 asap_alignment.py \
  --asap-root <ASAP_ROOT> \
  --performance Bach/Fugue/bwv_846/Shi05M.mid \
  --out alignment.csv \
  --rejected-out alignment_rejected.csv

python3 auto_label_candidates.py \
  --midi <ASAP_ROOT>/Bach/Fugue/bwv_846/Shi05M.mid \
  --reference-xml <ASAP_ROOT>/Bach/Fugue/bwv_846/xml_score.musicxml \
  --alignment alignment.csv \
  --out candidates_auto_labeled.csv \
  --piece asap_bach_bwv846_shi05m

python3 train_candidate_model.py \
  --inputs candidates_auto_labeled.csv \
  --out models/asap_candidate_model
```

最后一条命令仅验证训练接口；单一条目不能作为正式评估。正式实验必须按 `(composer, title)` 或至少按 `title` 分组切分，杜绝同一乐曲的不同演奏跨训练/验证/测试集泄漏。先以曲目独立验证报告候选级 ROC-AUC、PR-AUC、top-1 准确率和每事件“唯一正标签”约束，再决定是否进入 P4 解码评分器。

## 尚不在本轮范围内

- 多曲目的批处理 manifest 与曲目级划分；
- 不同作品版本、反复展开、装饰音的专项策略；
- voice 分配、时值、tie 的联合优化；
- P4 替换 P3 的生产验收。

这些边界留得很明确：数据有了门，模型仍然得先学会不踢门。 
