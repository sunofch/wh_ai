"""VLM服务器管理器测试"""
import pytest
from src.vlm_server import VLLMServerManager, get_vlm_server_manager


def test_server_manager_singleton():
    """测试单例模式"""
    manager1 = get_vlm_server_manager()
    manager2 = get_vlm_server_manager()
    assert manager1 is manager2


def test_port_mapping():
    """测试端口映射"""
    manager = VLLMServerManager()
    assert manager.port_map['qwen2'] == 8000
    assert manager.port_map['qwen35'] == 8001


def test_port_availability_check():
    """测试端口可用性检查"""
    manager = VLLMServerManager()
    # 假设8000端口未被占用（如果被占用了，测试会失败，这是预期的）
    assert manager._is_port_available(8999) == True  # 使用一个不太可能被占用的高端口


@pytest.mark.skipif(True, reason="需要GPU环境，跳过自动测试")
def test_server_lifecycle():
    """测试服务器生命周期（需要GPU）"""
    manager = VLLMServerManager()

    # 启动服务器
    assert manager.start_server('qwen2') == True
    assert manager.health_check('qwen2') == True

    # 停止服务器
    assert manager.stop_server('qwen2') == True
    assert manager.health_check('qwen2') == False
