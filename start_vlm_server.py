#!/usr/bin/env python
"""vLLM 服务器启动脚本

独立启动 vLLM 服务器进程，保存 PID 文件，实时显示日志
"""
import logging
import os
import subprocess
import sys
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.common.config import config
from src.vlm.server import get_vlm_server_manager


def read_config() -> dict:
    """读取 .env 配置

    Returns:
        包含模型类型、端口、模型名称的配置字典
    """
    model_type = config.vlm_selector.model_type.lower()

    # 标准化模型类型
    if model_type in ('qwen35', 'qwen3.5', 'qwen3'):
        model_type = 'qwen35'
    elif model_type in ('qwen2', 'qwen2-vl', 'qwen2vl'):
        model_type = 'qwen2'
    else:
        # 默认使用 qwen2
        model_type = 'qwen2'

    # 确定端口和模型名称
    base_port = config.vllm_server.base_port
    port_map = {
        'qwen2': base_port,
        'qwen35': base_port + 1
    }

    if model_type == 'qwen2':
        model_name = config.vlm.model
    else:
        model_name = config.vlm35.model

    return {
        'model_type': model_type,
        'port': port_map[model_type],
        'model_name': model_name
    }


def is_port_available(port: int) -> bool:
    """检查端口是否可用

    Args:
        port: 端口号

    Returns:
        bool: 可用返回 True
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def main():
    """主函数"""
    # 读取配置
    cfg = read_config()
    logger.info(f"读取配置: VLM_MODEL_TYPE={cfg['model_type']}")
    logger.info(f"启动模型: {cfg['model_name']} 在端口 {cfg['port']}")

    # 获取服务器管理器
    server_mgr = get_vlm_server_manager()

    # 检查现有 PID 文件
    if server_mgr.is_server_running():
        pid_info = server_mgr.load_pid_file()
        logger.error(
            f"服务器已在运行 (PID: {pid_info['pid']}, "
            f"端口: {pid_info['port']})\n"
            f"请先运行: python stop_vlm_server.py"
        )
        sys.exit(1)

    # 检查端口是否被占用
    if not is_port_available(cfg['port']):
        logger.error(
            f"端口 {cfg['port']} 已被占用\n"
            f"请运行: python stop_vlm_server.py"
        )
        sys.exit(1)

    # 构造 vllm serve 命令
    cmd = [
        'vllm', 'serve', cfg['model_name'],
        '--host', config.vllm_server.host,
        '--port', str(cfg['port']),
        '--tensor-parallel-size', str(config.vllm_server.tensor_parallel_size),
        '--gpu-memory-utilization', str(config.vllm_server.gpu_memory_utilization),
        '--limit-mm-per-prompt', config.vllm_server.limit_mm_per_prompt
    ]

    if config.vllm_server.max_model_len:
        cmd.extend(['--max-model-len', str(config.vllm_server.max_model_len)])

    logger.info(f"等待服务器就绪（最多 {config.vllm_server.startup_timeout} 秒）...")
    logger.info("========== vLLM 服务器启动 ==========")

    # 启动服务器（输出直接到终端，不经过管道）
    process = subprocess.Popen(
        cmd,
        stdout=None,
        stderr=None,
    )

    # 等待服务器健康检查通过
    max_wait = config.vllm_server.startup_timeout
    start_time = time.time()

    while time.time() - start_time < max_wait:
        time.sleep(1)
        if server_mgr.health_check(cfg['model_type']):
            elapsed = int(time.time() - start_time)
            logger.info(f"✓ vLLM 服务器启动成功 (PID: {process.pid}, 耗时: {elapsed}秒)")
            break
    else:
        # 启动超时
        process.terminate()
        process.wait(timeout=5)
        logger.error(f"服务器启动超时（{max_wait}秒）")
        logger.error("诊断建议:")
        logger.error("  1. 检查GPU状态: nvidia-smi")
        logger.error(f"  2. 检查端口: netstat -tlnp | grep {cfg['port']}")
        logger.error(f"  3. 增加超时: 在.env中设置 VLLM_SERVER_STARTUP_TIMEOUT={max_wait+60}")
        sys.exit(1)

    # 保存 PID 文件
    server_mgr.save_pid_file(cfg['model_type'], process.pid)
    logger.info(f"按 Ctrl+C 停止服务器")

    try:
        process.wait()
    except KeyboardInterrupt:
        logger.info("\n正在停止服务器...")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("服务器未响应 SIGTERM，使用 SIGKILL")
            process.kill()
            process.wait()

        # 清理 PID 文件
        try:
            os.remove(".vlm_server.pid")
        except OSError:
            pass

        logger.info("✓ 服务器已停止")


if __name__ == "__main__":
    main()
