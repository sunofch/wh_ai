"""Qwen35VLM vLLM集成测试"""
import pytest
from src.qwen35vlm import Qwen35VLM, get_vlm_instance


@pytest.mark.skipif(True, reason="需要GPU和vLLM服务器")
def test_qwen35vlm_text_only():
    """测试纯文本推理"""
    vlm = Qwen35VLM()
    result = vlm.process(text="你好")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.skipif(True, reason="需要GPU和vLLM服务器")
def test_qwen35vlm_extract_structured():
    """测试结构化信息提取"""
    vlm = Qwen35VLM()
    result = vlm.extract_structured_info(
        text="需要5个电机，非常紧急",
        format_instructions='{"part_name": "备件名称", "quantity": "数量"}'
    )
    assert isinstance(result, dict)
    assert "part_name" in result or "raw_response" in result
