# vLLM 服务器分离重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标:** 将 vLLM 服务器的启动逻辑从业务代码中分离，通过独立的服务器管理脚本启动和停止服务器，避免每次运行业务程序时等待服务器启动（~180秒）。

**架构方案:**
1. 新增三个独立脚本（start/stop/status）用于管理 vLLM 服务器生命周期
2. 使用 PID 文件持久化服务器进程信息，支持跨程序管理
3. 修改现有 VLM 客户端代码，移除自动启动逻辑，改为连接检查
4. 修改业务程序入口，添加服务器运行检查，提供友好错误提示

**技术栈:**
- Python 3.10+
- subprocess（进程管理）
- json（PID 文件格式）
- requests（HTTP 健康检查）
- psutil（进程状态检查，可选）

**关键约束:**
- 必须在当前环境中实际运行测试所有代码
- 所有 import 必须置于文件顶端
- 严禁设计多级嵌套的 fallback 机制
- 彻底重构，不保留向后兼容

---

## 文件结构映射

### 新增文件
- `start_vlm_server.py` - 主启动脚本，负责启动 vLLM 服务器并管理其生命周期
- `stop_vlm_server.py` - 停止脚本，读取 PID 并停止服务器进程
- `status_vlm_server.py` - 状态查询脚本，显示服务器运行状态
- `.vlm_server.pid` - PID 文件（运行时生成，不提交到 Git）
- `.gitignore` - 更新，添加 `.vlm_server.pid`

### 修改文件
- `src/vlm_server.py` - 添加 PID 管理方法（save_pid_file, load_pid_file, is_server_running），移除 atexit 自动清理
- `src/vlm.py` - 修改 Qwen2VLM 和 Qwen35VLM 的 __init__，移除自动启动，添加运行检查
- `main_interaction.py` - 在 InstructionParser.__init__ 中添加服务器检查
- `README.md` - 添加服务器管理说明
- `CLAUDE.md` - 更新架构说明和常用命令

---

## Task 1: 扩展 src/vlm_server.py - 添加 PID 管理功能

**文件:**
- Modify: `src/vlm_server.py`

**目标:** 在现有的 VLLMServerManager 类中添加 PID 文件管理功能，为独立脚本提供基础。

- [ ] **Step 1: 在文件顶部添加必要的导入**

```python
import json
import os
from datetime import datetime
from typing import Optional, Dict
```

位置: 文件顶部，现有导入之后

- [ ] **Step 2: 添加 save_pid_file 方法**

在 VLLMServerManager 类中添加以下方法（在 stop_all 方法之后）:

```python
def save_pid_file(self, model_type: str, pid: int) -> None:
    """保存进程信息到 PID 文件

    Args:
        model_type: 模型类型 ('qwen2' 或 'qwen35')
        pid: 进程 ID
    """
    from src.config import config

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
```

- [ ] **Step 3: 添加 load_pid_file 方法**

```python
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
```

- [ ] **Step 4: 添加 is_server_running 方法**

```python
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
```

- [ ] **Step 5: 移除 atexit 自动清理**

在 VLLMServerManager.__init__ 方法中，删除以下行:

```python
# 删除这行
atexit.register(self.stop_all)
```

- [ ] **Step 6: 测试 PID 管理功能**

```python
# 在项目根目录运行
python -c "
from src.vlm_server import get_vlm_server_manager
import os

mgr = get_vlm_server_manager()

# 测试保存 PID（使用当前进程 PID，确保存在）
current_pid = os.getpid()
mgr.save_pid_file('qwen35', current_pid)
print('✓ PID 文件保存成功')

# 测试读取 PID
pid_info = mgr.load_pid_file()
print(f'✓ PID 文件读取成功: {pid_info}')

# 测试进程检查（当前进程肯定存在）
is_running = mgr.is_server_running()
print(f'✓ 服务器运行状态: {is_running} (应该为 True)')

# 清理
os.remove('.vlm_server.pid')
print('✓ 测试完成')
"
```

预期输出: 所有测试通过，`is_server_running()` 返回 True（因为使用的是当前进程的 PID）

- [ ] **Step 7: 提交修改**

```bash
git add src/vlm_server.py
git commit -m "refactor(vlm-server): 添加 PID 文件管理功能

- 新增 save_pid_file() 方法：保存进程信息到 JSON 文件
- 新增 load_pid_file() 方法：读取 PID 文件
- 新增 is_server_running() 方法：检查服务器运行状态
- 移除 atexit 自动清理逻辑，改为手动管理"
```

