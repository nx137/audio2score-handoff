#!/usr/bin/env python3
"""P4c：踏板感知的结构化候选时值解码原型。

本模块将 P4a 的三类时间语义与 P4b 的多 voice 表示连接起来：

* duration 候选来自键盘释放、踏板声学结束、节拍栅格、下一同声部 onset；
* 选择时保持“同 voice 不重叠”这一硬约束；
* 选择代价由键盘/声学持续、节拍复杂度、跨小节 tie 复杂度共同决定；
* `candidate_probability` 是 P4d LightGBM 的接口。当前用可解释的规则先验；
  后续模型只替换该概率，不改变合法性约束与导出接口。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from analyze_pedal_durations import pedal_release_after
from voice_assignment import VoiceEvent, assign_voices, validate_voice_events

EPS = 1e-7


@dataclass(frozen=True)
class DurationCandidate:
    duration_ql: float
    source: str
    crosses_barline: bool
    score: float


def _snap_candidates(value: float, divisors=(8, 4, 3), radius=0.0) -> set[float]:
    candidates = set()
    for divisor in divisors:
        tick = 1.0 / divisor
        center = round(value / tick)
        for offset in range(-int(radius), int(radius) + 1):
            candidate = (center + offset) * tick
            if candidate > EPS:
                candidates.add(round(candidate, 9))
    return candidates


def generate_duration_candidates(start_ql, key_duration_ql, acoustic_duration_ql,
                                 next_voice_onset_ql=None, bar_ql=4.0,
                                 divisors=(8, 4, 3)) -> list[tuple[float, str]]:
    """从可解释的符号边界产生离散时值候选，不使用任意浮点回归。"""
    tagged: dict[float, set[str]] = {}

    def add(duration, source):
        if duration > EPS:
            tagged.setdefault(round(duration, 9), set()).add(source)

    for duration in _snap_candidates(key_duration_ql, divisors):
        add(duration, "key-release-grid")
    for duration in _snap_candidates(acoustic_duration_ql, divisors):
        add(duration, "pedal-acoustic-grid")

    # 当前小节的右边界是可读 tie 的候选结束点；跨线长音仍可保留，
    # 导出时由 tie_split_events 按小节拆分。
    bar_end = (math.floor(start_ql / bar_ql) + 1) * bar_ql
    add(bar_end - start_ql, "barline")

    if next_voice_onset_ql is not None and next_voice_onset_ql > start_ql + EPS:
        add(next_voice_onset_ql - start_ql, "next-voice-onset")

    return [(duration, "+".join(sorted(sources))) for duration, sources in sorted(tagged.items())]


def candidate_probability(duration, key_duration, acoustic_duration, source):
    """P4d 的可学习接口；目前为可解释的规则概率（0~1）。"""
    key_gap = abs(duration - key_duration)
    acoustic_gap = abs(duration - acoustic_duration)
    # 键盘释放是符号时值的首要证据；踏板只提供次要、非强制的持续证据。
    score = math.exp(-2.0 * key_gap) * 0.70 + math.exp(-1.2 * acoustic_gap) * 0.25
    if "barline" in source:
        score += 0.04
    if "next-voice-onset" in source:
        score += 0.02
    return min(score, 0.999)


def rank_candidates(start_ql, key_duration_ql, acoustic_duration_ql,
                    next_voice_onset_ql=None, bar_ql=4.0, divisors=(8, 4, 3)) -> list[DurationCandidate]:
    ranked = []
    for duration, source in generate_duration_candidates(
        start_ql, key_duration_ql, acoustic_duration_ql, next_voice_onset_ql,
        bar_ql, divisors,
    ):
        probability = candidate_probability(duration, key_duration_ql, acoustic_duration_ql, source)
        end = start_ql + duration
        crosses = math.floor((start_ql + EPS) / bar_ql) != math.floor((end - EPS) / bar_ql)
        # 较低 score 更好。跨小节不是错误，但只有当持续证据充分时才值得引入 tie。
        complexity = 0.06 if crosses else 0.0
        ranked.append(DurationCandidate(duration, source, crosses, -math.log(probability) + complexity))
    return sorted(ranked, key=lambda candidate: candidate.score)


def decode_hand(raw_events, pedals, hand: str, max_voices=6, bar_ql=4.0,
                divisors=(8, 4, 3)) -> list[VoiceEvent]:
    """先按原始键盘时值分 voice，再独立为每一声部选择合法的离散符号时值。

    此处的“第一候选”是 P4c 可运行基线。P4d 将以 LightGBM 概率替换打分函数，
    后续可扩展为 Viterbi / 最小费用流跨事件联合搜索。
    """
    base = assign_voices(raw_events, hand=hand, max_voices=max_voices)
    decoded: list[VoiceEvent] = []
    for voice in sorted({event.voice for event in base}):
        stream_events = sorted((event for event in base if event.voice == voice),
                               key=lambda event: (event.start_ql, event.pitch))
        unique_onsets = sorted({event.start_ql for event in stream_events})
        next_onset = {onset: unique_onsets[i + 1] if i + 1 < len(unique_onsets) else None
                      for i, onset in enumerate(unique_onsets)}
        for event in stream_events:
            key_duration = event.duration_ql
            acoustic_end = pedal_release_after(event.end_ql, pedals)
            acoustic_duration = acoustic_end - event.start_ql
            ranked = rank_candidates(
                event.start_ql, key_duration, acoustic_duration,
                next_onset[event.start_ql], bar_ql, divisors,
            )
            # 声部内的下一不同 onset 是硬边界；仍允许同 onset chord 共享持续。
            legal = [candidate for candidate in ranked if next_onset[event.start_ql] is None
                     or event.start_ql + candidate.duration_ql <= next_onset[event.start_ql] + EPS]
            best = legal[0] if legal else ranked[0]
            decoded.append(VoiceEvent(
                event.pitch, event.start_ql, best.duration_ql, event.velocity, voice, hand
            ))
    validate_voice_events(decoded)
    return sorted(decoded, key=lambda event: (event.hand, event.voice, event.start_ql, event.pitch))


def decode_score_hands(rh_events, lh_events, pedals, max_voices=6, bar_ql=4.0,
                       divisors=(8, 4, 3)) -> dict[str, list[VoiceEvent]]:
    return {
        "RH": decode_hand(rh_events, pedals, "RH", max_voices, bar_ql, divisors),
        "LH": decode_hand(lh_events, pedals, "LH", max_voices, bar_ql, divisors),
    }
