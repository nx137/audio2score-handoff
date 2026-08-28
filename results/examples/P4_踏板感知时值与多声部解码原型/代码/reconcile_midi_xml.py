#!/usr/bin/env python3
"""
reconcile_midi_xml.py — MIDI 输入 ↔ MusicXML 输出逐音对账。

用途:验证"多写/漏写音符"。用户此前发现 MusicXML 会把延音线拆成多个
<note>,因此对账前必须先把 tie 链合并成"真实音符事件"再与 MIDI 一一配对。

方法:
  1) MIDI 侧:pretty_midi 读出全部音符 (pitch, start_ql, dur_ql)。
  2) XML 侧:直接解析 MusicXML(ElementTree,不依赖 music21 读谱)。
     按 <measure> 内 <note> 顺序推算全局偏移(处理 <chord/>、<backup/>、
     <forward/>),把 <tie> 链合并为真实事件 (pitch, start_ql, dur_ql)。
  3) 配对:按 (pitch, start) 排序后贪心匹配,允许起止容差。
  4) 报告:多写(仅在 XML)、漏写(仅在 MIDI)的音符与所在小节。

用法:
  python3 reconcile_midi_xml.py --midi in.mid --xml out.xml \
      [--onset-tol 0.125] [--dur-tol 0.25]
"""
from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET

import pretty_midi

# 复用生产流水线的量化/分手/时值约束,确保“导出前基准”与实际输出同源。
from midi_to_score import (clip_to_next_onset, midi_to_events,
                           quantize_events, split_hands)

STEP_SEMIS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _pitch_midi(pitch_el) -> int | None:
    """<pitch> 元素 → MIDI 编号。"""
    if pitch_el is None:
        return None
    step = pitch_el.findtext("step")
    alter = int(pitch_el.findtext("alter") or 0)
    octave = int(pitch_el.findtext("octave"))
    return (octave + 1) * 12 + STEP_SEMIS[step] + alter


def midi_notes(midi_path: str, bpm: float | None = None) -> list:
    """MIDI → [(pitch, start_ql, dur_ql)]。"""
    pm = pretty_midi.PrettyMIDI(midi_path)
    if bpm is None:
        bpm = pm.get_tempo_changes()[1][0]   # 首个速度,与主流水线一致
    beat_sec = 60.0 / bpm
    out = []
    for inst in pm.instruments:
        for n in inst.notes:
            out.append((n.pitch, n.start / beat_sec,
                        (n.end - n.start) / beat_sec))
    return out


def notation_input_notes(midi_path: str, divisors=(8, 4, 3)) -> list:
    """复走生产流水线,返回跨小节拆分前的记谱输入事件。

    这是验证导出层“有没有凭空增删音”的正确基准。原始演奏 MIDI 的起音
    和时值会被量化器有意修改,不应把这些合法变化算作 XML 多写/漏写。
    """
    notes, _pedals, _meta = midi_to_events(midi_path)
    qnotes = quantize_events(notes, divisors=divisors)
    rh, lh = split_hands(qnotes)
    rh = clip_to_next_onset(rh, divisors=divisors)
    lh = clip_to_next_onset(lh, divisors=divisors)
    return [(p, s, d) for p, s, d, _v in rh + lh]


