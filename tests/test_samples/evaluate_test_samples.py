"""
测试样例评估脚本

用于评估VLM解析质量，对比实际输出和期望输出
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.test_samples.test_instruction_samples import (
    TestSample,
    ALL_TEST_SAMPLES,
    get_samples_by_category
)


class FieldEvaluation:
    """单个字段评估结果"""

    def __init__(self, field_name: str, expected: Any, actual: Any):
        self.field_name = field_name
        self.expected = expected
        self.actual = actual
        self.grade = self._calculate_grade()
        self.reason = self._generate_reason()

    def _calculate_grade(self) -> str:
        """计算字段等级：A/B/C"""
        if self.expected is None:
            # 期望为None，实际也为None -> A
            if self.actual is None:
                return "A"
            # 期望为None，实际不为None -> B（可能提取了额外信息）
            return "B"

        if self.actual is None:
            # 期望不为None，实际为None -> C
            return "C"

        # 两者都不为None，比较内容
        if self._is_equal():
            return "A"
        elif self._is_similar():
            return "B"
        else:
            return "C"

    def _is_equal(self) -> bool:
        """判断是否相等"""
        if isinstance(self.expected, str) and isinstance(self.actual, str):
            return self.expected.strip() == self.actual.strip()
        return self.expected == self.actual

    def _is_similar(self) -> bool:
        """判断是否相似（Grade B）"""
        if isinstance(self.expected, str) and isinstance(self.actual, str):
            # 包含关系
            if self.expected in self.actual or self.actual in self.expected:
                return True
            # 忽略大小写
            if self.expected.lower() == self.actual.lower():
                return True
        return False

    def _generate_reason(self) -> str:
        """生成评估原因"""
        if self.grade == "A":
            return "完全准确"
        elif self.grade == "B":
            if self.expected is None:
                return "提取了额外信息（可接受）"
            elif self.actual is None:
                return "未能提取（可接受）"
            else:
                return f"部分准确（期望: {self.expected}, 实际: {self.actual}）"
        else:  # Grade C
            if self.actual is None:
                return "未能提取关键字段"
            else:
                return f"不准确（期望: {self.expected}, 实际: {self.actual}）"


class SampleEvaluation:
    """单个测试样例评估结果"""

    def __init__(self, sample: TestSample, actual_output: Dict[str, Any]):
        self.sample = sample
        self.actual_output = actual_output
        self.field_evaluations = self._evaluate_all_fields()
        self.overall_grade = self._calculate_overall_grade()
        self.passed = self.overall_grade in ["A", "B"]

    def _evaluate_all_fields(self) -> Dict[str, FieldEvaluation]:
        """评估所有字段"""
        fields = [
            "part_name",
            "quantity",
            "model",
            "installation_equipment",
            "location",
            "description",
            "action_required"
        ]

        evaluations = {}
        for field in fields:
            expected = self.sample.expected_output.get(field)
            actual = self.actual_output.get(field)
            evaluations[field] = FieldEvaluation(field, expected, actual)

        return evaluations

    def _calculate_overall_grade(self) -> str:
        """计算整体等级"""
        # part_name 必须 Grade B 及以上
        if self.field_evaluations["part_name"].grade == "C":
            return "C"

        # 统计各等级数量
        non_null_fields = [
            f for f in self.field_evaluations.values()
            if self.sample.expected_output.get(f.field_name) is not None
        ]

        grade_counts = {"A": 0, "B": 0, "C": 0}
        for eval in non_null_fields:
            grade_counts[eval.grade] += 1

        # 判断标准
        total = len(non_null_fields)
        if total == 0:
            return "B"  # 空样例默认 B

        grade_a_ratio = grade_counts["A"] / total
        grade_b_plus_ratio = (grade_counts["A"] + grade_counts["B"]) / total

        if grade_a_ratio >= 0.8 and grade_counts["C"] == 0:
            return "A"
        elif grade_b_plus_ratio >= 0.6 and grade_counts["C"] <= 1:
            return "B"
        else:
            return "C"

    def generate_report(self) -> str:
        """生成评估报告"""
        lines = []
        lines.append(f"\n{'='*80}")
        lines.append(f"测试样例: {self.sample.category} - {self.sample.scenario}")
        lines.append(f"{'='*80}")
        lines.append(f"输入: {self.sample.input_text}")
        if self.sample.image_description:
            lines.append(f"图片: {self.sample.image_description}")
        lines.append(f"备注: {self.sample.notes}")
        lines.append(f"\n{'字段':<25} {'期望':<20} {'实际':<20} {'等级':<5} {'原因'}")
        lines.append(f"{'-'*80}")

        for field_name, evaluation in self.field_evaluations.items():
            if self.sample.expected_output.get(field_name) is not None or evaluation.actual is not None:
                expected_str = str(evaluation.expected)[:20] if evaluation.expected else "None"
                actual_str = str(evaluation.actual)[:20] if evaluation.actual else "None"
                lines.append(
                    f"{field_name:<25} {expected_str:<20} {actual_str:<20} "
                    f"{evaluation.grade:<5} {evaluation.reason}"
                )

        lines.append(f"{'-'*80}")
        lines.append(f"整体等级: {self.overall_grade} | {'✅ 通过' if self.passed else '❌ 不通过'}")
        lines.append(f"{'='*80}")

        return "\n".join(lines)


class TestSuiteEvaluator:
    """测试套件评估器"""

    def __init__(self, samples: List[TestSample] = None):
        self.samples = samples or ALL_TEST_SAMPLES
        self.evaluations: List[SampleEvaluation] = []

    def evaluate_sample(self, sample: TestSample, actual_output: Dict[str, Any]):
        """评估单个样例"""
        evaluation = SampleEvaluation(sample, actual_output)
        self.evaluations.append(evaluation)
        return evaluation

    def generate_summary_report(self) -> str:
        """生成汇总报告"""
        lines = []
        lines.append(f"\n{'='*80}")
        lines.append(f"测试套件评估汇总报告")
        lines.append(f"{'='*80}")
        lines.append(f"评估时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"测试样例总数: {len(self.evaluations)}")

        # 整体统计
        total = len(self.evaluations)
        passed = sum(1 for e in self.evaluations if e.passed)
        grade_a_count = sum(1 for e in self.evaluations if e.overall_grade == "A")
        grade_b_count = sum(1 for e in self.evaluations if e.overall_grade == "B")
        grade_c_count = sum(1 for e in self.evaluations if e.overall_grade == "C")
        pass_rate = (passed / total * 100) if total > 0 else 0

        lines.append(f"\n【整体统计】")
        lines.append(f"  通过: {passed}/{total} ({pass_rate:.1f}%)")
        lines.append(f"  等级 A: {grade_a_count} ({grade_a_count/total*100:.1f}%)")
        lines.append(f"  等级 B: {grade_b_count} ({grade_b_count/total*100:.1f}%)")
        lines.append(f"  等级 C: {grade_c_count} ({grade_c_count/total*100:.1f}%)")

        # 判断整体质量
        if pass_rate >= 90:
            overall_quality = "优秀 ⭐⭐⭐"
        elif pass_rate >= 80:
            overall_quality = "合格 ⭐⭐"
        else:
            overall_quality = "不合格 ⭐"

        lines.append(f"\n【整体质量】: {overall_quality}")

        # 分类统计
        lines.append(f"\n【分类统计】")
        categories = {}
        for evaluation in self.evaluations:
            category = evaluation.sample.category
            if category not in categories:
                categories[category] = {"total": 0, "passed": 0}
            categories[category]["total"] += 1
            if evaluation.passed:
                categories[category]["passed"] += 1

        for category, stats in sorted(categories.items()):
            pass_rate = stats["passed"] / stats["total"] * 100
            lines.append(f"  {category}: {stats['passed']}/{stats['total']} ({pass_rate:.1f}%)")

        # 字段统计
        lines.append(f"\n【字段准确率统计】")
        field_stats = {}
        for evaluation in self.evaluations:
            for field_name, field_eval in evaluation.field_evaluations.items():
                if field_name not in field_stats:
                    field_stats[field_name] = {"A": 0, "B": 0, "C": 0, "total": 0}
                if evaluation.sample.expected_output.get(field_name) is not None:
                    field_stats[field_name][field_eval.grade] += 1
                    field_stats[field_name]["total"] += 1

        for field_name, stats in sorted(field_stats.items()):
            if stats["total"] > 0:
                grade_a_rate = stats["A"] / stats["total"] * 100
                grade_b_plus_rate = (stats["A"] + stats["B"]) / stats["total"] * 100
                lines.append(
                    f"  {field_name}: A={stats['A']}/{stats['total']} ({grade_a_rate:.1f}%), "
                    f"B+={stats['A']+stats['B']}/{stats['total']} ({grade_b_plus_rate:.1f}%)"
                )

        # 失败样例
        failed_evaluations = [e for e in self.evaluations if not e.passed]
        if failed_evaluations:
            lines.append(f"\n【失败样例】 ({len(failed_evaluations)} 个)")
            for i, eval in enumerate(failed_evaluations[:10], 1):  # 最多显示10个
                lines.append(f"  {i}. {eval.sample.category} - {eval.sample.scenario}")
            if len(failed_evaluations) > 10:
                lines.append(f"  ... 还有 {len(failed_evaluations) - 10} 个失败样例")

        lines.append(f"{'='*80}\n")

        return "\n".join(lines)

    def export_report(self, filepath: str):
        """导出评估报告到JSON"""
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": len(self.evaluations),
                "passed": sum(1 for e in self.evaluations if e.passed),
                "grade_a": sum(1 for e in self.evaluations if e.overall_grade == "A"),
                "grade_b": sum(1 for e in self.evaluations if e.overall_grade == "B"),
                "grade_c": sum(1 for e in self.evaluations if e.overall_grade == "C"),
            },
            "samples": [
                {
                    "category": e.sample.category,
                    "scenario": e.sample.scenario,
                    "input": e.sample.input_text,
                    "expected": e.sample.expected_output,
                    "actual": e.actual_output,
                    "overall_grade": e.overall_grade,
                    "passed": e.passed,
                    "field_evaluations": {
                        field: {
                            "grade": eval.grade,
                            "expected": eval.expected,
                            "actual": eval.actual,
                            "reason": eval.reason
                        }
                        for field, eval in e.field_evaluations.items()
                    }
                }
                for e in self.evaluations
            ]
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        print(f"评估报告已导出到: {filepath}")


# ===== 模拟评估（用于测试） =====

def simulate_evaluation():
    """模拟评估流程（不依赖实际VLM）"""
    print("=" * 80)
    print("模拟评估流程")
    print("=" * 80)

    evaluator = TestSuiteEvaluator()

    # 模拟运行部分样例
    samples_to_test = ALL_TEST_SAMPLES[:5]  # 测试前5个样例

    for sample in samples_to_test:
        # 模拟VLM输出（这里使用期望输出，实际应替换为真实VLM输出）
        simulated_output = sample.expected_output.copy()

        # 评估
        evaluation = evaluator.evaluate_sample(sample, simulated_output)

        # 打印报告
        print(evaluation.generate_report())

    # 打印汇总
    print(evaluator.generate_summary_report())

    # 导出报告
    evaluator.export_report("test_evaluation_report.json")


# ===== 命令行工具 =====

def main():
    import argparse

    parser = argparse.ArgumentParser(description="测试样例评估工具")
    parser.add_argument("--category", help="评估特定类别")
    parser.add_argument("--scenario", help="评估特定场景关键词")
    parser.add_argument("--output", help="导出评估报告路径")
    parser.add_argument("--simulate", action="store_true", help="模拟评估（不依赖实际VLM）")

    args = parser.parse_args()

    if args.simulate:
        simulate_evaluation()
        return

    # TODO: 实现实际VLM评估流程
    print("实际VLM评估功能开发中...")
    print("提示：使用 --simulate 参数进行模拟评估")
    print("\n示例：")
    print("  python evaluate_test_samples.py --simulate")
    print("  python evaluate_test_samples.py --category '基础场景' --simulate")


if __name__ == "__main__":
    main()
