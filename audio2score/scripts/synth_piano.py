#!/usr/bin/env python3
"""synth_piano.py — 用纯 Python 合成钢琴音频(MIDI → WAV)。

用于模型验证:把已知内容的 MIDI(含 CC64 延音踏板)渲染成钢琴 wav,
再做"合成 → 转录 → 记谱"闭环对比。音色是简单物理模拟:
  * 基频 + 带非谐性(stretched)的泛音列
  * 快速起音 + 频率相关指数衰减(低音长、高音短)
  * 踏板区间内衰减变慢(模拟延音),复音叠加
"""
from __future__ import annotations

import numpy as np
import pretty_midi
import soundfile as sf

SR = 44100
INHARMONICITY = 0.00025      # 钢琴弦非谐性系数
PARTIALS = 8                 # 泛音个数
PEDAL_DECAY_FACTOR = 3.0     # 踩踏板时衰减时间倍数


def note_freq(midi_note: int) -> float:
    return 440.0 * 2 ** ((midi_note - 69) / 12)


def render_note(f0: float, dur: float, amp: float, pedal: bool) -> np.ndarray:
    """渲染单个音符的波形(含 attack/decay 包络与泛音列)。"""
    n = int(SR * (dur + 0.15))                     # 尾部留释放
    t = np.arange(n) / SR
    # 包络:5ms attack,之后指数衰减(频率相关)
    attack = min(0.005, dur / 4)
    env = np.ones(n)
    env[:int(attack * SR)] = np.linspace(0, 1, int(attack * SR))
    tau = 1.0 * (261.63 / f0) ** 0.4               # 低音衰减慢
    if pedal:
        tau *= PEDAL_DECAY_FACTOR
    env *= np.exp(-t / tau)
    # 泛音叠加(振幅 1/n^1.5,相位随机避免对齐过亮)
    rng = np.random.RandomState(int(f0 * 100) % 100000)
    wave = np.zeros(n)
    for p in range(1, PARTIALS + 1):
        f_n = p * f0 * (1 + INHARMONICITY * p * p)  # 非谐性:高泛音偏高
        a_n = amp / p ** 1.5
        if f_n > SR / 2 - 100:                      # 超过 Nyquist 截断
            break
        wave += a_n * np.sin(2 * np.pi * f_n * t + rng.uniform(0, 2 * np.pi))
    return wave * env


def midi_to_piano_wav(midi_path: str, out_wav: str):
    pm = pretty_midi.PrettyMIDI(midi_path)
    total = max(pm.get_end_time(), 1.0) + 1.5
    y = np.zeros(int(SR * total))

    # 踏板区间列表
    pedals: list = []
    pedal_on = None
    cc64 = [c for inst in pm.instruments for c in inst.control_changes if c.number == 64]
    for c in sorted(cc64, key=lambda c: c.time):
        if c.value >= 64 and pedal_on is None:
            pedal_on = c.time
        elif c.value < 64 and pedal_on is not None:
            pedals.append((pedal_on, c.time))
            pedal_on = None
    if pedal_on is not None:
        pedals.append((pedal_on, total))

    def in_pedal(t0: float, t1: float) -> bool:
        return any(s <= t0 + 0.01 and t1 - 0.01 <= e for s, e in pedals)

    rng = np.random.RandomState(0)
    for inst in pm.instruments:
        for note in inst.notes:
            f0 = note_freq(note.pitch)
            amp = (note.velocity / 127.0) ** 1.3 * 0.35
            dur = note.end - note.start
            wave = render_note(f0, dur, amp, in_pedal(note.start, note.end))
            i0 = int(note.start * SR)
            y[i0:i0 + len(wave)] += wave[:min(len(wave), len(y) - i0)]

    # 归一化 + 轻微本底噪声(模拟录音)
    peak = np.max(np.abs(y))
    if peak > 0:
        y = y / peak * 0.92
    y += rng.randn(len(y)) * 0.0006

    sf.write(out_wav, y.astype(np.float32), SR)
    print(f'已合成钢琴音频: {out_wav} ({total:.1f}s, {len(pedals)} 段踏板)')


if __name__ == '__main__':
    import sys
    midi_to_piano_wav(sys.argv[1], sys.argv[2])
