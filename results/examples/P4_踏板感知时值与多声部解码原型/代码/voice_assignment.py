#!/usr/bin/env python3
"""P4b：同手显式多声部的事件层表示与确定性声部分配。

该模块有意停留在“结构中间表示”层，不直接让 music21 自动排版。它首先
解决当前管线“单 hand / 单 voice 必须裁剪到下一任意 onset”的表示瓶颈：

* 同一声部内不允许相交的独立 onset；
* 不同声部允许持续音与后续音并存；
* 同 onset、同 voice、同 duration 的音可以写为 chord；
* 同 onset、不同 duration 的音必须保留为不同 voice，而非压缩成 max duration。

默认分配器是可解释的贪心最小代价基线；P4c 将替换其中的局部决策为全局解码。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


EPS = 1e-7


@dataclass(frozen=True)
class VoiceEvent:
    pitch: int
    start_ql: float
    duration_ql: float
    velocity: int
    voice: int
    hand: str

    @property
    def end_ql(self) -> float:
        return self.start_ql + self.duration_ql


def _active_at(events: Iterable[VoiceEvent], onset: float) -> list[VoiceEvent]:
    return [event for event in events if event.start_ql < onset - EPS and event.end_ql > onset + EPS]


def assign_voices(events, hand: str, max_voices=4) -> list[VoiceEvent]:
    """为一只手的事件分配独立 voice，保留原始（已量化）时值。

    规则：
    1. 一个 voice 内允许同 onset 事件并存，供后续形成 chord；
    2. 若 onset 不同则新事件不得覆盖该 voice 的现有持续音；
    3. 首先复用已出现且合法的 voice；在这些候选中，优先选择刚刚结束、且音高距离最近者，保持旋律/伴奏连续；
    4. 只有没有可复用 voice 时才新开 voice，并施加强复杂度代价；
    5. 超过 ``max_voices`` 时不静默截断，抛出异常，要求 P4c 的全局解码处理。
    """
    ordered = sorted(events, key=lambda event: (event[1], event[0], -event[2]))
    assigned: list[VoiceEvent] = []
    by_voice: dict[int, list[VoiceEvent]] = {}

    for pitch, start, duration, velocity in ordered:
        if duration <= EPS:
            continue
        candidates = []
        for voice in range(1, max_voices + 1):
            existing = by_voice.get(voice, [])
            active = _active_at(existing, start)
            if active:
                continue
            # MusicXML 的一个 Chord 只能共享一个整体时值。相同 onset 且不同时
            # 值的音虽然在抽象时间线上“不冲突”，却不能落在同一 voice；必须分配
            # 到不同 voice，避免导出器为了排版而把其中一个时值覆盖或截断。
            same_onset = [event for event in existing if abs(event.start_ql - start) <= EPS]
            if same_onset and any(abs(event.duration_ql - duration) > EPS for event in same_onset):
                continue
            previous = [event for event in existing if event.start_ql <= start + EPS]
            if previous:
                latest = max(previous, key=lambda event: (event.start_ql, event.end_ql))
                time_gap = max(0.0, start - latest.end_ql)
                pitch_gap = abs(pitch - latest.pitch)
                # 新开声部具有显式复杂度代价：在不破坏硬约束的前提下，
                # 先复用已有 voice，再按时间连续性和音高连续性细分排序。
                reuse_penalty = 0.0 if existing else 100.0
                cost = reuse_penalty + time_gap * 0.20 + pitch_gap * 0.05
            else:
                # 空声部的开启代价远高于任一可复用声部；这使该可解释基线
                # 近似“最少颜色”的区间着色，再以连续性做次级决策。
                cost = (0.0 if existing else 100.0) + voice * 0.001
            candidates.append((cost, voice))

        if not candidates:
            raise ValueError(
                f"{hand} 在 {start:.6f}QL 需要超过 {max_voices} 个声部；"
                "请增加 max_voices 或使用 P4c 全局解码。"
            )
        _cost, voice = min(candidates)
        event = VoiceEvent(pitch, start, duration, velocity, voice, hand)
        assigned.append(event)
        by_voice.setdefault(voice, []).append(event)

    validate_voice_events(assigned)
    return sorted(assigned, key=lambda event: (event.voice, event.start_ql, event.pitch))


def validate_voice_events(events: Iterable[VoiceEvent]) -> None:
    """验证每个 hand/voice 内不同 onset 不重叠；同 onset 允许作为 chord。"""
    by_stream: dict[tuple[str, int], list[VoiceEvent]] = {}
    for event in events:
        by_stream.setdefault((event.hand, event.voice), []).append(event)
    for (hand, voice), stream_events in by_stream.items():
        for previous, current in zip(
            sorted(stream_events, key=lambda event: (event.start_ql, event.pitch)),
            sorted(stream_events, key=lambda event: (event.start_ql, event.pitch))[1:],
        ):
            if current.start_ql > previous.start_ql + EPS and previous.end_ql > current.start_ql + EPS:
                raise ValueError(
                    f"{hand} voice {voice} overlap: p{previous.pitch}@{previous.start_ql:.6f} "
                    f"ends {previous.end_ql:.6f}, but p{current.pitch}@{current.start_ql:.6f} begins."
                )


def group_for_musicxml(events: Iterable[VoiceEvent]):
    """按 (voice, onset, duration) 分组，供导出层仅在真正等时值时构造 Chord。"""
    groups: dict[tuple[int, float, float], list[VoiceEvent]] = {}
    for event in events:
        groups.setdefault((event.voice, event.start_ql, event.duration_ql), []).append(event)
    return [(key, sorted(group, key=lambda event: event.pitch))
            for key, group in sorted(groups.items())]


def voice_statistics(events: Iterable[VoiceEvent]) -> dict:
    events = list(events)
    by_voice = {}
    for event in events:
        stats = by_voice.setdefault(event.voice, {"notes": 0, "first": event.start_ql, "last": event.end_ql})
        stats["notes"] += 1
        stats["first"] = min(stats["first"], event.start_ql)
        stats["last"] = max(stats["last"], event.end_ql)
    return {
        "note_count": len(events),
        "voice_count": len(by_voice),
        "voices": by_voice,
        "mixed_duration_same_onset_groups": sum(
            1 for _key, group in group_for_musicxml(events) if len(group) == 1
        ),
    }
