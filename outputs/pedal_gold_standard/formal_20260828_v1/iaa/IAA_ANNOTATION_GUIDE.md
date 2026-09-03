# IAA 复标标注说明

请为每个 iaa_<segment>.csv 的六列填写标注（与金标准同一套规则）：

1. acoustic_sustain: yes / no / uncertain——该音符是否被 CC64 或共振声学延音。
2. performance_pedal_action: hold / change / release / none / uncertain——CC64 在该事件附近的踏板动作。
3. published_score_pedal: start / change / stop / none / uncertain——出版谱在该事件处的踏板标记。
4. notation_decision: 记谱时值（QL 单位）——从候选时值中选择，或写明确时值。这是最关键的一列。
5. review_class: independent-voice / notation-shortening / pedal-only / other / 留空。
6. review_note: 自由文本说明决策理由。

辅助材料：同片段目录下的 performance_segment.mid（音频）与 reference_score.musicxml（谱面）。
不要参考原 events.csv 的标注值（避免记忆偏差）。