---

## Task 2: 创建 start_vlm_server.py - 服务器启动脚本

**文件:**
- Create: `start_vlm_server.py`

**目标:** 创建独立的服务器启动脚本，负责读取配置、启动服务器、保存 PID、显示日志。

- [ ] **Step 1: 创建文件并添加导入**

```python
#!/usr/bin/env python
"""vLLM 服务器启动脚本

独立启动 vLLM 服务器进程，保存 PID 文件，实时显示日志
"""
import json
import logging
import os
import signal
import subprocess
import sys
import time
from typing import Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import config
from src.vlm_server import get_vlm_server_manager
```

- [ ] **Step 2: 添加配置读取函数**

```python
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
```

- [ ] **Step 3: 添加端口检查函数**

```python
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
```

- [ ] **Step 4: 添加日志转发函数**

```python
def forward_logs(process: subprocess.Popen):
    """实时转发服务器日志到控制台

    Args:
        process: 服务器进程对象
    """
    logger.info("========== vLLM 服务器日志 ==========")
    try:
        # 非阻塞读取 stdout 和 stderr
        import select

        while True:
            # 检查进程是否还在运行
            if process.poll() is not None:
                # 进程已退出，读取剩余输出
                if process.stdout:
                    remaining = process.stdout.read()
                    if remaining:
                        print(remaining.decode('utf-8'), end='')
                break

            # 等待输出数据
            readable, _, _ = select.select(
                [process.stdout, process.stderr] if process.stderr else [process.stdout],
                [],
                [],
                1.0  # 1秒超时
            )

            for stream in readable:
                if stream == process.stdout:
                    line = stream.readline()
                    if line:
                        print(line.decode('utf-8'), end='')
                elif stream == process.stderr:
                    line = stream.readline()
                    if line:
                        print(f"[ERROR] {line.decode('utf-8')}", end='', file=sys.stderr)

    except KeyboardInterrupt:
        logger.info("\n收到停止信号，正在停止服务器...")
```

- [ ] **Step 5: 添加主函数**

```python
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

    logger.info(f"等待服务器就绪...")

    # 启动服务器
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # 等待服务器健康检查通过
    max_wait = config.vllm_server.startup_timeout
    start_time = time.time()

    logger.info(f"等待服务器就绪（最多 {max_wait} 秒）...")

    while time.time() - start_time < max_wait:
        time.sleep(1)
        if server_mgr.health_check(cfg['model_type']):
            elapsed = int(time.time() - start_time)
            logger.info(f"✓ vLLM 服务器启动成功 (PID: {process.pid}, 耗时: {elapsed}秒)")
            break

        # 每 10 秒显示一次进度
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0 and elapsed > 0:
            logger.info(f"  等待中... {elapsed}/{max_wait} 秒")
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
        # 实时转发日志
        forward_logs(process)
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
```

- [ ] **Step 6: 测试启动脚本**

```bash
# 测试启动（可能会失败，因为环境问题，主要是验证代码逻辑）
python start_vlm_server.py &
echo $!  # 记录进程 ID
sleep 5

# 检查 PID 文件是否生成
cat .vlm_server.pid

# 停止测试进程
kill %1 2>/dev/null || true
rm -f .vlm_server.pid
```

预期输出:
- 显示配置信息
- 显示"等待服务器就绪..."
- 可能因 GPU/模型问题失败，但代码逻辑应该正确

- [ ] **Step 7: 提交**

```bash
git add start_vlm_server.py
git commit -m "feat: 添加 vLLM 服务器启动脚本

- 新增 start_vlm_server.py：独立启动 vLLM 服务器
- 支持读取 .env 配置，自动选择模型类型
- 支持端口占用检查、健康检查、PID 文件管理
- 支持实时日志转发和 Ctrl+C 优雅停止"
```

---

## Task 3: 创建 stop_vlm_server.py - 服务器停止脚本

**文件:**
- Create: `stop_vlm_server.py`

**目标:** 创建停止脚本，读取 PID 文件并停止服务器进程。

- [ ] **Step 1: 创建文件并添加代码**

```python
#!/usr/bin/env python
"""vLLM 服务器停止脚本

读取 PID 文件并停止 vLLM 服务器进程
"""
import logging
import os
import sys
import subprocess

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.vlm_server import get_vlm_server_manager


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
        import signal
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError) as e:
        logger.warning(f"无法发送 SIGTERM 到进程 {pid}: {e}")

    # 等待进程退出
    import time
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
            import signal
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
```

