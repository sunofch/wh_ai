"""
自定义图提取器：港口领域实体和关系提取

根据 LlamaIndex 官方文档重构：
- 支持多种提取器类型
- 使用配置化的实体和关系提示
- 支持并行处理

参考文档：
https://docs.llamaindex.org.cn/en/stable/module_guides/indexing/lpg_index_guide/
"""
from typing import List, Optional, Any
from llama_index.core.indices.property_graph import (
    ImplicitPathExtractor,
    DynamicLLMPathExtractor,
    SimpleLLMPathExtractor,
    SchemaLLMPathExtractor,
)


def create_kg_extractors(config: Any, llm: Optional[Any] = None) -> List[Any]:
    """创建知识图谱提取器

    根据 LlamaIndex 官方文档，支持多种提取器：
    - ImplicitPathExtractor: 隐式提取器（无需 LLM，快速）
    - DynamicLLMPathExtractor: 动态 LLM 提取器（推荐，支持实体类型）
    - SimpleLLMPathExtractor: 简单 LLM 提取器（基础）

    Args:
        config: GraphRAGConfig 配置对象
        llm: LLM 实例，如果为 None 则跳过需要 LLM 的提取器

    Returns:
        提取器列表
    """
    extractors = []

    # 1. 隐式提取器（始终启用，无开销）
    extractors.append(ImplicitPathExtractor())

    # 2. 根据 extractor_type 配置创建提取器
    if config.extractor_type == "dynamic" and llm is not None:
        extractors.append(_create_dynamic_extractor(config, llm))
    elif config.extractor_type == "simple" and llm is not None:
        extractors.append(_create_simple_extractor(config, llm))
    elif config.extractor_type == "schema" and llm is not None:
        extractors.append(_create_schema_extractor(config, llm))

    return extractors


def _create_dynamic_extractor(config: Any, llm: Any) -> DynamicLLMPathExtractor:
    """创建动态 LLM 提取器（推荐）

    支持配置实体和关系类型提示，LLM 可以自由推断
    """
    return DynamicLLMPathExtractor(
        llm=llm,
        allowed_entity_types=config.entity_hints,
        allowed_relation_types=config.relation_hints,
        max_triplets_per_chunk=config.max_triplets_per_chunk,
        num_workers=config.num_workers,
    )


def _create_simple_extractor(config: Any, llm: Any) -> SimpleLLMPathExtractor:
    """创建简单 LLM 提取器

    基础的 LLM 提取器，提取单跳路径
    """
    return SimpleLLMPathExtractor(
        llm=llm,
        max_paths_per_chunk=config.max_triplets_per_chunk,
        num_workers=config.num_workers,
    )


def _create_schema_extractor(config: Any, llm: Any) -> SchemaLLMPathExtractor:
    """创建模式 LLM 提取器

    严格遵循定义的模式，提供更高的准确性
    """
    from typing import Literal

    # 从配置获取实体和关系类型
    entity_types = config.entity_hints if config.entity_hints else ["ENTITY"]
    relation_types = config.relation_hints if config.relation_hints else ["RELATION"]

    # 创建字面量类型
    if isinstance(entity_types, list) and len(entity_types) > 1:
        entities_literal = Literal[tuple(entity_types)]
    else:
        entities_literal = Literal["ENTITY"]

    if isinstance(relation_types, list) and len(relation_types) > 1:
        relations_literal = Literal[tuple(relation_types)]
    else:
        relations_literal = Literal["RELATION"]

    # 创建模式（所有实体可以连接所有关系）
    schema = {entity: relation_types for entity in entity_types}

    return SchemaLLMPathExtractor(
        llm=llm,
        possible_entities=entities_literal,
        possible_relations=relations_literal,
        kg_validation_schema=schema,
        strict=False,
        num_workers=config.num_workers,
        max_triplets_per_chunk=config.max_triplets_per_chunk,
    )
