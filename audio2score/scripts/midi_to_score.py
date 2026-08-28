#!/usr/bin/env python3
"""
midi_to_score.py — M0 基础管线:MIDI → 量化 → 左右手拆分 → 排谱 → MusicXML。

设计原则:
  * 输入:pretty_midi 可读的 .mid(支持 CC64 延音踏板事件)
  * 中间表示:扁平音符事件 (pitch, start_ql, dur_ql, velocity) + 踏板区间 (s, e)
  * 输出:MusicXML(含 <pedal>),供 Verovio / MuseScore 渲染五线谱
  * 模块边界:quantize_events() 是未来 P2"踏板感知量化"的替换单元——
    P2 只需在该函数里加入踏板分割与时值推断,下游排谱无需改动。

用法:
  python3 midi_to_score.py --midi ../samples/test_performance.mid \
      --out ../samples/test_score.xml
"""
from __future__ import annotations

import argparse

import pretty_midi
from music21 import chord, clef, duration, meter, note, stream, tempo, tie
from music21.expressions import PedalForm, PedalMark, PedalType
from music21.stream import makeNotation as mn

QUANTIZE_DIVISORS = (4, 3)  # 16 分音符 + 八分三连音网格
HAND_BOUNDARY = 60          # 右手 >= C4,左手 < C4(M0 启发式,后续升级)
BEAT_QN = 1.0               # 一拍 = 1 quarterLength


# --------------------------------------------------------------------------
# 1. MIDI → 事件
# --------------------------------------------------------------------------
def midi_to_events(midi_path: str):
    """读取 MIDI,返回 (notes, pedals, meta)。

    notes:  [(pitch, start_ql, dur_ql, velocity), ...],按起始排序
    pedals: [(start_ql, end_ql), ...]  来自 CC64 事件
    meta:   {'tempo_bpm': float, 'time_sigs': [(num, den, offset_ql), ...]}
    """
    pm = pretty_midi.PrettyMIDI(midi_path)
    tempo_changes = pm.get_tempo_changes()
    tempo_bpm = tempo_changes[1][0]  # 采用首个速度(全曲恒定,M0 简化)
    beat_sec = 60.0 / tempo_bpm

    notes = []
    for inst in pm.instruments:
        for n in inst.notes:
            notes.append((n.pitch, n.start / beat_sec,
                          (n.end - n.start) / beat_sec, n.velocity))

    time_sigs = [(int(t.numerator), int(t.denominator), float(t.time) / beat_sec)
                 for t in pm.time_signature_changes] or [(4, 4, 0.0)]

    # CC64 → 踏板区间:>=64 为踩下,<64 为释放
    pedals: list = []
    pedal_on: float | None = None
    cc64 = [c for inst in pm.instruments for c in inst.control_changes if c.number == 64]
    for c in sorted(cc64, key=lambda c: c.time):
        t = c.time / beat_sec
        if c.value >= 64 and pedal_on is None:
            pedal_on = t
        elif c.value < 64 and pedal_on is not None:
            pedals.append((pedal_on, t))
            pedal_on = None
    if pedal_on is not None:  # 踩到曲终未释放
        end = notes[-1][1] + notes[-1][2] if notes else 0.0
        pedals.append((pedal_on, end))
    return notes, pedals, {'tempo_bpm': float(tempo_bpm), 'time_sigs': time_sigs}


