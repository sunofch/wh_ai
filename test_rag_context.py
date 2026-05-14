"""
RAG 检索调试工具：查看送给 agent 的检索内容
"""
from src.rag import initialize_rag_system, get_unified_rag_manager


def run():
    print("\nRAG 检索调试")
    print("=" * 60)
    print("1. 传统 RAG (向量检索)")
    print("2. GraphRAG (知识图谱)")

    while True:
        choice = input("\n请选择 RAG 模式 (1/2): ").strip()
        if choice == "1":
            mode = "traditional"
            break
        elif choice == "2":
            mode = "graph"
            break
        else:
            print("无效选项，请重新输入")

    success = initialize_rag_system(mode=mode)
    if not success:
        print("❌ RAG 初始化失败")
        return

    manager = get_unified_rag_manager()
    print(f"\n✅ 初始化完成（模式: {mode}），直接回车退出\n")

    while True:
        query = input("请输入查询: ").strip()
        if not query:
            break

        results = manager.retrieve(query)
        print(f"\n检索到 {len(results)} 条结果")
        print("-" * 60)

        for idx, r in enumerate(results, 1):
            score = r.get("score", 0)
            text = r.get("text", "")
            print(f"[{idx}] score={score:.3f}")
            print(text)
            print()

        print("-" * 60 + "\n")


if __name__ == "__main__":
    run()
