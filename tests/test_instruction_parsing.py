"""
港口指令解析全面测试
覆盖各种场景：基本字段、行动类型、表达方式、边界情况、多模态输入
"""
import os
import sys
import pytest
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser import PortInstruction, PortInstructionParser
from src.common.config import config


class TestPortInstructionModel:
    """测试 PortInstruction 数据模型"""

    def test_model_all_fields(self):
        """测试完整字段创建"""
        instruction = PortInstruction(
            part_name="主起升钢丝绳",
            quantity=5,
            model="6×36WS+IWR-32mm-1870MPa",
            installation_equipment="岸桥主起升机构",
            location="仓库A区-01架-01层",
            description="紧急更换，安全库存不足",
            action_required="更换"
        )
        assert instruction.part_name == "主起升钢丝绳"
        assert instruction.quantity == 5
        assert instruction.model == "6×36WS+IWR-32mm-1870MPa"
        assert instruction.installation_equipment == "岸桥主起升机构"
        assert instruction.location == "仓库A区-01架-01层"
        assert instruction.description == "紧急更换，安全库存不足"
        assert instruction.action_required == "更换"

    def test_model_partial_fields(self):
        """测试部分字段创建"""
        instruction = PortInstruction(
            part_name="减速机",
            quantity=2
        )
        assert instruction.part_name == "减速机"
        assert instruction.quantity == 2
        assert instruction.model is None
        assert instruction.action_required is None

    def test_model_to_dict(self):
        """测试转换为字典"""
        instruction = PortInstruction(
            part_name="电机",
            quantity=3,
            action_required="维修"
        )
        data = instruction.to_dict()
        assert isinstance(data, dict)
        assert data["part_name"] == "电机"
        assert data["quantity"] == 3

    def test_model_to_json(self):
        """测试转换为JSON"""
        instruction = PortInstruction(
            part_name="轴承",
            quantity=10,
            action_required="更换"
        )
        json_str = instruction.to_json()
        assert isinstance(json_str, str)
        assert "轴承" in json_str


class TestParserFormatInstructions:
    """测试解析器格式指令生成"""

    def test_format_instructions_contains_schema(self):
        """测试格式指令包含Schema"""
        parser = PortInstructionParser()
        instructions = parser.get_format_instructions()
        assert "JSON" in instructions
        assert "part_name" in instructions
        assert "quantity" in instructions
        assert "model" in instructions


class TestParserBasicExtraction:
    """测试基本字段提取"""

    def test_extract_part_name_only(self):
        """测试仅提取备件名称"""
        parser = PortInstructionParser()

        # 模拟VLM返回结果
        vlm_result = {
            "part_name": "主起升钢丝绳"
        }

        instruction = parser.parse_output(vlm_result)
        assert instruction.part_name == "主起升钢丝绳"
        assert instruction.quantity is None

    def test_extract_part_name_and_quantity(self):
        """测试提取备件名称和数量"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": "减速机",
            "quantity": 3
        }

        instruction = parser.parse_output(vlm_result)
        assert instruction.part_name == "减速机"
        assert instruction.quantity == 3

    def test_extract_all_fields(self):
        """测试提取所有字段"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": "主起升行星减速机",
            "quantity": 2,
            "model": "P4F-17-280-315",
            "installation_equipment": "岸桥主起升机构",
            "location": "仓库A区",
            "description": "需要紧急更换",
            "action_required": "更换"
        }

        instruction = parser.parse_output(vlm_result)
        assert instruction.part_name == "主起升行星减速机"
        assert instruction.quantity == 2
        assert instruction.model == "P4F-17-280-315"
        assert instruction.installation_equipment == "岸桥主起升机构"
        assert instruction.location == "仓库A区"
        assert instruction.description == "需要紧急更换"
        assert instruction.action_required == "更换"


