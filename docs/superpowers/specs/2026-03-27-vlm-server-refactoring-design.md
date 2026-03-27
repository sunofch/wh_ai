# vLLM 服务器分离重构设计

**日期**: 2026-03-27
**作者**: Claude Code
**状态**: 设计阶段

## 1. 目标

将 vLLM 服务器的启动逻辑从业务代码中分离，避免每次运行 `main_interaction.py` 时都重新加载模型（当前需要等待 180 秒启动时间）。

**核心问题**：
- 当前 vLLM 服务器在 `main_interaction.py` 中自动启动
- 每次测试都需要等待服务器启动（~180 秒）
- 服务器退出后进程可能残留，占用端口

**解决方案**：
- 提供独立的服务器管理脚本
- 服务器与业务程序解耦，一次启动，多次使用

---

## 2. 架构设计

### 2.1 文件结构

```
项目根目录/
├── start_vlm_server.py      # 新增：主启动脚本
├── stop_vlm_server.py       # 新增：停止脚本
├── status_vlm_server.py     # 新增：状态查询脚本
└── src/
    ├── vlm_server.py        # 修改：移除 atexit，保留管理逻辑
    └── vlm.py               # 修改：移除自动启动，添加运行检查
```

### 2.2 模块职责

| 文件 | 职责 | 用户操作 |
|------|------|----------|
| `start_vlm_server.py` | 读取配置、启动服务器、保存 PID、显示日志 | `python start_vlm_server.py` |
| `stop_vlm_server.py` | 读取 PID、停止进程、清理文件 | `python stop_vlm_server.py` |
| `status_vlm_server.py` | 读取 PID、检查状态、显示信息 | `python status_vlm_server.py` |
| `src/vlm_server.py` | 服务器管理逻辑（启动/停止/健康检查） | 被上述脚本调用 |
| `src/vlm.py` | VLM 客户端（移除自动启动逻辑） | 被业务代码调用 |

---

## 3. 核心功能

### 3.1 PID 文件管理

**文件位置**: `.vlm_server.pid`（项目根目录）

**文件格式** (JSON):
```json
{
  "pid": 12345,
  "model_type": "qwen35",
  "port": 8001,
  "model_name": "Qwen/Qwen3.5-4B",
  "start_time": "2026-03-27T10:30:00"
}
```

**作用**:
- 持久化保存进程信息
- 程序退出后仍能找到并管理服务器进程
- 防止僵尸进程占用端口

**错误处理**:
- PID 文件损坏 → 显示警告，忽略并继续
- PID 文件中的进程不存在 → 自动清理文件
- 多个 PID 文件冲突 → 提示用户手动清理

### 3.2 配置读取

从 `.env` 读取配置：
```bash
VLM_MODEL_TYPE=qwen35           # 决定启动哪个模型
VLLM_SERVER_BASE_PORT=8000      # 端口映射：qwen2→8000, qwen35→8001
VLM_MODEL=Qwen/Qwen2-VL-2B-Instruct
VLM35_MODEL=Qwen/Qwen3.5-4B
```

**配置验证**:
- 检查 `VLM_MODEL_TYPE` 是否有效（qwen2/qwen35）
- 检查模型名称配置存在
- 检查端口未被占用

### 3.3 start_vlm_server.py

**执行流程**:
```
1. 读取 .env 配置
2. 检查端口是否被占用（如果占用，提示运行 stop_vlm_server.py）
3. 读取 .vlm_server.pid（如果存在，检查进程是否还在运行）
4. 启动 vLLM 服务器进程（subprocess.Popen）
5. 健康检查（等待服务器响应 /health，最多 180 秒）
6. 保存进程信息到 .vlm_server.pid
7. 实时转发服务器日志到控制台
8. 捕获 Ctrl+C → 优雅停止服务器（调用 stop_server）
```

**用户交互示例**:
```
$ python start_vlm_server.py
[INFO] 读取配置: VLM_MODEL_TYPE=qwen35
[INFO] 启动模型: Qwen/Qwen3.5-4B 在端口 8001
[INFO] 等待服务器就绪...
[INFO] ✓ vLLM 服务器启动成功 (PID: 12345)
[INFO] 按 Ctrl+C 停止服务器

========== vLLM 服务器日志 ==========
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### 3.4 stop_vlm_server.py

**执行流程**:
```
1. 读取 .vlm_server.pid
2. 验证文件中的进程是否存在
   - 不存在 → 显示"服务器未运行"，清理 PID 文件，退出
   - 存在 → 继续
