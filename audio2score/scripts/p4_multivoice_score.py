#!/usr/bin/env python3
"""P4b：从多声部事件导出 MusicXML。

该导出器独立于 P3 的单 voice 生产管线。它使用 ``VoiceEvent`` 构建每一只手
的多个 music21 Voice，使同手持续音与后续短音可以同时存在；跨小节音由成员级
start/continue/stop tie 表达。P3 的既有导出器不被修改，作为稳定回归基线。

导出后处理：
* ``write_musicxml_filtered`` 过滤 music21 对合法拍尾十六分组合的 beam 假阳性
  告警（不影响输出 XML）；
* ``sanitize_tie_accidentals`` 为 tie 两端补齐显式临时记号，避免 Verovio 因
  调号重置而把同一条 tie 的两端判定为不同音高、留下未闭合 tie。
"""
from __future__ import annotations

import argparse
import contextlib
import io
import math
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from music21 import beam, chord, clef, key as keymod, metadata, meter, note, stream, tempo, tie

from midi_to_score import (
    attach_pedals,
    detect_key,
    detect_time_signature,
    midi_to_events,
    quantize_events,
    split_hands,
)
from structured_duration_decoder import decode_score_hands
from voice_assignment import VoiceEvent, validate_voice_events

EPS = 1e-7

# music21 在部分尾拍十六分组合上会把合法的 '2/partial/right' + '2/stop' 误报为
# "messed up beam pair"（见 beam.Beams.mergeConnectingPartialBeams）。序列化后
# 仍是合法的 <beam number="2">forward hook</beam>，Verovio 渲染正常；此处仅
# 过滤这条已知的假阳性告警，不修改任何 beam 数据。
_BEAM_FALSE_POSITIVE = re.compile(r"Found a messed up beam pair")

# 升号/降号在五度圈中的先后顺序（正 fifths = 升号，负 fifths = 降号）。
_SHARP_ORDER = ["F", "C", "G", "D", "A", "E", "B"]
_FLAT_ORDER = ["B", "E", "A", "D", "G", "C", "F"]

_ALTER_TO_ACCIDENTAL = {
    0: "natural",
    1: "sharp",
    -1: "flat",
    2: "double-sharp",
    -2: "flat-flat",
    0.5: "quarter-sharp",
    -0.5: "quarter-flat",
}


def write_musicxml_filtered(score, out_path: Path) -> None:
    """写出 MusicXML，并在导出日志中过滤 music21 的 beam 假阳性告警。

    ``score.write('musicxml')`` 内部经 makeNotation.makeBeams 对每个 voice 重新
    成束；对"拍尾十六分 + 前一组 partial"这类合法组合，music21 会误报一条
    "messed up beam pair" 警告。输出 XML 本身有效（forward hook / Verovio 正常），
    故只过滤该行，其余 stderr 原样透传。
    """
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        score.write("musicxml", fp=str(out_path))
    # 该假阳性是一条跨两行的告警：首行为 "Found a messed up beam pair ..."，
    # 次行是引发告警的 beam 列表 repr。逐行过滤时需把紧随其后的续行一并丢弃，
    # 否则会留下一条孤立的列表打印。
    lines = buf.getvalue().splitlines(keepends=True)
    kept = []
    drop_next = False
    for line in lines:
        if _BEAM_FALSE_POSITIVE.search(line):
            drop_next = True
            continue
        if drop_next:
            drop_next = False
            continue
        kept.append(line)
    sys.stderr.write("".join(kept))


def _key_accidental_for_step(fifths: int, step: str) -> str:
    """返回调号对某一级（step）隐含的临时记号：natural / sharp / flat。"""
    if fifths > 0:
        return "sharp" if step in _SHARP_ORDER[:fifths] else "natural"
    if fifths < 0:
        return "flat" if step in _FLAT_ORDER[:abs(fifths)] else "natural"
    return "natural"