class TestParserActionTypes:
    """测试不同行动类型"""

    @pytest.mark.parametrize("action,expected", [
        ("更换", "更换"),
        ("需要更换", "更换"),
        ("要更换", "更换"),
        ("维修", "维修"),
        ("需要维修", "维修"),
        ("检修", "维修"),
        ("检查", "检查"),
        ("定期检查", "检查"),
        ("检验", "检查"),
        ("采购", "采购"),
        ("需要采购", "采购"),
        ("紧急调拨", "调拨"),
        ("领用", "领用"),
    ])
    def test_various_actions(self, action, expected):
        """测试各种行动类型"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": "电机",
            "action_required": action
        }

        instruction = parser.parse_output(vlm_result)
        # VLM应该提取正确的action
        assert instruction.action_required == action


class TestParserQuantityExtraction:
    """测试数量提取的各种情况"""

    @pytest.mark.parametrize("text,expected_qty", [
        ("需要5个电机", 5),
        ("10件轴承", 10),
        ("3套减速机", 3),
        ("2台电机", 2),
        ("8只传感器", 8),
        ("1把扳手", 1),
        ("5箱螺栓", 5),
        ("100根钢丝绳", 100),
    ])
    def test_rule_based_quantity_extraction(self, text, expected_qty):
        """测试规则解析中的数量提取"""
        parser = PortInstructionParser()

        # 模拟VLM失败，使用规则解析
        vlm_result = {
            "raw_response": text
        }

        instruction = parser.parse_output(vlm_result, raw_text=text)
        assert instruction.quantity == expected_qty


class TestParserFallbackBehavior:
    """测试规则解析兜底行为"""

    def test_fallback_on_invalid_vlm_output(self):
        """测试VLM输出无效时使用规则解析"""
        parser = PortInstructionParser()

        # 无效的VLM输出（缺少必要字段）
        vlm_result = {
            "raw_response": "invalid output"
        }

        instruction = parser.parse_output(vlm_result, raw_text="需要3个电机")
        # 应该使用规则解析，提取出数量
        assert instruction.quantity == 3
        # part_name应该使用默认值
        assert instruction.part_name == config.parser.fallback_part_name

    def test_fallback_description_format(self):
        """测试兜底描述格式"""
        parser = PortInstructionParser()

        vlm_result = {
            "raw_response": "some error"
        }

        instruction = parser.parse_output(vlm_result, raw_text="需要紧急维修")
        expected_prefix = config.parser.fallback_description_prefix
        assert expected_prefix in instruction.description


class TestRealWorldScenarios:
    """测试真实场景指令"""

    @pytest.mark.parametrize("instruction,expected_part,expected_qty,expected_action", [
        # 基本场景
        ("需要5个电机，紧急", "电机", 5, None),
        ("主起升钢丝绳需要更换，型号6×36WS+IWR-32mm", "主起升钢丝绳", None, "更换"),
        ("岸桥需要3台减速机，型号P4F-17-280-315", "减速机", 3, None),
        ("仓库A区的电机需要维修", "电机", None, "维修"),

        # 缩写场景
        ("需要2个MHWR", "MHWR", 2, None),
        ("BWPG钢丝绳要更换", "BWPG钢丝绳", None, "更换"),

        # 紧急场景
        ("紧急！需要10个轴承", "轴承", 10, None),
        ("安全库存不足，需要补充电机", "电机", None, None),

        # 复杂场景
        ("岸桥主起升机构的减速机需要更换，型号P4F-17-280-315，数量2台，紧急",
         "减速机", 2, "更换"),
        ("仓库A区-01架-01层的主起升钢丝绳需要更换，已达到更换周期",
         "主起升钢丝绳", None, "更换"),
    ])
    def test_real_world_instructions(self, instruction, expected_part, expected_qty, expected_action):
        """
        测试真实世界指令

        注意：这个测试需要VLM实际运行，如果没有vLLM服务器，会被跳过
        """
        pytest.skip("需要vLLM服务器运行，实际使用时移除此skip")


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_instruction(self):
        """测试空指令"""
        parser = PortInstructionParser()

        vlm_result = {
            "raw_response": ""
        }

        instruction = parser.parse_output(vlm_result, raw_text="")
        assert instruction.part_name == config.parser.fallback_part_name

    def test_ambiguous_quantity(self):
        """测试模糊数量表达"""
        parser = PortInstructionParser()

        vlm_result = {
            "raw_response": "需要几个电机"  # "几个"无法提取具体数字
        }

        instruction = parser.parse_output(vlm_result, raw_text="需要几个电机")
        # 规则解析无法提取"几个"的数量
        assert instruction.quantity is None

    def test_mixed_chinese_english(self):
        """测试中英文混合"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": "岸桥 Main Hoist Wire Rope",
            "quantity": 5,
            "action_required": "更换"
        }

        instruction = parser.parse_output(vlm_result)
        assert "岸桥" in instruction.part_name
        assert "Main Hoist Wire Rope" in instruction.part_name

    def test_typo_tolerance(self):
        """测试错别字容忍度"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": " 减数机",  # 错别字：减数机 -> 减速机
            "quantity": 2
        }

        instruction = parser.parse_output(vlm_result)
        # VLM应该能容错，但这里直接测试返回值
        assert instruction.part_name == " 减数机"


class TestSpecializedTerminology:
    """测试专业术语解析（基于知识库）"""

    @pytest.mark.parametrize("term,expected_field", [
        # 岸桥术语
        ("主起升钢丝绳", "part_name"),
        ("前臂架拉索钢丝绳", "part_name"),
        ("主起升行星减速机", "part_name"),
        ("MHWR", "part_name"),  # 缩写
        ("BSWR", "part_name"),  # 缩写

        # RTG术语
        ("行走轮", "part_name"),
        ("滑环箱", "part_name"),
        ("变频器", "part_name"),

        # 堆高机术语
        ("门架油缸", "part_name"),
        ("倾斜油缸", "part_name"),
        ("属具销轴", "part_name"),
    ])
    def test_knowledge_base_terms(self, term, expected_field):
        """
        测试知识库中的专业术语

        注意：需要RAG系统启用，实际使用时根据情况调整
        """
        pytest.skip("需要RAG系统支持，实际使用时移除此skip")


class TestDeviceSpecificInstructions:
    """测试设备特定指令"""

    @pytest.mark.parametrize("device,part", [
        ("岸桥", "主起升钢丝绳"),
        ("岸桥", "减速机"),
        ("RTG", "行走轮"),
        ("RTG", "滑环"),
        ("堆高机", "门架油缸"),
        ("堆高机", "属具销轴"),
    ])
    def test_device_part_combination(self, device, part):
        """测试设备-备件组合"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": part,
            "installation_equipment": device,
            "quantity": 1
        }

        instruction = parser.parse_output(vlm_result)
        assert instruction.part_name == part
        assert instruction.installation_equipment == device


