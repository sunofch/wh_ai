# 港口指令解析系统 - 测试样例使用指南

## 目录结构

```
tests/test_samples/
├── __init__.py                        # 模块初始化
├── test_instruction_samples.py        # 完整测试样例集（60+ 样例）
├── evaluate_test_samples.py           # 评估工具脚本
├── QUALITY_STANDARDS.md               # 评估标准文档
└── README.md                          # 本文件
```

## 快速开始

### 1. 查看测试样例统计

```bash
cd /home/catlab/wh/wh_graphrag_re

# 方式1: 使用 Python 模块
python -m tests.test_samples.test_instruction_samples summary

# 方式2: 直接运行脚本
python tests/test_samples/test_instruction_samples.py summary
```

输出示例：
```
================================================================================
港口指令解析系统 - 测试样例统计
================================================================================

【分类统计】
  基础场景: 5 个样例
  设备特定: 8 个样例
  行动类型: 9 个样例
  复杂场景: 5 个样例
  边界情况: 8 个样例
  专业术语: 6 个样例
  多模态输入: 5 个样例
  音频输入: 3 个样例

【总计】
  测试样例总数: 60

【场景分布】
  岸桥: 15 个样例
  RTG: 5 个样例
  堆高机: 5 个样例
  输送机: 2 个样例
  更换: 15 个样例
  维修: 10 个样例
  检查: 5 个样例
  采购: 5 个样例
  图片: 5 个样例
  音频: 3 个样例
```

### 2. 查看特定类别的测试样例

```bash
# 查看基础场景样例
python tests/test_samples/test_instruction_samples.py list "基础场景"

# 查看设备特定样例
python tests/test_samples/test_instruction_samples.py list "设备特定"
```

### 3. 导出测试样例到 JSON

```bash
# 导出所有样例
python tests/test_samples/test_instruction_samples.py export

# 导出到指定文件
python tests/test_samples/test_instruction_samples.py export my_samples.json
```

### 4. 运行模拟评估

```bash
# 运行模拟评估（不依赖实际VLM，用于验证评估逻辑）
python tests/test_samples/evaluate_test_samples.py --simulate
```

## 在代码中使用测试样例

### 基本使用

```python
from tests.test_samples import ALL_TEST_SAMPLES, get_samples_by_category

# 获取所有测试样例
for sample in ALL_TEST_SAMPLES:
    print(f"类别: {sample.category}")
    print(f"场景: {sample.scenario}")
    print(f"输入: {sample.input_text}")
    print(f"期望输出: {sample.expected_output}")
    print("-" * 80)

# 获取特定类别的样例
basic_samples = get_samples_by_category("基础场景")
for sample in basic_samples:
    # 测试基础场景
    pass
```

### 与 VLM 集成测试

```python
from tests.test_samples import ALL_TEST_SAMPLES
from main_interaction import InstructionParser

# 初始化你的解析器
parser = InstructionParser()

# 运行测试
results = []
for sample in ALL_TEST_SAMPLES:
    try:
        # 调用你的解析器
        actual_output = parser.parse_text(sample.input_text)

        # 评估结果
        from tests.test_samples.evaluate_test_samples import TestSuiteEvaluator
        evaluator = TestSuiteEvaluator()
        evaluation = evaluator.evaluate_sample(sample, actual_output)

        results.append({
            'sample': sample,
            'evaluation': evaluation
        })

        # 打印结果
        print(evaluation.generate_report())

    except Exception as e:
        print(f"测试失败: {sample.scenario}")
        print(f"错误: {e}")

# 生成汇总报告
evaluator.generate_summary_report()
```

### 自定义评估逻辑

```python
from tests.test_samples import TestSample
from tests.test_samples.evaluate_test_samples import FieldEvaluation

# 创建自定义样例
custom_sample = TestSample(
    category="自定义",
    scenario="我的测试场景",
    input_text="需要3个电机，紧急",
    expected_output={
        "part_name": "电机",
        "quantity": 3,
        "model": None,
        "installation_equipment": None,
        "location": None,
        "description": "紧急",
        "action_required": None
    }
)

# 评估单个字段
field_eval = FieldEvaluation(
    field_name="part_name",
    expected="电机",
    actual="电机"  # 你的 VLM 实际输出
)

print(f"等级: {field_eval.grade}")
print(f"原因: {field_eval.reason}")
```

