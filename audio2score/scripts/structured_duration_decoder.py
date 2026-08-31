#!/usr/bin/env python3
"""P4c：踏板感知的结构化候选时值解码原型。

本模块将 P4a 的三类时间语义与 P4b 的多 voice 表示连接起来：

* duration 候选来自键盘释放、踏板声学结束、节拍栅格、下一同声部 onset；
* 选择时保持“同 voice 不重叠”这一硬约束；
* 选择代价由键盘/声学持续、节拍复杂度、跨小节 tie 复杂度共同决定；
* `candidate_probability` 是 P4d LightGBM 的旧接口（按 duration/key/acoustic/source）；
  `feature_scorer`（接受 `candidate_features` dict → 概率）是模型接入点。
  当前用可解释的规则先验；模型只替换概率，不改变合法性约束与导出接口。
"""
from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from analyze_pedal_durations import pedal_release_after
from voice_assignment import VoiceEvent, assign_voices, validate_voice_events

EPS = 1e-7

# --- P1.5 候选生成增强（默认关闭，保持基线可复现） ---
# 启用方式：A2S_EXTEND_CANDIDATES=1 环境变量。
# 扩展内容（P1-6 天花板模拟口径）：
#   1) 按键时值延音扩展：key_duration x {2,3,4,1.5,0.5}
#   2) 常见短时值网格：{0.25, 0.5, 0.375, 1/6, 1/3, 1.0}
_EXTEND_CANDIDATES_ENV = "A2S_EXTEND_CANDIDATES"
KEY_EXTENSION_MULTIPLIERS = (2.0, 3.0, 4.0, 1.5, 0.5)
EXTRA_GRID_DURATIONS = (0.25, 0.5, 0.375, 1.0 / 6.0, 1.0 / 3.0, 1.0)


def extend_candidates_enabled() -> bool:
    """环境变量开关：仅 P1.5 实验启用，默认 False 保持历史行为。"""
    return os.environ.get(_EXTEND_CANDIDATES_ENV, "0").strip().lower() in {"1", "true", "yes"}


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

    # P1.5 候选增强：延音扩展时值（记谱时值 > 按键时值，踏板补足）与常见短时值网格。
    # 模拟显示可使"参考时值可达"率从 62.6% 提升至 95.8%（P1-6）；此处为实际生成实现。
    if extend_candidates_enabled():
        for multiplier in KEY_EXTENSION_MULTIPLIERS:
            add(key_duration_ql * multiplier, f"key-extension:{multiplier:g}")
        for duration in EXTRA_GRID_DURATIONS:
            add(duration, "extra-grid")

    return [(duration, "+".join(sorted(sources))) for duration, sources in sorted(tagged.items())]


def candidate_probability(duration, key_duration, acoustic_duration, source):
    """P4d 的可学习接口；目前为可解释的规则概率（0~1）。"""
    key_gap = abs(duration - key_duration)
    acoustic_gap = abs(duration - acoustic_duration)
    score = math.exp(-2.0 * key_gap) * 0.70 + math.exp(-1.2 * acoustic_gap) * 0.25
    if "barline" in source:
        score += 0.04
    if "next-voice-onset" in source:
        score += 0.02
    return min(score, 0.999)


def candidate_feature_probability(features: dict) -> float:
    """规则 fallback 的特征空间评分：接受 ``candidate_features`` 的 dict。

    与 ``candidate_probability`` 等价（回退路径与旧接口行为一致），但签名改为
    特征 dict，使 LightGBM 缺失时 ``feature_scorer`` 路径仍可运行。
    """
    return candidate_probability(
        features["candidate_duration_ql"],
        features["key_duration_ql"],
        features["acoustic_duration_ql"],
        features["candidate_source"],
    )


