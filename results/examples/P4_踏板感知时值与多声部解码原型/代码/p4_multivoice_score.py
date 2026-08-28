#!/usr/bin/env python3
"""P4b：从多声部事件导出 MusicXML。

该导出器独立于 P3 的单 voice 生产管线。它使用 ``VoiceEvent`` 构建每一只手
的多个 music21 Voice，使同手持续音与后续短音可以同时存在；跨小节音由成员级
start/continue/stop tie 表达。P3 的既有导出器不被修改，作为稳定回归基线。
"""
from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path

from music21 import chord, clef, key as keymod, metadata, meter, note, stream, tempo, tie

from midi_to_score import (
    detect_key,
    detect_time_signature,
    midi_to_events,
    quantize_events,
    split_hands,
)
from structured_duration_decoder import decode_score_hands
from voice_assignment import VoiceEvent, validate_voice_events

EPS = 1e-7


def split_voice_events_at_barlines(events, bar_ql: float):
    """逐 voice 在小节边界切分事件，并赋予成员级 tie 标记。"""
    out = []
    for event in events:
        start = event.start_ql
        end = event.end_ql
        boundaries = []
        boundary = (math.floor(start / bar_ql) + 1) * bar_ql
        while boundary < end - EPS:
            boundaries.append(boundary)
            boundary += bar_ql
        points = [start, *boundaries, end]
        for index, (left, right) in enumerate(zip(points, points[1:])):
            role = None
            if len(points) > 2:
                role = "start" if index == 0 else ("stop" if index == len(points) - 2 else "continue")
            out.append((
                VoiceEvent(event.pitch, left, right - left, event.velocity, event.voice, event.hand),
                role,
            ))
    return out


def _music_element(group):
    """相同 voice/onset/duration 的事件组转换为 Note 或 Chord。"""
    role_set = {role for _event, role in group}
    if len(role_set) > 1:
        # 同声部、同起点、同时值却有不同 tie 语义极少出现。保守地保持独立，
        # 而不是丢弃成员级 tie；调用方会将其拆为独立组。
        raise ValueError("同一 Chord 组中存在不一致的 tie 角色")
    role = next(iter(role_set))
    events = [event for event, _role in group]
    if len(events) == 1:
        event = events[0]
        element = note.Note(event.pitch, quarterLength=event.duration_ql)
        element.volume.velocity = event.velocity
        if role:
            element.tie = tie.Tie(role)
        return element
    members = []
    for event in sorted(events, key=lambda item: item.pitch):
        member = note.Note(event.pitch, quarterLength=event.duration_ql)
        member.volume.velocity = event.velocity
        if role:
            member.tie = tie.Tie(role)
        members.append(member)
    element = chord.Chord(members)
    element.quarterLength = events[0].duration_ql
    return element


def _voice_measure_elements(segments, measure_index, bar_ql):
    """生成一个 voice 在一个小节内的事件；无内容时返回整小节 rest。"""
    start = measure_index * bar_ql
    end = start + bar_ql
    relevant = [(event, role) for event, role in segments
                if start - EPS <= event.start_ql < end - EPS]
    grouped = defaultdict(list)
    for event, role in relevant:
        # tie 角色不同的同 onset/duration 音不可合入一个 Chord。
        grouped[(event.start_ql, event.duration_ql, role)].append((event, role))
    result = []
    cursor = start
    for (offset, duration, _role), group in sorted(grouped.items()):
        if offset < cursor - EPS:
            raise ValueError(f"voice 内重叠：{offset:.6f} < {cursor:.6f}")
        if offset > cursor + EPS:
            result.append((cursor - start, note.Rest(quarterLength=offset - cursor)))
        element = _music_element(group)
        result.append((offset - start, element))
        cursor = offset + duration
    if cursor < end - EPS:
        result.append((cursor - start, note.Rest(quarterLength=end - cursor)))
    if cursor > end + EPS:
        raise ValueError("事件未经正确小节切分")
    return result