def xml_real_events(xml_path: str) -> list:
    """MusicXML → 真实音符事件(合并 tie 链)。

    返回 [(pitch, start_ql, dur_ql, measure_no), ...]。

    偏移约定(与 music21 读谱一致):
      * 小节内光标只按 <duration> 的**原始值**推进(music21 对 offset 游标
        使用 raw 时值,不做 time-modification 归一;`<duration>` 本身就是
        实际时值——四分三连音写 0.667QL);
      * 休止符是 <note type="rest"> 而非 <forward>,同样要推进光标;
      * 小节原点按拍号取 (measure_no-1)*bar_ql,不累计实际光标——
        否则残留的微超(overfull)会把后续小节整体推偏。
    """
    root = ET.parse(xml_path).getroot()
    events: list = []
    # (part, voice, pitch) -> events 中首段的可变记录[pitch, start, total_dur, measure_no]。
    # 多声部 MusicXML 中不同 voice 可以在同一时刻保留相同 pitch；若只按 pitch
    # 追踪，会把两条合法 tie 链错误串接，进而虚报多写或起音漂移。
    open_by_stream_pitch: dict = {}
    bar_ql = 4.0               # 默认 4/4,遇 <attributes> 拍号覆盖

    for part_index, part_el in enumerate(root.iter("part")):
        part_id = part_el.get("id") or str(part_index)
        divisions = None
        first_attr = True
        for measure_el in part_el.findall("measure"):
            measure_no = int(measure_el.get("number") or 0)
            cursor = 0.0
            last_note_start = 0.0
            for child in measure_el:
                tag = child.tag
                if tag == "attributes":
                    d = child.findtext("divisions")
                    if d:
                        divisions = int(d)
                    if first_attr and divisions:
                        beats = child.findtext("time/beats")
                        btype = child.findtext("time/beat-type")
                        if beats and btype:
                            bar_ql = 4.0 * float(beats) / float(btype)
                        first_attr = False
                elif tag == "note":
                    if divisions is None:
                        continue
                    raw = int(child.findtext("duration") or 0) / divisions
                    is_grace = child.find("grace") is not None
                    is_chord_member = child.find("chord") is not None
                    pitch = _pitch_midi(child.find("pitch"))
                    if is_grace:
                        continue                    # 装饰音不计时值、不推进
                    note_start = last_note_start if is_chord_member else cursor
                    if pitch is not None:
                        start = (measure_no - 1) * bar_ql + note_start
                        voice_id = child.findtext("voice") or "1"
                        stream_key = (part_id, voice_id, pitch)
                        tie_types = {el.get("type") for el in child.findall("tie")}
                        has_start = "start" in tie_types
                        has_stop = "stop" in tie_types
                        event = open_by_stream_pitch.get(stream_key)
                        if has_stop and event is not None:
                            # MusicXML 用 stop+start 表示 tie 中间段：先续接旧链；
                            # 若同时有 start，链保持打开，否则在此结束。
                            event[2] = start + raw - event[1]
                            if not has_start:
                                del open_by_stream_pitch[stream_key]
                        elif has_stop:
                            # 损坏 XML 的孤立 stop：保留为独立事件，便于报差异。
                            event = [pitch, start, raw, measure_no]
                            events.append(event)
                            if has_start:
                                open_by_stream_pitch[stream_key] = event
                        else:
                            event = [pitch, start, raw, measure_no]
                            events.append(event)
                            if has_start:
                                open_by_stream_pitch[stream_key] = event
                    if not is_chord_member:
                        last_note_start = cursor
                        cursor += raw                # 含休止符(rest 也是 note)
                elif tag == "backup":
                    cursor -= int(child.findtext("duration") or 0) / divisions
                elif tag == "forward":
                    cursor += int(child.findtext("duration") or 0) / divisions
    return [tuple(event) for event in events]


def reconcile(midi_evts: list, xml_evts: list, onset_tol=0.125, dur_tol=0.25):
    """按同音高事件的时间顺序配对，分别报告增删、起音漂移与时值差异。

    “多写/漏写”只由各音高的事件数决定；相同音高的第 n 次起音配对后，
    起音和时值超出容差分别列入差异。这样不会把 MusicXML 排谱造成的局部
    节奏漂移误报成凭空新增/删除音符。
    """
    by_pitch_midi: dict = {}
    by_pitch_xml: dict = {}
    for event in midi_evts:
        by_pitch_midi.setdefault(event[0], []).append(event)
    for event in xml_evts:
        by_pitch_xml.setdefault(event[0], []).append(event)
    for events in by_pitch_midi.values():
        events.sort(key=lambda e: e[1])
    for events in by_pitch_xml.values():
        events.sort(key=lambda e: e[1])

    extra: list = []
    missing: list = []
    onset_diffs: list = []
    dur_diffs: list = []
    for pitch in sorted(set(by_pitch_midi) | set(by_pitch_xml)):
        mm = by_pitch_midi.get(pitch, [])
        xx = by_pitch_xml.get(pitch, [])
        n = min(len(mm), len(xx))
        for i in range(n):
            _p, s, d = mm[i]
            _xp, xs, xd, bar = xx[i]
            if abs(xs - s) > onset_tol:
                onset_diffs.append((pitch, s, xs, bar))
            if abs(xd - d) > dur_tol:
                dur_diffs.append((pitch, s, d, xd, bar))
        missing.extend((p, s, d, None) for p, s, d in mm[n:])
        extra.extend(xx[n:])
    return extra, missing, onset_diffs, dur_diffs


