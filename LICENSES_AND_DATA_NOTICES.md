# 数据、模型与再分发说明

## ASAP 数据

- 本包的 `data/ASAP/` 来自 ASAP（Aligned Scores and Performances）项目快照，包含项目需要的 MIDI、MusicXML、标注和元数据，不含原始音频。
- 上游随附的 `data/ASAP/LICENSE.md` 标明为 **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International（CC BY-NC-SA 4.0）**。使用、复制、修改与再分发必须遵守该许可；特别注意非商业、署名和相同方式共享要求。
- 数据集论文引用信息在 `data/ASAP/README.md` 中。本项目 C 阶段使用作品隔离的 120 演奏/31 作品 test manifest，并非声称使用了 ASAP 全量音频。

## 音频转录前端

`frontend/piano_transcription/` 包含历史推理源码与权重，仅为可复现项目快照而提供。其上游源码、权重及依赖的独立许可未在本交接工作中完成法律审查；在公开发布、商业使用或再次分发前，接手者须核验原始来源、权重和 PyTorch 等依赖的许可。

## P4 候选模型与项目代码

`audio2score/models/` 的 LightGBM Booster 是本项目由 ASAP 对齐候选监督训练得到的冻结研究模型。其固定哈希写入 `audio2score/models/README.md`、`NEXT_AI_CONTEXT.md` 与 `CHECKSUMS.sha256`。若修改、重训或替换模型，必须另建版本和证据目录，不可伪装为冻结模型。

## 不含内容

本包不包含 API keys、访问令牌、密码、环境变量值、原始 MAESTRO 音频或外部账户信息。任何需要额外下载的资源均应由接手者自行从合法来源获取并遵守其许可。
