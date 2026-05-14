# Neo4j 使用说明

本项目使用 Neo4j 作为 GraphRAG 的图谱存储后端，替代原有的本地 JSON 文件存储。

---

## 服务管理

```bash
sudo neo4j start     # 启动
sudo neo4j stop      # 停止
sudo neo4j restart   # 重启
sudo neo4j status    # 查看状态
```

Web 控制台：`http://localhost:7474`，账号 `neo4j`，密码见 `.env`。

---

## 配置（.env）

```ini
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=sunofch1
NEO4J_DATABASE=neo4j
```

---

## 图谱数据生命周期

### 首次运行

启动任意使用 GraphRAG 的程序（如 `python main_rag.py` 选择 GraphRAG 模式），系统检测到 Neo4j 为空，自动从 `data/knowledge_base/` 构建图谱并写入，耗时取决于文档量。

### 后续运行

检测到 Neo4j 已有数据，直接加载，无需重建。

### 手动重建

在代码中调用 `rebuild_index()`，或直接用 cypher-shell 清空后重启应用：

```bash
cypher-shell -u neo4j -p sunofch1 "MATCH (n) DETACH DELETE n;"
```

---

## 检索模式（GRAPH_RETRIEVAL_VECTOR_INCLUDE_TEXT）

在 `.env` 中控制检索结果内容：

| 值 | 行为 |
|----|------|
| `false`（默认） | 返回主语实体的全部三元组（精准模式） |
| `true` | 返回三元组 + 原始文档块（完整上下文模式） |

**`false` 时的查询逻辑：**

1. 向量搜索命中匹配三元组，例如：`防冲击护目镜 -> 型号为 -> VMaxx-OTG-CLR-UVEX`
2. 提取主语实体：`防冲击护目镜`
3. 查询该实体在 Neo4j 中的全部出向三元组返回

---

## 常用 Cypher 操作

```bash
# 进入交互式 shell
cypher-shell -u neo4j -p sunofch1
```

```cypher
-- 查看节点总数
MATCH (n) RETURN count(n);

-- 查看所有实体（前20个）
MATCH (n) RETURN n.name LIMIT 20;

-- 查询某实体的全部关系
MATCH (n)-[r]->(m) WHERE n.name = "深沟球轴承"
RETURN n.name, type(r), m.name;

-- 查看图谱 schema
CALL apoc.meta.schema();

-- 清空所有数据（触发重建）
MATCH (n) DETACH DELETE n;
```

---

## 调试工具

```bash
python test_rag_context.py
```

选择 GraphRAG 模式后循环输入查询，直接显示检索到的三元组内容（即送给 agent 的信息）。

---

## 依赖说明

- **APOC 插件**：`Neo4jPropertyGraphStore` 初始化时需要 `apoc.meta.data()`，必须安装
- **Python 包**：`llama-index-graph-stores-neo4j>=0.7.0`、`neo4j>=5.28.4`

完整安装步骤见 `docs/neo4j_setup.md`。