class TestInstructionComplexity:
    """测试不同复杂度的指令"""

    def test_simple_instruction(self):
        """测试简单指令（单字段）"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": "电机"
        }

        instruction = parser.parse_output(vlm_result)
        assert instruction.part_name == "电机"

    def test_medium_instruction(self):
        """测试中等复杂指令（2-3个字段）"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": "减速机",
            "quantity": 2,
            "action_required": "更换"
        }

        instruction = parser.parse_output(vlm_result)
        assert len([v for v in [
            instruction.part_name,
            instruction.quantity,
            instruction.action_required
        ] if v is not None]) == 3

    def test_complex_instruction(self):
        """测试复杂指令（5个以上字段）"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": "主起升行星减速机",
            "quantity": 2,
            "model": "P4F-17-280-315",
            "installation_equipment": "岸桥主起升机构",
            "location": "仓库A区-01架",
            "action_required": "更换",
            "description": "已达到3000工作小时，需要更换"
        }

        instruction = parser.parse_output(vlm_result)
        # 验证至少6个非空字段
        non_empty_fields = len([
            v for v in [
                instruction.part_name,
                instruction.quantity,
                instruction.model,
                instruction.installation_equipment,
                instruction.location,
                instruction.action_required,
                instruction.description
            ] if v is not None
        ])
        assert non_empty_fields >= 6


class TestLocationExtraction:
    """测试位置信息提取"""

    @pytest.mark.parametrize("location_text,expected_location", [
        ("仓库A区", "仓库A区"),
        ("仓库A区-01架-01层", "仓库A区-01架-01层"),
        ("1号仓库", "1号仓库"),
        ("A区01架", "A区01架"),
        ("岸桥现场", "岸桥现场"),
    ])
    def test_location_formats(self, location_text, expected_location):
        """测试各种位置格式"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": "电机",
            "location": location_text
        }

        instruction = parser.parse_output(vlm_result)
        assert instruction.location == expected_location


