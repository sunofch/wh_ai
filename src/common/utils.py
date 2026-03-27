"""
通用工具函数模块
"""
import base64
import io
from typing import Union

import numpy as np
import torch
from PIL import Image


def get_device(device_str: str = "auto") -> str:
    """统一的设备选择逻辑

    Args:
        device_str: 设备字符串 ("auto", "cuda", "cpu")

    Returns:
        str: 实际使用的设备字符串 ("cuda" 或 "cpu")
    """
    if device_str == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device_str


def image_to_base64(image: Union[str, Image.Image, np.ndarray]) -> str:
    """将各种格式的图片转换为 Base64 Data URI

    Args:
        image: 图片对象，支持文件路径、PIL Image、numpy 数组

    Returns:
        str: Base64 编码的 data URI 字符串

    Raises:
        ValueError: 当输入类型不支持时
    """
    # 如果是路径（URL、data URI、或文件路径），直接返回（Qwen 支持本地路径）
    if isinstance(image, str):
        return image

    # numpy 数组转 PIL Image
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)

    # PIL Image 转 Base64
    if isinstance(image, Image.Image):
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/jpeg;base64,{img_str}"

    raise ValueError(f"不支持的图片类型: {type(image)}")
