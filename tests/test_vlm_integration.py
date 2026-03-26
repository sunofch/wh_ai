"""VLM统一入口集成测试"""
import pytest
from src.vlm import VLMClass, VLM_NAME, get_vlm_instance


def test_vlm_selector():
    """测试VLM选择器"""
    assert VLM_NAME in ["Qwen2-VL", "Qwen3.5-VLM"], f"未知的VLM名称: {VLM_NAME}"
    print(f"当前VLM: {VLM_NAME}")


@pytest.mark.skipif(True, reason="需要GPU和vLLM服务器")
def test_vlm_unified_interface():
    """测试统一接口"""
    vlm = get_vlm_instance()

    # 测试process方法
    result = vlm.process(text="你好")
    assert isinstance(result, str)
    assert len(result) > 0

    # 测试extract_structured_info方法
    result = vlm.extract_structured_info(
        text="需要5个电机",
        format_instructions='{"part_name": "string", "quantity": "int"}'
    )
    assert isinstance(result, dict)
