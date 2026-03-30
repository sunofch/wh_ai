"""
测试样例快速演示脚本

展示测试样例的结构和使用方法
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.test_samples import (
    ALL_TEST_SAMPLES,
    get_samples_by_category,
    print_sample_summary
)


def show_sample_examples():
    """展示各类测试样例示例"""
    print("\n" + "="*80)
    print("港口指令解析系统 - 测试样例示例")
    print("="*80)

    categories = [
        "基础场景",
        "设备特定",
        "行动类型",
        "复杂场景",
        "边界情况",
        "专业术语",
        "多模态输入",
        "音频输入"
    ]

    for category in categories:
        samples = get_samples_by_category(category)
        if not samples:
            continue

        print(f"\n{'='*80}")
        print(f"【{category}】 - {len(samples)} 个样例")
        print(f"{'='*80}")

        # 展示前2个样例
        for i, sample in enumerate(samples[:2], 1):
            print(f"\n样例 {i}: {sample.scenario}")
            print(f"  输入: {sample.input_text}")
            if sample.image_description:
                print(f"  图片: {sample.image_description}")
            print(f"  期望输出:")
            for field, value in sample.expected_output.items():
                if value is not None:
                    print(f"    {field}: {value}")
            if sample.notes:
                print(f"  备注: {sample.notes}")

        if len(samples) > 2:
            print(f"\n  ... 还有 {len(samples) - 2} 个样例")


def show_quality_standards():
    """展示质量标准"""
    print("\n" + "="*80)
    print("质量评估标准")
    print("="*80)

    print("\n【字段等级标准】")
    print("  Grade A (优秀): 完全准确")
    print("  Grade B (合格): 基本正确，但有小问题")
    print("  Grade C (不合格): 字段错误或未提取")

    print("\n【整体等级标准】")
    print("  Overall A: 所有关键字段准确，≥ 80% 非空字段 Grade A，无 Grade C")
    print("  Overall B: 关键字段 Grade B+，≥ 60% 非空字段 Grade B+，Grade C ≤ 1")
    print("  Overall C: 不满足 Overall B")

    print("\n【通过标准】")
    print("  优秀: ≥ 90% 测试用例达到 Overall A")
    print("  合格: ≥ 80% 测试用例达到 Overall B 及以上")
    print("  不合格: < 80% 测试用例达到 Overall B 及以上")


def show_usage_examples():
    """展示使用示例"""
    print("\n" + "="*80)
    print("代码使用示例")
    print("="*80)

    print("\n【示例1: 获取所有测试样例】")
    print("""
from tests.test_samples import ALL_TEST_SAMPLES

for sample in ALL_TEST_SAMPLES:
    print(f"输入: {sample.input_text}")
    print(f"期望: {sample.expected_output}")
    """)

    print("\n【示例2: 获取特定类别样例】")
    print("""
from tests.test_samples import get_samples_by_category

basic_samples = get_samples_by_category("基础场景")
for sample in basic_samples:
    # 测试基础场景
    pass
    """)

    print("\n【示例3: 与VLM集成测试】")
    print("""
from tests.test_samples import ALL_TEST_SAMPLES
from main_interaction import InstructionParser

parser = InstructionParser()

for sample in ALL_TEST_SAMPLES:
    # 调用解析器
    actual_output = parser.parse_text(sample.input_text)

    # 对比期望输出
    expected = sample.expected_output
    # ... 评估逻辑
    """)


def show_statistics():
    """展示统计信息"""
    print("\n" + "="*80)
    print("测试样例统计")
    print("="*80)

    total = len(ALL_TEST_SAMPLES)
    print(f"\n测试样例总数: {total}")

    # 分类统计
    from collections import Counter
    categories = [s.category for s in ALL_TEST_SAMPLES]
    category_counts = Counter(categories)

    print("\n【分类统计】")
    for category, count in category_counts.most_common():
        print(f"  {category}: {count} 个样例")

    # 场景关键词统计
    print("\n【场景覆盖】")
    scenario_keywords = {
        "岸桥": 0, "RTG": 0, "堆高机": 0, "输送机": 0,
        "更换": 0, "维修": 0, "检查": 0, "采购": 0,
        "图片": 0, "音频": 0
    }

    for sample in ALL_TEST_SAMPLES:
        text = sample.input_text + " " + sample.scenario
        for keyword in scenario_keywords:
            if keyword in text or sample.image_description:
                scenario_keywords[keyword] += 1

    for keyword, count in scenario_keywords.items():
        if count > 0:
            print(f"  {keyword}: {count} 个样例")


def main():
    """主函数"""
    # 打印统计摘要
    print_sample_summary()

    # 展示样例示例
    show_sample_examples()

    # 展示质量标准
    show_quality_standards()

    # 展示使用示例
    show_usage_examples()

    # 展示统计信息
    show_statistics()

    print("\n" + "="*80)
    print("更多信息请参考: tests/test_samples/README.md")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