def candidate_features(event: VoiceEvent, key_duration_ql: float,
                       acoustic_duration_ql: float, candidate: DurationCandidate,
                       next_voice_onset_ql: float | None, bar_ql: float) -> dict:
    """为候选级模型构建无泄漏特征；标签由人工复核或对齐乐谱另行提供。"""
    beat_position = (event.start_ql % bar_ql) / bar_ql
    next_gap = (next_voice_onset_ql - event.start_ql
                if next_voice_onset_ql is not None else -1.0)
    return {
        "pitch": event.pitch,
        "velocity": event.velocity,
        "voice": event.voice,
        "onset_ql": round(event.start_ql, 9),
        "beat_position": round(beat_position, 9),
        "key_duration_ql": round(key_duration_ql, 9),
        "acoustic_duration_ql": round(acoustic_duration_ql, 9),
        "pedal_extension_ql": round(acoustic_duration_ql - key_duration_ql, 9),
        "next_voice_gap_ql": round(next_gap, 9),
        "candidate_duration_ql": round(candidate.duration_ql, 9),
        "candidate_key_gap_ql": round(abs(candidate.duration_ql - key_duration_ql), 9),
        "candidate_acoustic_gap_ql": round(abs(candidate.duration_ql - acoustic_duration_ql), 9),
        "candidate_crosses_barline": int(candidate.crosses_barline),
        "candidate_has_barline": int("barline" in candidate.source),
        "candidate_has_next_onset": int("next-voice-onset" in candidate.source),
        "rule_probability": round(math.exp(-candidate.score), 9),
        "candidate_source": candidate.source,
    }


def rank_candidates(start_ql, key_duration_ql, acoustic_duration_ql,
                    next_voice_onset_ql=None, bar_ql=4.0, divisors=(8, 4, 3),
                    probability_fn: Callable | None = None, *,
                    event: VoiceEvent | None = None,
                    feature_scorer: Callable | None = None,
                    fuse_alpha: float | None = None) -> list[DurationCandidate]:
    """返回候选及代价；模型仅替换概率，结构合法性始终在解码器中验证。

    两条评分路径：
    * ``feature_scorer``（可调用 dict → 概率）与 ``event`` 同时提供时，用
      ``candidate_features`` 构造完整特征向量打分——LightGBM 适配器在此接入；
    * 否则沿用 ``probability_fn``（旧解码 API，按 duration/key/acoustic/source）。
    即使走模型路径，``rule_probability`` 特征仍由规则概率填充，与训练 CSV 口径一致。
    """
    probability_fn = probability_fn or candidate_probability
    feature_scorer = feature_scorer or candidate_feature_probability
    ranked = []
    for duration, source in generate_duration_candidates(
        start_ql, key_duration_ql, acoustic_duration_ql, next_voice_onset_ql,
        bar_ql, divisors,
    ):
        end = start_ql + duration
        crosses = math.floor((start_ql + EPS) / bar_ql) != math.floor((end - EPS) / bar_ql)
        complexity = 0.06 if crosses else 0.0
        rule_probability = max(EPS, min(0.999999, probability_fn(
            duration, key_duration_ql, acoustic_duration_ql, source
        )))
        if event is not None:
            features = candidate_features(
                event, key_duration_ql, acoustic_duration_ql,
                DurationCandidate(duration, source, crosses,
                                  -math.log(rule_probability) + complexity),
                next_voice_onset_ql, bar_ql,
            )
            probability = max(EPS, min(0.999999, float(feature_scorer(features))))
            if fuse_alpha is not None:
                probability = ((1.0 - fuse_alpha) * probability
                               + fuse_alpha * rule_probability)
                probability = max(EPS, min(0.999999, probability))
        else:
            probability = rule_probability
        ranked.append(DurationCandidate(duration, source, crosses, -math.log(probability) + complexity))
    # 同一离散时值可同时被多个证据源提出。对解码而言它们是同一个选择；
    # 合并来源并保留最低代价，避免自动监督为同一个符号时值写多个正例。
    unique = {}
    for candidate in ranked:
        key = round(candidate.duration_ql, 9)
        existing = unique.get(key)
        if existing is None:
            unique[key] = candidate
        elif candidate.score < existing.score:
            unique[key] = DurationCandidate(candidate.duration_ql,
                                            f"{existing.source}|{candidate.source}",
                                            candidate.crosses_barline, candidate.score)
        else:
            unique[key] = DurationCandidate(existing.duration_ql,
                                            f"{existing.source}|{candidate.source}",
                                            existing.crosses_barline, existing.score)
    return sorted(unique.values(), key=lambda candidate: candidate.score)


