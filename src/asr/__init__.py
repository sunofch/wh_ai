"""ASR (Automatic Speech Recognition) 自动语音识别模块"""

from .whisper import WhisperASR, get_asr_instance

__all__ = [
    'WhisperASR',
    'get_asr_instance',
]
