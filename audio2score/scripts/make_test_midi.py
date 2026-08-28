#!/usr/bin/env python3
"""
make_test_midi.py — 生成一段"仿真转录输出"的钢琴 MIDI。

用途:P1/M0 验证管线的测试数据。刻意模拟真实转录输出的特征:
  * 单手单轨(与转录模型输出一致,考验声部/左右手拆分)
  * 附点、三连音等复杂节奏(考验量化器)
  * ±15ms 时序抖动(考验量化鲁棒性)
  * CC64 延音踏板事件
  * 旋律与伴奏不同的力度
"""
from __future__ import annotations

import random

import pretty_midi

RNG = random.Random(42)  # 固定种子,可复现

TICKS_PER_BEAT = 480  # 内部仅用于打点,输出为秒

def sec(beat: float, tempo_bpm: float = 90.0) -> float:
    """将拍号转成秒。1 拍 = 60/tempo 秒。"""
    return beat * 60.0 / tempo_bpm

def jitter(seconds: float, max_ms: float = 15.0) -> float:
    """在音符起始时间上叠加 ±max_ms 的均匀抖动,模拟转录时序误差。"""
    return seconds + RNG.uniform(-max_ms, max_ms) * 1e-3

def build_midi() -> pretty_midi.PrettyMIDI:
    pm = pretty_midi.PrettyMIDI(initial_tempo=90.0)

    # ---- 右手旋律:8 小节,含附点 / 三连音 / 和弦 ----
    # 每元素:(音高, 起始拍, 时值拍, 力度)
    rh_events = [
        # 小节 1:C 大调,四分+二分混合
        (76, 0.0, 1.0, 96),    # E5
        (79, 1.0, 1.0, 92),    # G5
        (72, 2.0, 2.0, 90),    # C5(二分)
        # 小节 2
        (74, 4.0, 1.0, 94),    # D5
        (77, 5.0, 1.0, 92),    # F5
        (71, 6.0, 2.0, 90),    # B4(二分)
        # 小节 3:四分连奏
        (76, 8.0, 1.0, 92),    # E5
        (79, 9.0, 1.0, 90),    # G5
        (72, 10.0, 1.0, 88),   # C5
        (76, 11.0, 1.0, 90),   # E5
        # 小节 4:附点四分 + 八分 + 二分
        (74, 12.0, 1.5, 94),   # D5(附点四分)
        (72, 13.5, 0.5, 86),   # C5(八分)
        (71, 14.0, 1.0, 88),   # B4
        (72, 15.0, 1.0, 90),   # C5
        # 小节 5:右手和弦(三音)
        (67, 16.0, 1.0, 80),   # G4
        (71, 16.0, 1.0, 82),   # B4
        (74, 16.0, 1.0, 84),   # D5
        (67, 17.0, 1.0, 80),
        (71, 17.0, 1.0, 82),
        (74, 17.0, 1.0, 84),
        (72, 18.0, 2.0, 90),   # C5(二分)
        # 小节 6:三连音(一拍三个)
        (69, 20.0, 1/3, 90),   # A4
        (71, 20.0+1/3, 1/3, 92),  # B4
        (72, 20.0+2/3, 1/3, 94),  # C5
        (74, 21.0, 1.0, 92),   # D5
        (76, 22.0, 1.0, 94),   # E5
        (77, 23.0, 1.0, 92),   # F5
        # 小节 7
        (79, 24.0, 1.0, 96),   # G5
        (77, 25.0, 1.0, 92),   # F5
        (76, 26.0, 1.0, 90),   # E5
        (74, 27.0, 1.0, 88),   # D5
        # 小节 8:结束
        (72, 28.0, 4.0, 92),   # C5(全音符)
    ]

    # ---- 左手伴奏:低音 + 分解和弦,始终低于 C4(60),避免声部分歧 ----
    # (音高, 起始拍, 时值拍, 力度)
    lh_events = [
        (48, 0.0, 2.0, 66),   # C3
        (55, 2.0, 2.0, 62),   # G3
        (50, 4.0, 2.0, 64),   # D3
        (57, 6.0, 2.0, 60),   # A3
        (48, 8.0, 2.0, 64),
        (55, 10.0, 2.0, 60),
        (50, 12.0, 2.0, 62),
        (52, 14.0, 2.0, 60),  # E3
        (43, 16.0, 1.0, 70),  # G2
        (50, 17.0, 1.0, 62),  # D3
        (43, 18.0, 2.0, 66),  # G2
        (45, 20.0, 1.0, 66),  # A2
        (52, 21.0, 1.0, 60),  # E3
        (53, 22.0, 1.0, 62),  # F3
        (55, 23.0, 1.0, 62),  # G3
        (48, 24.0, 1.0, 66),  # C3
        (55, 25.0, 1.0, 60),  # G3
        (57, 26.0, 1.0, 60),  # A3
        (55, 27.0, 1.0, 58),  # G3
        (48, 28.0, 4.0, 66),  # C3(全音符)
    ]

    # 合成单轨(转录模型输出的真实形态:一条钢琴轨)
    piano = pretty_midi.Instrument(program=0, is_drum=False, name="Piano")

    def add_events(events, velocity_scale=1.0):
        last_end: dict = {}
        for pitch, start_beat, dur_beat, vel in events:
            start = jitter(sec(start_beat))
            end = start + sec(dur_beat) * (1.0 + RNG.uniform(-0.02, 0.02))
            # 保证不早于起始、不塌缩
            end = max(end, start + 0.05)
            # 真实演奏同一琴键不可能重叠:若被 jitter 推回与前音重叠,则后移 start
            if pitch in last_end and start < last_end[pitch] - 1e-6:
                start = last_end[pitch]
                end = max(end, start + 0.05)
            last_end[pitch] = end
            note = pretty_midi.Note(
                velocity=int(vel * velocity_scale), pitch=pitch,
                start=start, end=end,
            )
            piano.notes.append(note)

    add_events(rh_events, velocity_scale=1.0)
    add_events(lh_events, velocity_scale=0.7)  # 伴奏整体更轻

    pm.instruments.append(piano)

    # ---- 延音踏板(CC64):第 1-2 小节整段踩住,第 5-6 小节踩住 ----
    def add_pedal(start_beat, end_beat):
        t0, t1 = sec(start_beat), sec(end_beat)
        piano.control_changes.append(pretty_midi.ControlChange(64, 127, t0))
        piano.control_changes.append(pretty_midi.ControlChange(64, 0, t1))

    add_pedal(0.0, 8.0)
    add_pedal(16.0, 24.0)

    pm.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0.0))
    return pm


if __name__ == "__main__":
    out = "/home/user/.clawsgo/projects/a1c4aad0-038d-4c75-ab75-64ac0670657c/audio2score/samples/test_performance.mid"
    pm = build_midi()
    pm.write(out)
    print(f"已生成测试 MIDI: {out}")
    print(f"音符数: {len(pm.instruments[0].notes)}, 踏板事件数: {len(pm.instruments[0].control_changes)}")
    print(f"时长: {pm.get_end_time():.2f}s @ 90BPM, 4/4, 8 小节")