def build_multivoice_part(events, hand_name, clef_obj, tempo_bpm, time_sig, key_signature):
    """把一只手的 VoiceEvent 导出为带独立 music21 Voice 的 Part。"""
    validate_voice_events(events)
    num, den = time_sig
    bar_ql = 4.0 * num / den
    segments = split_voice_events_at_barlines(events, bar_ql)
    max_end = max((event.end_ql for event in events), default=0.0)
    measure_count = max(1, math.ceil((max_end - EPS) / bar_ql))
    voice_ids = sorted({event.voice for event in events}) or [1]

    part = stream.Part(id=hand_name)
    for measure_number in range(1, measure_count + 1):
        measure = stream.Measure(number=measure_number)
        if measure_number == 1:
            measure.insert(0, meter.TimeSignature(f"{num}/{den}"))
            measure.insert(0, clef_obj)
            measure.insert(0, tempo.MetronomeMark(number=tempo_bpm))
            if key_signature is not None:
                measure.insert(0, keymod.KeySignature(key_signature))
        for voice_id in voice_ids:
            voice = stream.Voice(id=str(voice_id))
            own_segments = [(event, role) for event, role in segments if event.voice == voice_id]
            for local_offset, element in _voice_measure_elements(
                own_segments, measure_number - 1, bar_ql
            ):
                voice.insert(local_offset, element)
            measure.insert(0, voice)
        part.insert((measure_number - 1) * bar_ql, measure)
    part.partName = hand_name
    return part


def assemble_multivoice_score(rh_events, lh_events, tempo_bpm, time_sig, key_signature, title):
    score = stream.Score()
    score.metadata = metadata.Metadata(
        title=title, composer="ClawsGO Science / audio2score P4"
    )
    score.insert(0, build_multivoice_part(
        rh_events, "Piano R.H.", clef.TrebleClef(), tempo_bpm, time_sig, key_signature
    ))
    score.insert(0, build_multivoice_part(
        lh_events, "Piano L.H.", clef.BassClef(), tempo_bpm, time_sig, key_signature
    ))
    return score


def decode_midi_to_voice_events(midi_path, divisors=(8, 4, 3), max_voices=6):
    notes, pedals, meta = midi_to_events(midi_path)
    qnotes = quantize_events(notes, divisors=divisors)
    detected = detect_time_signature(qnotes, meta["tempo_bpm"], meta["time_sigs"])
    time_sig = detected or meta["time_sigs"][0][:2]
    key = detect_key(qnotes)
    rh, lh = split_hands(qnotes)
    bar_ql = 4.0 * time_sig[0] / time_sig[1]
    decoded = decode_score_hands(rh, lh, pedals, max_voices=max_voices,
                                 bar_ql=bar_ql, divisors=divisors)
    return decoded, meta, time_sig, key


def main():
    parser = argparse.ArgumentParser(description="P4 多声部 MIDI → MusicXML 原型")
    parser.add_argument("--midi", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--title", default="P4 Multi-voice Piano Transcription")
    parser.add_argument("--divisors", default="8,4,3")
    parser.add_argument("--max-voices", type=int, default=6)
    args = parser.parse_args()

    divisors = tuple(int(item) for item in args.divisors.split(","))
    decoded, meta, time_sig, key = decode_midi_to_voice_events(
        args.midi, divisors=divisors, max_voices=args.max_voices
    )
    score = assemble_multivoice_score(
        decoded["RH"], decoded["LH"], meta["tempo_bpm"], time_sig,
        key.sharps if key else None, args.title,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    score.write("musicxml", fp=str(out))
    print(
        f"写出 {out}；拍号 {time_sig[0]}/{time_sig[1]}；"
        f"RH {len(decoded['RH'])} 音/{len(set(event.voice for event in decoded['RH']))} voice；"
        f"LH {len(decoded['LH'])} 音/{len(set(event.voice for event in decoded['LH']))} voice"
    )


if __name__ == "__main__":
    main()
