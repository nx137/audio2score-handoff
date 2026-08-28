"""torchlibrosa.stft 兼容实现:Spectrogram + LogmelFilterBank。

数值对齐原训练特征管线:
  * STFT: n_fft=2048, hop=160, hann(periodic), center=True, pad='reflect', power
  * Mel: 229 个滤波器, sr=16000, fmin=30, fmax=8000, norm='slaney'(librosa 0.6 算法)
"""
import numpy as np
import torch
import torch.nn as nn


def _hz_to_mel(f):
    """librosa.audio.hz_to_mel(htk=False) —— Slaney 标度(线性段 + 对数段)。"""
    f = np.asarray(f, dtype=float)
    f_min, f_sp = 0.0, 200.0 / 3
    mels = (f - f_min) / f_sp
    min_log_hz, min_log_mel = 1000.0, (1000.0 - f_min) / f_sp
    logstep = np.log(6.4) / 27.0
    if np.isscalar(mels):
        if f > min_log_hz:
            mels = min_log_mel + np.log(f / min_log_hz) / logstep
    else:
        mels[f > min_log_hz] = min_log_mel + np.log(f[f > min_log_hz] / min_log_hz) / logstep
    return mels


def _mel_to_hz(mels):
    """librosa.audio.mel_to_hz(htk=False) 的逆变换。"""
    mels = np.asarray(mels, dtype=float)
    f_min, f_sp = 0.0, 200.0 / 3
    freqs = f_min + f_sp * mels
    min_log_hz, min_log_mel = 1000.0, (1000.0 - f_min) / f_sp
    logstep = np.log(6.4) / 27.0
    if np.isscalar(freqs):
        if mels > min_log_mel:
            freqs = min_log_hz * np.exp(logstep * (mels - min_log_mel))
    else:
        freqs[mels > min_log_mel] = min_log_hz * np.exp(logstep * (mels[mels > min_log_mel] - min_log_mel))
    return freqs


def _mel_filterbank(sr, n_fft, n_mels, fmin, fmax):
    """librosa.filters.mel(sr, n_fft, n_mels, fmin, fmax, htk=False, norm='slaney')。

    返回 (n_mels, n_fft//2 + 1) 的滤波矩阵,与 librosa 0.6 数值一致。
    """
    n_bins = n_fft // 2 + 1
    fftfreqs = np.fft.fftfreq(n_fft, 1.0 / sr)[:n_bins]  # 0..sr/2
    min_mel, max_mel = _hz_to_mel(fmin), _hz_to_mel(fmax)
    mels = np.linspace(min_mel, max_mel, n_mels + 2)
    mels_hz = _mel_to_hz(mels)

    weights = np.empty((n_mels, n_bins), dtype=np.float64)
    for i in range(n_mels):
        lower, center, upper = mels_hz[i], mels_hz[i + 1], mels_hz[i + 2]
        # 上升段
        left = (fftfreqs - lower) / (center - lower)
        # 下降段
        right = (upper - fftfreqs) / (upper - center)
        weights[i] = np.maximum(0.0, np.minimum(left, right))

    # Slaney 归一化
    enorm = 2.0 / (mels_hz[2:n_mels + 2] - mels_hz[:n_mels])
    weights *= enorm[:, np.newaxis]
    return weights.astype(np.float32)


class Spectrogram(nn.Module):
    """功率谱提取:输入 (batch, time) 或 (batch, 1, time) → (batch, 1, time, freq)。"""

    def __init__(self, n_fft, hop_length, win_length, window='hann',
                 center=True, pad_mode='reflect', freeze_parameters=True):
        super().__init__()
        self.n_fft, self.hop_length, self.win_length = n_fft, hop_length, win_length
        self.center, self.pad_mode = center, pad_mode
        if window == 'hann':
            self.window = torch.hann_window(win_length, periodic=True)
        else:
            raise ValueError('仅支持 hann')

    def forward(self, input):
        # input: (batch, time) 或 (batch, 1, time)
        if input.dim() == 3:
            input = input[:, 0, :]
        win = self.window.to(input.device)
        stft = torch.stft(input, self.n_fft, self.hop_length, self.win_length,
                          window=win, center=self.center, pad_mode=self.pad_mode,
                          return_complex=True)          # (batch, freq, time)
        power = (stft.abs() ** 2).transpose(1, 2).unsqueeze(1)  # (batch, 1, time, freq)
        return power


class LogmelFilterBank(nn.Module):
    """对数 Mel 特征:输入 (batch, 1, time, freq) 功率谱 → (batch, 1, time, n_mels)。

    与 torchlibrosa 一致:log10(clamp(x @ melW, min=amin)),ref=1,top_db=None。
    """

    def __init__(self, sr, n_fft, n_mels, fmin, fmax, ref=1.0, amin=1e-10,
                 top_db=None, freeze_parameters=True):
        super().__init__()
        mel = _mel_filterbank(sr, n_fft, n_mels, fmin, fmax).T  # (freq, n_mels)
        self.register_buffer('melW', torch.from_numpy(mel))
        self.ref, self.amin, self.top_db = ref, amin, top_db

    def forward(self, input):
        # input: (batch, 1, time, freq)
        x = torch.matmul(input, self.melW)                  # (batch, 1, time, n_mels)
        x = torch.clamp(x, min=self.amin)
        x = torch.log10(x / self.ref)
        if self.top_db is not None:
            x = torch.clamp(x, min=x.max() - self.top_db)
        return x