# --------------------------------------------------------------------------
# 2. 量化(未来的"踏板感知量化"替换此函数)
# --------------------------------------------------------------------------
def quantize_events(events, divisors=QUANTIZE_DIVISORS, onset_tol_ql=0.045):
    """把 (pitch, start, dur, vel) 量化到网格。

    自研量化器(不依赖 music21 的 Stream.quantize,后者对同 offset 和弦
    有 look-ahead 缺陷):
      1) 按 onset 容差聚类同奏音符(避免和弦被误当作相邻事件);
      2) 每个 onset/时值独立吸附到网格(divisors 的 1/d 刻度);
      3) 同音高相邻音符:重叠则截断、小间隙则填平(模拟 look-ahead 行为)。

    onset_tol_ql: 同奏判定容差(QL)。90bpm 下 0.045QL ≈ 30ms。
    """
    ticks = sorted({1.0 / d for d in divisors})

    def snap(x):
        best, be = None, None
        for t in ticks:
            cand = round(x / t) * t
            err = abs(cand - x)
            if be is None or err < be:
                best, be = cand, err
        return best

    # 1) onset 聚类
    evs = sorted(events, key=lambda e: e[1])
    clusters = []
    for e in evs:
        for cl in clusters:
            if abs(cl["ref"] - e[1]) <= onset_tol_ql:
                cl["notes"].append(e)
                break
        else:
            clusters.append({"ref": e[1], "notes": [e]})

    out = []
    for cl in clusters:
        qoff = snap(cl["ref"])
        for pitch, _s, d, v in cl["notes"]:
            qd = max(snap(d), min(ticks))
            out.append([pitch, qoff, qd, v])

    # 2) 同音高:重叠截断 + 小间隙填平
    out.sort(key=lambda x: (x[1], x[0]))
    by_pitch: dict = {}
    for e in out:
        by_pitch.setdefault(e[0], []).append(e)
    for notes in by_pitch.values():
        for i in range(len(notes) - 1):
            cur, nxt = notes[i], notes[i + 1]
            end = cur[1] + cur[2]
            if end > nxt[1] + 1e-9:          # 重叠 → 截断到下一音起点
                notes[i][2] = max(nxt[1] - cur[1], min(ticks))
            elif nxt[1] - end < 0.5 * min(ticks):  # 小间隙(<半 tick) → 填平
                notes[i][2] = nxt[1] - cur[1]
    return [tuple(e) for e in out]


def clip_to_next_onset(events, divisors=QUANTIZE_DIVISORS):
    """单声部内:音符时值上限 = 到本声部下一**任意** onset 的网格距离。

    每只手目前输出为单一 MusicXML voice，因而该手内不同音高的交叠若不
    显式分 voice，导出时会被顺序写入并把小节时值撑爆。这里将每个音符限制
    到该手下一任意起音，保留同 onset 的和弦，同时确保单声部时间线无交叠。
    真正需保留的跨声部/跨小节延音由后续多 voice 编码处理；左右手仍分别调用，
    不会把左手延音截到右手旋律起音。
    """
    evs = sorted(events, key=lambda e: e[1])
    onsets = sorted({e[1] for e in evs})
    next_start = {o: onsets[i + 1] for i, o in enumerate(onsets[:-1])}
    out = [list(e) for e in evs]
    for e in out:
        nxt = next_start.get(e[1])
        if nxt is not None:
            # 不能把小于最小网格的实际间隔抬高到 ``min(ticks)``：在三连音
            # (1/3) 与 32 分网格(1/8)交界会制造 1/24 QL 的重叠，随后被
            # makeRests 误写为伪 64 分休止并造成小节超拍。此处以真实的量化
            # onset 间隔截断；极短片段将在后续节奏/声部模型中进一步处理。
            gap = nxt - e[1]
            if gap > 1e-9:
                e[2] = min(e[2], gap)
    return [tuple(e) for e in out]


# --------------------------------------------------------------------------
# 3. 左右手拆分 + 排谱
# --------------------------------------------------------------------------
def split_hands(events):
    """按音高拆分:M0 启发式(HAND_BOUNDARY),真实转录的声部分配留待 P2。"""
    rh = [e for e in events if e[0] >= HAND_BOUNDARY]
    lh = [e for e in events if e[0] < HAND_BOUNDARY]
    return rh, lh


def build_part(events, part_name, clef_obj, tempo_bpm=90.0, time_sigs=None,
               key_sharps=None):
    """构建单一 Part(音符 + 调号 + 拍号 + 速度 + 谱号),再做完整排谱。"""
    part = stream.Part()
    if key_sharps is not None:
        from music21 import key as keymod
        part.insert(0, keymod.KeySignature(key_sharps))  # 调号必须在 part 层
    time_sigs = time_sigs or [(4, 4, 0.0)]
    for num, den, off in time_sigs:
        part.insert(off, meter.TimeSignature(f"{num}/{den}"))
    part.insert(0, tempo.MetronomeMark(number=tempo_bpm))
    part.insert(0, clef_obj)
    for offset, el in group_simultaneous(events):
        part.insert(offset, el)

    # 连音组标记(1/3 QL 八分三连音)
    mark_tuplets(part)

    # 完整排谱:小节 → 补休止 → 跨小节延音线 → 符杠
    part = mn.makeMeasures(part, inPlace=False)
    part = mn.makeRests(part, fillGaps=True, inPlace=False)
    part = mn.makeTies(part, inPlace=False)
    bar_ql = 4.0 * time_sigs[0][0] / time_sigs[0][1]
    normalize_measure_durations(part, bar_ql)
    part = mn.makeBeams(part, inPlace=False)
    return part