## 测试样例分类说明

### 1. 基础场景 (BASIC)
- **目的**: 验证基本功能
- **样例数**: 5 个
- **覆盖**: 单字段、多字段、基本组合
- **通过标准**: ≥ 90% Overall A

**示例**:
- "需要5个电机"
- "主起升钢丝绳，型号6×36WS+IWR-32mm-1870MPa"

### 2. 设备特定 (DEVICE_SPECIFIC)
- **目的**: 验证不同设备的识别
- **样例数**: 8 个
- **覆盖**: 岸桥、RTG、堆高机、输送机
- **通过标准**: ≥ 85% Overall A

**示例**:
- "岸桥主起升机构的钢丝绳需要更换"
- "RTG行走轮需要更换，8个"

### 3. 行动类型 (ACTION_TYPES)
- **目的**: 验证行动识别和归并
- **样例数**: 9 个
- **覆盖**: 更换、维修、检查、采购、调拨、领用
- **通过标准**: ≥ 90% Overall A

**示例**:
- "减速机需要更换"
- "滑环箱需要定期检查"
- "电机安全库存不足，需要采购"

### 4. 复杂场景 (COMPLEX)
- **目的**: 验证复杂信息处理
- **样例数**: 5 个
- **覆盖**: 多字段、多备件、技术参数、原因说明
- **通过标准**: ≥ 80% Overall A

**示例**:
- "岸桥主起升机构的行星减速机需要更换，型号P4F-17-280-315，数量2台..."
- "岸桥需要以下备件：主起升钢丝绳2根；减速机3台；电机5台"

### 5. 边界情况 (EDGE_CASES)
- **目的**: 验证异常处理
- **样例数**: 8 个
- **覆盖**: 空指令、模糊数量、口语化、错别字
- **通过标准**: ≥ 75% Overall A

**示例**:
- "需要几个电机"（模糊数量）
- "那个...呃...岸桥的钢丝绳...嗯...好像需要换了"（口语化）
- "岸桥减数机需要更换"（错别字）

### 6. 专业术语 (TERMINOLOGY)
- **目的**: 验证专业术语识别
- **样例数**: 6 个
- **覆盖**: 缩写展开、技术参数、专业词汇
- **通过标准**: ≥ 85% Overall A

**示例**:
- "MHWR需要更换"（MHWR = Main Hoist Wire Rope）
- "轴承型号INA/FAG-NU316，内径80mm"

### 7. 多模态输入 (MULTIMODAL)
- **目的**: 验证图片+文本解析
- **样例数**: 5 个
- **覆盖**: 设备铭牌、备件外观、故障现象、仓库场景、技术图纸
- **通过标准**: ≥ 80% Overall A

**示例**:
- 文本: "这个设备的减速机坏了"
- 图片: 岸桥主起升机构的减速机铭牌（型号P4F-17-280-315）

### 8. 音频输入 (AUDIO)
- **目的**: 验证语音识别处理
- **样例数**: 3 个
- **覆盖**: 标准语音、方言口音、嘈杂环境
- **通过标准**: ≥ 75% Overall A

**示例**:
- "需要5个电机，紧急"（ASR转录结果）
- "岸桥的钢丝绳要换了，两根"（带口音）

## 评估标准详解

### 字段等级标准

#### Grade A（优秀）
- **part_name**: 完全准确，展开缩写，纠正错别字
- **quantity**: 准确提取数字
- **model**: 完整型号信息
- **installation_equipment**: 包含设备和部位
- **location**: 准确的地理位置（非库存位置）
- **description**: 准确的补充信息
- **action_required**: 标准行动类型

#### Grade B（合格）
- 基本正确，但存在小问题：
  - 未展开缩写
  - 缺少部分细节
  - 格式稍有偏差

