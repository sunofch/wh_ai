"""
统一 VLM 接口模块

根据配置动态选择使用 Qwen2-VL 或 Qwen3.5-VLM
"""
from functools import lru_cache
from typing import Any, Dict, Optional

from src.common.config import config

# 根据 VLM_MODEL_TYPE 配置动态导入相应的 VLM 模块
VLM_MODEL_TYPE = config.vlm_selector.model_type.lower()

if VLM_MODEL_TYPE in ('qwen35', 'qwen3.5', 'qwen3'):
    from .qwen35 import Qwen35VLM as VLMClass
    from .qwen35 import get_vlm_instance as _get_vlm_instance
    VLM_NAME = "Qwen3.5-VLM"
elif VLM_MODEL_TYPE in ('qwen2', 'qwen2-vl', 'qwen2vl'):
    from .qwen2 import Qwen2VLM as VLMClass
    from .qwen2 import get_vlm_instance as _get_vlm_instance
    VLM_NAME = "Qwen2-VL"
else:
    # 默认使用 Qwen2-VL
    from .qwen2 import Qwen2VLM as VLMClass
    from .qwen2 import get_vlm_instance as _get_vlm_instance
    VLM_NAME = "Qwen2-VL"


@lru_cache(maxsize=1)
def get_vlm_instance():
    """获取 VLM 单例实例

    根据配置返回相应的 VLM 实例 (Qwen2-VL 或 Qwen3.5-VLM)

    Returns:
        VLM 单例实例
    """
    return _get_vlm_instance()


def get_vlm_with_rag(
    mode: str = 'traditional',
    enable_rag: bool = True
):
    """获取VLM实例并初始化指定模式的RAG

    Args:
        mode: RAG模式 ('traditional' | 'graph')
        enable_rag: 是否启用RAG

    Returns:
        带RAG配置的VLM实例，或None
    """
    try:
        # 先初始化RAG系统
        if enable_rag:
            from src.rag import initialize_rag_system
            if not initialize_rag_system(mode=mode):
                return None

        # 获取VLM实例
        vlm = get_vlm_instance()

        # 更新RAG设置
        vlm._rag_enabled = enable_rag
        if enable_rag:
            from src.rag import get_unified_rag_manager
            vlm.rag_manager = get_unified_rag_manager()

        return vlm
    except Exception as e:
        print(f"获取带RAG的VLM实例失败: {e}")
        return None


__all__ = [
    'VLMClass',
    'VLM_NAME',
    'get_vlm_instance',
    'get_vlm_with_rag',
]