def normalize_measure_durations(part, bar_ql, tolerance=0.20):
    """把排谱后的小节时值规范到拍号长度。

    music21 在三连音与边界量化误差叠加时，可能将一小段超拍（常为 1/24
    QL）保留到小节末，并由 makeRests 写成伪 64 分休止符。这里仅处理小于
    tolerance 的微小溢出：优先缩短/移除末尾休止；其余情况不在排谱后
    盲目截短音符，以免破坏真实时值或延音线。超过阈值的异常保留，避免静默
    损坏真实乐句。

    注意 ``makeRests`` 会在已有音符 offset 不连续时插入休止。用“元素时值
    求和”判断小节长度会把 offset 间的重叠/空隙误算进去；因此以每个元素的
    ``offset + quarterLength`` 计算末端位置。Chord 作为一个占时元素计一次。
    对没有 voice 编码的单一声部而言，任何与 Note/Chord 时段相交的 Rest 都是
    ``makeRests`` 在混合量化网格下产生的伪休止，应先移除而不能参与计时。
    """
    for measure in part.getElementsByClass("Measure"):
        timed = list(measure.notesAndRests)
        sounding = [el for el in timed if not isinstance(el, note.Rest)]
        for rest in [el for el in timed if isinstance(el, note.Rest)]:
            rs = float(rest.offset)
            re = rs + float(rest.quarterLength)
            overlaps_sound = any(
                rs < float(el.offset + el.quarterLength) - 1e-7
                and re > float(el.offset) + 1e-7
                for el in sounding
            )
            if overlaps_sound:
                measure.remove(rest)

        timed = list(measure.notesAndRests)
        if not timed:
            continue
        end = max(float(el.offset + el.quarterLength) for el in timed)
        excess = end - bar_ql
        if excess <= 1e-7 or excess > tolerance:
            continue

        # 只修剪实际越过小节边界的休止，优先处理常见的 1/24 QL 伪休止。
        rests = [el for el in timed if isinstance(el, note.Rest)]
        for rest in reversed(rests):
            rest_start = float(rest.offset)
            rest_end = rest_start + float(rest.quarterLength)
            if rest_end <= bar_ql + 1e-7:
                continue
            if rest_start >= bar_ql - 1e-7:
                measure.remove(rest)
            else:
                rest.quarterLength = bar_ql - rest_start
            break


def detect_key(events):
    """加权 Krumhansl-Schmuckler 调性推断 + 终止音锚定。

    原 KS 对全体音符等权统计音高类别,转调多的曲目(肖邦、斯卡拉蒂)常
    把主调推偏(如 G 大调被推成 D 大调)。这里做两处增强:
      1) 音高类别按时值加权——长音(常落在主和弦)权重大;
      2) 终止音锚定——乐曲最后一个低音几乎总是主音,给该调候选加分。
    返回 music21 Key 对象;信号不足返回 None。
    """
    import numpy as np

    # Krumhansl-Schmuckler 经典 key profile(12 个音级权重)
    MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52,
                    5.19, 2.39, 3.66, 2.29, 2.88], dtype=float)
    MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54,
                    4.75, 3.98, 2.69, 3.34, 3.17], dtype=float)

    events = sorted(events, key=lambda e: e[1])
    if not events:
        return None

    pc = np.zeros(12)
    for pitch, _s, d, _v in events:
        pc[pitch % 12] += max(d, 0.1)          # 时值加权
    pcv = pc / pc.sum()

    def corr(x, y):
        x = x - x.mean()
        y = y - y.mean()
        denom = np.linalg.norm(x) * np.linalg.norm(y)
        return float((x * y).sum() / denom) if denom > 0 else 0.0

    # 终止根音:最后一个 onset 的最低音
    last_onset = events[-1][1]
    term_notes = [e for e in events if abs(e[1] - last_onset) < 1e-6]
    term_pc = min(e[0] for e in term_notes) % 12

    results = []
    for i in range(12):                        # i = 主音 pitch class
        for mode, prof in (("major", MAJ), ("minor", MIN)):
            sc = corr(pcv, np.roll(prof, i))
            if mode == "major" and i == term_pc:
                sc += 0.05                     # 终止音=主音(大调)加分
            elif mode == "minor" and i == term_pc:
                sc += 0.04
            results.append((sc, i, mode))
    results.sort(key=lambda r: r[0], reverse=True)
    best_c, best_pc, best_mode = results[0]

    if best_c < 0.3:                           # 信号太弱
        return None

    from music21 import key as keymod
    from music21 import pitch as pitchmod
    tonic = pitchmod.Pitch(best_pc + 60)       # pc → 具体音名
    return keymod.Key(tonic, mode=best_mode)


