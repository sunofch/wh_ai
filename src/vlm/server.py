"""VLM服务器管理器

负责vLLM服务器的启动、停止和健康检查
"""
import json
import os
import socket
import subprocess
import time
from datetime import datetime
from typing import Dict, Optional

import requests

from src.config import config


class VLLMServerManager:
    """vLLM服务器生命周期管理"""

    def __init__(self):
        self.servers: Dict[str, subprocess.Popen] = {}
        self.port_map = {
            'qwen2': config.vllm_server.base_port,
            'qwen35': config.vllm_server.base_port + 1
        }

    def _is_port_available(self, port: int) -> bool:
        """检查端口是否可用

        Args:
            port: 端口号

        Returns:
            bool: 可用返回True
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return True
            except OSError:
                return False

    def start_server(self, model_type: str) -> bool:
        """启动指定模型的vLLM服务器

        Args:
            model_type: 'qwen2' 或 'qwen35'

        Returns:
            bool: 启动成功返回True

        Raises:
            RuntimeError: 启动失败时抛出异常
        """
        if model_type in self.servers:
            if self.health_check(model_type):
                return True
            else:
                self.stop_server(model_type)

        # 获取模型配置
        if model_type == 'qwen2':
            model_name = config.vlm.model
            port = self.port_map['qwen2']
        elif model_type == 'qwen35':
            model_name = config.vlm35.model
            port = self.port_map['qwen35']
        else:
            raise ValueError(f"不支持的模型类型: {model_type}")

        # 检查端口是否可用
        if not self._is_port_available(port):
            raise RuntimeError(
                f"端口 {port} 已被占用，请检查是否有其他vLLM服务器正在运行，"
                f"或修改.env中的VLLM_SERVER_BASE_PORT配置"
            )

        # 构造vllm serve命令
        cmd = [
            'vllm', 'serve', model_name,
            '--host', config.vllm_server.host,
            '--port', str(port),
            '--tensor-parallel-size', str(config.vllm_server.tensor_parallel_size),
            '--gpu-memory-utilization', str(config.vllm_server.gpu_memory_utilization),
            '--limit-mm-per-prompt', config.vllm_server.limit_mm_per_prompt
        ]

        # 可选参数
        if config.vllm_server.max_model_len:
            cmd.extend(['--max-model-len', str(config.vllm_server.max_model_len)])

        # 启动服务器
        print(f"启动vLLM服务器: {model_name} 在端口 {port}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        self.servers[model_type] = process

        # 等待服务器就绪（使用配置的超时时间）
        max_wait = config.vllm_server.startup_timeout
        for i in range(max_wait):
            if self.health_check(model_type):
                print(f"vLLM服务器 {model_type} 启动成功")
                return True
            time.sleep(1)

        # 启动失败 - 捕获错误输出
        try:
            stdout, stderr = process.communicate(timeout=1)
        except:
            stdout, stderr = process.stdout.read(), process.stderr.read()

        self.stop_server(model_type)

        error_msg = f"vLLM服务器 {model_type} 启动超时（等待{max_wait}秒）"
        if stderr:
            error_msg += f"\n错误输出:\n{stderr[-500:]}"  # 最后500字符
        if stdout:
            error_msg += f"\n输出:\n{stdout[-500:]}"

        # 提供诊断建议
        error_msg += f"\n\n诊断建议:"
        error_msg += f"\n  1. 检查GPU状态: nvidia-smi"
        error_msg += f"\n  2. 检查端口占用: netstat -tlnp | grep {port}"
        error_msg += f"\n  3. 增加超时时间: 在.env中设置 VLLM_SERVER_STARTUP_TIMEOUT={max_wait + 60}"
        error_msg += f"\n  4. 查看vLLM日志: 检查stderr输出中的错误信息"

        raise RuntimeError(error_msg)

    def stop_server(self, model_type: str) -> bool:
        """停止服务器

        Args:
            model_type: 模型类型

        Returns:
            bool: 停止成功返回True
        """
        if model_type not in self.servers:
            return True

        process = self.servers[model_type]
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

        del self.servers[model_type]
        return True

    def health_check(self, model_type: str, max_retries: int = 3) -> bool:
        """检查服务器健康状态

        Args:
            model_type: 模型类型
            max_retries: 最大重试次数

        Returns:
            bool: 健康返回True
        """
        for attempt in range(max_retries):
            try:
                url = self.get_server_url(model_type)
                response = requests.get(f"{url}/health", timeout=2)
                return response.status_code == 200
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(0.5)
        return False

    def get_server_url(self, model_type: str) -> str:
        """获取服务器URL

        Args:
            model_type: 模型类型

        Returns:
            str: 服务器URL
        """
        port = self.port_map[model_type]
        return f"http://{config.vllm_server.host}:{port}"

    def stop_all(self):
        """停止所有服务器"""
        for model_type in list(self.servers.keys()):
            self.stop_server(model_type)

    def save_pid_file(self, model_type: str, pid: int) -> None:
        """保存进程信息到 PID 文件

        Args:
            model_type: 模型类型 ('qwen2' 或 'qwen35')
            pid: 进程 ID
        """
        # 确定模型名称
        if model_type == 'qwen2':
            model_name = config.vlm.model
        elif model_type == 'qwen35':
            model_name = config.vlm35.model
        else:
            model_name = "unknown"

        pid_info = {
            "pid": pid,
            "model_type": model_type,
            "port": self.port_map[model_type],
            "model_name": model_name,
            "start_time": datetime.now().isoformat()
        }

        with open(".vlm_server.pid", "w") as f:
            json.dump(pid_info, f, indent=2)

    def load_pid_file(self) -> Optional[Dict]:
        """读取 PID 文件

        Returns:
            PID 信息字典，如果文件不存在或损坏返回 None
        """
        try:
            with open(".vlm_server.pid", "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def is_server_running(self) -> bool:
        """检查服务器是否正在运行

        Returns:
            bool: 服务器运行中返回 True
        """
        pid_info = self.load_pid_file()
        if not pid_info:
            return False

        # 检查进程是否存在
        try:
            pid = pid_info["pid"]
            # 使用 os.kill(pid, 0) 检查进程是否存在
            # 如果进程存在，os.kill(pid, 0) 不抛出异常
            # 如果进程不存在，抛出 ProcessLookupError
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            # 进程不存在，清理 PID 文件
            try:
                os.remove(".vlm_server.pid")
            except OSError:
                pass
            return False


# 全局单例
_vlm_server_manager: Optional[VLLMServerManager] = None


def get_vlm_server_manager() -> VLLMServerManager:
    """获取VLM服务器管理器单例

    Returns:
        VLLMServerManager: 单例实例
    """
    global _vlm_server_manager
    if _vlm_server_manager is None:
        _vlm_server_manager = VLLMServerManager()
    return _vlm_server_manager
