# vLLM重构设计文档

## 项目概述

将wh_graphrag_re项目中的Qwen2-VL和Qwen3.5-VLM模型完全迁移到vLLM架构，移除transformers直接推理依赖。

**设计日期**: 2026-03-26
**目标**: 纯vLLM实现，无降级逻辑
**约束**: 单GPU环境，优化推理速度

## 当前架构

```
main_interaction.py
  ↓
src/vlm.py (统一VLM入口)
  ↓
src/qwen2vlm.py / src/qwen35vlm.py (transformers直接加载)
  ↓
transformers.AutoModelForCausalLM
  ↓
GPU推理
```

## 目标架构

```
main_interaction.py
  ↓
src/vlm.py (统一VLM入口)
  ↓
src/qwen2vlm.py / src/qwen35vlm.py (OpenAI客户端)
  ↓
vLLM Server (localhost:8000/8001)
  ↓
GPU推理 (PagedAttention优化)
```

## 核心组件设计

### 1. VLM服务器管理器 (`src/vlm_server.py`)

```python
import subprocess
import time
import requests
from typing import Dict, Optional
from src.config import config

class VLLMServerManager:
    """vLLM服务器生命周期管理"""

    def __init__(self):
        self.servers: Dict[str, subprocess.Popen] = {}
        self.port_map = {
            'qwen2': config.vllm_server.base_port,
            'qwen35': config.vllm_server.base_port + 1
        }

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
        else:  # qwen35
            model_name = config.vlm35.model
            port = self.port_map['qwen35']

        # 构造vllm serve命令
        cmd = [
            'vllm', 'serve', model_name,
            '--host', config.vllm_server.host,
            '--port', str(port),
            '--tensor-parallel-size', str(config.vllm_server.tensor_parallel_size),
            '--gpu-memory-utilization', str(config.vllm_server.gpu_memory_utilization),
            '--limit-mm-per-prompt', str(config.vllm_server.limit_mm_per_prompt)
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

        # 等待服务器就绪
        max_wait = 60  # 最多等待60秒
        for i in range(max_wait):
            if self.health_check(model_type):
                print(f"vLLM服务器 {model_type} 启动成功")
                return True
            time.sleep(1)

        # 启动失败
        self.stop_server(model_type)
        raise RuntimeError(f"vLLM服务器 {model_type} 启动超时")

    def stop_server(self, model_type: str) -> bool:
        """停止服务器"""
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

    def health_check(self, model_type: str) -> bool:
        """检查服务器健康状态"""
        try:
            url = self.get_server_url(model_type)
            response = requests.get(f"{url}/health", timeout=2)
            return response.status_code == 200
        except:
            return False

    def get_server_url(self, model_type: str) -> str:
        """获取服务器URL"""
        port = self.port_map[model_type]
        return f"http://{config.vllm_server.host}:{port}"

    def stop_all(self):
        """停止所有服务器"""
        for model_type in list(self.servers.keys()):
            self.stop_server(model_type)


# 全局单例
_vlm_server_manager: Optional[VLLMServerManager] = None

def get_vlm_server_manager() -> VLLMServerManager:
    """获取VLM服务器管理器单例"""
    global _vlm_server_manager
    if _vlm_server_manager is None:
        _vlm_server_manager = VLLMServerManager()
    return _vlm_server_manager
```

### 2. 重构后的Qwen2VLM类 (`src/qwen2vlm.py`)