3. 发送 SIGTERM 信号（process.terminate()）
4. 等待进程退出（最多 10 秒）
   - 超时 → 发送 SIGKILL（process.kill()）
5. 清理 .vlm_server.pid
6. 显示停止成功消息
```

**用户交互示例**:
```
$ python stop_vlm_server.py
[INFO] 正在停止 vLLM 服务器 (PID: 12345)...
[INFO] ✓ 服务器已停止
```

### 3.5 status_vlm_server.py

**执行流程**:
```
1. 读取 .vlm_server.pid
2. 如果文件不存在 → 显示"服务器未运行"
3. 如果文件存在：
   - 检查进程是否运行（psutil.pid_exists()）
   - 检查 HTTP 健康状态（requests.get(/health)）
   - 显示详细信息（PID、模型、端口、启动时间、健康状态）
```

**用户交互示例**:
```
$ python status_vlm_server.py
vLLM 服务器状态: ✓ 运行中
  - PID: 12345
  - 模型: Qwen/Qwen3.5-4B
  - 端口: 8001
  - 启动时间: 2026-03-27 10:30:00
  - 健康检查: ✓ 正常
```

---

## 4. 架构决策：为什么选择完全分离

### 4.1 设计权衡

**方案 A（未采用）**：保持自动启动，优化启动速度
- 优点：对现有代码改动最小
- 缺点：仍然存在启动等待时间，未解决核心问题

**方案 B（采用）**：完全分离服务器管理
- 优点：
  - ✅ 完全消除业务代码中的启动等待
  - ✅ 服务器与业务程序完全解耦
  - ✅ 支持多程序共享一个服务器
  - ✅ 更符合微服务架构理念
- 缺点：
  - 需要修改现有代码
  - 需要手动管理服务器生命周期
  - 影响自动化测试流程

**选择方案 B 的原因**：
1. 核心目标是"测试时不用反复加载模型"，只有完全分离才能彻底解决
2. 开发环境通常需要长时间运行多个程序，共享服务器更高效
3. 手动管理服务器生命周期是开发者可以接受的成本

### 4.2 迁移策略

**阶段 1：添加新功能（不破坏现有代码）**
- 新增 `start_vlm_server.py`, `stop_vlm_server.py`, `status_vlm_server.py`
- 修改 `src/vlm_server.py`：添加 PID 管理方法
- 修改 `src/vlm.py`：**同时支持自动启动和手动启动模式**

**阶段 2：修改业务代码**
- 修改所有使用 VLM 的入口点：
  - `main_interaction.py`
  - `main_rag.py`
  - `test_*.py` 测试文件
- 添加服务器运行检查
- 提供友好的错误提示

**阶段 3：清理遗留代码**
- 移除 `atexit.register(self.stop_all)`
- 移除自动启动逻辑
- 更新文档

**兼容性设计**：
在过渡期，使用环境变量控制行为：
```bash
# 旧模式（兼容）：自动启动服务器
export VLM_SERVER_MANUAL=false

# 新模式：手动管理服务器
export VLM_SERVER_MANUAL=true
```

---

## 5. 代码修改

### 5.1 src/vlm_server.py

**移除**:
```python
# 删除自动清理逻辑
atexit.register(self.stop_all)
```

**保留**:
- `VLLMServerManager` 类
- `start_server(model_type)` 方法
- `stop_server(model_type)` 方法
- `health_check(model_type)` 方法
- `_is_port_available(port)` 方法

**新增方法**:
```python
def save_pid_file(self, model_type: str, pid: int):
    """保存 PID 到 .vlm_server.pid"""
    pid_info = {
        "pid": pid,
        "model_type": model_type,
        "port": self.port_map[model_type],
        "model_name": config.vlm.model if model_type == 'qwen2' else config.vlm35.model,
        "start_time": datetime.now().isoformat()
    }
    with open(".vlm_server.pid", "w") as f:
        json.dump(pid_info, f, indent=2)

