"""
配置管理模块：使用 Pydantic BaseSettings 进行类型安全和验证

从 config.ini 迁移到环境变量配置系统
"""
from pathlib import Path
from typing import List, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppConfig(BaseSettings):
    """应用配置基类，统一配置行为"""
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="allow"
    )


class ASRConfig(BaseAppConfig):
    """ASR 模型配置"""
    model: str = Field(default="large-v3-turbo", alias="ASR_MODEL")
    device: str = Field(default="auto", alias="ASR_DEVICE")
    language: str = Field(default="zh", alias="ASR_LANGUAGE")


class VLMConfig(BaseAppConfig):
    """VLM 模型配置"""
    model: str = Field(default="Qwen/Qwen2-VL-2B-Instruct", alias="VLM_MODEL")
    device: str = Field(default="auto", alias="VLM_DEVICE")
    max_tokens: int = Field(default=512, alias="VLM_MAX_TOKENS")


class ParserConfig(BaseAppConfig):
    """解析器配置"""
    confidence_threshold: float = Field(default=0.9, alias="PARSER_CONFIDENCE_THRESHOLD")
    default_urgency: str = Field(default="中", alias="PARSER_DEFAULT_URGENCY")
    fallback_part_name: str = Field(default="未知备件", alias="PARSER_FALLBACK_PART_NAME")
    fallback_description_prefix: str = Field(
        default="自动解析失败，原始信息",
        alias="PARSER_FALLBACK_DESCRIPTION_PREFIX"
    )


class PathsConfig(BaseAppConfig):
    """路径配置"""
    cache_dir: Path = Field(default=Path("./models"), alias="CACHE_DIR")
    output_dir: Path = Field(default=Path("./output"), alias="OUTPUT_DIR")
    knowledge_base: Path = Field(default=Path("./data/knowledge_base"), alias="KNOWLEDGE_BASE_PATH")
    vector_db: Path = Field(default=Path("./data/vector_db"), alias="VECTOR_DB_PATH")
    graph_db: Path = Field(default=Path("./data/graph_db"), alias="GRAPH_DB_PATH")


class RAGConfig(BaseAppConfig):
    """RAG 基础配置"""
    enabled: bool = Field(default=True, alias="RAG_ENABLED")
    graph_enabled: bool = Field(default=True, alias="RAG_GRAPH_ENABLED")
    embedding_model: str = Field(default="BAAI/bge-m3", alias="RAG_EMBEDDING_MODEL")
    device: str = Field(default="auto", alias="RAG_DEVICE")
    top_k: int = Field(default=3, alias="RAG_TOP_K")


class RetrievalConfig(BaseAppConfig):
    """检索配置"""
    mode: str = Field(default="hybrid", alias="RAG_RETRIEVAL_MODE")
    threshold_strict: float = Field(default=0.7, alias="RAG_RETRIEVAL_THRESHOLD_STRICT")
    threshold_medium: float = Field(default=0.35, alias="RAG_RETRIEVAL_THRESHOLD_MEDIUM")
    threshold_relaxed: float = Field(default=0.25, alias="RAG_RETRIEVAL_THRESHOLD_RELAXED")
    min_results_expected: int = Field(default=2, alias="RAG_RETRIEVAL_MIN_RESULTS_EXPECTED")
    hybrid_enabled: bool = Field(default=True, alias="RAG_RETRIEVAL_HYBRID_ENABLED")
    fusion_method: str = Field(default="rrf", alias="RAG_RETRIEVAL_FUSION_METHOD")
    vector_weight: float = Field(default=0.7, alias="RAG_RETRIEVAL_VECTOR_WEIGHT")
    keyword_weight: float = Field(default=0.3, alias="RAG_RETRIEVAL_KEYWORD_WEIGHT")


class RerankConfig(BaseAppConfig):
    """重排序配置"""
    enabled: bool = Field(default=True, alias="RAG_RERANK_ENABLED")
    model: str = Field(default="BAAI/bge-reranker-v2-m3", alias="RAG_RERANK_MODEL")
    rerank_top_k: int = Field(default=10, alias="RAG_RERANK_TOP_K")
    final_top_k: int = Field(default=3, alias="RAG_RERANK_FINAL_TOP_K")
    device: str = Field(default="auto", alias="RAG_RERANK_DEVICE")