```python
"""
多模态视觉语言模型模块 (Qwen2-VL + vLLM)
"""
import json
import re
from functools import lru_cache
from typing import Any, Dict, Optional

from openai import OpenAI
from PIL import Image
import numpy as np

import json_repair

from src.config import config
from src.vlm_server import get_vlm_server_manager
from src.utils import image_to_base64

# 尝试导入 RAG 模块
try:
    from src.rag_manager import UnifiedRAGManager, initialize_rag_system
    HAS_RAG = True
except ImportError:
    HAS_RAG = False
    UnifiedRAGManager = None
    initialize_rag_system = None


class Qwen2VLM:
    def __init__(self):
        model_name = config.vlm.model
        self.max_new_tokens = config.vlm.max_tokens

        # RAG 配置
        self._rag_enabled = config.rag.enabled
        self.rag_manager = None

        # 获取vLLM服务器管理器并启动服务器
        self.server_manager = get_vlm_server_manager()

        if not self.server_manager.health_check('qwen2'):
            self.server_manager.start_server('qwen2')

        # 初始化OpenAI客户端
        server_url = self.server_manager.get_server_url('qwen2')
        self.client = OpenAI(
            api_key="EMPTY",
            base_url=f"{server_url}/v1",
            timeout=120.0  # vLLM推理可能需要更长时间
        )

        # 初始化 RAG 检索器
        if HAS_RAG and initialize_rag_system:
            mode = 'graph' if config.rag.graph_enabled else 'traditional'
            self._rag_enabled = initialize_rag_system(mode=mode)
            if self._rag_enabled:
                from src.rag_manager import get_unified_rag_manager
                self.rag_manager = get_unified_rag_manager()

        print(f"Qwen2-VL vLLM客户端初始化完成: {server_url}")

    def process(
        self,
        text: Optional[str] = None,
        image: Any = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """Qwen2-VL 推理入口

        Args:
            text: 输入文本
            image: 图片输入（支持文件路径、PIL Image、numpy 数组等）
            system_prompt: 系统提示词

        Returns:
            str: 模型生成的响应文本
        """
        if not text and not image:
            return ""

        # 构造OpenAI格式请求
        content = []

        # 添加图像
        if image is not None:
            try:
                image_base64 = image_to_base64(image)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                })
            except Exception as e:
                print(f"图片处理失败: {e}")

        # 添加文本
        if text:
            content.append({"type": "text", "text": text})

        # 构造messages
        messages = [{"role": "user", "content": content}]

        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        # 调用vLLM服务器
        try:
            response = self.client.chat.completions.create(
                model=config.vlm.model,
                messages=messages,
                max_tokens=self.max_new_tokens,
                temperature=0.0
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise RuntimeError(f"vLLM推理失败: {e}")

    def extract_structured_info(
        self,
        text: str,
        format_instructions: str = "",
        image: Any = None,
        enable_rag: Optional[bool] = None
    ) -> Dict[str, Any]:
        """从多模态输入中提取结构化信息

        Args:
            text: 输入文本
            format_instructions: 格式化指令（通常为 JSON Schema）
            image: 图片输入（可选）
            enable_rag: 是否启用RAG，None表示使用配置值

        Returns:
            Dict[str, Any]: 解析后的结构化数据，包含解析结果或原始响应
        """
        # 构造system prompt
        system_prompt = """
        你是一位专业的港口作业指令解析助手。
        你的任务是根据用户的语音文本和图片，提取结构化数据。
        请严格参考以下信息。
        tip:注意型号和英文缩写的区别！
        """

        # RAG 知识注入
        rag_enabled = enable_rag if enable_rag is not None else self._rag_enabled
        if rag_enabled and self.rag_manager and text:
            try:
                results = self.rag_manager.retrieve(text)
                if results:
                    rag_context = self.rag_manager.format_context(results)
                    system_prompt += f"\n\n{rag_context}\n"
            except Exception as e:
                print(f"RAG 检索失败: {e}")

        # 动态追加来自 Parser 的严格 Schema 指令
        if format_instructions:
            system_prompt += f"\n\n# 格式要求\n{format_instructions}"

        user_text = text if text else "无文本指令"

        response = self.process(
            text=user_text,
            image=image,
            system_prompt=system_prompt
        )

        # 使用 json_repair 进行鲁棒解析
        try:
            # 尝试正则聚焦 {...}，去除首尾废话
            match = re.search(r'\{.*\}', response, re.DOTALL)
            candidate_text = match.group() if match else response

            parsed_obj = json_repair.loads(candidate_text)

            # 返回字典类型结果
            if isinstance(parsed_obj, dict):
                return parsed_obj
            # 如果返回列表，取第一个元素
            if isinstance(parsed_obj, list) and parsed_obj and isinstance(parsed_obj[0], dict):
                return parsed_obj[0]

            return {"raw_response": response}

        except Exception as e:
            print(f"JSON解析失败: {e}")
            return {"raw_response": response}


@lru_cache(maxsize=1)
def get_vlm_instance() -> Qwen2VLM:
    """获取 VLM 单例实例

    Returns:
        Qwen2VLM: 单例 VLM 实例
    """
    return Qwen2VLM()


def get_vlm_with_rag(
    mode: str = 'traditional',
    enable_rag: bool = True
) -> Optional[Qwen2VLM]:
    """获取VLM实例并初始化指定模式的RAG

    Args:
        mode: RAG模式 ('traditional' | 'graph')
        enable_rag: 是否启用RAG

    Returns:
        Qwen2VLM: 带RAG配置的VLM实例
    """
    # 先初始化RAG系统
    if enable_rag:
        from src.rag_manager import initialize_rag_system
        if not initialize_rag_system(mode=mode):
            raise RuntimeError("RAG系统初始化失败")

    # 获取VLM实例
    vlm = get_vlm_instance()

    # 更新RAG设置
    vlm._rag_enabled = enable_rag
    if enable_rag:
        from src.rag_manager import get_unified_rag_manager
        vlm.rag_manager = get_unified_rag_manager()

    return vlm
```

### 3. 重构后的Qwen35VLM类 (`src/qwen35vlm.py`)

Qwen35VLM与Qwen2VLM结构完全一致，只需替换以下部分：