def sanitize_tie_accidentals(xml_path: Path) -> None:
    """给 tie 两端补齐与书写音高一致的显式临时记号，避免 Verovio 未闭合 tie。

    背景：Verovio 在小节起点把每小节的行内临时记号状态重置为调号（ResetAccidentals）。
    当 music21 只在 tie 链的某些音符上写出显式 <accidental>、而下一小节开头的
    continue/stop 音符没有时，tie 两端会得到不同的 gestural 音高（如 F 大调里
    B 自然音在前一小节、后一小节被当成 B 降音），IsEnharmonicWith 判不等，
    tie 永不闭合，Verovio 报 "N ties left open"。

    修复：对所有带 <tied> 的音符，若其 <pitch><alter> 与调号隐含记号不一致，
    补写显式 <accidental>。这使整条 tie 链的 gestural 音高一致，且不改变书写音高，
    因此不影响逐音对账（reconcile 只读 pitch/start/duration/tie）。
    """
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    for part in root:
        if part.tag != "part":
            continue
        fifths = None
        for measure in part.findall("measure"):
            # 调号在小节内可能变化（转调）；music21 只在变化处重写 <key>。
            # 逐小节维护当前调号，避免全曲误用第一小节的 fifths 判断。
            for attr in measure.findall("attributes"):
                fifths_el = attr.find("key/fifths")
                if fifths_el is not None and fifths_el.text:
                    fifths = int(fifths_el.text)
            if fifths is None:
                # 无任何调号（全临时记号谱）时无法判断，保守跳过。
                continue
            for note_el in measure.iter("note"):
                if note_el.find("notations/tied") is None:
                    continue
                pitch = note_el.find("pitch")
                if pitch is None:
                    continue
                step = pitch.findtext("step")
                if not step:
                    continue
                alter_el = pitch.find("alter")
                alter = float(alter_el.text) if alter_el is not None else 0.0
                written = _ALTER_TO_ACCIDENTAL.get(alter)
                if written is None:
                    continue
                if written == _key_accidental_for_step(fifths, step):
                    continue
                existing = note_el.findall("accidental")
                if existing and existing[0].text == written:
                    continue
                accidental = ET.Element("accidental")
                accidental.text = written
                notations = note_el.find("notations")
                insert_at = list(note_el).index(notations) if notations is not None else len(list(note_el))
                note_el.insert(insert_at, accidental)
    tree.write(str(xml_path), encoding="UTF-8", xml_declaration=False)



def insert_exact_pedals(xml_path: Path, pedals: list[tuple[float, float]],
                        bar_ql: float) -> None:
    """在踏板区间的精确位置写入 MusicXML <direction><pedal/></direction>。

    ``pedals`` 为段内 QL 坐标的 (start, end) 区间（相对 MIDI 起点 0）。
    与 ``attach_pedals``（吸附到最近音符）不同，本函数不吸附：位置由
    CC64 事件本身决定，用 ``<offset>`` 写入小节内精确偏移，从而保留
    演奏层踏板的真实时序。同位置的 stop+start 合并为 ``change``。
    """
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    parts = root.findall("part")
    part = parts[1] if len(parts) > 1 else parts[0]
    measures = {int(m.get("number")): m for m in part.findall("measure")}
    divisions = None
    for m in measures.values():
        d = m.find("attributes/divisions")
        if d is not None:
            divisions = int(d.text)
            break
    if divisions is None:
        raise RuntimeError("cannot find divisions in MusicXML")
    events = []
    for s, e in pedals:
        events.append((s, "start"))
        events.append((e, "stop"))
    events.sort(key=lambda item: (item[0], 0 if item[1] == "start" else 1))
    merged = []
    i = 0
    while i < len(events):
        pos, typ = events[i]
        if (typ == "stop" and i + 1 < len(events)
                and events[i + 1][0] == pos and events[i + 1][1] == "start"):
            merged.append((pos, "change"))
            i += 2
        else:
            merged.append((pos, typ))
            i += 1
    for pos, typ in merged:
        measure_num = int(math.floor(pos / bar_ql)) + 1
        offset_ql = pos - (measure_num - 1) * bar_ql
        offset_div = int(round(max(0.0, offset_ql) * divisions))
        m = measures.get(measure_num)
        if m is None:
            continue
        direction = ET.SubElement(m, "direction")
        direction.set("placement", "below")
        dtype = ET.SubElement(direction, "direction-type")
        pedal = ET.SubElement(dtype, "pedal")
        pedal.set("type", typ)
        if offset_div > 0:
            off = ET.SubElement(direction, "offset")
            off.text = str(offset_div)
    tree.write(str(xml_path), encoding="UTF-8", xml_declaration=False)


def sanitize_pedal_retakes(xml_path: Path) -> None:
    """把同一落点的踏板 stop/start 合并为 MusicXML ``change``。

    ``PedalMark`` 为每个 CC64 区间写出一对独立的 start/stop。相邻区间的松踏与
    再踩若都吸附到同一个记谱事件，music21 会在该位置串行输出 stop、start；这在
    语义上是一次换踏（retake），而 MusicXML 应使用单个 ``type="change"``。
    不同落点的两端保持原样，避免将真实的无踏间隔错误压缩。
    """
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            children = list(measure)
            index = 0
            while index + 1 < len(children):
                current, following = children[index], children[index + 1]
                current_pedal = current.find("direction-type/pedal") if current.tag == "direction" else None
                following_pedal = (following.find("direction-type/pedal")
                                   if following.tag == "direction" else None)
                if (current_pedal is not None and following_pedal is not None
                        and current_pedal.get("type") == "stop"
                        and following_pedal.get("type") == "start"):
                    current_pedal.set("type", "change")
                    measure.remove(following)
                    children.pop(index + 1)
                    continue
                index += 1
    tree.write(str(xml_path), encoding="UTF-8", xml_declaration=False)


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
                # 声部时值由候选解码器决定；清除 music21 自动 beam，避免
                # 不同 voice 的局部时值组合触发错误的 beam 配对警告。
                if hasattr(element, "beams"):
                    element.beams = beam.Beams()
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


