# P4 生产候选模型

## `p4_asap_cross_piece_v1`

该模型是 P4 多声部、踏板感知结构化时值解码的**可选**候选评分器。它只对已经满足结构硬约束的离散时值候选排序；不会直接生成浮点时值，也不会绕过同手同声部无重叠、下一同声部起音边界、跨小节 tie 与小节时值合法性约束。

- 训练监督：ASAP 对齐演奏与参考 MusicXML 的可靠候选标签；按 `(composer, title)` 作品隔离，不让同一作品的不同演奏跨训练、验证和测试集合。
- 模型格式：LightGBM Booster（`.txt`）及特征顺序元数据（`.json`）。
- 正式评估：去重后的未见作品测试集中，候选事件 Top-1 时值选择准确率为 `0.73875`，规则评分基线为 `0.62508`。
- 回退：若没有安装 LightGBM、模型文件缺失或不指定 `--candidate-model`，`p4_multivoice_score.py` 确定性回退到规则评分，仍保留全部结构硬约束。

## 校验和

| 文件 | SHA-256 |
|---|---|
| `p4_asap_cross_piece_v1.txt` | `31f58cf9bc022a686eedc60ed9af6c621eac69ba4569cccf24147bdd4877b666` |
| `p4_asap_cross_piece_v1.json` | `7dbeadb4fd5549de5e984444d0c77921ad8b3dbdaa44e6798279fcec342c6fe6` |

## 生产命令

```bash
python3 audio2score/scripts/p4_multivoice_score.py \
  --midi input.mid \
  --out output.musicxml \
  --candidate-model audio2score/models/p4_asap_cross_piece_v1 \
  --max-voices 12
```

导出回归应使用相同模型和声部上限：

```bash
python3 audio2score/scripts/reconcile_midi_xml.py \
  --midi input.mid \
  --xml output.musicxml \
  --reference p4 \
  --candidate-model audio2score/models/p4_asap_cross_piece_v1 \
  --max-voices 12
```

对账命令在显式指定模型但模型无法加载时会失败，而不是悄悄改用规则基准；这是为了确保验证的确实是与导出完全相同的解码配置。