def detect_time_signature(events, bpm, meta_sigs=None):
    """从低音 onset 的自相关周期推断拍号。

    背景:很多曲谱 MIDI 的 time-signature meta 是默认值(如统一写 4/4),
    与真实拍号不符(莫扎特小步舞曲 K.4 的 meta 为 4/4,实为 3/4)。
    做法:取每个 onset 的最低音(低音线条),对候选小节长做周期自相关
    (主周期 + 半小节次强拍 + 两倍超周期加权),峰值对应真实小节结构。

    返回 (num, den);信号不足返回 None。
    """
    import numpy as np

    cands = [((2, 4), 2.0), ((3, 4), 3.0), ((4, 4), 4.0)]
    # meta 提供的候选优先参与(如 meta 明确 6/8)
    if meta_sigs:
        for num, den, _off in meta_sigs:
            bar = 4.0 * num / den
            if bar <= 0:
                continue
            if not any(bar == b for _c, b in cands):
                cands.append(((num, den), bar))

    by_o: dict = {}
    for p, s, d, v in events:
        by_o.setdefault(round(s, 4), []).append(p)
    bass_t = sorted(by_o)
    if len(bass_t) < 8:
        return None

    dt = 0.25                                  # 采样步长(QL)
    span = bass_t[-1]
    n = max(1, int(span / dt) + 1)
    sig = np.zeros(n)
    for t in bass_t:
        i = int(round(t / dt))
        if 0 <= i < n:
            sig[i] = 1.0

    def corr(period):
        lag = int(round(period / dt))
        if lag <= 0 or lag >= n:
            return 0.0
        x = sig[:-lag]
        denom = float(x.sum())
        return float((x * sig[lag:]).sum()) / denom if denom > 0 else 0.0

    # 主周期 corr(bar) 直接比较——半小节周期会把 2/4 主拍周期算进去,
    # 令 3/4 圆舞曲被误判为 2/4。3/4 与 6/8 的小节同为 3QL,此处统一按
    # bar 判定,内部再按 (3,4) 优先(music21 可从 6 个八分音符重音区分,
    # 留待后续;若 meta 明确 6/8 则候选自然带出)。
    scored = []
    for (num, den), bar in cands:
        scored.append((corr(bar), num, den, bar))
    scored.sort(key=lambda s: s[0], reverse=True)
    sc0, num0, den0, bar0 = scored[0]

    # 信号过弱:无明显周期性 → 放弃推断
    if sc0 < 0.35:
        return None
    # 4/4 保守回退:若 4/4 与最优分差 < 8% 且 4/4 在前二,选 4/4(默认值安全)
    for sc, num, den, bar in scored[:2]:
        if (num, den) == (4, 4) and sc >= sc0 * 0.92:
            return (4, 4)
    # 同 bar 候选中优先 3/4 而非 6/8
    for sc, num, den, bar in scored:
        if abs(bar - bar0) < 1e-9 and sc >= sc0 - 1e-9 and (num, den) != (6, 8):
            return (num, den)
    return (num0, den0)


def tie_split_events(events, bar_ql):
    """把跨小节长音按小节边界切段,返回 (pitch, s, d, vel, tie_role)。

    必须与 clip_to_next_onset 一样按声部(左右手)分别调用。
    tie_role ∈ {None, 'start', 'continue', 'stop}:单段为 None;跨小节时
    首段 start、中间段 continue、末段 stop。

    两个作用,缺一不可:
      1) 每段都落在小节内 —— 避免长音溢出小节线,把 makeMeasures 的后续
         小节整体推偏(overfull 漂移,曾让 K.4 左手第 18 小节漂移 +18.9QL);
      2) 显式 tie —— 相邻同音高段不会被 makeTies 误判为独立音符,跨小节
         延音线正确渲染(此前手工切分不标 tie 导致"多写音符" bug)。
    """
    import math
    out = []
    for pitch, s, d, vel in events:
        if d <= 0:
            continue
        end = s + d
        r = (math.floor(s / bar_ql) + 1) * bar_ql      # 当前小节右边界
        if r <= s + 1e-9:
            r = s + bar_ql                             # start 恰在边界 → 下一小节
        segs = []
        while end > r + 1e-6:
            segs.append((pitch, s, r - s, vel))
            s = r
            r += bar_ql
        segs.append((pitch, s, end - s, vel))
        n_seg = len(segs)
        for i, (p, ss, dd, vv) in enumerate(segs):
            role = None
            if n_seg > 1:
                role = "start" if i == 0 else ("stop" if i == n_seg - 1 else "continue")
            out.append((p, ss, dd, vv, role))
    return out


