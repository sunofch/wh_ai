"""
多模态视觉语言模型模块 (适配 Qwen2-VL)
"""
import json
import re
from functools import lru_cache
from typing import Any, Dict, Optional, Union

import torch
from PIL import Image
import numpy as np
from qwen_vl_utils import process_vision_info
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

import json_repair

from src.config import config
from src.utils import get_device, image_to_base64

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
        device_str = config.vlm.device
        self.max_new_tokens = config.vlm.max_tokens

        self.device = get_device(device_str)

        # RAG 配置
        self._rag_enabled = config.rag.enabled
        self.rag_manager = None

        print(f"加载 Qwen2-VL 模型: {model_name} 在 {self.device} 上...")
        try:
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                model_name,
                torch_dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
                device_map=self.device,
                trust_remote_code=True
            )
            self.processor = AutoProcessor.from_pretrained(
                model_name,
                trust_remote_code=True,
                use_fast=True
            )
            self.model.eval()
        except Exception as e:
            raise RuntimeError(f"加载模型失败: {e}")

        # 初始化 RAG 检索器
        if HAS_RAG and initialize_rag_system:
            mode = 'graph' if config.rag.graph_enabled else 'traditional'
            self._rag_enabled = initialize_rag_system(mode=mode)
            if self._rag_enabled:
                from src.rag_manager import get_unified_rag_manager
                self.rag_manager = get_unified_rag_manager()

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

        # 1. 图像预处理
        image_input = None
        if image is not None:
            try:
                image_input = image_to_base64(image)
            except Exception as e:
                print(f"图片处理失败: {e}")
                image_input = None

        # 2. 构建消息
        messages = []
        if system_prompt:
             messages.append({"role": "system", "content": [{"type": "text", "text": system_prompt}]})
            
        user_content = []
        if image_input:
            user_content.append({"type": "image", "image": image_input})
        if text:
            user_content.append({"type": "text", "text": text})
        messages.append({"role": "user", "content": user_content})

        # 3. 预处理 inputs
        text_input = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        
        inputs = self.processor(
            text=[text_input],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.device)

        # 4. 推理
        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
            )
        
        # 5. 解码
        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        
        return output_text.strip()

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
        # === 核心修改点：System Prompt ===
        # 专注于"业务推理逻辑"
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
        Qwen2VLM: 带RAG配置的VLM实例，或None
    """
    try:
        # 先初始化RAG系统
        if enable_rag:
            from src.rag_manager import initialize_rag_system
            if not initialize_rag_system(mode=mode):
                return None

        # 获取VLM实例
        vlm = get_vlm_instance()

        # 更新RAG设置
        vlm._rag_enabled = enable_rag
        if enable_rag:
            from src.rag_manager import get_unified_rag_manager
            vlm.rag_manager = get_unified_rag_manager()

        return vlm
    except Exception as e:
        print(f"获取带RAG的VLM实例失败: {e}")
        return None