#!/usr/bin/env python
"""vLLM 服务器启动脚本 — 按 Ctrl+C 停止"""
import logging
import socket
import subprocess
import sys
import time
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.common.config import config
from src.vlm.server import get_vlm_server_manager


def _resolve_model_type() -> str:
    model_type = config.vlm_selector.model_type.lower()
    if model_type in ('qwen35', 'qwen3.5', 'qwen3'):
        return 'qwen35'
    return 'qwen2'


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def main():
    server_mgr = get_vlm_server_manager()
    model_type = _resolve_model_type()
    cmd = server_mgr.build_cmd(model_type)
    env = server_mgr.build_env()

    model_name = cmd[2]
    port = int(cmd[cmd.index('--port') + 1])
    logger.info(f"模型: {model_name}  端口: {port}")
    if env.get('CUDA_VISIBLE_DEVICES'):
        logger.info(f"GPU 选择: CUDA_VISIBLE_DEVICES={env['CUDA_VISIBLE_DEVICES']}")
    if env.get('HF_HUB_OFFLINE') == '1':
        logger.info("离线模式：从本地缓存加载模型")
    if '--enable-lora' in cmd:
        lora_args = [cmd[i + 1] for i, v in enumerate(cmd) if v == '--lora-modules']
        logger.info(f"LoRA adapters: {lora_args}")

    if is_port_in_use(port):
        logger.error(f"端口 {port} 已被占用，服务器可能已在运行")
        sys.exit(1)

    process = subprocess.Popen(cmd, env=env)
    logger.info("========== vLLM 服务器启动中 ==========")

    max_wait = config.vllm_server.startup_timeout
    start_time = time.time()

    while time.time() - start_time < max_wait:
        time.sleep(1)
        if server_mgr.health_check(model_type):
            elapsed = int(time.time() - start_time)
            logger.info(f"✓ 启动成功 (PID: {process.pid}, 耗时: {elapsed}秒)")
            logger.info("按 Ctrl+C 停止服务器")
            break
    else:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        logger.error(f"启动超时（{max_wait}秒）")
        logger.error(f"  检查 GPU: nvidia-smi")
        logger.error(f"  检查端口: netstat -tlnp | grep {port}")
        logger.error(f"  增加超时: VLLM_SERVER_STARTUP_TIMEOUT={max_wait + 60}")
        sys.exit(1)

    try:
        process.wait()
    except KeyboardInterrupt:
        logger.info("\n正在停止服务器...")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("SIGTERM 无响应，使用 SIGKILL")
            process.kill()
            process.wait()
        logger.info("✓ 服务器已停止")


if __name__ == "__main__":
    main()