```python
class Qwen35VLM:
    def __init__(self):
        model_name = config.vlm35.model
        self.max_new_tokens = config.vlm35.max_tokens

        # ... 启动qwen35服务器而非qwen2 ...

        if not self.server_manager.health_check('qwen35'):
            self.server_manager.start_server('qwen35')

        server_url = self.server_manager.get_server_url('qwen35')
        # ... 其余逻辑相同 ...
```

### 4. 配置扩展 (`src/config.py`)

```python
class VLLMServerConfig(BaseAppConfig):
    """vLLM服务器配置"""
    enabled: bool = Field(default=True, alias="VLLM_SERVER_ENABLED")
    host: str = Field(default="localhost", alias="VLLM_SERVER_HOST")
    base_port: int = Field(default=8000, alias="VLLM_SERVER_BASE_PORT")
    tensor_parallel_size: int = Field(default=1, alias="VLLM_SERVER_TP_SIZE")
    gpu_memory_utilization: float = Field(default=0.9, alias="VLLM_SERVER_GPU_MEM_UTIL")
    max_model_len: Optional[int] = Field(default=None, alias="VLLM_SERVER_MAX_MODEL_LEN")
    limit_mm_per_prompt: str = Field(
        default='{"image": 4}',
        alias="VLLM_SERVER_LIMIT_MM_PER_PROMPT"
    )

    @field_validator('limit_mm_per_prompt', mode='before')
    @classmethod
    def parse_json(cls, v):
        if isinstance(v, str):
            return json.dumps(json.loads(v))
        return json.dumps(v)


class Config(BaseSettings):
    # ... 现有配置 ...
    vllm_server: VLLMServerConfig = VLLMServerConfig()
```

### 5. 环境变量配置 (`.env.example`)

```bash
# ====================
# vLLM服务器配置
# ====================
VLLM_SERVER_ENABLED=true
VLLM_SERVER_HOST=localhost
VLLM_SERVER_BASE_PORT=8000
VLLM_SERVER_TP_SIZE=1
VLLM_SERVER_GPU_MEM_UTIL=0.9
# VLLM_SERVER_MAX_MODEL_LEN=8192  # 可选
VLLM_SERVER_LIMIT_MM_PER_PROMPT={"image": 4}
```

### 6. 依赖更新 (`requirements.txt`)

```txt
# 核心依赖
transformers>=5.3.0
qwen-vl-utils>=0.0.14
langchain>=1.2.3
# ... 其他现有依赖 ...

# vLLM核心库
vllm>=0.6.1

# OpenAI API客户端 (用于vLLM通信)
openai>=1.0.0

# HTTP客户端
requests>=2.31.0
```

## 数据流详解

### 1. 初始化流程

```
应用启动
  ↓
首次调用 get_vlm_instance()
  ↓
Qwen2VLM.__init__()
  ↓
VLLMServerManager.start_server('qwen2')
  ↓
subprocess启动vllm serve进程
  ↓
health_check等待服务器就绪
  ↓
初始化OpenAI客户端
  ↓
准备就绪
```

### 2. 推理流程

```
用户输入: text + image
  ↓
VLM.process()
  ↓
image_to_base64()编码图像
  ↓
构造OpenAI格式messages
  ↓
client.chat.completions.create()
  ↓
HTTP POST → vLLM服务器
  ↓
vLLM: 多模态编码 + 推理
  ↓
HTTP ← 返回结果
  ↓
解析响应文本
  ↓
返回结果
```

## 错误处理

### 服务器启动失败

```python
# 直接抛出异常，让调用方处理
if not self.server_manager.health_check('qwen2'):
    self.server_manager.start_server('qwen2')  # 内部抛出RuntimeError
```

### 推理失败

```python
try:
    response = self.client.chat.completions.create(...)
except Exception as e:
    raise RuntimeError(f"vLLM推理失败: {e}")  # 直接抛出，不降级
```

### RAG检索失败

```python
try:
    results = self.rag_manager.retrieve(text)
except Exception as e:
    print(f"RAG 检索失败: {e}")  # 仅记录日志，继续推理
```

## 性能优化

### vLLM服务器参数调优

**单GPU配置**:
```bash
--tensor-parallel-size 1          # 单卡
--gpu-memory-utilization 0.9      # 90%显存
--max-model-len 8192              # 限制上下文长度
--limit-mm-per-prompt '{"image": 4}'  # 最多4张图
```

**性能优化技巧**:
1. 启用前缀缓存: `--enable-prefix-caching`
2. 调整并发数: `--max-num-seqs 16`
3. 使用FP16: `--dtype float16`

### 客户端优化

1. **连接复用**: OpenAI客户端保持长连接
2. **合理timeout**: 设置120秒避免过早超时
3. **批处理**: 利用vLLM的连续批处理能力

## 测试计划

