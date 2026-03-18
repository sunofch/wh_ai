"""
GraphRAG 核心模块：基于 PropertyGraphIndex 的知识图谱检索

根据 LlamaIndex 官方文档重构：
- 使用 PropertyGraphIndex.from_documents() 构建图
- 使用 index.storage_context.persist() 保存索引
- 使用 load_index_from_storage() 加载索引
- 支持多种提取器和检索器

参考文档：
https://docs.llamaindex.org.cn/en/stable/module_guides/indexing/lpg_index_guide/
"""
import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Any

from llama_index.core import (
    PropertyGraphIndex,
    Document,
    Settings,
    StorageContext,
    load_index_from_storage,
)
from llama_index.core.graph_stores import SimplePropertyGraphStore
from llama_index.core.indices.property_graph import (
    PGRetriever,
    VectorContextRetriever,
    LLMSynonymRetriever,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.llms.deepseek import DeepSeek

from src.config import config
from src.utils import get_device
from src.graph_extractors import create_kg_extractors

logger = logging.getLogger(__name__)


@dataclass
class GraphRAGConfig:
    """GraphRAG 配置管理 - 简化版，使用全局 config 对象"""

    # 基础配置
    graph_enabled: bool
    graph_db_path: Path
    knowledge_base_path: Path

    # 图谱构建配置
    extractor_type: str = "dynamic"
    max_triplets_per_chunk: int = 15
    num_workers: int = 4

    # 实体和关系提示
    entity_hints: List[str] = field(default_factory=list)
    relation_hints: List[str] = field(default_factory=list)

    # LLM 配置
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    deepseek_temperature: float = 0.7

    # 图检索配置
    sub_retrievers: List[str] = field(default_factory=lambda: ["vector", "synonym"])
    vector_top_k: int = 5
    vector_path_depth: int = 1
    synonym_max_keywords: int = 8
    synonym_path_depth: int = 1

    # 性能优化配置
    query_cache_ttl: int = 3600
    cache_max_size: int = 100

    # RAG 基础配置
    embedding_model: str = "BAAI/bge-m3"
    device: str = "auto"
    top_k: int = 3

    @classmethod
    def from_config(cls) -> "GraphRAGConfig":
        """从全局 config 对象加载配置"""
        return cls(
            graph_enabled=config.rag.graph_enabled,
            graph_db_path=config.paths.graph_db,
            knowledge_base_path=config.paths.knowledge_base,
            extractor_type=config.graph_rag.extractor_type,
            max_triplets_per_chunk=config.graph_rag.max_triplets_per_chunk,
            num_workers=config.graph_rag.num_workers,
            entity_hints=config.graph_rag.entity_hints,
            relation_hints=config.graph_rag.relation_hints,
            llm_provider=config.graph_rag.llm_provider,
            deepseek_api_key=config.graph_rag.deepseek_api_key,
            deepseek_base_url=config.graph_rag.deepseek_base_url,
            deepseek_model=config.graph_rag.deepseek_model,
            deepseek_temperature=config.graph_rag.deepseek_temperature,
            sub_retrievers=config.graph_retrieval.sub_retrievers,
            vector_top_k=config.graph_retrieval.vector_top_k,
            vector_path_depth=config.graph_retrieval.vector_path_depth,
            synonym_max_keywords=config.graph_retrieval.synonym_max_keywords,
            synonym_path_depth=config.graph_retrieval.synonym_path_depth,
            query_cache_ttl=config.graph_performance.query_cache_ttl,
            cache_max_size=config.graph_performance.cache_max_size,
            embedding_model=config.rag.embedding_model,
            device=config.rag.device,
            top_k=config.rag.top_k,
        )


def initialize_llm(config: GraphRAGConfig) -> Optional[Any]:
    """根据配置初始化 LLM

    Args:
        config: GraphRAG 配置对象

    Returns:
        配置好的 LLM 实例，如果配置无效则返回 None
    """
    llm = None

    if config.llm_provider == "deepseek":
        if not config.deepseek_api_key:
            logger.warning("DeepSeek API key 未配置，将使用隐式提取器")
            return None

        try:
            llm = DeepSeek(
                model=config.deepseek_model,
                api_key=config.deepseek_api_key,
                temperature=config.deepseek_temperature,
            )
            logger.info(f"DeepSeek LLM 初始化成功: {config.deepseek_model}")
        except Exception as e:
            logger.error(f"DeepSeek LLM 初始化失败: {e}")
            return None

    elif config.llm_provider == "openai":
        api_key = config.graph_rag.openai_api_key
        model = config.graph_rag.openai_model
        base_url = config.graph_rag.openai_base_url

        if not api_key:
            logger.warning("OpenAI API key 未配置")
            return None

        try:
            llm = OpenAI(
                api_key=api_key,
                model=model,
                base_url=base_url,
                temperature=0.7,
            )
            logger.info(f"OpenAI LLM 初始化成功: {model}")
        except Exception as e:
            logger.error(f"OpenAI LLM 初始化失败: {e}")
            return None

    return llm


class GraphRAGRetriever:
    """GraphRAG 检索器

    基于 LlamaIndex PropertyGraphIndex 实现，支持多种检索器组合
    """

    def __init__(self, config: GraphRAGConfig):
        self.config = config
        self._initialized = False

        self.llm: Optional[Any] = None
        self.embed_model: Optional[Any] = None
        self.index: Optional[PropertyGraphIndex] = None
        self.graph_retriever: Optional[PGRetriever] = None
        self.query_cache: Dict[str, Dict[str, Any]] = {}

        if self.config.graph_enabled:
            self._initialize()

    def _initialize(self):
        """初始化 GraphRAG"""
        logger.info("正在初始化 GraphRAG 模块...")

        # 初始化嵌入模型
        device = get_device(self.config.device)
        self.embed_model = HuggingFaceEmbedding(
            model_name=self.config.embedding_model,
            device=device,
            trust_remote_code=True
        )
        Settings.embed_model = self.embed_model

        # 初始化 LLM
        self.llm = initialize_llm(self.config)
        if self.llm:
            Settings.llm = self.llm
        else:
            Settings.llm = None
            logger.info("未配置 LLM，将仅使用隐式提取器")

        # 加载或创建图谱索引
        self.index = self._load_or_create_graph_index()

        # 初始化图检索器
        self._initialize_graph_retriever()

        self._initialized = True
        logger.info(">>> GraphRAG 模块初始化完成")

    def _load_or_create_graph_index(self) -> PropertyGraphIndex:
        """加载或创建图谱索引

        按照 LlamaIndex 官方文档推荐的方式：
        1. 尝试从存储中加载已有索引
        2. 如果不存在，从文档构建新索引
        """
        storage_dir = self.config.graph_db_path / "storage"

        if storage_dir.exists():
            try:
                logger.info(f"从存储中加载图谱索引: {storage_dir}")
                storage_context = StorageContext.from_defaults(persist_dir=str(storage_dir))
                index = load_index_from_storage(storage_context)
                return index
            except Exception as e:
                logger.warning(f"加载图谱存储失败: {e}，重新构建")

        return self._build_graph_index()

    def _build_graph_index(self) -> PropertyGraphIndex:
        """从文档构建图谱索引

        使用 PropertyGraphIndex.from_documents() 构建图
        """
        logger.info(f"正在从知识库构建图谱: {self.config.knowledge_base_path}")

        documents = self._load_documents()
        if not documents:
            logger.warning("未找到任何知识库文档")
            return PropertyGraphIndex.from_documents([])

        logger.info(f"加载了 {len(documents)} 个文档")

        # 创建提取器
        kg_extractors = create_kg_extractors(self.config, self.llm)

        # 构建图谱索引
        start_time = time.time()
        index = PropertyGraphIndex.from_documents(
            documents,
            kg_extractors=kg_extractors,
            show_progress=True
        )
        elapsed = time.time() - start_time
        logger.info(f"图谱构建完成，耗时: {elapsed:.2f}s")

        # 持久化索引
        storage_dir = self.config.graph_db_path / "storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        index.storage_context.persist(persist_dir=str(storage_dir))
        logger.info(f"图谱已保存到: {storage_dir}")

        return index

    def _load_documents(self) -> List[Document]:
        """从知识库目录加载文档"""
        from llama_index.core import SimpleDirectoryReader

        if not self.config.knowledge_base_path.exists():
            logger.warning(f"知识库路径不存在: {self.config.knowledge_base_path}")
            return []

        reader = SimpleDirectoryReader(
            input_dir=str(self.config.knowledge_base_path),
            recursive=True,
            required_exts=['.md', '.txt', '.json', '.yaml', '.yml', '.pdf', '.docx', '.doc', '.xlsx', '.xls']
        )
        return reader.load_data()

    def _initialize_graph_retriever(self):
        """初始化图检索器"""
        sub_retrievers = []

        # 向量上下文检索器
        if "vector" in self.config.sub_retrievers:
            vector_retriever = VectorContextRetriever(
                self.index.property_graph_store,
                #【关键修复】：必须传入 vector_store，否则会导致检索失败
                vector_store=self.index.vector_store,
                embed_model=self.embed_model,
                include_text=True,
                similarity_top_k=self.config.vector_top_k,
                path_depth=self.config.vector_path_depth,
            )
            sub_retrievers.append(vector_retriever)
            logger.info("向量上下文检索器已初始化")

        # 同义词检索器（需要 LLM）
        if "synonym" in self.config.sub_retrievers and self.llm is not None:
            synonym_retriever = LLMSynonymRetriever(
                self.index.property_graph_store,
                llm=self.llm,
                include_text=True,
                max_keywords=self.config.synonym_max_keywords,
                path_depth=self.config.synonym_path_depth,
            )
            sub_retrievers.append(synonym_retriever)
            logger.info("同义词检索器已初始化")
        elif "synonym" in self.config.sub_retrievers and self.llm is None:
            logger.info("同义词检索器跳过（未配置 LLM）")

        # 创建组合检索器
        if sub_retrievers:
            self.graph_retriever = PGRetriever(sub_retrievers=sub_retrievers)
            logger.info(f"图检索器已初始化，包含 {len(sub_retrievers)} 个子检索器")

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """检索图谱

        Args:
            query: 查询文本

        Returns:
            检索结果列表，每个结果包含 text, score, metadata, source 字段
        """
        if not self._initialized:
            logger.warning("GraphRAG 模块未初始化")
            return []

        if not query or not query.strip():
            return []

        start_time = time.time()

        # 检查缓存
        if self.config.query_cache_ttl > 0:
            cache_key = self._get_cache_key(query)
            if cache_key in self.query_cache:
                cached = self.query_cache[cache_key]
                if time.time() - cached['timestamp'] < self.config.query_cache_ttl:
                    logger.info(f"缓存命中: {query[:50]}...")
                    return cached['results']

        # 图检索
        graph_results = self._retrieve_graph(query) if self.graph_retriever else []

        # 更新缓存
        if self.config.query_cache_ttl > 0:
            self._update_cache(query, graph_results)

        elapsed = time.time() - start_time
        logger.info(f"GraphRAG 检索耗时: {elapsed:.3f}s")

        return graph_results[:self.config.top_k]

    def _retrieve_graph(self, query: str) -> List[Dict[str, Any]]:
        """图检索"""
        if not self.graph_retriever:
            return []

        nodes = self.graph_retriever.retrieve(query)

        results = []
        for node in nodes:
            results.append({
                'text': node.node.text if hasattr(node.node, 'text') else str(node.node),
                'score': node.score if hasattr(node, 'score') else 0.5,
                'metadata': node.node.metadata if hasattr(node.node, 'metadata') else {},
                'source': 'graph',
            })

        return results

    def _get_cache_key(self, query: str) -> str:
        """生成缓存键"""
        import hashlib
        return hashlib.md5(query.encode()).hexdigest()

    def _update_cache(self, query: str, results: List[Dict[str, Any]]):
        """更新缓存"""
        cache_key = self._get_cache_key(query)
        self.query_cache[cache_key] = {
            'results': results,
            'timestamp': time.time()
        }

        # 限制缓存大小
        if len(self.query_cache) > self.config.cache_max_size:
            # 移除最旧的缓存项
            oldest_key = min(self.query_cache.keys(),
                           key=lambda k: self.query_cache[k]['timestamp'])
            del self.query_cache[oldest_key]

    def rebuild_index(self) -> bool:
        """重建图谱索引"""
        if not self._initialized:
            logger.error("GraphRAG 模块未初始化，无法重建索引")
            return False

        try:
            logger.info("正在重建图谱索引...")
            self.index = self._build_graph_index()
            self._initialize_graph_retriever()
            logger.info("图谱索引重建完成")
            return True
        except Exception as e:
            logger.error(f"图谱索引重建失败: {e}")
            return False

    def get_graph_stats(self) -> Dict[str, Any]:
        """获取图谱统计信息"""
        if not self._initialized:
            return {}

        try:
            triplets = self.index.property_graph_store.get_triplets()

            node_ids = set()
            for triplet in triplets:
                node_ids.add(triplet.subject)
                node_ids.add(triplet.object)

            node_count = len(node_ids)
            relation_count = len(triplets)

            return {
                'node_count': node_count,
                'relation_count': relation_count,
                'graph_store_path': str(self.config.graph_db_path),
            }
        except Exception as e:
            logger.warning(f"获取图谱统计信息失败: {e}")
            return {
                'node_count': 0,
                'relation_count': 0,
                'graph_store_path': str(self.config.graph_db_path),
            }

    def is_enabled(self) -> bool:
        """检查 GraphRAG 是否启用"""
        return self.config.graph_enabled and self._initialized

    def get_status(self) -> Dict[str, Any]:
        """获取 GraphRAG 状态信息"""
        status = {
            'enabled': self.config.graph_enabled,
            'initialized': self._initialized,
            'graph_stats': self.get_graph_stats() if self._initialized else {}
        }

        if self._initialized:
            status.update({
                'embedding_model': self.config.embedding_model,
                'device': str(self.config.device),
                'top_k': self.config.top_k,
                'sub_retrievers': self.config.sub_retrievers,
                'cache_size': len(self.query_cache),
                'cache_ttl': self.config.query_cache_ttl
            })

        return status


# 单例缓存
@lru_cache(maxsize=1)
def get_graph_rag_instance() -> Optional[GraphRAGRetriever]:
    """获取 GraphRAG 检索器单例

    Returns:
        GraphRAG 检索器实例，如果初始化失败或未启用则返回 None
    """
    try:
        config = GraphRAGConfig.from_config()
        rag = GraphRAGRetriever(config)
        return rag if rag.is_enabled() else None
    except Exception as e:
        logger.warning(f"GraphRAG 初始化失败: {e}")
        return None


def check_graph_rag_available() -> bool:
    """检查 GraphRAG 功能是否可用"""
    return True