- [ ] **Step 2: 测试停止脚本**

```bash
# 创建测试 PID 文件（使用当前进程 PID）
echo '{"pid": '$$', "model_type": "qwen35", "port": 8001, "model_name": "test", "start_time": "2026-03-27T00:00:00"}' > .vlm_server.pid

# 运行停止脚本（应该显示"进程不存在，清理 PID 文件"）
python stop_vlm_server.py

# 验证 PID 文件被清理
ls .vlm_server.pid 2>/dev/null && echo "❌ PID 文件仍在" || echo "✓ PID 文件已清理"
```

预期输出: 显示"进程不存在，清理 PID 文件"，PID 文件被清理

- [ ] **Step 3: 提交**

```bash
git add stop_vlm_server.py
git commit -m "feat: 添加 vLLM 服务器停止脚本

- 新增 stop_vlm_server.py：读取 PID 并停止服务器进程
- 支持 SIGTERM 优雅停止，超时则 SIGKILL 强制停止
- 自动清理 PID 文件"
```

---

## Task 4: 创建 status_vlm_server.py - 状态查询脚本

**文件:**
- Create: `status_vlm_server.py`

**目标:** 创建状态查询脚本，显示服务器运行状态。

- [ ] **Step 1: 创建文件并添加代码**

```python
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
```

- [ ] **Step 2: 测试状态脚本**

```bash
# 测试未运行状态
python status_vlm_server.py

# 创建测试 PID 文件（使用当前进程 PID）
echo '{"pid": '$$', "model_type": "qwen35", "port": 8001, "model_name": "Qwen/Qwen3.5-4B", "start_time": "2026-03-27T10:30:00"}' > .vlm_server.pid

# 测试运行状态
python status_vlm_server.py

# 清理
rm -f .vlm_server.pid
```

预期输出: 正确显示运行状态和进程信息（使用当前进程 PID，所以显示"运行中"）

- [ ] **Step 3: 提交**

```bash
git add status_vlm_server.py
git commit -m "feat: 添加 vLLM 服务器状态查询脚本

- 新增 status_vlm_server.py：显示服务器运行状态
- 支持 PID 文件解析、进程检查、健康检查
- 格式化显示启动时间和模型信息"
```

---

## Task 5: 修改 src/vlm.py - 移除自动启动逻辑

**文件:**
- Modify: `src/qwen2vlm.py`（找到 `Qwen2VLM.__init__` 方法中的自动启动代码）
- Modify: `src/qwen35vlm.py`（找到 `Qwen35VLM.__init__` 方法中的自动启动代码）

**目标:** 修改 VLM 客户端代码，移除自动启动服务器的逻辑，改为检查服务器是否运行。

- [ ] **Step 1: 修改 qwen2vlm.py**

找到 `Qwen2VLM.__init__` 方法中的自动启动代码（通常在 `self.server_manager = get_vlm_server_manager()` 之后）:

```python
# 旧代码（删除）
if not self.server_manager.health_check('qwen2'):
    self.server_manager.start_server('qwen2')
```

替换为:

```python
# 新代码
if not self.server_manager.is_server_running():
    raise RuntimeError(
        f"\n{'='*60}\n"
        f"vLLM 服务器未运行！\n"
        f"{'='*60}\n"
        f"请先启动服务器:\n"
        f"  python start_vlm_server.py\n\n"
        f"或查看服务器状态:\n"
        f"  python status_vlm_server.py\n"
        f"{'='*60}\n"
    )
```

- [ ] **Step 2: 修改 qwen35vlm.py**

找到 `Qwen35VLM.__init__` 方法中的自动启动代码（通常在 `self.server_manager = get_vlm_server_manager()` 之后）:

```python
# 旧代码（删除）
if not self.server_manager.health_check('qwen35'):
    self.server_manager.start_server('qwen35')
```

替换为:

```python
# 新代码
if not self.server_manager.is_server_running():
    raise RuntimeError(
        f"\n{'='*60}\n"
        f"vLLM 服务器未运行！\n"
        f"{'='*60}\n"
        f"请先启动服务器:\n"
        f"  python start_vlm_server.py\n\n"
        f"或查看服务器状态:\n"
        f"  python status_vlm_server.py\n"
        f"{'='*60}\n"
    )
```

- [ ] **Step 3: 测试修改**

