#!/usr/bin/env python
"""vLLM 服务器停止脚本

读取 PID 文件并停止 vLLM 服务器进程
"""
import logging
import os
import signal
import sys
import time

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.vlm.server import get_vlm_server_manager


def main():
    """主函数"""
    server_mgr = get_vlm_server_manager()

    # 读取 PID 文件
    pid_info = server_mgr.load_pid_file()
    if not pid_info:
        logger.info("服务器未运行（PID 文件不存在）")
        sys.exit(0)

    pid = pid_info["pid"]
    logger.info(f"正在停止 vLLM 服务器 (PID: {pid})...")

    # 检查进程是否存在
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        logger.info("进程不存在，清理 PID 文件")
        try:
            os.remove(".vlm_server.pid")
        except OSError:
            pass
        sys.exit(0)

    # 发送 SIGTERM（跨平台方式）
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError) as e:
        logger.warning(f"无法发送 SIGTERM 到进程 {pid}: {e}")

    # 等待进程退出
    for i in range(10):
        time.sleep(1)
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            # 进程已退出
            logger.info("✓ 服务器已停止")
            break
    else:
        # 超时，使用 SIGKILL
        logger.warning("服务器未响应 SIGTERM，使用 SIGKILL 强制停止")
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)
        except (OSError, ProcessLookupError) as e:
            logger.error(f"无法停止进程: {e}")
            sys.exit(1)

        logger.info("✓ 服务器已强制停止")

    # 清理 PID 文件
    try:
        os.remove(".vlm_server.pid")
    except OSError:
        pass


if __name__ == "__main__":
    main()