def group_simultaneous(events):
    """把同 onset 的音符合成 Chord 再插入。

    若以独立 Note 平铺插入,music21 导出的 MusicXML 不会加 <chord> 标记,
    和弦会被读成先后出现的音符(小节拍数被撑爆)。这里按 onset 聚类成
    Chord,保留各音力度;同 onset 不同时值时 Chord 取最大时值
    (真正的多声部独立时值留待 P3 的声部划分)。

    事件格式 (pitch, s, d, vel[, tie_role]):tie_role 来自 tie_split_events,
    构造每个 Note 时独立写入延音标记。和弦成员可能混合普通音、start、
    continue、stop，不能用整个 Chord 的共同 role，否则会丢失成员级 tie。
    """
    by_offset: dict = {}
    for ev in events:
        pitch, s, d, v = ev[:4]
        role = ev[4] if len(ev) > 4 else None
        by_offset.setdefault(s, []).append((pitch, d, v, role))
    result = []
    for s in sorted(by_offset):
        group = by_offset[s]
        if len(group) == 1:
            p, d, v, role = group[0]
            n = note.Note(pitch=p, quarterLength=d)
            n.volume.velocity = v
            if role:
                n.tie = tie.Tie(role)
            result.append((s, n))
        else:
            notes = []
            for p, d, v, role in group:
                n = note.Note(pitch=p, quarterLength=d)
                n.volume.velocity = v
                if role:
                    n.tie = tie.Tie(role)
                notes.append(n)
            c = chord.Chord(notes)
            c.quarterLength = max(n.quarterLength for n in notes)
            result.append((s, c))
    return result


def mark_tuplets(part):
    """把连续的 1/3 QL(八分三连音)音符按三个一组标记为 Tuplet(3,2)。"""
    notes = part.notes  # 按 offset 排序
    i = 0
    n = len(notes)
    while i < n:
        if abs(notes[i].duration.quarterLength - 1 / 3) < 1e-6:
            j = i
            while j < n and abs(notes[j].duration.quarterLength - 1 / 3) < 1e-6:
                j += 1
            run = notes[i:j]
            for k in range(0, len(run) - 2, 3):
                t = duration.Tuplet(3, 2)
                for nd in run[k:k + 3]:
                    nd.tuplet = t
            i = j
        else:
            i += 1


# --------------------------------------------------------------------------
# 4. 踏板 → PedalMark spanner(挂在左手声部下谱表下方)
# --------------------------------------------------------------------------
def attach_pedals(part, pedal_intervals):
    """把踏板区间挂成 PedalMark spanner。interval 起点/终点吸附到音符。

    注意:音符进入 measure 后 .offset 是小节内局部偏移,必须用
    getOffsetInHierarchy() 取全局偏移来比对踏板边界。
    """
    notes = sorted(part.recurse().notes,
                   key=lambda n: n.getOffsetInHierarchy(part))
    for s, e in pedal_intervals:
        start_note = find_nearest_note(notes, s, part)
        end_note = find_nearest_note(notes, e, part)
        if start_note is None or end_note is None:
            continue
        pm = PedalMark()
        pm.pedalType = PedalType.Sustain
        pm.pedalForm = PedalForm.Symbol  # 标准 "Ped. ... *" 记号
        pm.placement = "below"
        pm.addSpannedElements([start_note, end_note])
        part.insert(0, pm)


def find_nearest_note(notes, offset_ql, site):
    """找全局 offset 最近(且 >= 目标)的音符;无则取最后一个。

    site 为音符所属的最顶层 Stream(用于取全局偏移)。
    """
    best = None
    for n in notes:
        if n.getOffsetInHierarchy(site) >= offset_ql - 1e-6:
            best = n
            break
    if best is None and notes:
        best = notes[-1]
    return best


# --------------------------------------------------------------------------
# 5. 组装 Score 并导出
# --------------------------------------------------------------------------
def assemble_score(rh_part, lh_part, title="Untitled", tempo_bpm=90.0):
    score = stream.Score()
    score.insert(0, tempo.MetronomeMark(number=tempo_bpm))
    rh_part.partName = "Piano R.H."
    lh_part.partName = "Piano L.H."
    score.insert(0, rh_part)
    score.insert(0, lh_part)
    from music21 import metadata
    score.metadata = metadata.Metadata(title=title, composer="ClawsGO Science / audio2score")
    return score


