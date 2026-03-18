"""
RAG 检索模块 (基于 LlamaIndex + SimpleVectorStore)
用于检索港口作业相关知识库来增强指令解析

功能:
- 向量检索（基于 BGE-M3 嵌入）
- 自适应相似度阈值（三级fallback）
- 混合检索（BM25 + 向量）
- Reranking重排序
- 多格式文档支持（PDF, Word, Excel）
- 语义分割chunking
- 无文件锁定问题（使用 JSON 持久化）
"""
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 核心依赖
from llama_index.core import VectorStoreIndex, Document, Settings, SimpleDirectoryReader, StorageContext
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.vector_stores import SimpleVectorStore

# 可选依赖
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.node_parser import SemanticSplitterNodeParser
from llama_index.core.node_parser import MarkdownNodeParser

from src.config import config
from src.utils import get_device

logger = logging.getLogger(__name__)


class RAGConfig:
    """RAG配置管理 - 简化版，使用全局 config 对象"""

    def __init__(self):
        # 基础配置 - 直接从全局 config 对象获取
        self.enabled = config.rag.enabled
        self.embedding_model = config.rag.embedding_model
        self.device = config.rag.device
        self.top_k = config.rag.top_k

        # 检索模式
        self.retrieval_mode = config.retrieval.mode
        self.threshold_strict = config.retrieval.threshold_strict
        self.threshold_medium = config.retrieval.threshold_medium
        self.threshold_relaxed = config.retrieval.threshold_relaxed
        self.min_results_expected = config.retrieval.min_results_expected
        self.hybrid_enabled = config.retrieval.hybrid_enabled
        self.fusion_method = config.retrieval.fusion_method

        # Rerank配置
        self.rerank_enabled = config.rerank.enabled
        self.rerank_model = config.rerank.model
        self.rerank_device = config.rerank.device
        self.rerank_top_k = config.rerank.rerank_top_k
        self.final_top_k = config.rerank.final_top_k

        # Chunking配置
        self.chunking_strategy = config.chunking.strategy
        self.chunk_size = config.chunking.chunk_size
        self.chunk_overlap = config.chunking.chunk_overlap

        # Markdown切分配置
        self.markdown_chunking_enabled = config.chunking.markdown_chunking_enabled
        self.markdown_heading_level = config.chunking.markdown_heading_level
        self.markdown_preserve_tables = config.chunking.markdown_preserve_tables
        self.metadata_include_heading = config.chunking.metadata_include_heading
        self.metadata_include_position = config.chunking.metadata_include_position

        # 路径配置
        self.knowledge_base_path = config.paths.knowledge_base
        self.vector_db_path = config.paths.vector_db


