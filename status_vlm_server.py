#!/usr/bin/env python
"""vLLM 服务器状态查询"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.common.config import config
from src.vlm.server import get_vlm_server_manager


def main():
    base_port = config.vllm_server.base_port
    server_mgr = get_vlm_server_manager()

    any_running = False
    for model_type, port in [('qwen2', base_port), ('qwen35', base_port + 1)]:
        if server_mgr.health_check(model_type, max_retries=1):
            print(f"✓ {model_type} 运行中 (端口 {port})")
            any_running = True
        else:
            print(f"✗ {model_type} 未运行 (端口 {port})")

    if not any_running:
        print("提示: 运行 'python start_vlm_server.py' 启动服务器")


if __name__ == "__main__":
    main()
