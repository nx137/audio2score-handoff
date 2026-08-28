# torchlibrosa 兼容层(纯 torch 实现,无老依赖)。
# 原包依赖 torchlibrosa 0.0.4(numba 0.48,不支持 Python 3.12),
# 这里用 torch.stft + 自实现 mel 滤波器组(复刻 librosa 0.6 算法)提供等价接口。
from .stft import Spectrogram, LogmelFilterBank  # noqa: F401