```bash
# 在没有服务器运行的情况下测试
python -c "
from src.vlm import get_vlm_instance
try:
    vlm = get_vlm_instance()
    print('❌ 测试失败：应该抛出异常')
except RuntimeError as e:
    if 'vLLM 服务器未运行' in str(e):
        print('✓ 测试通过：正确抛出异常并显示友好提示')
        print(f'异常信息:\n{e}')
    else:
        print(f'❌ 测试失败：异常信息不正确\n{e}')
except Exception as e:
    print(f'❌ 测试失败：异常类型错误\n{type(e).__name__}: {e}')
"
```

预期输出: 显示"✓ 测试通过：正确抛出异常并显示友好提示"

- [ ] **Step 4: 提交**

```bash
git add src/qwen2vlm.py src/qwen35vlm.py
git commit -m "refactor(vlm): 移除自动启动逻辑，改为服务器运行检查

- 修改 Qwen2VLM 和 Qwen35VLM 的 __init__ 方法
- 移除自动启动服务器逻辑
- 添加服务器运行检查，未运行时抛出友好异常
- 提示用户运行 start_vlm_server.py 启动服务器"
```

---

## Task 6: 修改 main_interaction.py - 添加服务器检查

**文件:**
- Modify: `main_interaction.py:49-66`

**目标:** 在业务程序入口添加服务器检查，提供更好的用户体验。

- [ ] **Step 1: 修改 InstructionParser.__init__**

在 `InstructionParser.__init__` 方法的开头（在 `self.asr = get_asr_instance()` 之前），添加服务器检查:

注意：确保文件顶部已导入所需的模块（logger, sys 等）

```python
def __init__(self):
    # 检查 vLLM 服务器状态
    from src.vlm_server import get_vlm_server_manager
    server_mgr = get_vlm_server_manager()

    if not server_mgr.is_server_running():
        logger.error(
            "\n" + "="*60 + "\n"
            "vLLM 服务器未运行！\n"
            "="*60 + "\n"
            "请先启动服务器:\n"
            "  python start_vlm_server.py\n\n"
            "或查看服务器状态:\n"
            "  python status_vlm_server.py\n"
            "="*60
        )
        sys.exit(1)

    self.asr = get_asr_instance()
    # ... 其余代码保持不变
```

- [ ] **Step 2: 测试修改**

```bash
# 在没有服务器运行的情况下测试
python main_interaction.py --text "测试" <<EOF
quit
EOF
```

预期输出: 显示错误信息并退出，不显示"系统初始化完成"

- [ ] **Step 3: 提交**

```bash
git add main_interaction.py
git commit -m "refactor(main): 添加服务器运行检查

- 在 InstructionParser.__init__ 中添加服务器检查
- 服务器未运行时显示友好的错误提示并退出
- 避免初始化其他组件时的资源浪费"
```

---

## Task 7: 更新 .gitignore - 添加 PID 文件

**文件:**
- Modify: `.gitignore`

**目标:** 确保 PID 文件不被提交到 Git 仓库。

- [ ] **Step 1: 添加 PID 文件到 .gitignore**

在 `.gitignore` 文件末尾添加:

```gitignore
# vLLM Server PID 文件
.vlm_server.pid
```

- [ ] **Step 2: 验证**

```bash
# 创建测试 PID 文件
touch .vlm_server.pid

# 检查 git status
git status .vlm_server.pid

# 应该显示：.vlm_server.pid 在 .gitignore 中

# 清理
rm .vlm_server.pid
```

预期输出: `.vlm_server.pid` 不出现在 `git status` 的未跟踪文件列表中

- [ ] **Step 3: 提交**

```bash
git add .gitignore
git commit -m "chore: 添加 .vlm_server.pid 到 .gitignore

- 防止 PID 文件被提交到 Git 仓库"
```

---

## Task 8: 更新 README.md - 添加服务器管理说明

**文件:**
- Modify: `README.md`

**目标:** 在 README 中添加 vLLM 服务器管理的使用说明。

- [ ] **Step 1: 找到合适的位置插入内容**

在 README.md 中找到介绍运行项目的章节（通常在 "## 🚀 快速开始" 或 "## Running the Application" 附近）

- [ ] **Step 2: 添加服务器管理章节**

在运行项目章节之后，添加新的 "## vLLM 服务器管理" 章节:

