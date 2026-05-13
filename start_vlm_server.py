#!/usr/bin/env python
"""vLLM 服务器启动脚本 — 按 Ctrl+C 停止"""
import logging
import os
import socket
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.common.config import config
from src.vlm.server import get_vlm_server_manager


def read_config() -> dict:
    model_type = config.vlm_selector.model_type.lower()
    if model_type in ('qwen35', 'qwen3.5', 'qwen3'):
        model_type = 'qwen35'
    else:
        model_type = 'qwen2'

    base_port = config.vllm_server.base_port
    port = base_port + (1 if model_type == 'qwen35' else 0)
    model_name = config.vlm35.model if model_type == 'qwen35' else config.vlm.model

    return {'model_type': model_type, 'port': port, 'model_name': model_name}


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def main():
    cfg = read_config()
    logger.info(f"模型: {cfg['model_name']}  端口: {cfg['port']}")

    if is_port_in_use(cfg['port']):
        logger.error(f"端口 {cfg['port']} 已被占用，服务器可能已在运行")
        sys.exit(1)

    cmd = [
        'vllm', 'serve', cfg['model_name'],
        '--host', config.vllm_server.host,
        '--port', str(cfg['port']),
        '--tensor-parallel-size', str(config.vllm_server.tensor_parallel_size),
        '--gpu-memory-utilization', str(config.vllm_server.gpu_memory_utilization),
        '--limit-mm-per-prompt', config.vllm_server.limit_mm_per_prompt,
        '--enable-auto-tool-choice',
        '--tool-call-parser', 'hermes',
    ]

    if config.vllm_server.max_model_len:
        cmd.extend(['--max-model-len', str(config.vllm_server.max_model_len)])

    env = os.environ.copy()
    if config.vllm_server.cuda_visible_devices is not None:
        env['CUDA_VISIBLE_DEVICES'] = config.vllm_server.cuda_visible_devices
        logger.info(f"GPU 选择: CUDA_VISIBLE_DEVICES={config.vllm_server.cuda_visible_devices}")
    if os.environ.get('VLLM_OFFLINE', '').lower() in ('1', 'true', 'yes'):
        env['HF_HUB_OFFLINE'] = '1'
        env['TRANSFORMERS_OFFLINE'] = '1'
        logger.info("离线模式：从本地缓存加载模型")

    process = subprocess.Popen(cmd, env=env)
    logger.info("========== vLLM 服务器启动中 ==========")

    server_mgr = get_vlm_server_manager()
    max_wait = config.vllm_server.startup_timeout
    start_time = time.time()

    while time.time() - start_time < max_wait:
        time.sleep(1)
        if server_mgr.health_check(cfg['model_type']):
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
        logger.error(f"  检查端口: netstat -tlnp | grep {cfg['port']}")
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
