"""
ASR模块：使用openai/whisper进行语音转文字
"""
import io
from functools import lru_cache
from typing import Optional, Union

import numpy as np
import soundfile as sf
import torch
import whisper
from scipy import signal

from src.common.config import config
from src.common.utils import get_device

class WhisperASR:
    def __init__(self):
        # 从配置文件读取参数
        model_name = config.asr.model
        device_str = config.asr.device

        # 使用统一的设备选择逻辑
        self.device = get_device(device_str)
            
        print(f"加载ASR模型: {model_name} 在 {self.device} 上...")
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
                fp16=(self.device == "cuda")
            )
            text = result["text"].strip()
            return text
        except Exception as e:
            print(f"ASR转录错误: {e}")
            return ""

    def transcribe_bytes(self, audio_bytes: bytes) -> str:
        """直接从二进制流转录

        Args:
            audio_bytes: 音频数据的字节流

        Returns:
            str: 转录后的文本内容
        """
        # 读取字节流
        audio_data, sr = sf.read(io.BytesIO(audio_bytes))
        
        # 确保数据是 float32 (soundfile 默认可能是 float64)
        audio_data = audio_data.astype(np.float32)

        # 重采样到 16000 Hz (Whisper 要求)
        if sr != 16000:
            num_samples = int(len(audio_data) * 16000 / sr)
            audio_data = signal.resample(audio_data, num_samples)
            
        return self.transcribe(audio_data)

# 线程安全的单例模式
@lru_cache(maxsize=1)
def get_asr_instance() -> WhisperASR:
    """获取 ASR 单例实例

    Returns:
        WhisperASR: 单例 ASR 实例
    """
    return WhisperASR()