#### Grade C（不合格）
- 字段错误或未提取

### 整体等级标准

- **Overall A**: 所有关键字段准确，≥ 80% 非空字段 Grade A，无 Grade C
- **Overall B**: 关键字段 Grade B+，≥ 60% 非空字段 Grade B+，Grade C ≤ 1
- **Overall C**: 不满足 Overall B

详细标准请参考：[QUALITY_STANDARDS.md](QUALITY_STANDARDS.md)

## 实际使用场景

### 场景1: 开发阶段验证

```bash
# 运行模拟评估，验证评估逻辑
python tests/test_samples/evaluate_test_samples.py --simulate

# 查看特定类别样例
python tests/test_samples/test_instruction_samples.py list "基础场景"
```

### 场景2: VLM 调优

```python
from tests.test_samples import get_samples_by_category
from your_vlm import YourVLM

# 获取问题类别样例
edge_cases = get_samples_by_category("边界情况")

# 测试不同 prompt
vlm = YourVLM()
for sample in edge_cases:
    result = vlm.parse(sample.input_text)
    print(f"输入: {sample.input_text}")
    print(f"输出: {result}")
    print(f"期望: {sample.expected_output}")
    print("-" * 80)
```

### 场景3: 质量监控

```python
from tests.test_samples.evaluate_test_samples import TestSuiteEvaluator

# 定期运行完整测试集
evaluator = TestSuiteEvaluator()

for sample in ALL_TEST_SAMPLES:
    actual_output = your_vlm.parse(sample.input_text)
    evaluator.evaluate_sample(sample, actual_output)

# 生成报告
print(evaluator.generate_summary_report())

# 导出报告
evaluator.export_report("quality_report_2025_01_01.json")
```

### 场景4: CI/CD 集成

```yaml
# .github/workflows/test.yml
name: VLM Quality Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run VLM quality tests
        run: |
          python tests/test_samples/evaluate_test_samples.py --output test_report.json
      - name: Upload test report
        uses: actions/upload-artifact@v2
        with:
          name: test-report
          path: test_report.json
```

## 常见问题

### Q1: 如何添加自定义测试样例？

```python
from tests.test_samples import TestSample

custom_sample = TestSample(
    category="自定义",
    scenario="我的场景",
    input_text="你的输入文本",
    image_description="图片描述（可选）",
    expected_output={
        "part_name": "期望的备件名称",
        "quantity": 期望的数量,
        # ... 其他字段
    },
    notes="备注说明"
)

# 使用自定义样例
print(custom_sample.input_text)
print(custom_sample.expected_output)
```

### Q2: 如何处理多备件场景？

对于多备件输入（如"需要钢丝绳2根、减速机3台、电机5台"），建议：
1. 提取主要备件到 `part_name`
2. 将其他备件信息放入 `description` 字段

示例：
```json
{
  "part_name": "钢丝绳",
  "quantity": 2,
  "description": "还需要：减速机3台、电机5台"
}
```

### Q3: location 字段应该包含什么？

`location` 是**用户指定的地理位置**，不是库存位置。

- ✅ 正确: `location = "仓库A区"` + `description = "从01架-01层取"`
- ❌ 错误: `location = "仓库A区-01架-01层"`

### Q4: 如何评估多模态输入？

多模态评估需要实际图片，目前提供的是图片描述。你可以：
1. 根据描述创建测试图片
2. 使用实际图片运行测试
3. 对比 VLM 从图片中提取的信息

## 参考文档

- [评估标准详解](QUALITY_STANDARDS.md)
- [测试样例源码](test_instruction_samples.py)
- [评估工具源码](evaluate_test_samples.py)

## 贡献指南

欢迎贡献新的测试样例！请遵循以下规范：

1. **样例真实性**: 基于真实港口场景
2. **期望输出准确**: 仔细校验期望输出
3. **场景覆盖**: 优先覆盖缺失场景
4. **文档完善**: 添加清晰的场景描述和备注

## 联系方式

如有问题或建议，请联系项目维护者。
