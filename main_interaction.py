"""
主指令解析模块：All-in-VLM 架构
"""
import logging
import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Union, Optional, Any, Callable
import numpy as np


# 尝试导入录音相关库
try:
    import sounddevice as sd
    import soundfile as sf
    HAS_RECORDING_LIB = True
except ImportError:
    HAS_RECORDING_LIB = False

from src.asr import get_asr_instance
from src.vlm import get_vlm_instance
from src.parser import PortInstructionParser, PortInstruction
from src.config import config

# 尝试导入 RAG 模块
try:
    from src.rag_manager import UnifiedRAGManager, initialize_rag_system
    HAS_RAG = True
except ImportError:
    HAS_RAG = False
    UnifiedRAGManager = None
    initialize_rag_system = None

# 常量定义
DEFAULT_SAMPLE_RATE = 16000  # 默认采样率
DEFAULT_RECORD_DURATION = 5  # 默认录音时长（秒）

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

class InstructionParser:
    def __init__(self):
        self.asr = get_asr_instance()
        self.vlm = get_vlm_instance()
        self.parser = PortInstructionParser()

        # RAG 状态管理
        self.rag_enabled = config.rag.enabled
        self.rag_manager = None

        if HAS_RAG and initialize_rag_system:
            mode = 'graph' if config.rag.graph_enabled else 'traditional'
            self.rag_enabled = initialize_rag_system(mode=mode)
            if self.rag_enabled:
                from src.rag_manager import get_unified_rag_manager
                self.rag_manager = get_unified_rag_manager()

        logger.info(">>> 系统初始化完成 (模型已加载到显存)")

    def set_rag_enabled(self, enabled: bool):
        """动态启用/禁用 RAG"""
        if not HAS_RAG or not self.rag_manager:
            logger.warning("RAG 模块不可用")
            return

        self.rag_enabled = enabled
        if self.rag_manager:
            self.rag_manager.set_enabled(enabled)
        self.vlm._rag_enabled = enabled  # 同时更新 VLM 的 RAG 状态
        status = "启用" if enabled else "禁用"
        logger.info(f">>> RAG 已{status}")

    def get_rag_status(self) -> dict:
        """获取 RAG 状态"""
        if not HAS_RAG or not self.rag_manager:
            return {
                "available": False,
                "enabled": self.rag_enabled
            }

        status = self.rag_manager.get_status()
        status["enabled"] = self.rag_enabled
        return status
    
    def parse(
        self,
        audio: Optional[Union[str, bytes, np.ndarray]] = None,
        text: Optional[str] = None,
        image: Optional[Any] = None
    ) -> PortInstruction:
        context_text = ""

        # 1. 语音处理
        if audio is not None:
            t_asr_start = time.time()
            try:
                # transcribe 支持路径和 numpy 数组，transcribe_bytes 处理字节数据
                if isinstance(audio, bytes):
                    transcribed = self.asr.transcribe_bytes(audio)
                else:
                    transcribed = self.asr.transcribe(audio)

                t_asr_end = time.time()
                print(f"   >> [性能] ASR 语音识别耗时: {t_asr_end - t_asr_start:.4f} 秒")

                logger.info(f"语音转录内容: {transcribed}")
                context_text += transcribed + " "
            except Exception as e:
                logger.error(f"ASR失败: {e}")

        # 2. 文本拼接
        if text:
            context_text += text

        context_text = context_text.strip()

        if not context_text and image is None:
            return PortInstruction(description="无有效输入", confidence=0.0)

        # 3. VLM 推理
        if image:
            logger.info(f"正在分析图片与指令... (文本: {context_text or '无'})")
        else:
            logger.info(f"正在分析指令... (文本: {context_text})")

        try:
            t_vlm_start = time.time()

            format_instructions = self.parser.get_format_instructions()
            vlm_result = self.vlm.extract_structured_info(
                text=context_text,
                image=image,
                format_instructions=format_instructions
            )

            t_vlm_end = time.time()
            print(f"   >> [性能] VLM 视觉推理耗时: {t_vlm_end - t_vlm_start:.4f} 秒")

            instruction = self.parser.parse_output(vlm_result, raw_text=context_text)
            return instruction

        except Exception as e:
            logger.error(f"解析异常: {e}")
            return self.parser._rule_based_parse(context_text)

def create_parser() -> InstructionParser:
    """创建并初始化指令解析器实例

    Returns:
        InstructionParser: 初始化完成的解析器实例
    """
    return InstructionParser()