class ChunkingConfig(BaseAppConfig):
    """分块配置"""
    strategy: str = Field(default="semantic", alias="RAG_CHUNKING_STRATEGY")
    chunk_size: int = Field(default=1024, alias="RAG_CHUNKING_CHUNK_SIZE")
    chunk_overlap: int = Field(default=128, alias="RAG_CHUNKING_CHUNK_OVERLAP")
    semantic_splitter_threshold: float = Field(default=0.6, alias="RAG_CHUNKING_SEMANTIC_SPLITTER_THRESHOLD")
    min_chunk_size: int = Field(default=128, alias="RAG_CHUNKING_MIN_CHUNK_SIZE")
    markdown_chunking_enabled: bool = Field(default=True, alias="RAG_CHUNKING_MARKDOWN_ENABLED")
    markdown_heading_level: int = Field(default=2, alias="RAG_CHUNKING_MARKDOWN_HEADING_LEVEL")
    markdown_preserve_tables: bool = Field(default=True, alias="RAG_CHUNKING_MARKDOWN_PRESERVE_TABLES")
    metadata_include_heading: bool = Field(default=True, alias="RAG_CHUNKING_METADATA_INCLUDE_HEADING")
    metadata_include_position: bool = Field(default=False, alias="RAG_CHUNKING_METADATA_INCLUDE_POSITION")


class GraphRAGConfig(BaseAppConfig):
    """GraphRAG 配置"""
    extractor_type: str = Field(default="dynamic", alias="GRAPH_RAG_EXTRACTOR_TYPE")
    max_triplets_per_chunk: int = Field(default=15, alias="GRAPH_RAG_MAX_TRIPLETS_PER_CHUNK")
    num_workers: int = Field(default=4, alias="GRAPH_RAG_NUM_WORKERS")
    entity_hints: Union[List[str], str] = Field(
        default=["港口设备", "系统机构", "备件零件", "规格型号", "存放库位"],
        alias="GRAPH_RAG_ENTITY_HINTS"
    )
    relation_hints: Union[List[str], str] = Field(
        default=["包含", "属于", "规格为", "存放于", "别名为"],
        alias="GRAPH_RAG_RELATION_HINTS"
    )
    llm_provider: str = Field(default="deepseek", alias="GRAPH_RAG_LLM_PROVIDER")
    deepseek_api_key: str = Field(default="", alias="GRAPH_RAG_DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com/v1", alias="GRAPH_RAG_DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-chat", alias="GRAPH_RAG_DEEPSEEK_MODEL")
    deepseek_temperature: float = Field(default=0.7, alias="GRAPH_RAG_DEEPSEEK_TEMPERATURE")

    @field_validator('entity_hints', 'relation_hints', mode='before')
    @classmethod
    def parse_comma_separated(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(',') if item.strip()]
        return v


class GraphRetrievalConfig(BaseAppConfig):
    """图谱检索配置"""
    sub_retrievers: Union[List[str], str] = Field(
        default=["vector", "synonym"],
        alias="GRAPH_RETRIEVAL_SUB_RETRIEVERS"
    )
    vector_top_k: int = Field(default=5, alias="GRAPH_RETRIEVAL_VECTOR_TOP_K")
    vector_path_depth: int = Field(default=1, alias="GRAPH_RETRIEVAL_VECTOR_PATH_DEPTH")
    synonym_max_keywords: int = Field(default=8, alias="GRAPH_RETRIEVAL_SYNONYM_MAX_KEYWORDS")
    synonym_path_depth: int = Field(default=1, alias="GRAPH_RETRIEVAL_SYNONYM_PATH_DEPTH")

    @field_validator('sub_retrievers', mode='before')
    @classmethod
    def parse_comma_separated(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(',') if item.strip()]
        return v


class GraphPerformanceConfig(BaseAppConfig):
    """图谱性能配置"""
    query_cache_ttl: int = Field(default=3600, alias="GRAPH_QUERY_CACHE_TTL")
    cache_max_size: int = Field(default=100, alias="GRAPH_CACHE_MAX_SIZE")


class Config(BaseSettings):
    """全局配置"""
    # 模型配置
    asr: ASRConfig = ASRConfig()
    vlm: VLMConfig = VLMConfig()
    parser: ParserConfig = ParserConfig()

    # 路径配置
    paths: PathsConfig = PathsConfig()

    # RAG 配置
    rag: RAGConfig = RAGConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    rerank: RerankConfig = RerankConfig()
    chunking: ChunkingConfig = ChunkingConfig()

    # GraphRAG 配置
    graph_rag: GraphRAGConfig = GraphRAGConfig()
    graph_retrieval: GraphRetrievalConfig = GraphRetrievalConfig()
    graph_performance: GraphPerformanceConfig = GraphPerformanceConfig()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"  # 允许额外字段
    )


# 全局配置实例
config = Config()