def _stream_next_onsets(events: Iterable[VoiceEvent]) -> dict[tuple[int, float], float | None]:
    next_onset = {}
    for voice in sorted({event.voice for event in events}):
        onsets = sorted({event.start_ql for event in events if event.voice == voice})
        for index, onset in enumerate(onsets):
            next_onset[(voice, onset)] = onsets[index + 1] if index + 1 < len(onsets) else None
    return next_onset


def _candidate_sets(base, pedals, bar_ql, divisors, probability_fn, feature_scorer=None,
                    fuse_alpha: float | None = None):
    next_onsets = _stream_next_onsets(base)
    result = []
    for event in sorted(base, key=lambda item: (item.start_ql, item.voice, item.pitch)):
        next_onset = next_onsets[(event.voice, event.start_ql)]
        key_duration = event.duration_ql
        acoustic_duration = pedal_release_after(event.end_ql, pedals) - event.start_ql
        ranked = rank_candidates(event.start_ql, key_duration, acoustic_duration,
                                 next_onset, bar_ql, divisors, probability_fn,
                                 event=event, feature_scorer=feature_scorer,
                                 fuse_alpha=fuse_alpha)
        legal = [candidate for candidate in ranked if next_onset is None
                 or event.start_ql + candidate.duration_ql <= next_onset + EPS]
        if not legal:
            raise ValueError(f"voice {event.voice} 在 {event.start_ql:.6f}QL 没有合法时值候选")
        result.append((event, key_duration, acoustic_duration, next_onset, legal))

    # 同一 voice、同一 onset 的多个音最终会编码为一个 MusicXML Chord，必须共享
    # 一个符号时值。基础分配阶段已保证原始时值一致，但候选解码会按音高等特征
    # 独立排序；若不在此处施加联合约束，可能把同一 chord 拆成重叠的独立元素。
    by_chord_onset = {}
    for item in result:
        event = item[0]
        by_chord_onset.setdefault((event.voice, event.start_ql), []).append(item)
    constrained = []
    for stream_items in by_chord_onset.values():
        duration_sets = [
            {round(candidate.duration_ql, 9) for candidate in item[4]}
            for item in stream_items
        ]
        shared_durations = set.intersection(*duration_sets)
        if not shared_durations:
            event = stream_items[0][0]
            raise ValueError(
                f"voice {event.voice} 在 {event.start_ql:.6f}QL 的同起点和弦没有共同合法时值"
            )
        for event, key_duration, acoustic_duration, next_onset, legal in stream_items:
            constrained.append((
                event,
                key_duration,
                acoustic_duration,
                next_onset,
                [candidate for candidate in legal
                 if round(candidate.duration_ql, 9) in shared_durations],
            ))
    return constrained


def _decode_measure_dp(items, bar_start, bar_ql):
    """按小节对候选组合作精确 DP；事件之间独立但整个小节共享复杂度预算。"""
    bar_end = bar_start + bar_ql
    # 同 voice 同 onset 的项将写成一个 Chord，故必须作为一个联合决策：选中同一
    # 时值，并累加各成员的候选代价。不能仅约束候选集的交集，否则 DP 仍可能给
    # 同一和弦成员分别选中不同的合法时值。
    grouped_indices = {}
    for index, (event, *_rest) in enumerate(items):
        grouped_indices.setdefault((event.voice, event.start_ql), []).append(index)
    groups = [indices for _key, indices in sorted(
        grouped_indices.items(), key=lambda item: min(item[1])
    )]

    states = {0: (0.0, [])}
    for indices in groups:
        member_candidates = []
        for index in indices:
            event, _key, _acoustic, _next, candidates = items[index]
            member_candidates.append([
                candidate for candidate in candidates
                if event.start_ql < bar_end - EPS or not candidate.crosses_barline
            ])
        duration_sets = [
            {round(candidate.duration_ql, 9) for candidate in candidates}
            for candidates in member_candidates
        ]
        shared_durations = set.intersection(*duration_sets)
        options = []
        for duration in shared_durations:
            chosen = [next(
                candidate for candidate in candidates
                if round(candidate.duration_ql, 9) == duration
            ) for candidates in member_candidates]
            crosses = chosen[0].crosses_barline
            tie_cost = 0.10 if crosses else 0.0
            end = items[indices[0]][0].start_ql + chosen[0].duration_ql
            sync_cost = 0.015 if abs(end % 1.0) > EPS else 0.0
            options.append((chosen, sum(candidate.score for candidate in chosen) + tie_cost + sync_cost))
        if not options:
            event = items[indices[0]][0]
            raise ValueError(
                f"voice {event.voice} 在 {event.start_ql:.6f}QL 的同起点和弦没有小节内合法共同候选"
            )

        updated = {}
        for count, (cost, chosen_by_group) in states.items():
            for chosen, option_cost in options:
                new_count = count + int(chosen[0].crosses_barline)
                proposal = (cost + option_cost, chosen_by_group + [chosen])
                existing = updated.get(new_count)
                if existing is None or proposal[0] < existing[0]:
                    updated[new_count] = proposal
        states = updated
    # 多条跨线 tie 会损害阅读性，作为小节级联合代价而非逐音的局部常数。
    chosen_groups = min(states.items(), key=lambda item: item[1][0] + 0.04 * item[0])[1][1]
    choices = [None] * len(items)
    for indices, chosen in zip(groups, chosen_groups):
        for index, candidate in zip(indices, chosen):
            choices[index] = candidate
    return 0.0, choices


