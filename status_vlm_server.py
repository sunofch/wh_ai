#!/usr/bin/env python
"""vLLM 服务器状态查询脚本

显示 vLLM 服务器的运行状态
"""
import os
import sys
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.vlm_server import get_vlm_server_manager


def main():
    """主函数"""
    server_mgr = get_vlm_server_manager()

    # 读取 PID 文件
    pid_info = server_mgr.load_pid_file()
    if not pid_info:
        print("vLLM 服务器状态: 未运行")
        print("  提示: 运行 'python start_vlm_server.py' 启动服务器")
        sys.exit(0)

    # 检查进程是否运行
    try:
        pid = pid_info["pid"]
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        print("vLLM 服务器状态: 已停止（PID 文件残留）")
        print("  清理中...")
        try:
            os.remove(".vlm_server.pid")
        except OSError:
            pass
        print("  ✓ PID 文件已清理")
        sys.exit(0)

    # 显示状态信息
    print("vLLM 服务器状态: ✓ 运行中")
    print(f"  - PID: {pid_info['pid']}")
    print(f"  - 模型: {pid_info['model_name']}")
    print(f"  - 端口: {pid_info['port']}")

    # 格式化启动时间
    start_time = pid_info.get('start_time', 'unknown')
    if start_time != 'unknown':
        try:
            dt = datetime.fromisoformat(start_time)
            print(f"  - 启动时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        except ValueError:
            print(f"  - 启动时间: {start_time}")

    # 健康检查
    if server_mgr.health_check(pid_info['model_type']):
        print(f"  - 健康检查: ✓ 正常")
    else:
        print(f"  - 健康检查: ✗ 失败")


if __name__ == "__main__":
    main()
