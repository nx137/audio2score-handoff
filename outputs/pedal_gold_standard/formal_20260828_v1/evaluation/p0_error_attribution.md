# P0 误差归因（unmatched / learned / oracle）

- 片段 40，gold 事件 4672

## 1. 无匹配输出归因（按原因 × 管线）

| 原因 | p4_exact | p4_fused | p4_learned | p4_no_pedal | p4_rule |
|---|---|---|---|---|---|
| hand_mismatch | 0 | 0 | 0 | 0 | 0 |
| pitch_missing | 615 | 616 | 613 | 693 | 615 |
| onset_shift | 0 | 0 | 0 | 1 | 0 |

## 2. oracle 三层归因

- 精确可达率: 0.7414
- oracle@0.25: 0.9441
- 不可达缺口按 review_class: {'notation-shortening': 252, 'independent-voice': 8, 'none': 1}

## 3. 各 review_class 的 @0.25 时值一致率

| review_class | p4_exact | p4_fused | p4_learned | p4_no_pedal | p4_rule |
|---|---|---|---|---|---|
| independent-voice | 0.794 | 0.779 | 0.507 | 0.787 | 0.794 |
| none | 0.980 | 0.980 | 0.908 | 0.980 | 0.980 |
| notation-shortening | 0.671 | 0.677 | 0.736 | 0.671 | 0.671 |
| pedal-only | 0.989 | 0.989 | 0.857 | 0.987 | 0.989 |