def decode_hand(raw_events, pedals, hand: str, max_voices=6, bar_ql=4.0,
                divisors=(8, 4, 3), probability_fn: Callable | None = None,
                feature_scorer: Callable | None = None,
                fuse_alpha: float | None = None) -> list[VoiceEvent]:
    """以固定 voice 分配为前提，按小节动态规划选择联合最优的离散时值。

    ``feature_scorer`` 提供时对完整 ``candidate_features`` 向量打分（LightGBM
    适配器接入点）；否则按 ``probability_fn``（规则）打分。结构合法性始终验证。
    """
    base = assign_voices(raw_events, hand=hand, max_voices=max_voices)
    candidate_sets = _candidate_sets(base, pedals, bar_ql, divisors, probability_fn,
                                     feature_scorer, fuse_alpha)
    by_measure = {}
    for item in candidate_sets:
        measure = int(math.floor((item[0].start_ql + EPS) / bar_ql))
        by_measure.setdefault(measure, []).append(item)

    decoded = []
    for measure, items in sorted(by_measure.items()):
        _cost, choices = _decode_measure_dp(items, measure * bar_ql, bar_ql)
        for (event, _key, _acoustic, _next, _candidates), choice in zip(items, choices):
            decoded.append(VoiceEvent(event.pitch, event.start_ql, choice.duration_ql,
                                      event.velocity, event.voice, hand))
    validate_voice_events(decoded)
    return sorted(decoded, key=lambda event: (event.hand, event.voice, event.start_ql, event.pitch))


def write_candidate_table(raw_events, pedals, hand: str, output_path: str | Path,
                          max_voices=6, bar_ql=4.0, divisors=(8, 4, 3)) -> int:
    """写出人工标注 / LightGBM 训练共用的候选级 CSV，初始标签为空。"""
    base = assign_voices(raw_events, hand=hand, max_voices=max_voices)
    rows = []
    for event, key_duration, acoustic_duration, next_onset, candidates in _candidate_sets(
        base, pedals, bar_ql, divisors, None
    ):
        for candidate in candidates:
            row = candidate_features(event, key_duration, acoustic_duration, candidate,
                                     next_onset, bar_ql)
            row["label"] = ""
            row["review_class"] = ""
            row["review_note"] = ""
            rows.append(row)
    fieldnames = list(rows[0]) if rows else ["label"]
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def decode_score_hands(rh_events, lh_events, pedals, max_voices=6, bar_ql=4.0,
                       divisors=(8, 4, 3), probability_fn: Callable | None = None,
                       feature_scorer: Callable | None = None,
                       fuse_alpha: float | None = None) -> dict[str, list[VoiceEvent]]:
    """整首解码：左右手分别走 ``decode_hand``，可传入规则概率函数或特征打分器。"""
    return {
        "RH": decode_hand(rh_events, pedals, "RH", max_voices, bar_ql, divisors,
                          probability_fn, feature_scorer, fuse_alpha),
        "LH": decode_hand(lh_events, pedals, "LH", max_voices, bar_ql, divisors,
                          probability_fn, feature_scorer, fuse_alpha),
    }
