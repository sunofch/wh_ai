# GraphRAG Reranker 性能基准

## 测试环境

- 日期: 2026-03-27
- GraphRAG 启用: True
- Reranker 启用: **False (基准测试)**
- 知识库: 港口设备备件文档

## 初始化性能

- GraphRAG 初始化耗时: **16.870s**
  - 包含嵌入模型加载 (BGE-M3)
  - 图谱索引加载

## 查询性能基准

| 查询 | 耗时 | 结果数 | rerank_score |
|------|------|--------|--------------|
| bwpg | 0.226s | 3 | ❌ |
| bcdp | 0.022s | 3 | ❌ |
| sdpg | 0.022s | 3 | ❌ |
| 溜槽耐磨板 | 0.024s | 3 | ❌ |

**平均查询耗时: 0.074s** (不含初始化)

## 后续测试

启用 Reranker 后，重新运行相同测试以评估：
1. 查询耗时变化（预期略有增加）
2. 结果质量提升（通过 rerank_score 评估）
3. Top-K 准确性改善

## 测试命令

```bash
python -c "
import time
from src.graph_rag import GraphRAGRetriever
from src.config import config

print('=== GraphRAG 性能基准测试 ===')
print(f'Reranker 启用状态: {config.graph_rerank.enabled}')
print()

retriever = GraphRAGRetriever()

test_queries = ['bwpg', 'bcdp', 'sdpg', '溜槽耐磨板']
print('测试查询性能:')
print('-' * 60)

for query in test_queries:
    start = time.time()
    results = retriever.retrieve(query)
    elapsed = time.time() - start
    print(f'查询: {query:20s} | 耗时: {elapsed:.3f}s | 结果数: {len(results)}')
    if results and 'rerank_score' in results[0]:
        print(f'  └─ 最高 rerank_score: {results[0].get(\"rerank_score\", 0):.4f}')
"
```