### 单元测试

```python
# tests/test_vlm_server.py
def test_server_start():
    manager = VLLMServerManager()
    manager.start_server('qwen2')
    assert manager.health_check('qwen2')

def test_server_stop():
    manager = VLLMServerManager()
    manager.start_server('qwen2')
    manager.stop_server('qwen2')
    assert not manager.health_check('qwen2')

# tests/test_qwen2vlm.py
def test_text_only():
    vlm = Qwen2VLM()
    result = vlm.process(text="你好")
    assert result

def test_with_image():
    vlm = Qwen2VLM()
    result = vlm.process(text="这是什么", image="test.jpg")
    assert result

def test_extract_structured():
    vlm = Qwen2VLM()
    result = vlm.extract_structured_info(text="需要5个电机")
    assert "part_name" in result or "raw_response" in result
```

### 集成测试

```python
# tests/test_integration.py
def test_full_pipeline():
    """测试完整流程"""
    vlm = get_vlm_instance()
    result = vlm.extract_structured_info(
        text="需要5个电机，紧急",
        format_instructions='{"part_name": "string", "quantity": "int"}'
    )
    assert isinstance(result, dict)
```

### 性能测试

```python
# tests/benchmark.py
import time

def benchmark_inference_speed():
    """基准测试：推理速度"""
    vlm = Qwen2VLM()

    start = time.time()
    for i in range(10):
        vlm.process(text="测试文本")
    end = time.time()

    avg_time = (end - start) / 10
    print(f"平均推理时间: {avg_time:.2f}s")

def benchmark_throughput():
    """基准测试：吞吐量"""
    # 使用vLLM的批处理能力
    pass
```

## 部署流程

### 1. 环境准备

```bash
# 安装vLLM
pip install vllm>=0.6.1

# 安装OpenAI客户端
pip install openai>=1.0.0

# 安装HTTP库
pip install requests>=2.31.0
```

### 2. 配置更新

```bash
# 复制配置模板
cp .env.example .env

# 编辑配置
nano .env
```

关键配置:
```bash
VLLM_SERVER_ENABLED=true
VLLM_SERVER_HOST=localhost
VLLM_SERVER_BASE_PORT=8000
```

### 3. 启动应用

```bash
python main_interaction.py
```

首次启动会自动下载vLLM和模型，等待时间较长。

### 4. 验证

```bash
# 检查vLLM服务器是否运行
curl http://localhost:8000/health

# 测试推理
python -c "from src.qwen2vlm import get_vlm_instance; vlm = get_vlm_instance(); print(vlm.process('你好'))"
```

## 性能预期

基于vLLM官方基准（Qwen2-VL-2B）：

| 指标 | 值 |
|------|-----|
| 首token延迟 (TTFT) | ~800ms |
| 生成速度 | ~40 tok/s |
| GPU利用率 | ~90% |
| 显存占用 (2B模型) | ~5GB |

## 故障排查

### 问题1: vLLM服务器启动失败

**症状**: `RuntimeError: vLLM服务器启动超时`

**排查**:
1. 检查CUDA是否可用: `python -c "import torch; print(torch.cuda.is_available())"`
2. 检查端口占用: `netstat -an | grep 8000`
3. 查看vLLM日志（如果单独启动）

**解决**:
- 修改 `VLLM_SERVER_BASE_PORT`
- 检查GPU驱动

### 问题2: 推理速度慢

**症状**: 单次推理 > 10秒

**排查**:
1. 检查GPU利用率: `nvidia-smi`
2. 查看vLLM服务器日志

**解决**:
- 降低 `--max-model-len`
- 提高 `--gpu-memory-utilization` 到0.95

### 问题3: 内存溢出

**症状**: CUDA out of memory

**解决**:
```bash
# 在.env中设置
VLLM_SERVER_MAX_MODEL_LEN=4096
VLLM_SERVER_LIMIT_MM_PER_PROMPT={"image": 2}
```

## 迁移路径

### 阶段1: 基础设施 (Day 1)

- [ ] 创建 `src/vlm_server.py`
- [ ] 扩展 `src/config.py`
- [ ] 更新 `.env.example`
- [ ] 更新 `requirements.txt`

### 阶段2: VLM重构 (Day 2-3)

- [ ] 重构 `src/qwen2vlm.py`
- [ ] 重构 `src/qwen35vlm.py`
- [ ] 测试基本功能

### 阶段3: 集成测试 (Day 4)

- [ ] 测试完整流程
- [ ] 性能基准测试
- [ ] 更新文档

## 参考资料

- vLLM文档: https://docs.vllm.ai/
- Qwen2-VL: https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen2.5-VL.html
- 多模态支持: https://docs.vllm.ai/en/stable/models/vlm.html

---

**文档版本**: 2.0 (纯vLLM实现)
**最后更新**: 2026-03-26