class RAGRetriever:
    """传统 RAG 检索器（基于向量检索）"""

    def __init__(self):
        self.config = RAGConfig()

        # 确保目录存在
        self.config.vector_db_path.mkdir(parents=True, exist_ok=True)

        # 初始化组件
        self.embed_model = None
        self.index = None
        self.vector_retriever = None
        self.bm25_retriever = None
        self.reranker = None
        self.splitter = None

        self._initialized = False

        if self.config.enabled:
            self._initialize()

    def _initialize(self):
        """初始化嵌入模型和向量索引"""
        logger.info("正在初始化 RAG 模块...")

        # 1. 初始化嵌入模型
        device = get_device(self.config.device)
        logger.info(f"加载嵌入模型: {self.config.embedding_model} 在 {device} 上")

        self.embed_model = HuggingFaceEmbedding(
            model_name=self.config.embedding_model,
            device=device,
            trust_remote_code=True
        )
        Settings.embed_model = self.embed_model

        # 2. 初始化chunking策略
        self._initialize_splitter()

        # 3. 初始化reranker
        if self.config.rerank_enabled:
            self._initialize_reranker()

        # 3. 加载或创建向量索引
        self._load_or_create_index()

        self._initialized = True
        logger.info(">>> RAG 模块初始化完成")
        logger.info(
            f"检索模式: {self.config.retrieval_mode}, "
            f"混合检索: {self.config.hybrid_enabled}, "
            f"Reranking: {self.config.rerank_enabled}"
        )

    def _initialize_splitter(self):
        """
        初始化chunking策略（用于非Markdown文件）
        Markdown文件在 _build_index 中单独处理
        """
        if self.config.chunking_strategy == "semantic":
            self.splitter = SemanticSplitterNodeParser(
                buffer_size=1,
                breakpoint_percentile_threshold=60,
                embed_model=self.embed_model
            )
            logger.info("使用语义分割策略（用于非Markdown文件）")
        else:  # fixed策略
            self.splitter = SentenceSplitter(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap
            )
            logger.info(f"使用固定分割策略 (size={self.config.chunk_size}, overlap={self.config.chunk_overlap})")

    def _initialize_reranker(self):
        """初始化BGE重排序器"""
        try:
            from FlagEmbedding import FlagReranker
            device = get_device(self.config.rerank_device)
            self.reranker = FlagReranker(self.config.rerank_model, device=device)
            logger.info(f"Reranker已加载: {self.config.rerank_model}")
        except Exception as e:
            logger.warning(f"Reranker初始化失败: {e}，reranking功能将禁用")
            self.reranker = None
            self.config.rerank_enabled = False

    def _load_or_create_index(self):
        """加载或创建向量索引（使用 SimpleVectorStore）"""
        vector_store_path = self.config.vector_db_path / "vector_store.json"

        # 创建 StorageContext，使用 SimpleVectorStore
        if vector_store_path.exists():
            try:
                vector_store = SimpleVectorStore.from_persist_path(str(vector_store_path))
                logger.info("加载现有向量存储")
            except Exception as e:
                logger.warning(f"加载向量存储失败: {e}，创建新的")
                vector_store = SimpleVectorStore()
        else:
            vector_store = SimpleVectorStore()

        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # 检查是否需要构建索引
        if self.config.knowledge_base_path.exists() and list(self.config.knowledge_base_path.rglob("*")):
            self._build_index(storage_context, vector_store_path)
        else:
            logger.warning(f"知识库目录为空: {self.config.knowledge_base_path}")
            # 创建空索引
            self.index = VectorStoreIndex.from_documents([], storage_context=storage_context)

        self._initialize_retrievers()

    def _build_index(self, storage_context: StorageContext, vector_store_path: Path):
        """从知识库文档构建向量索引"""
        try:
            logger.info(f"正在从知识库构建索引: {self.config.knowledge_base_path}")

            documents = self._load_documents()

            if not documents:
                logger.warning("未找到任何知识库文档")
                self.index = VectorStoreIndex.from_documents([], storage_context=storage_context)
                return

            logger.info(f"加载了 {len(documents)} 个文档")

            # 检查是否需要为MD文件使用专用切分策略
            if self.config.markdown_chunking_enabled:
                # 分离MD文档和其他文档
                md_docs = [doc for doc in documents if doc.metadata.get('file_path', '').endswith('.md')]
                other_docs = [doc for doc in documents if not doc.metadata.get('file_path', '').endswith('.md')]

                logger.info(f"MD文档: {len(md_docs)}个, 其他文档: {len(other_docs)}个")
                if md_docs:
                    logger.info(f"MD文件将使用Markdown切分策略，其他文件将使用{self.config.chunking_strategy}策略")

                all_nodes = []

                # 处理MD文档（使用MarkdownNodeParser）
                if md_docs:
                    try:
                        from llama_index.core.node_parser import MarkdownNodeParser
                        md_splitter = MarkdownNodeParser(
                            max_heading_level=self.config.markdown_heading_level,
                            include_metadata=self.config.metadata_include_heading,
                        )
                        md_nodes = md_splitter.get_nodes_from_documents(md_docs)
                        all_nodes.extend(md_nodes)
                        logger.info(f"Markdown文档切分: {len(md_docs)}个文档 → {len(md_nodes)}个nodes")
                    except Exception as e:
                        logger.warning(f"Markdown切分失败: {e}，使用默认策略")
                        if self.splitter:
                            md_nodes = self.splitter.get_nodes_from_documents(md_docs)
                            all_nodes.extend(md_nodes)

                # 处理其他文档（使用 self.splitter，已在 _initialize_splitter 中配置）
                if other_docs:
                    if self.splitter:
                        other_nodes = self.splitter.get_nodes_from_documents(other_docs)
                        all_nodes.extend(other_nodes)
                        logger.info(f"其他文档切分: {len(other_docs)}个文档 → {len(other_nodes)}个nodes")
                    else:
                        # 如果没有配置splitter，直接添加文档
                        logger.warning("未配置切分器，直接使用文档创建索引")

                # 直接从nodes创建索引
                if all_nodes:
                    self.index = VectorStoreIndex(
                        nodes=all_nodes,
                        storage_context=storage_context,
                        show_progress=True
                    )
                else:
                    self.index = VectorStoreIndex.from_documents([], storage_context=storage_context)

            else:
                # 使用单一策略处理所有文档
                transformations = [self.splitter] if self.splitter else None
                self.index = VectorStoreIndex.from_documents(
                    documents,
                    storage_context=storage_context,
                    show_progress=True,
                    transformations=transformations
                )

            # 保存向量存储
            storage_context.vector_store.persist(str(vector_store_path))
            logger.info(f"向量存储已保存到: {vector_store_path}")

        except Exception as e:
            logger.error(f"索引构建失败: {e}")
            raise

    def _load_documents(self) -> List[Document]:
        """从知识库目录加载所有文档"""
        if not self.config.knowledge_base_path.exists():
            logger.warning(f"知识库路径不存在: {self.config.knowledge_base_path}")
            return []

        reader = SimpleDirectoryReader(
            input_dir=str(self.config.knowledge_base_path),
            recursive=True,
            required_exts=['.md', '.txt', '.json', '.yaml', '.yml', '.pdf', '.docx', '.doc', '.xlsx', '.xls']
        )
        return reader.load_data()

    def _initialize_retrievers(self):
        """初始化检索器"""
        self.vector_retriever = self.index.as_retriever(
            similarity_top_k=self.config.top_k * 2 if self.config.hybrid_enabled else self.config.top_k
        )

        if self.config.hybrid_enabled:
            try:
                # FAISS 索引包含所有 nodes，BM25 可以正常工作
                self.bm25_retriever = BM25Retriever.from_defaults(
                    index=self.index,
                    similarity_top_k=self.config.top_k * 2
                )
                logger.info("混合检索器已初始化（向量 FAISS + BM25）")
            except Exception as e:
                logger.warning(f"BM25检索器初始化失败: {e}，将仅使用向量检索")
                self.bm25_retriever = None
                self.config.hybrid_enabled = False

        # 兼容性属性
        self.retriever = self.vector_retriever

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """检索：使用传统 RAG（向量检索）"""
        import time

        if not self._initialized or not self.vector_retriever:
            logger.warning("RAG 模块未初始化")
            return []

        if not query or not query.strip():
            return []

        start_time = time.time()

        # 选择检索模式
        if self.config.retrieval_mode == "hybrid" and self.config.hybrid_enabled:
            results = self._retrieve_hybrid(query)
        elif self.config.retrieval_mode == "adaptive":
            results = self._retrieve_adaptive(query)
        else:  # fixed mode
            results = self._retrieve_fixed(query)

        # Reranking
        if self.reranker and results and self.config.rerank_enabled:
            results = self._rerank_results(query, results)

        return results[:self.config.top_k]

    def _retrieve_hybrid(self, query: str) -> List[Dict[str, Any]]:
        """混合检索（向量 + BM25）+ 融合"""
        vector_nodes = self.vector_retriever.retrieve(query)
        bm25_nodes = self.bm25_retriever.retrieve(query) if self.bm25_retriever else []

        fusion_method = self.config.fusion_method
        if fusion_method == "rrf":
            fused_results = self._rrf_fusion(vector_nodes, bm25_nodes)
        elif fusion_method == "weighted":
            fused_results = self._weighted_fusion(vector_nodes, bm25_nodes)
        else:  # concat
            fused_results = self._concat_fusion(vector_nodes, bm25_nodes)

        logger.debug(f"混合检索: 向量{len(vector_nodes)} + BM25{len(bm25_nodes)} → {fusion_method}融合 → {len(fused_results)}")
        return fused_results

    def _retrieve_adaptive(self, query: str) -> List[Dict[str, Any]]:
        """自适应阈值检索（三级fallback）"""
        thresholds = [
            self.config.threshold_medium,
            self.config.threshold_strict,
            self.config.threshold_relaxed
        ]

        for threshold in thresholds:
            results = self._retrieve_at_threshold(query, threshold)

            if len(results) >= self.config.min_results_expected:
                avg_score = sum(r['score'] for r in results) / len(results)
                if avg_score >= 0.4:
                    logger.info(f"自适应阈值: 使用{threshold:.2f}，检索到{len(results)}个结果")
                    return results

            logger.debug(f"阈值{threshold:.2f}结果不足，尝试下一级...")

        return results if results else []

    def _retrieve_fixed(self, query: str) -> List[Dict[str, Any]]:
        """固定阈值检索"""
        threshold = self.config.threshold_medium
        return self._retrieve_at_threshold(query, threshold)

    def _retrieve_at_threshold(self, query: str, threshold: float) -> List[Dict[str, Any]]:
        """使用指定阈值进行检索"""
        try:
            nodes = self.vector_retriever.retrieve(query)

            results = []
            for node in nodes:
                score = getattr(node, 'score', 0.0)
                if score >= threshold:
                    results.append({
                        'text': node.node.text,
                        'score': score,
                        'metadata': node.node.metadata
                    })

            return results

        except Exception as e:
            logger.error(f"检索失败: {e}")
            return []

    def _rrf_fusion(self, vector_results: List, bm25_results: List, k: int = 60) -> List[Dict[str, Any]]:
        """倒数秩融合（Reciprocal Rank Fusion）"""
        scores = {}

        for rank, node in enumerate(vector_results, 1):
            node_id = id(node.node)
            vector_score = getattr(node, 'score', 0.0)
            scores[node_id] = {
                'score': 1 / (k + rank),
                'node': node.node,
                'vector_score': vector_score
            }

        for rank, node in enumerate(bm25_results, 1):
            node_id = id(node.node)
            if node_id in scores:
                scores[node_id]['score'] += 1 / (k + rank)
            else:
                scores[node_id] = {
                    'score': 1 / (k + rank),
                    'node': node.node,
                    'vector_score': 0.0
                }

        results = [
            {
                'text': data['node'].text,
                'score': data['score'],
                'vector_score': data['vector_score'],
                'metadata': data['node'].metadata
            }
            for data in sorted(scores.values(), key=lambda x: x['score'], reverse=True)
        ]

        return results[:self.config.rerank_top_k]

    def _weighted_fusion(self, vector_results: List, bm25_results: List) -> List[Dict[str, Any]]:
        """加权融合：使用配置的权重合并向量相似度和 BM25 分数"""
        vector_weight = self.config.vector_weight
        keyword_weight = self.config.keyword_weight
        scores = {}

        # 归一化向量分数（假设最高为1.0）
        for node in vector_results:
            node_id = id(node.node)
            vector_score = getattr(node, 'score', 0.0)
            scores[node_id] = {
                'score': vector_score * vector_weight,
                'node': node.node,
                'vector_score': vector_score
            }

        # BM25 使用倒数排名作为分数
        for rank, node in enumerate(bm25_results, 1):
            node_id = id(node.node)
            bm25_score = 1.0 / (rank + 1)  # 简单的倒数排名分数
            if node_id in scores:
                scores[node_id]['score'] += bm25_score * keyword_weight
            else:
                scores[node_id] = {
                    'score': bm25_score * keyword_weight,
                    'node': node.node,
                    'vector_score': 0.0
                }

        results = [
            {
                'text': data['node'].text,
                'score': data['score'],
                'vector_score': data['vector_score'],
                'metadata': data['node'].metadata
            }
            for data in sorted(scores.values(), key=lambda x: x['score'], reverse=True)
        ]

        return results[:self.config.rerank_top_k]

    def _concat_fusion(self, vector_results: List, bm25_results: List) -> List[Dict[str, Any]]:
        """简单拼接融合：向量结果优先，去重后追加 BM25 结果"""
        results = []
        seen_ids = set()

        # 添加向量检索结果
        for node in vector_results:
            node_id = id(node.node)
            seen_ids.add(node_id)
            results.append({
                'text': node.node.text,
                'score': getattr(node, 'score', 0.0),
                'metadata': node.node.metadata
            })

        # 添加 BM25 结果（去重）
        for node in bm25_results:
            if id(node.node) not in seen_ids:
                results.append({
                    'text': node.node.text,
                    'score': 0.5,
                    'metadata': node.node.metadata
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:self.config.rerank_top_k]

    def _rerank_results(self, query: str, results: List[Dict]) -> List[Dict]:
        """使用reranker重新排序"""
        if not results:
            return results

        try:
            texts = [r['text'] for r in results]
            pairs = [[query, text] for text in texts]
            scores = self.reranker.compute_score(pairs)

            for i, result in enumerate(results):
                result['rerank_score'] = float(scores[i])

            results.sort(key=lambda x: x['rerank_score'], reverse=True)
            logger.info(f"Reranking完成，最高分: {max(r['rerank_score'] for r in results):.3f}")
            return results

        except Exception as e:
            logger.warning(f"Reranking失败: {e}")
            return results

    def format_context(self, results: List[Dict[str, Any]]) -> str:
        """将检索结果格式化为提示词上下文"""
        if not results:
            return ""

        context_parts = ["# 相关知识库信息\n"]

        for i, result in enumerate(results, 1):
            metadata = result.get('metadata', {})
            file_path = metadata.get('file_path', '未知来源')
            context_parts.append(f"## 来源 {i}: {file_path}")
            context_parts.append(result['text'])
            context_parts.append("")

        return "\n".join(context_parts)

    def rebuild_index(self) -> bool:
        """重建知识库索引（向量索引）"""
        try:
            logger.info("正在重建向量索引...")

            # 删除现有向量存储
            vector_store_path = self.config.vector_db_path / "vector_store.json"
            if vector_store_path.exists():
                vector_store_path.unlink()
                logger.info(f"已删除现有向量存储: {vector_store_path}")

            # 重新构建索引
            self._load_or_create_index()

            logger.info("索引重建完成")
            return True

        except Exception as e:
            logger.error(f"索引重建失败: {e}")
            return False

    def is_enabled(self) -> bool:
        """检查 RAG 是否启用"""
        return self.config.enabled and self._initialized

    def get_status(self) -> Dict[str, Any]:
        """获取 RAG 状态信息"""
        status = {
            'enabled': self.config.enabled,
            'initialized': self._initialized,
            'embedding_model': self.config.embedding_model,
            'device': str(self.config.device) if self.embed_model else 'N/A',
            'vector_store': 'SimpleVectorStore',
            'top_k': self.config.top_k,
            'retrieval_mode': self.config.retrieval_mode,
            'chunking_strategy': self.config.chunking_strategy,
            'hybrid_enabled': self.config.hybrid_enabled,
            'rerank_enabled': self.config.rerank_enabled,
            'knowledge_base_path': str(self.config.knowledge_base_path),
            'vector_db_path': str(self.config.vector_db_path),
        }

        if self.config.retrieval_mode in ('adaptive', 'hybrid'):
            status['thresholds'] = {
                'strict': self.config.threshold_strict,
                'medium': self.config.threshold_medium,
                'relaxed': self.config.threshold_relaxed
            }

        return status


@lru_cache(maxsize=1)
def get_rag_instance() -> Optional[RAGRetriever]:
    """获取 RAG 检索器单例"""
    try:
        rag = RAGRetriever()
        return rag if rag.is_enabled() else None
    except Exception as e:
        logger.warning(f"RAG 初始化失败: {e}")
        return None


def check_rag_available() -> bool:
    """检查 RAG 功能是否可用"""
    return True


def initialize_rag_if_enabled(config_enabled: bool) -> Tuple[bool, Optional[RAGRetriever]]:
    """统一的 RAG 初始化接口"""
    if not config_enabled:
        return False, None

    try:
        retriever = get_rag_instance()
        if retriever:
            logger.info(">>> RAG 模块已启用")
            return True, retriever

        logger.warning(">>> RAG 模块初始化失败，将使用无 RAG 模式")
        return False, None

    except Exception as e:
        logger.warning(f">>> RAG 模块加载失败: {e}")
        return False, None