def main():
    ap = argparse.ArgumentParser(description="MIDI → MusicXML 基础记谱管线")
    ap.add_argument("--midi", required=True, help="输入 MIDI 路径")
    ap.add_argument("--out", required=True, help="输出 MusicXML 路径")
    ap.add_argument("--title", default="Piano Transcription", help="曲目标题")
    ap.add_argument("--divisors", default="8,4,3",
                    help="量化网格(1/d 刻度,逗号分隔),默认 8,4,3 = 32分/16分/八分三连")
    args = ap.parse_args()

    notes, pedals, meta = midi_to_events(args.midi)
    divisors = tuple(int(x) for x in args.divisors.split(","))
    qnotes = quantize_events(notes, divisors=divisors)
    print(f"读取 {len(notes)} 音,{len(pedals)} 踏板区间;量化后 {len(qnotes)} 音 "
          f"({meta['tempo_bpm']:.0f}BPM {meta['time_sigs'][0][0]}/{meta['time_sigs'][0][1]})")

    # 拍号验证/推断:曲谱 MIDI 的 time-signature meta 常是默认值(4/4),
    # 用低音 onset 周期自相关重新检测(meta 与检测冲突时以检测为准)
    det_ts = detect_time_signature(qnotes, meta["tempo_bpm"], meta["time_sigs"])
    if det_ts is not None:
        meta_ts = meta["time_sigs"]
        if meta_ts[0][:2] != det_ts:
            print(f"拍号: MIDI meta {meta_ts[0][0]}/{meta_ts[0][1]} → "
                  f"低音周期检测 {det_ts[0]}/{det_ts[1]}")
            meta["time_sigs"] = [(det_ts[0], det_ts[1], 0.0)]
        else:
            print(f"拍号: {det_ts[0]}/{det_ts[1]} (meta 一致)")
    else:
        print(f"拍号: 采用 MIDI meta "
              f"{meta['time_sigs'][0][0]}/{meta['time_sigs'][0][1]} (检测信号不足)")

    # 调号推断(演奏 MIDI 常缺 key meta)
    key_obj = detect_key(qnotes)
    if key_obj is not None:
        print(f"推断调性: {key_obj.name}({key_obj.sharps:+d} 个升降号)")

    rh, lh = split_hands(qnotes)
    # 左右手各自做"下一 onset"时值约束(跨声部不互相截断)
    rh = clip_to_next_onset(rh, divisors=divisors)
    lh = clip_to_next_onset(lh, divisors=divisors)
    # 跨小节长音按小节边界切段 + 显式延音标记:
    #   既避免 makeMeasures 的 overfull 漂移,又避免相邻同音高重奏
    num, den, _off = meta["time_sigs"][0]
    bar_ql = 4.0 * num / den
    rh = tie_split_events(rh, bar_ql)
    lh = tie_split_events(lh, bar_ql)
    print(f"右手 {len(rh)} 音(含延音段),左手 {len(lh)} 音(含延音段)")

    rh_part = build_part(rh, "R.H.", clef.TrebleClef(),
                         tempo_bpm=meta["tempo_bpm"], time_sigs=meta["time_sigs"],
                         key_sharps=key_obj.sharps if key_obj else None)
    lh_part = build_part(lh, "L.H.", clef.BassClef(),
                         tempo_bpm=meta["tempo_bpm"], time_sigs=meta["time_sigs"],
                         key_sharps=key_obj.sharps if key_obj else None)
    attach_pedals(lh_part, pedals)

    score = assemble_score(rh_part, lh_part, title=args.title,
                           tempo_bpm=meta["tempo_bpm"])
    score.write("musicxml", fp=args.out)
    print(f"已写出 MusicXML: {args.out}")

    # 简单自检:统计小节数与每小节音符/休止(和弦计入各组成音)
    for p in score.parts:
        ms = p.getElementsByClass("Measure")
        n_notes = sum(len(m.flatten().notes) for m in ms)
        n_rests = sum(len(m.recurse().getElementsByClass("Rest")) for m in ms)
        n_chords = sum(len(m.recurse().getElementsByClass("Chord")) for m in ms)
        print(f"  {p.partName}: {len(ms)} 小节, {n_notes} 音符"
              f"(含 {n_chords} 个和弦), {n_rests} 休止")


if __name__ == "__main__":
    main()