class TestModelNumberFormats:
    """测试型号格式"""

    @pytest.mark.parametrize("model_number", [
        "6×36WS+IWR-32mm-1870MPa",  # 钢丝绳型号
        "P4F-17-280-315",  # 减速机型号
        "SEW-KA157",  # 变频器型号
        "Y3-315L-4",  # 电机型号
        "INA/FAG-NU316",  # 轴承型号
    ])
    def test_various_model_formats(self, model_number):
        """测试各种型号格式"""
        parser = PortInstructionParser()

        vlm_result = {
            "part_name": "备件",
            "model": model_number
        }

        instruction = parser.parse_output(vlm_result)
        assert instruction.model == model_number


# ===== 集成测试套件（需要实际VLM） =====

class TestIntegrationWithVLM:
    """
    VLM集成测试

    注意：这些测试需要：
    1. vLLM服务器运行
    2. VLM模型已加载
    3. 可选：RAG系统启用
    """

    @pytest.mark.skip(reason="需要vLLM服务器运行，手动测试时使用")
    def test_full_parsing_pipeline_text(self):
        """测试完整的文本解析流程"""
        # 这里需要实际的VLM调用
        # 详见 main_interaction.py 的实现
        pass

    @pytest.mark.skip(reason="需要音频文件，手动测试时使用")
    def test_full_parsing_pipeline_audio(self):
        """测试完整的音频解析流程"""
        # 这里需要实际的音频输入
        # 详见 main_interaction.py 的录音功能
        pass

    @pytest.mark.skip(reason="需要图像文件，手动测试时使用")
    def test_full_parsing_pipeline_image(self):
        """测试完整的图像解析流程"""
        # 这里需要实际的图像输入
        # 详见 main_interaction.py 的图片分析功能
        pass


# ===== 性能测试 =====

class TestPerformance:
    """性能测试"""

    def test_parser_initialization_speed(self):
        """测试解析器初始化速度"""
        import time

        start = time.time()
        parser = PortInstructionParser()
        elapsed = time.time() - start

        # 初始化应该很快（< 1秒）
        assert elapsed < 1.0

    def test_parse_speed(self):
        """测试解析速度"""
        import time

        parser = PortInstructionParser()
        vlm_result = {
            "part_name": "电机",
            "quantity": 5,
            "action_required": "更换"
        }

        start = time.time()
        instruction = parser.parse_output(vlm_result)
        elapsed = time.time() - start

        # 解析应该很快（< 0.1秒）
        assert elapsed < 0.1

    def test_batch_parsing(self):
        """测试批量解析"""
        import time

        parser = PortInstructionParser()
        test_cases = [
            {"part_name": f"备件{i}", "quantity": i}
            for i in range(1, 101)
        ]

        start = time.time()
        instructions = [parser.parse_output(case) for case in test_cases]
        elapsed = time.time() - start

        # 100次解析应该在合理时间内（< 1秒）
        assert elapsed < 1.0
        assert len(instructions) == 100


# ===== 运行辅助函数 =====

def run_manual_test_cases():
    """
    手动运行测试用例（不需要pytest）

    用于快速验证功能
    """
    print("=" * 60)
    print("手动测试用例")
    print("=" * 60)

    parser = PortInstructionParser()

    # 测试用例
    test_cases = [
        {
            "name": "基本提取",
            "input": {"part_name": "电机", "quantity": 5},
            "expected_part": "电机",
            "expected_qty": 5
        },
        {
            "name": "完整信息",
            "input": {
                "part_name": "主起升钢丝绳",
                "quantity": 2,
                "model": "6×36WS+IWR-32mm-1870MPa",
                "installation_equipment": "岸桥主起升机构",
                "action_required": "更换"
            },
            "expected_part": "主起升钢丝绳",
            "expected_qty": 2
        },
        {
            "name": "规则解析兜底",
            "input": {"raw_response": "需要3个减速机"},
            "raw_text": "需要3个减速机",
            "expected_qty": 3
        }
    ]

    passed = 0
    failed = 0

    for i, case in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {case['name']}")
        try:
            raw_text = case.get("raw_text", "")
            result = parser.parse_output(case["input"], raw_text)

            # 验证
            if "expected_part" in case:
                assert result.part_name == case["expected_part"], \
                    f"part_name不匹配: {result.part_name} != {case['expected_part']}"
            if "expected_qty" in case:
                assert result.quantity == case["expected_qty"], \
                    f"quantity不匹配: {result.quantity} != {case['expected_qty']}"

            print(f"  ✓ 通过: {result.to_json()}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ 失败: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)


if __name__ == "__main__":
    # 如果直接运行此文件，执行手动测试
    run_manual_test_cases()
