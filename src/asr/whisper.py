"""
ASR模块：使用openai/whisper进行语音转文字
"""
import io
import logging
import threading
from typing import Optional, Union

import numpy as np
import soundfile as sf
import torch
import whisper
from scipy import signal

from src.common.config import config
from src.common.utils import get_device

logger = logging.getLogger(__name__)


class WhisperASR:
    def __init__(self):
        # 从配置文件读取参数
        model_name = config.asr.model
        device_str = config.asr.device

        # 使用统一的设备选择逻辑
        self.device = get_device(device_str)
            
        logger.info("加载ASR模型: %s 在 %s 上...", model_name, self.device)
        try:
            self.model = whisper.load_model(model_name, device=self.device)
        except Exception as e:
            raise RuntimeError(f"加载Whisper模型失败: {e}")
        
    def transcribe(
        self,
        audio_input: Union[str, np.ndarray],
        language: Optional[str] = None
    ) -> str:
        """将音频转录为文字

        Args:
            audio_input: 音频文件路径(str) 或 16kHz的音频数据(np.ndarray)
            language: 指定语言代码 (如 "zh")，不传则使用配置默认值

        Returns:
            str: 转录后的文本内容
        """
        # 使用配置中的默认语言
        if language is None:
            language = config.asr.language
            
        # 优化：直接处理 Numpy 数组
        # Whisper 接受 float32 类型的 numpy 数组
        if isinstance(audio_input, np.ndarray):
            if audio_input.dtype != np.float32:
                audio_input = audio_input.astype(np.float32)
        
        try:
            # 直接传递 audio_input 给模型，不再创建临时文件
            result = self.model.transcribe(
                audio_input,
                language=language,
                fp16=self.device.startswith("cuda"),
            )
            return result["text"].strip()
        except Exception as e:
            # 不再静默吞掉错误：向上抛出，便于调用方区分“无语音”与“转写失败”
            logger.error("ASR 转录失败: %s", e)
            raise RuntimeError(f"ASR 转录失败: {e}") from e

    def transcribe_bytes(self, audio_bytes: bytes) -> str:
        """直接从二进制流转录

        Args:
            audio_bytes: 音频数据的字节流

        Returns:
            str: 转录后的文本内容
        """
        # 读取字节流
        audio_data, sr = sf.read(io.BytesIO(audio_bytes))

        # 多声道降混为单声道 (Whisper 只接受一维单声道数组)
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        # 确保数据是 float32 (soundfile 默认可能是 float64)
        audio_data = audio_data.astype(np.float32)

        # 重采样到 16000 Hz (Whisper 要求)
        if sr != 16000:
            num_samples = int(len(audio_data) * 16000 / sr)
            audio_data = signal.resample(audio_data, num_samples)
            
        return self.transcribe(audio_data)

# 线程安全的单例：双重检查锁，确保高并发首次请求只加载一份模型
_asr_instance: Optional[WhisperASR] = None
_asr_lock = threading.Lock()


def get_asr_instance() -> WhisperASR:
    """获取 ASR 单例实例

    Returns:
        WhisperASR: 单例 ASR 实例
    """
    global _asr_instance
    if _asr_instance is None:
        with _asr_lock:
            if _asr_instance is None:
                _asr_instance = WhisperASR()
    return _asr_instance