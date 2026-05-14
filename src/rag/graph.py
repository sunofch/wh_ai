"""
GraphRAG 核心模块：基于 PropertyGraphIndex + Neo4j 的知识图谱检索

存储后端：Neo4jPropertyGraphStore（替代原 SimplePropertyGraphStore 文件存储）
- 图谱数据和向量索引均持久化到 Neo4j
- 首次运行自动从知识库构建并写入 Neo4j
- 后续启动检测到 Neo4j 有数据则直接加载，无需重建
"""
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Any

from llama_index.core import (
    PropertyGraphIndex,
    Document,
    Settings,
    StorageContext,
)
from llama_index.core.indices.property_graph import (
    PGRetriever,
    VectorContextRetriever,
    LLMSynonymRetriever,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.deepseek import DeepSeek

from src.common.config import config
from src.common.utils import get_device
from .graph_extractors import create_kg_extractors
from src.common.reranker import get_reranker_instance

logger = logging.getLogger(__name__)


def initialize_llm() -> Optional[Any]:
    """根据全局 config 初始化 LLM"""
    cfg = config.graph_rag

    if cfg.llm_provider == "deepseek":
        if not cfg.deepseek_api_key:
            logger.warning("DeepSeek API key 未配置，将使用隐式提取器")
            return None

        try:
            llm = DeepSeek(
                model=cfg.deepseek_model,
                api_key=cfg.deepseek_api_key,
                temperature=cfg.deepseek_temperature,
            )
            logger.info(f"DeepSeek LLM 初始化成功: {cfg.deepseek_model}")
            return llm
        except Exception as e:
            logger.error(f"DeepSeek LLM 初始化失败: {e}")
            return None

    return None


class GraphRAGRetriever:
    """GraphRAG 检索器

    基于 LlamaIndex PropertyGraphIndex 实现，支持多种检索器组合
    """

    def __init__(self):
        self._initialized = False

        self.llm: Optional[Any] = None
        self.embed_model: Optional[Any] = None
        self.index: Optional[PropertyGraphIndex] = None
        self.graph_retriever: Optional[PGRetriever] = None
        self.query_cache: Dict[str, Dict[str, Any]] = {}
        self.reranker = None

        if config.rag.graph_enabled:
            self._initialize()

    def _initialize(self):
        """初始化 GraphRAG"""
        logger.info("正在初始化 GraphRAG 模块...")

        # 初始化嵌入模型
        device = get_device(config.rag.device)
        self.embed_model = HuggingFaceEmbedding(
            model_name=config.rag.embedding_model,
            device=device,
            trust_remote_code=True
        )
        Settings.embed_model = self.embed_model

        # 初始化 LLM
        self.llm = initialize_llm()
        if self.llm:
            Settings.llm = self.llm
        else:
            Settings.llm = None
            logger.info("未配置 LLM，将仅使用隐式提取器")

        # 加载或创建图谱索引
        self.index = self._load_or_create_graph_index()

        # 初始化图检索器
        self._initialize_graph_retriever()

        # 初始化 Reranker
        self.reranker = get_reranker_instance()
        if self.reranker.is_enabled():
            logger.info("Reranker 已集成到 GraphRAG")

        self._initialized = True
        logger.info(">>> GraphRAG 模块初始化完成")

    def _create_neo4j_store(self):
        """创建 Neo4j 图谱存储实例"""
        from llama_index.graph_stores.neo4j import Neo4jPropertyGraphStore
        return Neo4jPropertyGraphStore(
            username=config.neo4j.username,
            password=config.neo4j.password,
            url=config.neo4j.uri,
            database=config.neo4j.database,
        )

    def _neo4j_has_data(self, graph_store) -> bool:
        """检查 Neo4j 是否已有图谱数据"""
        try:
            with graph_store._driver.session(database=config.neo4j.database) as session:
                result = session.run("MATCH (n) RETURN count(n) AS cnt LIMIT 1")
                return result.single()["cnt"] > 0
        except Exception as e:
            logger.warning(f"Neo4j 数据检查失败: {e}")
            return False

    def _load_or_create_graph_index(self) -> PropertyGraphIndex:
        """连接 Neo4j，有数据则直接加载，否则重新构建"""
        graph_store = self._create_neo4j_store()

        if self._neo4j_has_data(graph_store):
            logger.info("从 Neo4j 加载现有图谱数据")
            return PropertyGraphIndex.from_documents(
                [],
                property_graph_store=graph_store,
            )

        return self._build_graph_index(graph_store)

    def _build_graph_index(self, graph_store=None) -> PropertyGraphIndex:
        """从文档构建图谱索引并写入 Neo4j"""
        logger.info(f"正在从知识库构建图谱: {config.paths.knowledge_base}")

        documents = self._load_documents()
        if not documents:
            logger.warning("未找到任何知识库文档")
            if graph_store:
                return PropertyGraphIndex.from_documents([], property_graph_store=graph_store)
            return PropertyGraphIndex.from_documents([])

        logger.info(f"加载了 {len(documents)} 个文档")

        splitter = SentenceSplitter(
            chunk_size=config.graph_rag.chunk_size,
            chunk_overlap=config.graph_rag.chunk_overlap
        )
        logger.info(f"GraphRAG 分块配置: chunk_size={config.graph_rag.chunk_size}, chunk_overlap={config.graph_rag.chunk_overlap}")

        kg_extractors = create_kg_extractors(config.graph_rag, self.llm)

        start_time = time.time()
        kwargs = {"property_graph_store": graph_store} if graph_store else {}
        index = PropertyGraphIndex.from_documents(
            documents,
            transformations=[splitter],
            kg_extractors=kg_extractors,
            show_progress=True,
            **kwargs,
        )
        elapsed = time.time() - start_time
        logger.info(f"图谱构建完成，耗时: {elapsed:.2f}s（已写入 Neo4j）")

        return index

    def _load_documents(self) -> List[Document]:
        """从知识库目录加载文档"""
        from llama_index.core import SimpleDirectoryReader

        if not config.paths.knowledge_base.exists():
            logger.warning(f"知识库路径不存在: {config.paths.knowledge_base}")
            return []

        reader = SimpleDirectoryReader(
            input_dir=str(config.paths.knowledge_base),
            recursive=True,
            required_exts=['.md', '.txt', '.json', '.yaml', '.yml', '.pdf', '.docx', '.doc', '.xlsx', '.xls']
        )
        return reader.load_data()

    def _initialize_graph_retriever(self):
        """初始化图检索器"""
        sub_retrievers = []

        # 向量上下文检索器（Neo4j 原生支持向量检索，无需额外 vector_store）
        if "vector" in config.graph_retrieval.sub_retrievers:
            vector_retriever = VectorContextRetriever(
                self.index.property_graph_store,
                embed_model=self.embed_model,
                include_text=config.graph_retrieval.vector_include_text,
                similarity_top_k=config.graph_retrieval.vector_top_k,
                path_depth=config.graph_retrieval.vector_path_depth,
            )
            sub_retrievers.append(vector_retriever)
            logger.info("向量上下文检索器已初始化（Neo4j 向量索引）")

        # 同义词检索器（需要 LLM）
        if "synonym" in config.graph_retrieval.sub_retrievers and self.llm is not None:
            synonym_retriever = LLMSynonymRetriever(
                self.index.property_graph_store,
                llm=self.llm,
                include_text=True,
                max_keywords=config.graph_retrieval.synonym_max_keywords,
                path_depth=config.graph_retrieval.synonym_path_depth,
            )
            sub_retrievers.append(synonym_retriever)
            logger.info("同义词检索器已初始化")
        elif "synonym" in config.graph_retrieval.sub_retrievers and self.llm is None:
            logger.info("同义词检索器跳过（未配置 LLM）")

        # 创建组合检索器
        if sub_retrievers:
            self.graph_retriever = PGRetriever(sub_retrievers=sub_retrievers)
            logger.info(f"图检索器已初始化，包含 {len(sub_retrievers)} 个子检索器")

    def retrieve(self, query: str) -> List[Dict[str, Any]]:
        """检索图谱"""
        if not self._initialized:
            logger.warning("GraphRAG 模块未初始化")
            return []

        if not query or not query.strip():
            return []

        start_time = time.time()

        # 检查缓存
        if config.graph_performance.query_cache_ttl > 0:
            cache_key = self._get_cache_key(query)
            if cache_key in self.query_cache:
                cached = self.query_cache[cache_key]
                if time.time() - cached['timestamp'] < config.graph_performance.query_cache_ttl:
                    logger.info(f"缓存命中: {query[:50]}...")
                    return cached['results']

        # 图检索
        graph_results = self._retrieve_graph(query) if self.graph_retriever else []

        # include_text=False 时做实体展开：从匹配三元组提取主语，查询其全部关系
        if not config.graph_retrieval.vector_include_text:
            graph_results = self._expand_from_results(graph_results)

        # Reranker 精排
        if config.graph_rerank.enabled and self.reranker.is_enabled():
            logger.info(f"Reranker 精排前: {len(graph_results)} 个候选")
            graph_results = self.reranker.rerank(
                query,
                graph_results,
                top_k=config.graph_rerank.final_top_k
            )

        # 更新缓存
        if config.graph_performance.query_cache_ttl > 0:
            self._update_cache(query, graph_results)

        elapsed = time.time() - start_time
        logger.info(f"GraphRAG 检索耗时: {elapsed:.3f}s")

        return graph_results[:config.rag.top_k]

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

    def _expand_from_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从检索结果中提取主语实体，展开其全部三元组"""
        entity_names: set = set()
        for r in results:
            for line in r.get('text', '').strip().split('\n'):
                line = line.strip()
                if ' -> ' in line:
                    entity_names.add(line.split(' -> ')[0].strip())

        if not entity_names:
            return results

        expanded = self._expand_entity_triplets(entity_names)
        return expanded if expanded else results

    def _expand_entity_triplets(self, entity_names: set) -> List[Dict[str, Any]]:
        """查询每个实体在 Neo4j 中的全部出向三元组"""
        results = []
        try:
            graph_store = self._create_neo4j_store()
            with graph_store._driver.session(database=config.neo4j.database) as session:
                for entity_name in entity_names:
                    records = list(session.run(
                        "MATCH (n)-[r]->(m) WHERE n.name = $name "
                        "RETURN n.name AS subject, "
                        "COALESCE(r.label, type(r)) AS relation, "
                        "m.name AS object",
                        name=entity_name,
                    ))
                    if not records:
                        continue
                    triplets = [
                        f"{rec['subject']} -> {rec['relation']} -> {rec['object']}"
                        for rec in records
                    ]
                    results.append({
                        'text': '\n'.join(triplets),
                        'score': 1.0,
                        'metadata': {'entity': entity_name},
                        'source': 'graph',
                    })
        except Exception as e:
            logger.warning(f"实体扩展查询失败: {e}")
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
        if len(self.query_cache) > config.graph_performance.cache_max_size:
            # 移除最旧的缓存项
            oldest_key = min(self.query_cache.keys(),
                           key=lambda k: self.query_cache[k]['timestamp'])
            del self.query_cache[oldest_key]

    def rebuild_index(self) -> bool:
        """清空 Neo4j 数据后重建图谱索引"""
        if not self._initialized:
            logger.error("GraphRAG 模块未初始化，无法重建索引")
            return False

        try:
            logger.info("正在重建图谱索引（清空 Neo4j 后重建）...")
            graph_store = self._create_neo4j_store()
            with graph_store._driver.session(database=config.neo4j.database) as session:
                session.run("MATCH (n) DETACH DELETE n")
            self.index = self._build_graph_index(graph_store)
            self._initialize_graph_retriever()
            logger.info("图谱索引重建完成")
            return True
        except Exception as e:
            logger.error(f"图谱索引重建失败: {e}")
            return False

    def is_enabled(self) -> bool:
        """检查 GraphRAG 是否启用"""
        return config.rag.graph_enabled and self._initialized

    def get_status(self) -> Dict[str, Any]:
        """获取 GraphRAG 状态信息"""
        status = {
            'enabled': config.rag.graph_enabled,
            'initialized': self._initialized,
        }

        if self._initialized:
            status.update({
                'embedding_model': config.rag.embedding_model,
                'device': str(config.rag.device),
                'top_k': config.rag.top_k,
                'sub_retrievers': config.graph_retrieval.sub_retrievers,
                'cache_size': len(self.query_cache),
                'cache_ttl': config.graph_performance.query_cache_ttl
            })

        return status


# 单例缓存
@lru_cache(maxsize=1)
def get_graph_rag_instance() -> Optional[GraphRAGRetriever]:
    """获取 GraphRAG 检索器单例"""
    try:
        rag = GraphRAGRetriever()
        return rag if rag.is_enabled() else None
    except Exception as e:
        logger.warning(f"GraphRAG 初始化失败: {e}")
        return None


def check_graph_rag_available() -> bool:
    """检查 GraphRAG 功能是否可用"""
    return True