def decode_midi_to_voice_events(midi_path, divisors=(8, 4, 3), max_voices=6,
                                feature_scorer=None, use_pedal=True,
                                fuse_alpha: float | None = None):
    """读取 MIDI 并作多声部解码，可严格关闭踏板信息。

    ``feature_scorer`` 可为 LightGBM 候选评分器；缺省时结构化解码器使用规则评分。
    ``use_pedal=False`` 时，真实 CC64 不进入声学时值、候选特征或候选排序。
    无论评分来源如何，声部无重叠和小节边界均由解码器的硬约束保证。
    """
    notes, pedals, meta = midi_to_events(midi_path)
    qnotes = quantize_events(notes, divisors=divisors)
    detected = detect_time_signature(qnotes, meta["tempo_bpm"], meta["time_sigs"])
    time_sig = detected or meta["time_sigs"][0][:2]
    key = detect_key(qnotes)
    rh, lh = split_hands(qnotes)
    bar_ql = 4.0 * time_sig[0] / time_sig[1]
    decoder_pedals = pedals if use_pedal else []
    decoded = decode_score_hands(rh, lh, decoder_pedals, max_voices=max_voices,
                                 bar_ql=bar_ql, divisors=divisors,
                                 feature_scorer=feature_scorer, fuse_alpha=fuse_alpha)
    return decoded, pedals, meta, time_sig, key


def main():
    parser = argparse.ArgumentParser(description="P4 多声部 MIDI → MusicXML 原型")
    parser.add_argument("--midi", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--title", default="P4 Multi-voice Piano Transcription")
    parser.add_argument("--divisors", default="8,4,3")
    parser.add_argument("--max-voices", type=int, default=6)
    parser.add_argument(
        "--candidate-model", default=None,
        help="可选 LightGBM 候选模型前缀（.txt/.json）；缺失或不可用时回退规则评分",
    )
    parser.add_argument(
        "--fuse-alpha", type=float, default=None,
        help="候选评分融合系数：模型概率与规则先验的加权混合（0=纯模型，1=纯规则）；需与 --candidate-model 一起使用",
    )
    parser.add_argument(
        "--pedal-placement", choices=("snap", "exact"), default="snap",
        help="踏板符号位置策略：snap=吸附到最近音符（默认，PedalMark spanner）；exact=精确位置（CC64 区间边界，<offset> 写入，更忠实演奏层时序）",
    )
    parser.add_argument(
        "--no-pedal", action="store_true",
        help="严格禁用 CC64：不参与时值候选/评分特征，也不输出 MusicXML 踏板符号",
    )
    args = parser.parse_args()

    divisors = tuple(int(item) for item in args.divisors.split(","))
    feature_scorer = None
    scorer_name = "规则评分"
    if args.candidate_model:
        from train_candidate_model import probability_from_model
        scorer = probability_from_model(args.candidate_model)
        if getattr(scorer, "score_features", None) is not None:
            feature_scorer = scorer
            scorer_name = f"LightGBM：{args.candidate_model}"
        else:
            print(f"候选模型不可用，回退规则评分：{args.candidate_model}", file=sys.stderr)
    decoded, pedals, meta, time_sig, key = decode_midi_to_voice_events(
        args.midi, divisors=divisors, max_voices=args.max_voices,
        feature_scorer=feature_scorer, use_pedal=not args.no_pedal,
        fuse_alpha=args.fuse_alpha,
    )
    score = assemble_multivoice_score(
        decoded["RH"], decoded["LH"], meta["tempo_bpm"], time_sig,
        key.sharps if key else None, args.title,
    )
    # 无踏板模式不读取 CC64 的解码结果，也不输出踏板符号；有踏板模式才附加
    # 标准 PedalMark，保持其作为声学延续证据与演奏标记的独立语义。
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not args.no_pedal and args.pedal_placement == "exact":
        # exact：不吸附音符，写出后在 XML 层插入精确位置 <direction><pedal/>
        write_musicxml_filtered(score, out)
        insert_exact_pedals(out, pedals, bar_ql)
    else:
        if not args.no_pedal:
            attach_pedals(score.parts[1], pedals)
        write_musicxml_filtered(score, out)
        if not args.no_pedal:
            sanitize_pedal_retakes(out)
    sanitize_tie_accidentals(out)
    pedal_status = (
        "禁用（不参与时值候选/评分特征/符号输出）"
        if args.no_pedal else "启用"
    )
    print(
        f"写出 {out}；评分={scorer_name}；踏板={pedal_status}；拍号 {time_sig[0]}/{time_sig[1]}；"
        f"RH {len(decoded['RH'])} 音/{len(set(event.voice for event in decoded['RH']))} voice；"
        f"LH {len(decoded['LH'])} 音/{len(set(event.voice for event in decoded['LH']))} voice"
    )


if __name__ == "__main__":
    main()