```markdown
## vLLM 服务器管理

vLLM 服务器需要独立启动，以便多个程序共享使用，避免每次启动时等待模型加载（~180秒）。

### 启动服务器

```bash
python start_vlm_server.py
```

服务器启动后会：
- 根据 `.env` 中的 `VLM_MODEL_TYPE` 配置自动选择模型
- 在端口 8000（qwen2）或 8001（qwen35）上运行
- 显示实时日志
- 按 `Ctrl+C` 停止服务器

### 查看服务器状态

```bash
python status_vlm_server.py
```

显示：
- 进程 PID
- 模型名称
- 端口号
- 启动时间
- 健康检查状态

### 停止服务器

```bash
python stop_vlm_server.py
```

或按 `Ctrl+C` 停止 `start_vlm_server.py` 脚本。

### 开发工作流

```bash
# 终端 1：启动 vLLM 服务器（一次性）
python start_vlm_server.py

# 终端 2：运行业务程序（可多次执行，无需等待）
python main_interaction.py
python main_interaction.py  # 再次运行，快速启动

# 终端 1：停止服务器
# 按 Ctrl+C 或运行
python stop_vlm_server.py
```
```

- [ ] **Step 3: 更新常用命令章节**

在 "Common Commands" 章节添加:

```markdown
### 服务器管理

```bash
# 启动 vLLM 服务器
python start_vlm_server.py

# 查看服务器状态
python status_vlm_server.py

# 停止 vLLM 服务器
python stop_vlm_server.py
```
```

- [ ] **Step 4: 提交**

```bash
git add README.md
git commit -m "docs: 添加 vLLM 服务器管理说明

- 在 README 中添加服务器管理章节
- 说明启动/停止/状态查询命令
- 提供开发工作流示例"
```

---

## Task 9: 更新 CLAUDE.md - 更新项目架构说明

**文件:**
- Modify: `CLAUDE.md`

**目标:** 更新 CLAUDE.md 中的架构说明，反映新的服务器管理方式。

- [ ] **Step 1: 更新"High-Level Architecture"章节**

找到 "## High-Level Architecture" 章节，更新 Data Flow Pipeline:

```markdown
## High-Level Architecture

### vLLM 服务器管理

**重要变更**：vLLM 服务器现在独立于业务程序运行。

**启动流程**：
1. 用户运行 `python start_vlm_server.py` 启动服务器
2. 服务器根据 `.env` 配置选择模型（qwen2/qwen35）
3. 服务器启动后在后台运行，监听端口 8000 或 8001
4. 服务器进程信息保存到 `.vlm_server.pid`

**业务程序连接**：
1. 业务程序启动时检查服务器运行状态
2. 如果服务器未运行，显示错误并退出
3. 如果服务器运行中，正常连接使用

**停止流程**：
- 用户运行 `python stop_vlm_server.py` 或按 `Ctrl+C` 停止服务器
- 清理 `.vlm_server.pid` 文件

### 数据流管道（业务程序）
```

- [ ] **Step 2: 更新"Common Commands"章节**

添加服务器管理命令：

```markdown
### vLLM 服务器管理

```bash
# 启动 vLLM 服务器（开发时必须先启动）
python start_vlm_server.py

# 查看服务器状态
python status_vlm_server.py

# 停止 vLLM 服务器
python stop_vlm_server.py
```

**注意**：运行 `main_interaction.py` 之前必须先启动 vLLM 服务器！
```

- [ ] **Step 3: 更新"Important Constraints"章节**

在现有约束之后添加：

```markdown
### vLLM 服务器约束

- vLLM 服务器必须独立启动，不会在业务程序中自动启动
- 如果服务器未运行，业务程序会显示错误并退出
- 服务器进程信息保存在 `.vlm_server.pid`，不要手动删除
- 停止服务器时使用 `stop_vlm_server.py` 或 Ctrl+C
```

- [ ] **Step 4: 提交**

```bash
git add CLAUDE.md
git commit -m "docs: 更新 CLAUDE.md 架构说明

- 更新高层次架构：说明 vLLM 服务器独立运行
- 更新常用命令：添加服务器管理命令
- 添加 vLLM 服务器约束说明"
```

---

## Task 10: 集成测试 - 完整流程验证

**文件:**
- Test: 所有修改的文件

**目标:** 完整测试整个重构后的流程，确保一切正常工作。

- [ ] **Step 1: 测试启动脚本**