def record_audio_clip(duration=DEFAULT_RECORD_DURATION, fs=DEFAULT_SAMPLE_RATE) -> Optional[np.ndarray]:
    """
    录制音频片段 (直接返回内存数据)

    Args:
        duration: 录音时长（秒）
        fs: 采样率

    Returns:
        Numpy数组 (float32)，失败返回 None
    """
    logger.info(f"正在录音 ({duration}秒)...")
    try:
        myrecording = sd.rec(int(duration * fs), samplerate=fs, channels=1)
        for i in range(duration):
            time.sleep(1)
            logger.debug(f"剩余 {duration-i-1} 秒...")
        sd.wait()
        logger.info("录音结束，正在处理...")

        return myrecording.flatten().astype(np.float32)
    except Exception as e:
        logger.error(f"录音失败: {e}")
        return None

def interactive_mode() -> None:
    """增强版交互模式 V2

    提供命令行交互界面，支持文本、图片、音频输入和 RAG 管理
    """
    print("="*60)
    print("港口指令解析系统 - 全能交互模式")
    print("支持操作：")
    print("   1. 输入文本指令 (如：需要5个电机)")
    print("   2. 输入文件路径 (直接将 图片/音频 文件拖入窗口)")
    print("   3. 输入 'r' 开始实时录音 (默认5秒)")
    print("   4. 输入 'q' 退出")
    if HAS_RAG:
        print("\nRAG 管理命令：")
        print("   - rag:status  查看 RAG 状态")
        print("   - rag:enable  启用 RAG")
        print("   - rag:disable 禁用 RAG")
        print("   - rag:rebuild 重建知识库索引")
    print("="*60)

    print("正在初始化模型...")
    parser = create_parser()

    while True:
        try:
            user_input = input("\n[输入] > ").strip()

            if user_input.lower() in ['q', 'exit', 'quit']:
                logger.info("再见！")
                break

            if not user_input:
                continue

            # RAG 管理命令 - 使用调度模式
            if HAS_RAG and user_input.lower() in RAG_COMMAND_HANDLERS:
                RAG_COMMAND_HANDLERS[user_input.lower()](parser)
                continue

            # 功能 1: 主菜单录音
            if user_input.lower() == 'r':
                if not HAS_RECORDING_LIB:
                    logger.error("未安装录音库 (pip install sounddevice)")
                    continue
                audio_data = record_audio_clip(duration=DEFAULT_RECORD_DURATION)
                if audio_data is not None:
                    res = parser.parse(audio=audio_data)
                    print_result(res)
                continue

            # 功能 2: 智能路径识别
            clean_path = user_input.strip('"').strip("'")

            if os.path.exists(clean_path) and os.path.isfile(clean_path):
                ext = os.path.splitext(clean_path)[1].lower()

                # 图片处理流程
                if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp']:
                    logger.info(f"检测到图片: {clean_path}")

                    prompt_hint = "   (可选) 请输入文本 或 输入 'r' 录音描述 [回车跳过]: "
                    extra_input = input(prompt_hint).strip()

                    extra_text = ""
                    temp_audio_data = None

                    if extra_input.lower() == 'r':
                        if HAS_RECORDING_LIB:
                            temp_audio_data = record_audio_clip(duration=DEFAULT_RECORD_DURATION)
                        else:
                            logger.warning("录音库未安装，跳过语音")
                    else:
                        extra_text = extra_input

                    res = parser.parse(image=clean_path, text=extra_text, audio=temp_audio_data)
                    print_result(res)

                # 音频处理流程 (本地文件)
                elif ext in ['.wav', '.mp3', '.m4a', '.flac', '.ogg']:
                    logger.info(f"检测到音频: {clean_path}")
                    res = parser.parse(audio=clean_path)
                    print_result(res)

                else:
                    logger.warning(f"无法识别格式，作为纯文本处理")
                    res = parser.parse(text=user_input)
                    print_result(res)

            # 功能 3: 纯文本
            else:
                res = parser.parse(text=user_input)
                print_result(res)

        except KeyboardInterrupt:
            logger.info("\n再见！")
            break
        except Exception as e:
            # 打印完整的错误栈以便调试
            traceback.print_exc()
            logger.error(f"发生错误: {e}")

def print_result(result: PortInstruction) -> None:
    """美化输出结果

    Args:
        result: 解析后的指令结果
    """
    print("-" * 40)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    print("-" * 40)


