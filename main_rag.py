"""
统一的 RAG 检索系统
支持传统 RAG 和 GraphRAG 两种检索模式

使用方式:
    python main_rag.py  # 启动并选择系统
"""
import logging
import sys
from typing import Optional

from src.rag import get_rag_instance, check_rag_available
from src.graph_rag import get_graph_rag_instance, check_graph_rag_available

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class UnifiedRAGCLI:
    """统一的 RAG 命令行界面"""

    def __init__(self):
        self.mode: Optional[str] = None  # 'rag' or 'graph'
        self.rag = None
        self.graph_rag = None
        self.running = True

    def show_welcome_menu(self):
        """显示欢迎菜单，让用户选择系统"""
        print("=" * 60)
        print("  RAG 检索系统 - 系统选择")
        print("=" * 60)
        print()
        print("请选择要使用的 RAG 系统:")
        print()
        print("  1. 传统 RAG (向量检索)")
        print("     - 基于 BGE-M3 嵌入")
        print("     - 支持混合检索 (BM25 + 向量)")
        print("     - 支持重排序")
        print()
        print("  2. GraphRAG (知识图谱)")
        print("     - 基于知识图谱的检索")
        print("     - 支持多跳关系推理")
        print("     - 适合复杂关系查询")
        print()
        print("=" * 60)

        while True:
            try:
                choice = input("  输入选择 (1 或 2): ").strip()
                if choice == '1':
                    self.mode = 'rag'
                    print("\n已选择: 传统 RAG 模式")
                    return True
                elif choice == '2':
                    self.mode = 'graph'
                    print("\n已选择: GraphRAG 模式")
                    return True
                else:
                    print("  [错误] 请输入 1 或 2")
            except KeyboardInterrupt:
                print("\n\n程序已退出")
                return False

    def initialize_rag(self):
        """初始化传统 RAG 系统"""
        if not check_rag_available():
            print("\n[错误] RAG 依赖未安装")
            print("请运行: pip install -r requirements.txt")
            return False

        print("正在初始化传统 RAG 模块...")
        self.rag = get_rag_instance()

        if not self.rag or not self.rag.is_enabled():
            print("[错误] RAG 初始化失败")
            return False

        print("[成功] RAG 模块初始化完成")
        return True

    def initialize_graph_rag(self):
        """初始化 GraphRAG 系统"""
        if not check_graph_rag_available():
            print("\n[错误] GraphRAG 依赖未安装")
            print("请运行: pip install -r requirements.txt")
            return False

        print("正在初始化 GraphRAG 模块...")
        self.graph_rag = get_graph_rag_instance()

        if not self.graph_rag or not self.graph_rag.is_enabled():
            print("[错误] GraphRAG 初始化失败")
            return False

        print("[成功] GraphRAG 模块初始化完成")
        return True

    def show_rag_status(self):
        """显示 RAG 状态（基础配置）"""
        if not self.rag:
            return

        status = self.rag.get_status()

        print("\n[系统状态]")
        print(f"  嵌入模型: {status['embedding_model']}")
        print(f"  设备: {status['device']}")
        print(f"  检索模式: {status['retrieval_mode']}")
        print(f"  Top-K: {status['top_k']}")
        print(f"  混合检索: {'启用' if status['hybrid_enabled'] else '禁用'}")
        print(f"  重排序: {'启用' if status['rerank_enabled'] else '禁用'}")

        if 'thresholds' in status:
            print(f"\n[检索阈值]")
            print(f"  严格: {status['thresholds']['strict']}")
            print(f"  中等: {status['thresholds']['medium']}")
            print(f"  宽松: {status['thresholds']['relaxed']}")

        print(f"\n[路径]")
        print(f"  知识库: {status['knowledge_base_path']}")
        print(f"  向量库: {status['vector_db_path']}")

    def show_graph_rag_stats(self):
        """显示 GraphRAG 状态（基础配置）"""
        if not self.graph_rag:
            return

        status = self.graph_rag.get_status()
        graph_stats = status.get('graph_stats', {})

        print("\n[系统状态]")
        print(f"  嵌入模型: {status.get('embedding_model', 'N/A')}")
        print(f"  设备: {status.get('device', 'N/A')}")
        print(f"  子检索器: {', '.join(status.get('sub_retrievers', []))}")
        print(f"  Top-K: {status.get('top_k', 'N/A')}")

        print(f"\n[图谱统计]")
        print(f"  节点数: {graph_stats.get('node_count', 0)}")
        print(f"  关系数: {graph_stats.get('relation_count', 0)}")

        print(f"\n[路径]")
        print(f"  知识库: {status.get('knowledge_base_path', 'N/A')}")
        print(f"  图谱存储: {graph_stats.get('graph_store_path', 'N/A')}")

    def run_rag_mode(self):
        """运行传统 RAG 模式"""
        print("\n" + "=" * 60)
        print("[RAG 系统] 模式: 传统向量检索")
        print("=" * 60)
        print()
        print("可用命令:")
        print("  查询文本       - 执行检索")
        print("  status         - 显示系统状态")
        print("  rebuild        - 重建索引")
        print("  help           - 显示帮助")
        print("  quit           - 退出系统")
        print("=" * 60)

        while self.running:
            try:
                user_input = input("\n查询> ").strip()

                if not user_input:
                    continue

                # 处理命令
                if user_input.lower() == 'quit':
                    print("\n再见！")
                    break

                elif user_input.lower() == 'help':
                    print("\n可用命令:")
                    print("  查询文本       - 执行检索")
                    print("  status         - 显示系统状态")
                    print("  rebuild        - 重建索引")
                    print("  help           - 显示帮助")
                    print("  quit           - 退出系统")

                elif user_input.lower() == 'status':
                    self.show_rag_status()

                elif user_input.lower() == 'rebuild':
                    self.rag_rebuild()

                # 执行检索
                else:
                    self.rag_search(user_input)

            except KeyboardInterrupt:
                print("\n\n程序已退出")
                break

            except Exception as e:
                logger.error(f"处理命令时出错: {e}")
                print(f"[错误] {e}")

    def run_graph_rag_mode(self):
        """运行 GraphRAG 模式"""
        print("\n" + "=" * 60)
        print("[GraphRAG 系统] 模式: 知识图谱检索")
        print("=" * 60)
        print()
        print("可用命令:")
        print("  查询文本       - 执行图谱检索")
        print("  stats          - 显示图谱统计")
        print("  rebuild        - 重建图谱索引")
        print("  help           - 显示帮助")
        print("  quit           - 退出系统")
        print("=" * 60)

        while self.running:
            try:
                user_input = input("\n查询> ").strip()

                if not user_input:
                    continue

                # 处理命令
                if user_input.lower() == 'quit':
                    print("\n再见！")
                    break

                elif user_input.lower() == 'help':
                    print("\n可用命令:")
                    print("  查询文本       - 执行图谱检索")
                    print("  stats          - 显示图谱统计")
                    print("  rebuild        - 重建图谱索引")
                    print("  help           - 显示帮助")
                    print("  quit           - 退出系统")

                elif user_input.lower() == 'stats':
                    self.show_graph_rag_stats()

                elif user_input.lower() == 'rebuild':
                    self.graph_rag_rebuild()

                # 执行检索
                else:
                    self.graph_rag_search(user_input)

            except KeyboardInterrupt:
                print("\n\n程序已退出")
                break

            except Exception as e:
                logger.error(f"处理命令时出错: {e}")
                print(f"[错误] {e}")

    def rag_search(self, query: str):
        """执行传统 RAG 检索"""
        if not query or not query.strip():
            print("[提示] 请输入查询内容")
            return

        print(f"\n[检索中] 查询: {query}")
        print("-" * 60)

        try:
            results = self.rag.retrieve(query)

            if not results:
                print("[结果] 未找到相关文档")
                return

            print(f"[结果] 检索到 {len(results)} 个相关文档\n")
            for i, result in enumerate(results, 1):
                self._display_rag_result(i, result)

        except Exception as e:
            logger.error(f"检索失败: {e}")
            print(f"[错误] 检索失败: {e}")

    def _display_rag_result(self, index: int, result: dict):
        """显示 RAG 检索结果"""
        metadata = result.get('metadata', {})
        file_path = metadata.get('file_path', '未知来源')

        print(f"【结果 {index}】")
        print(f"  来源: {file_path}")

        # 显示分数
        scores = []
        if 'score' in result:
            scores.append(f"向量相似度={result['score']:.3f}")
        if 'rerank_score' in result:
            scores.append(f"重排序={result['rerank_score']:.3f}")

        if scores:
            print(f"  分数: {', '.join(scores)}")

        # 显示内容
        text = result['text']
        print(f"  内容:\n    {text}\n")

    def graph_rag_search(self, query: str):
        """执行 GraphRAG 检索"""
        if not query or not query.strip():
            print("[提示] 请输入查询内容")
            return

        print(f"\n[检索中] 查询: {query}")
        print("-" * 60)

        try:
            results = self.graph_rag.retrieve(query)

            if not results:
                print("[结果] 未找到相关节点")
                return

            print(f"[结果] 检索到 {len(results)} 个相关节点\n")
            for i, result in enumerate(results, 1):
                self._display_graph_rag_result(i, result)

        except Exception as e:
            logger.error(f"图谱检索失败: {e}")
            print(f"[错误] 检索失败: {e}")

    def _display_graph_rag_result(self, index: int, result: dict):
        """显示 GraphRAG 检索结果"""
        metadata = result.get('metadata', {})

        print(f"【节点 {index}】")
        print(f"  类型: 图谱节点")

        # 显示分数
        if 'score' in result:
            print(f"  分数: {result['score']:.3f}")

        # 显示元数据
        if metadata:
            print(f"  元数据: {metadata}")

        # 显示内容
        text = result['text']
        print(f"  内容:\n    {text}\n")

    def rag_rebuild(self):
        """重建 RAG 索引"""
        print("\n[重建索引]")
        print("正在重新构建向量索引...")
        print("提示: 修改 .env 后重建索引可应用新配置\n")

        success = self.rag.rebuild_index()

        if success:
            print("[成功] 向量索引重建完成")
            print("\n更新后的配置:")
            self.show_rag_status()
        else:
            print("[失败] 向量索引重建失败，请检查日志")

    def graph_rag_rebuild(self):
        """重建 GraphRAG 索引"""
        print("\n[重建索引]")
        print("正在重新构建知识图谱...")
        print("提示: 修改 .env 后重建索引可应用新配置\n")

        success = self.graph_rag.rebuild_index()

        if success:
            print("[成功] 图谱索引重建完成")
            print("\n更新后的配置:")
            self.show_graph_rag_stats()
        else:
            print("[失败] 图谱索引重建失败，请检查日志")

    def run(self):
        """主运行入口"""
        # 显示欢迎菜单
        if not self.show_welcome_menu():
            return

        # 根据选择初始化系统
        if self.mode == 'rag':
            if not self.initialize_rag():
                print("\n初始化失败，程序退出")
                return
            self.show_rag_status()
            self.run_rag_mode()

        elif self.mode == 'graph':
            if not self.initialize_graph_rag():
                print("\n初始化失败，程序退出")
                return
            self.show_graph_rag_stats()
            self.run_graph_rag_mode()


def main():
    """主函数"""
    cli = UnifiedRAGCLI()
    cli.run()


if __name__ == "__main__":
    main()