def describe(evts, max_show=12):
    lines = []
    for p, s, d, bar in evts[:max_show]:
        where = f" 小节{bar}" if bar is not None else ""
        lines.append(f"  p{p}({pretty_name(p)}){where} 偏移{s:.2f} 时值{d:.3f}")
    if len(evts) > max_show:
        lines.append(f"  … 共 {len(evts)} 条,仅列前 {max_show}")
    return "\n".join(lines)


def pretty_name(pitch):
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return names[pitch % 12] + str(pitch // 12 - 1)


def main():
    ap = argparse.ArgumentParser(description="MIDI ↔ MusicXML 逐音对账")
    ap.add_argument("--midi", required=True)
    ap.add_argument("--xml", required=True)
    ap.add_argument("--bpm", type=float, default=None,
                    help="拍速(仅 raw 模式;默认从 MIDI 首速度读取)")
    ap.add_argument("--divisors", default="8,4,3",
                    help="记谱量化网格,须与 midi_to_score 一致")
    ap.add_argument("--reference", choices=("notation", "raw"), default="notation",
                    help="对账基准:notation=导出前中间事件(默认),raw=原始演奏 MIDI")
    ap.add_argument("--onset-tol", type=float, default=0.125)
    ap.add_argument("--dur-tol", type=float, default=0.25)
    args = ap.parse_args()

    divisors = tuple(int(x) for x in args.divisors.split(","))
    if args.reference == "notation":
        midi_evts = notation_input_notes(args.midi, divisors=divisors)
        ref_name = "记谱输入事件"
    else:
        midi_evts = midi_notes(args.midi, args.bpm)
        ref_name = "原始 MIDI 音符"
    xml_evts = xml_real_events(args.xml)
    extra, missing, onset_diffs, dur_diffs = reconcile(
        midi_evts, xml_evts,
        onset_tol=args.onset_tol,
        dur_tol=args.dur_tol,
    )

    print(f"{ref_name}: {len(midi_evts)}  | XML 真实音符事件(延音线已合并): {len(xml_evts)}")
    print(f"多写(仅 XML): {len(extra)}  | 漏写(仅 MIDI): {len(missing)}"
          f"  | 起音漂移>{args.onset_tol}: {len(onset_diffs)}"
          f"  | 时值偏差>{args.dur_tol}: {len(dur_diffs)}")
    if extra:
        print("多写明细(前 12 条):\n" + describe(extra))
    if missing:
        print("漏写明细(前 12 条):\n" + describe(missing))
    if onset_diffs:
        lines = []
        for p, s_mid, s_xml, bar in onset_diffs[:8]:
            lines.append(f"  p{p}({pretty_name(p)}) 小节{bar} "
                         f"MIDI偏移{s_mid:.2f}→XML偏移{s_xml:.2f}")
        if len(onset_diffs) > 8:
            lines.append(f"  … 共 {len(onset_diffs)} 处")
        print("起音漂移明细(前 8 条):\n" + "\n".join(lines))
    if dur_diffs:
        lines = []
        for p, s, d_mid, d_xml, bar in dur_diffs[:8]:
            lines.append(f"  p{p}({pretty_name(p)}) 小节{bar} 偏移{s:.2f} "
                         f"MIDI时值{d_mid:.3f}→XML时值{d_xml:.3f}")
        if len(dur_diffs) > 8:
            lines.append(f"  … 共 {len(dur_diffs)} 处")
        print("时值偏差明细(前 8 条):\n" + "\n".join(lines))

    ok = not extra and not missing
    print("对账结果:", "✅ 完全一致" if ok else "❌ 存在差异")
    return 0 if ok else 1


if __name__ == "__main__":
    main()