def handle_rag_status(parser: InstructionParser) -> None:
    """处理 RAG 状态查询命令"""
    status = parser.get_rag_status()
    print("\n" + "=" * 40)
    print("RAG 状态信息")
    print("=" * 40)
    print(f"系统: {'启用' if status.get('enabled', False) else '禁用'}")
    print(f"可用性: {'可用' if status.get('available', False) else '不可用'}")
    print(f"当前模式: {status.get('mode', 'N/A')}")

    if status.get('available'):
        rag_type = status.get('type', 'N/A')
        print(f"RAG类型: {rag_type}")

        if rag_type == 'graph':
            # GraphRAG 特定信息
            graph_stats = status.get('graph_stats', {})
            if graph_stats:
                print(f"图谱节点数: {graph_stats.get('node_count', 0)}")
                print(f"图谱关系数: {graph_stats.get('relation_count', 0)}")
            print(f"提取器类型: {status.get('extractor_type', 'N/A')}")
            print(f"最大三元组数: {status.get('max_triplets_per_chunk', 'N/A')}")
        else:
            # 传统RAG特定信息
            print(f"嵌入模型: {status.get('embedding_model', 'N/A')}")
            print(f"设备: {status.get('device', 'N/A')}")
            print(f"检索模式: {status.get('retrieval_mode', 'N/A')}")
            print(f"Top-K: {status.get('top_k', 'N/A')}")
            print(f"知识库路径: {status.get('knowledge_base_path', 'N/A')}")
            print(f"向量库路径: {status.get('vector_db_path', 'N/A')}")

    if status.get('last_error'):
        print(f"错误信息: {status['last_error']}")

    print("=" * 40)


def handle_rag_enable(parser: InstructionParser, enabled: bool) -> None:
    """处理 RAG 启用/禁用命令"""
    parser.set_rag_enabled(enabled)


def handle_rag_rebuild(parser: InstructionParser) -> None:
    """处理 RAG 索引重建命令"""
    if not parser.rag_manager:
        logger.warning("RAG 模块未初始化")
        return
    logger.info("正在重建知识库索引...")
    if parser.rag_manager.rebuild_index():
        logger.info(">>> 索引重建完成")
    else:
        logger.error(">>> 索引重建失败")

def handle_graph_stats(parser: InstructionParser) -> None:
    """处理GraphRAG统计命令"""
    if not HAS_RAG or not parser.rag_manager:
        print("\nGraphRAG不可用")
        return

    status = parser.get_rag_status()
    if status.get('mode') != 'graph':
        print("\n当前不是GraphRAG模式")
        return

    print("\n" + "=" * 40)
    print("GraphRAG 统计信息")
    print("=" * 40)

    if status.get('graph_stats'):
        stats = status['graph_stats']
        print(f"图谱节点数: {stats.get('node_count', 0)}")
        print(f"图谱关系数: {stats.get('relation_count', 0)}")
        if stats.get('build_time'):
            print(f"构建时间: {stats['build_time']}")

        # 显示提取器信息
        print(f"\n提取器配置:")
        print(f"类型: {status.get('extractor_type', 'N/A')}")
        print(f"最大三元组/块: {status.get('max_triplets_per_chunk', 'N/A')}")
        print(f"实体类型: {status.get('entity_hints', 'N/A')}")
    else:
        print("暂无统计数据")

    print("=" * 40)
    
# RAG 命令处理调度表
RAG_COMMAND_HANDLERS: dict[str, Callable[[InstructionParser], None]] = {
    "rag:status": handle_rag_status,
    "rag:enable": lambda p: handle_rag_enable(p, True),
    "rag:disable": lambda p: handle_rag_enable(p, False),
    "rag:rebuild": handle_rag_rebuild,
    "rag:graph": handle_graph_stats,  # 新增GraphRAG统计命令
}



if __name__ == "__main__":
    parser_arg = argparse.ArgumentParser()
    parser_arg.add_argument("--text", type=str, help="单次测试：文本指令")
    parser_arg.add_argument("--image", type=str, help="单次测试：图片路径")
    parser_arg.add_argument("--audio", type=str, help="单次测试：音频路径")
    
    args = parser_arg.parse_args()
    
    if args.text or args.image or args.audio:
        parser = create_parser()
        res = parser.parse(text=args.text, image=args.image, audio=args.audio)
        # 单次运行也建议用 print_result 保持一致，但这里保持原样输出 JSON
        print(res.to_json())
    else:
        interactive_mode()