def load_pid_file(self) -> Optional[Dict]:
    """读取 .vlm_server.pid，返回进程信息"""
    try:
        with open(".vlm_server.pid", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def is_server_running(self) -> bool:
    """检查服务器是否正在运行（通过 PID 文件）"""
    pid_info = self.load_pid_file()
    if not pid_info:
        return False

    # 检查进程是否存在
    try:
        import psutil
        return psutil.pid_exists(pid_info["pid"])
    except ImportError:
        # 如果没有 psutil，使用 os.kill(0) 检查
        import os
        import signal
        try:
            os.kill(pid_info["pid"], 0)
            return True
        except (OSError, ProcessLookupError):
            return False
```

### 5.2 src/vlm.py（修改）

**修改 `Qwen2VLM.__init__()` 和 `Qwen35VLM.__init__()`**:

**步骤 1：添加环境变量检查**
```python
# 在 __init__ 开始处添加
import os
from src.config import config

# 检查是否为手动管理模式
manual_mode = os.getenv("VLM_SERVER_MANUAL", "false").lower() == "true"

# 获取vLLM服务器管理器
self.server_manager = get_vlm_server_manager()
model_type = 'qwen2' if isinstance(self, Qwen2VLM) else 'qwen35'

# 检查服务器状态
if manual_mode:
    # 手动模式：不自动启动，抛出异常
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
else:
    # 自动模式（兼容旧代码）：自动启动服务器
    if not self.server_manager.health_check(model_type):
        self.server_manager.start_server(model_type)
```

**步骤 2：移除 atexit 自动清理（阶段 3）**
```python
# 在 src/vlm_server.py 中移除
# atexit.register(self.stop_all)  # 删除这行
```

### 5.3 main_interaction.py（修改）

**在 `InstructionParser.__init__()` 中添加服务器检查**：
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
    self.vlm = get_vlm_instance()  # 这里会抛出 RuntimeError 如果服务器未运行
    # ...
```

### 5.4 测试文件修改

**所有测试文件（test_*.py）都需要添加**：
```python
import os
os.environ["VLM_SERVER_MANUAL"] = "true"  # 启用手动模式

def test_something():
    # 测试前检查服务器
    from src.vlm_server import get_vlm_server_manager
    if not get_vlm_server_manager().is_server_running():
        pytest.skip("vLLM 服务器未运行，请先运行: python start_vlm_server.py")
    # ... 测试代码
```

---

## 6. 代码修改清单

### 6.1 新增文件

- [ ] `start_vlm_server.py` - 主启动脚本
- [ ] `stop_vlm_server.py` - 停止脚本
- [ ] `status_vlm_server.py` - 状态查询脚本
- [ ] `.vlm_server.pid` - PID 文件（运行时生成）
- [ ] `.env.example` - 更新配置示例

### 6.2 修改文件

**src/vlm_server.py**
- [ ] 移除 `atexit.register(self.stop_all)`（阶段 3）
- [ ] 新增 `save_pid_file()` 方法
- [ ] 新增 `load_pid_file()` 方法
- [ ] 新增 `is_server_running()` 方法

**src/vlm.py**
- [ ] 修改 `Qwen2VLM.__init__()`: 添加手动模式支持
- [ ] 修改 `Qwen35VLM.__init__()`: 添加手动模式支持
- [ ] 添加环境变量检查逻辑

**main_interaction.py**
- [ ] 在 `InstructionParser.__init__()` 中添加服务器检查

**main_rag.py**
- [ ] 添加服务器运行检查（如果使用 VLM）

**test_*.py 文件**
- [ ] 添加 pytest skip 装饰器或前置检查
- [ ] 更新测试文档

### 6.3 文档更新

- [ ] `README.md`：添加服务器管理说明
- [ ] `CLAUDE.md`：更新项目架构说明
- [ ] 新增 `docs/vlm-server-management.md`：详细使用指南

---

## 7. 错误场景处理

```python
# 旧代码（移除）
if not self.server_manager.health_check('qwen2'):
    self.server_manager.start_server('qwen2')

# 新代码
if not self.server_manager.health_check('qwen2'):
    raise RuntimeError(
        "vLLM 服务器未运行！\n"
        "请先启动服务器: python start_vlm_server.py\n"
        "或查看状态: python status_vlm_server.py"
    )
```

---

## 5. 错误场景处理

| 场景 | 处理方式 | 用户提示 |
|------|----------|----------|
| 端口被占用 | 停止启动流程 | "端口 8001 已被占用，请运行 `python stop_vlm_server.py`" |
| 配置错误 | 停止启动流程 | 显示具体配置项问题，提示修改 .env |
| 启动超时 | 停止并清理进程 | 显示诊断建议（GPU 状态、日志、增加超时时间） |
| PID 文件损坏 | 显示警告，继续启动 | "警告：PID 文件损坏，已忽略" |
| 僵尸进程 | 自动检测并清理 | "检测到僵尸进程，已清理" |
| 服务器崩溃 | status 检测进程不存在 | "服务器已崩溃，已清理 PID 文件" |
| 业务程序连接失败 | 抛出 RuntimeError，友好提示 | 显示启动命令和状态查询命令 |
| 测试时服务器未启动 | pytest skip | 跳过测试，提示启动服务器 |
| 误操作停止服务器 | 检测活跃连接并询问 | "检测到活跃连接，是否继续停止？(y/N): " |

---

## 8. 编码规范约束

**重要**：实现时必须遵守以下规则：

### 6.1 避免过度设计

- **严禁**设计多级嵌套的 Fallback 机制
- **优先**确保核心机制的完整实现
- **若**因技术限制无法实现，应立即停止并向用户提出具体问题

**示例**（不要这样做）:
```python
# ❌ 错误：多级 fallback
try:
    start_server()
except Exception as e:
    try:
        fallback_method_1()
    except Exception:
        try:
            fallback_method_2()
        except Exception:
            # ...
```

**正确做法**:
```python
# ✅ 正确：直接失败并给出明确错误信息
if not server_manager.health_check():
    raise RuntimeError("vLLM 服务器未运行！\n请先启动服务器: python start_vlm_server.py")
```

### 6.2 必须实际测试

- **严禁**提交未经实际运行验证的"理论可行"代码
- **必须**在当前环境中运行并测试所有代码
- **若**测试失败或环境受限，必须在提交前告知具体原因

### 6.3 导入规范

- **所有** import 语句必须统一置于源文件顶端
- **严禁**在函数内部或逻辑代码中间进行延迟导入

**示例**:
```python
# ✅ 正确
import subprocess
import json
from typing import Optional

def some_function():
    # 函数逻辑

# ❌ 错误
def some_function():
    import subprocess  # 延迟导入
```

---

## 9. 使用流程

### 7.1 开发测试流程

```bash
# 终端 1：启动 vLLM 服务器（一次性）
python start_vlm_server.py

# 终端 2：运行业务程序（可多次执行，无需等待服务器启动）
python main_interaction.py
python main_interaction.py
python main_interaction.py

# 终端 1：停止服务器
# 按 Ctrl+C 或运行
python stop_vlm_server.py
```

### 7.2 典型工作流

1. **启动开发环境**:
   ```bash
   python start_vlm_server.py   # 终端 1
   ```

2. **开发测试循环**:
   ```bash
   # 修改代码后，直接运行
   python main_interaction.py   # 终端 2

   # 再次运行，无需等待
   python main_interaction.py

   # 查看服务器状态
   python status_vlm_server.py
   ```

3. **结束开发**:
   ```bash
   python stop_vlm_server.py    # 清理服务器
   ```

---

## 10. 测试计划

### 8.1 单元测试

- ✅ PID 文件读写测试
- ✅ 端口占用检测测试
- ✅ 健康检查测试
- ✅ 进程启动/停止测试

### 8.2 集成测试

- ✅ 完整启动流程测试
- ✅ 业务程序连接测试
- ✅ Ctrl+C 优雅停止测试
- ✅ 僵尸进程清理测试

### 8.3 边界测试

- ✅ 端口被占用场景
- ✅ PID 文件损坏场景
- ✅ 配置错误场景
- ✅ 服务器崩溃场景

---

## 11. 实现检查清单

### 9.1 start_vlm_server.py

- [ ] 读取 .env 配置
- [ ] 检查端口占用
- [ ] 检查现有 PID 文件
- [ ] 启动 vLLM 服务器进程
- [ ] 健康检查（最多 180 秒）
- [ ] 保存 PID 文件
- [ ] 实时显示日志
- [ ] Ctrl+C 捕获并优雅停止
- [ ] 错误处理和友好提示

### 9.2 stop_vlm_server.py

- [ ] 读取 PID 文件
- [ ] 验证进程存在
- [ ] 发送 SIGTERM
- [ ] 等待退出（10 秒超时）
- [ ] 超时则 SIGKILL
- [ ] 清理 PID 文件
- [ ] 友好提示

### 9.3 status_vlm_server.py

- [ ] 读取 PID 文件
- [ ] 检查进程存在
- [ ] HTTP 健康检查
- [ ] 格式化显示状态
- [ ] 错误处理

### 9.4 src/vlm_server.py

- [ ] 移除 `atexit.register(self.stop_all)`
- [ ] 新增 `save_pid_file()` 方法
- [ ] 新增 `load_pid_file()` 方法
- [ ] 保持现有功能不变

### 9.5 src/vlm.py

- [ ] 修改 `Qwen2VLM.__init__()`: 移除自动启动
- [ ] 修改 `Qwen35VLM.__init__()`: 移除自动启动
- [ ] 添加服务器运行检查
- [ ] 抛出友好异常

---

## 12. 迁移检查清单

### 12.1 阶段 1：添加新功能（不破坏现有代码）

**目标**：添加服务器管理功能，保持向后兼容

- [ ] 创建 `start_vlm_server.py`
- [ ] 创建 `stop_vlm_server.py`
- [ ] 创建 `status_vlm_server.py`
- [ ] 修改 `src/vlm_server.py`：
  - [ ] 新增 `save_pid_file()` 方法
  - [ ] 新增 `load_pid_file()` 方法
  - [ ] 新增 `is_server_running()` 方法
  - [ ] **暂时保留** `atexit.register(self.stop_all)`
- [ ] 修改 `src/vlm.py`：
  - [ ] 添加环境变量 `VLM_SERVER_MANUAL` 检查
  - [ ] **暂时保留**自动启动逻辑（当 `VLM_SERVER_MANUAL=false` 时）
- [ ] 测试：确保现有代码仍然工作

### 12.2 阶段 2：修改业务代码

**目标**：修改所有使用 VLM 的入口点

- [ ] 修改 `main_interaction.py`：
  - [ ] 添加服务器运行检查
  - [ ] 提供友好的错误提示
- [ ] 修改 `main_rag.py`（如果使用 VLM）
- [ ] 修改所有 `test_*.py` 文件：
  - [ ] 添加 pytest skip 装饰器
  - [ ] 更新测试文档
- [ ] 更新 `README.md`：
  - [ ] 添加服务器管理章节
  - [ ] 添加使用流程示例
- [ ] 测试：确保手动模式正常工作

### 12.3 阶段 3：清理遗留代码

**目标**：移除自动启动逻辑，完全切换到手动模式

- [ ] 修改 `src/vlm_server.py`：
  - [ ] **移除** `atexit.register(self.stop_all)`
- [ ] 修改 `src/vlm.py`：
  - [ ] **移除**自动启动逻辑
  - [ ] **移除**环境变量检查（默认手动模式）
- [ ] 更新 `.env.example`：
  - [ ] 移除 `VLM_SERVER_MANUAL` 配置
- [ ] 最终测试：
  - [ ] 完整启动流程测试
  - [ ] 多程序共享服务器测试
  - [ ] 所有测试用例通过

---

## 13. 验收标准

- [x] 设计文档完成（包含迁移计划）
- [ ] 阶段 1 完成：新功能添加，向后兼容
- [ ] 阶段 2 完成：业务代码修改
- [ ] 阶段 3 完成：遗留代码清理
- [ ] 所有代码实现完成
- [ ] 在当前环境中测试通过
- [ ] 所有测试场景验证通过
- [ ] 代码符合编码规范约束
- [ ] 文档更新（README.md, CLAUDE.md）
- [ ] Git 提交并推送到仓库

---

## 附录 A：风险评估

### A.1 技术风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| PID 文件竞态条件 | 中 | 中 | 使用文件锁，添加进程验证 |
| 僵尸进程 | 低 | 中 | 自动检测并清理，提供手动停止命令 |
| 健康检查超时 | 低 | 低 | 增加重试次数，优化超时时间 |
| 多进程并发访问 | 中 | 低 | HTTP 无状态，无并发问题 |

### A.2 迁移风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 破坏现有测试 | 高 | 高 | 分阶段迁移，添加 pytest skip |
| 用户不适应 | 中 | 中 | 详细文档，友好的错误提示 |
| CI/CD 失败 | 中 | 高 | 在 CI 中自动启动服务器 |

### A.3 运维风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 忘记启动服务器 | 高 | 低 | 友好的错误提示，快速失败 |
| 服务器崩溃 | 低 | 中 | 自动检测崩溃，清理 PID 文件 |
| 端口冲突 | 中 | 低 | 端口检测，提供停止命令 |

---

## 附录 B：回滚计划

如果迁移过程中遇到严重问题，可以回滚到旧版本：

```bash
# 回滚步骤
git revert <commit-hash>  # 回滚迁移的提交
git push

# 清理遗留文件
rm -f start_vlm_server.py stop_vlm_server.py status_vlm_server.py
rm -f .vlm_server.pid
```

回滚后恢复：
- 自动启动模式工作正常
- 所有测试用例通过
- 用户体验与之前一致

---

## 附录 C：参考资源

- [vLLM Offline Inference 文档](https://docs.vllm.ai/en/v0.13.0/serving/offline_inference/)
- [Python subprocess.Popen 文档](https://docs.python.org/3/library/subprocess.html)
- 项目现有代码：`src/vlm_server.py`, `src/vlm.py`