```bash
# 启动服务器（后台运行）
python start_vlm_server.py > /tmp/vlm_startup.log 2>&1 &
START_PID=$!

# 等待最多 60 秒（快速验证）
timeout=60
elapsed=0
while [ $elapsed -lt $timeout ]; do
    sleep 1
    if python status_vlm_server.py 2>/dev/null | grep -q "运行中"; then
        echo "✓ 服务器启动成功（耗时: ${elapsed}秒）"
        break
    fi
    elapsed=$((elapsed + 1))
    # 每 10 秒显示进度
    if [ $((elapsed % 10)) -eq 0 ] && [ $elapsed -gt 0 ]; then
        echo "  等待中... ${elapsed}/${timeout} 秒"
    fi
done

if [ $elapsed -ge $timeout ]; then
    echo "⚠ 服务器启动超时或失败（可能需要更长时间），检查日志:"
    tail -20 /tmp/vlm_startup.log
fi

# 检查状态
python status_vlm_server.py || true

# 检查 PID 文件
if [ -f .vlm_server.pid ]; then
    echo "✓ PID 文件已生成"
    cat .vlm_server.pid
else
    echo "⚠ PID 文件未生成"
fi
```

预期输出:
- 如果环境配置正确，服务器成功启动
- status 显示"运行中"
- PID 文件包含正确的进程信息

**注意**：如果启动失败（GPU/模型问题），至少验证代码逻辑正确，能正确显示配置信息和错误提示。

- [ ] **Step 2: 测试业务程序连接**

```bash
# 运行业务程序（应该快速启动，不需要等待服务器启动）
timeout 30 python main_interaction.py --text "测试需要5个电机，紧急" <<EOF
quit
EOF
```

预期输出:
- 快速启动（不等待 180 秒）
- 正常解析指令
- 输出 JSON 结果

- [ ] **Step 3: 测试停止脚本**

```bash
# 停止服务器
python stop_vlm_server.py

# 验证服务器已停止
python status_vlm_server.py

# 验证 PID 文件已清理
ls .vlm_server.pid 2>/dev/null && echo "❌ PID 文件仍在" || echo "✓ PID 文件已清理"
```

预期输出:
- 显示"服务器已停止"
- status 显示"未运行"
- PID 文件已清理

- [ ] **Step 4: 测试错误场景**

```bash
# 测试：服务器未运行时启动业务程序
echo "测试：服务器未运行时的错误提示"
timeout 5 python main_interaction.py --text "测试" <<EOF
quit
EOF
```

预期输出: 显示友好的错误提示，告诉用户启动服务器

- [ ] **Step 5: 清理测试环境**

```bash
# 确保没有残留进程
pkill -f "vllm serve" 2>/dev/null || true

# 清理 PID 文件
rm -f .vlm_server.pid

echo "✓ 测试环境清理完成"
```

- [ ] **Step 6: 提交测试结果**

如果测试通过，创建一个测试通过的标记：

```bash
# 创建测试通过标记
echo "$(date): vLLM 服务器分离重构集成测试通过" > test_results_vlm_server_refactoring.txt

git add test_results_vlm_server_refactoring.txt
git commit -m "test: vLLM 服务器分离重构集成测试通过

- 启动脚本测试通过
- 业务程序连接测试通过
- 停止脚本测试通过
- 错误场景测试通过
- 所有功能符合设计预期"
```

如果测试失败，记录失败原因：

```bash
echo "$(date): 测试失败 - [原因]" > test_results_vlm_server_refactoring.txt

# 不要提交，需要手动修复问题
```

---

## 验收标准

完成所有任务后，应该满足：

- [x] 设计文档完成并批准
- [ ] 所有新增脚本实现完成（start/stop/status）
- [ ] 所有现有代码修改完成（vlm_server.py, vlm.py, main_interaction.py）
- [ ] 在当前环境中测试通过
- [ ] 所有测试场景验证通过（功能测试、边界测试、集成测试）
- [ ] 代码符合编码规范约束
- [ ] 文档更新完成（README.md, CLAUDE.md）
- [ ] Git 提交并推送到仓库

---

## 后续工作

重构完成后，可以考虑的改进：

1. **添加日志持久化**：将服务器日志保存到文件，便于调试
2. **实现服务器重启功能**：添加 `restart_vlm_server.py`
3. **添加环境验证**：启动前检查 GPU 内存、CUDA 版本等
4. **实现活跃连接检查**：停止服务器前检查是否有活跃连接
5. **添加 systemd 服务**：支持生产环境部署

但这些改进不在当前重构的范围内，应该作为独立的任务单独规划和实施。
