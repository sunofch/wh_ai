"""VLM (Vision Language Model) 视觉语言模型推理引擎模块"""

from .router import get_vlm_instance, VLM_NAME
from .server import get_vlm_server_manager

__all__ = [
    'get_vlm_instance',
    'VLM_NAME',
    'get_vlm_server_manager',
]
