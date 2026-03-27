"""
测试 RAG 上下文注入功能
"""
from src.rag import initialize_rag_system, get_unified_rag_manager

def test_rag_context(mode: str, query: str):
    """测试 RAG 上下文注入"""
    mode_name = "传统 RAG" if mode == 'traditional' else "GraphRAG"
    print("=" * 60)
    print(f"测试 {mode_name} 上下文注入")
    print("=" * 60)

    # 初始化 RAG
    success = initialize_rag_system(mode=mode)
    if not success:
        print(f"❌ {mode_name} 初始化失败")
        if mode == 'graph':
            print("   提示: 可能未配置 DeepSeek API Key")
        return

    manager = get_unified_rag_manager()

    print(f"\n📝 查询: {query}")
    print("-" * 60)

    # 执行检索
    results = manager.retrieve(query)
    print(f"🔍 检索到 {len(results)} 个结果\n")

    if not results:
        print("❌ 未检索到任何结果")
        return

    # 格式化上下文
    context = manager.format_context(results)

    # 输出注入的上下文
    print("📋 注入的上下文内容:")
    print("=" * 60)
    print(context)
    print("=" * 60)

    # 验证是否包含分数
    has_score = '[' in context and '.3f' in context
    print(f"\n✅ 验证结果: {'❌ 包含分数' if has_score else '✅ 不包含分数'}")

if __name__ == "__main__":
    print("RAG 上下文注入测试工具")
    print("=" * 60)

    # 选择模式
    print("\n请选择 RAG 模式:")
    print("1. 传统 RAG (向量检索)")
    print("2. GraphRAG (知识图谱)")

    while True:
        choice = input("\n请输入选项 (1/2): ").strip()
        if choice == '1':
            mode = 'traditional'
            break
        elif choice == '2':
            mode = 'graph'
            break
        else:
            print("❌ 无效选项，请重新输入")

    # 输入查询
    query = input("\n请输入测试查询: ").strip()
    if not query:
        query = "需要5个电机，紧急"
        print(f"使用默认查询: {query}")

    # 执行测试
    test_rag_context(mode, query)
