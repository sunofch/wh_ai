# 港口指令解析系统 - 评估标准

## 测试质量评估标准

### 1. 字段提取准确率

#### 1.1 part_name（备件名称）

**优秀 (Grade A)**:
- 完全准确提取备件名称
- 正确展开缩写（如 MHWR → 主起升钢丝绳）
- 自动纠正错别字（如"减数机" → "减速机"）
- 正确处理中英文混合（如 "岸桥 Main Hoist Wire Rope" → "岸桥主起升钢丝绳"）

**合格 (Grade B)**:
- 备件名称基本正确，但存在以下小问题之一：
  - 未展开缩写（仍输出 "MHWR"）
  - 未纠正错别字
  - 包含冗余修饰词

**不合格 (Grade C)**:
- 备件名称错误或提取失败
- 提取到无关内容

**示例评估**:
```
输入: "MHWR需要更换，2根"
✅ Grade A: part_name = "主起升钢丝绳"
⚠️ Grade B: part_name = "MHWR"（未展开缩写）
❌ Grade C: part_name = "钢丝绳"（缺少"主起升"限定）
```

#### 1.2 quantity（数量）

**优秀 (Grade A)**:
- 准确提取阿拉伯数字
- 正确处理中文数字（如"五" → 5）
- 正确处理各种单位（个、件、套、台、根等）

**合格 (Grade B)**:
- 数量提取正确，但以下情况之一：
  - 未能转换中文数字
  - 未能识别模糊数量（"几个"、"一些"等，可输出None）

**不合格 (Grade C)**:
- 数量提取错误
- 提取到非数字内容

**示例评估**:
```
输入: "需要5个电机"
✅ Grade A: quantity = 5
✅ Grade A: quantity = 5（正确识别单位）

输入: "需要几个电机"
✅ Grade B: quantity = None（模糊数量，正确处理）
❌ Grade C: quantity = "几个"（应该输出None或整数）
```

#### 1.3 model（型号）

**优秀 (Grade A)**:
- 完整准确提取型号信息
- 正确处理复杂型号格式（如 "6×36WS+IWR-32mm-1870MPa"）
- 从图片中识别型号信息

**合格 (Grade B)**:
- 型号基本正确，但以下情况之一：
  - 缺少部分细节（如缺少"1870MPa"）
  - 格式稍有偏差（如空格、大小写）

**不合格 (Grade C)**:
- 型号错误或未提取

**示例评估**:
```
输入: "主起升钢丝绳，型号6×36WS+IWR-32mm-1870MPa"
✅ Grade A: model = "6×36WS+IWR-32mm-1870MPa"
⚠️ Grade B: model = "6×36WS+IWR-32mm"（缺少强度等级）
❌ Grade C: model = "32mm"（信息不完整）
```

#### 1.4 installation_equipment（安装设备）

**优秀 (Grade A)**:
- 准确提取设备名称和部位（如"岸桥主起升机构"）
- 从上下文推断设备信息

**合格 (Grade B)**:
- 设备名称正确，但以下情况之一：
  - 缺少具体部位（如只输出"岸桥"，未输出"主起升机构"）
  - 包含冗余信息

**不合格 (Grade C)**:
- 设备名称错误或未提取

**示例评估**:
```
输入: "岸桥主起升机构的钢丝绳需要更换"
✅ Grade A: installation_equipment = "岸桥主起升机构"
⚠️ Grade B: installation_equipment = "岸桥"（缺少具体机构）
❌ Grade C: installation_equipment = None（未能提取）
```

#### 1.5 location（地理位置）

**优秀 (Grade A)**:
- 准确提取用户指定的地理位置
- 区分设备位置和仓库位置
- 从图片中识别位置标签

**合格 (Grade B)**:
- 位置基本正确，但以下情况之一：
  - 位置信息不完整
  - 包含设备信息（应放入installation_equipment）

**不合格 (Grade C)**:
- 位置提取错误或混淆

**重要说明**:
- `location` 字段是**用户指定的地理位置**，如"仓库A区"、"岸桥现场"
- **不是**备件的库存位置（这是常见错误）

**示例评估**:
```
输入: "仓库A区需要10个轴承"
✅ Grade A: location = "仓库A区"
✅ Grade A: location = "仓库A区"（用户指定位置）

❌ 常见错误: location = "仓库A区-01架-01层"（这是库存位置，不是用户指定的地理位置）
✅ 正确: location = "仓库A区" + description = "从01架-01层取"
```

#### 1.6 description（描述信息）

**优秀 (Grade A)**:
- 准确提取补充描述信息（如"紧急"、"安全库存不足"）
- 包含技术参数（如"功率75kW"）
- 包含原因说明（如"已达到3000工作小时"）

**合格 (Grade B)**:
- 描述信息基本正确

**不合格 (Grade C)**:
- 描述信息错误或冗余

**示例评估**:
```
输入: "需要5个电机，紧急"
✅ Grade A: description = "紧急"
✅ Grade A: description = "紧急"（简洁准确）

输入: "岸桥主起升机构的行星减速机需要更换，已达到3000工作小时"
✅ Grade A: description = "已达到3000工作小时"
```

#### 1.7 action_required（行动类型）

**优秀 (Grade A)**:
- 准确识别行动类型：更换、维修、检查、采购、调拨、领用
- 正确归并相似行动（如"需要更换" → "更换"，"检修" → "维修"）

**合格 (Grade B)**:
- 行动类型基本正确，但以下情况之一：
  - 未能归并（如输出"需要更换"而非"更换"）
  - 包含冗余修饰

**不合格 (Grade C)**:
- 行动类型错误或未提取

**行动归并规则**:
```
更换相关: 更换、需要更换、要更换、更换为 → "更换"
维修相关: 维修、需要维修、检修、保养、维护 → "维修"
检查相关: 检查、需要检查、检验、定期检查、安全检查 → "检查"
采购相关: 采购、需要采购、订购、买 → "采购"
调拨相关: 调拨、紧急调拨、调货 → "调拨"
领用相关: 领用、领取 → "领用"
```

**示例评估**:
```
输入: "减速机需要更换"
✅ Grade A: action_required = "更换"
⚠️ Grade B: action_required = "需要更换"（未归并）
❌ Grade C: action_required = None（未能提取）
```

---

### 2. 整体评估标准

#### 2.1 综合评分

**优秀 (Overall A)**:
- 所有关键字段（part_name）准确
- 至少 80% 的非空字段达到 Grade A
- 无 Grade C 字段

**合格 (Overall B)**:
- 所有关键字段（part_name）达到 Grade B 及以上
- 至少 60% 的非空字段达到 Grade B 及以上
- Grade C 字段不超过 1 个

**不合格 (Overall C)**:
- 关键字段（part_name）为 Grade C
- Grade C 字段超过 1 个

#### 2.2 特殊场景评估

**多备件场景**:
```
输入: "岸桥需要以下备件：主起升钢丝绳2根；减速机3台；电机5台"

评估标准:
✅ 优秀: 提取主要备件（如"主起升钢丝绳"），其他放入 description
⚠️ 合格: 只提取第一个备件
❌ 不合格: 提取混乱或错误
```

**多模态场景**:
```
输入: 文本 + 图片

评估标准:
✅ 优秀: 从图片中识别关键信息（型号、位置标签等）
⚠️ 合格: 仅使用文本信息，忽略图片
❌ 不合格: 图片信息识别错误
```

**口语/噪音场景**:
```
输入: "那个...呃...岸桥的钢丝绳...嗯...好像需要换了"

评估标准:
✅ 优秀: 过滤口语停顿，提取核心信息
⚠️ 合格: 提取基本正确，但包含冗余信息
❌ 不合格: 提取失败或错误
```

---

### 3. 通过标准

#### 3.1 单个测试用例

- **通过**: Overall B 及以上
- **不通过**: Overall C

#### 3.2 整体测试集

- **优秀**: ≥ 90% 测试用例达到 Overall A
- **合格**: ≥ 80% 测试用例达到 Overall B 及以上
- **不合格**: < 80% 测试用例达到 Overall B 及以上

#### 3.3 分类通过标准

不同类别可能有不同的通过标准：

| 测试类别 | 优秀标准 | 合格标准 |
|---------|---------|---------|
| 基础场景 | ≥ 95% Overall A | ≥ 90% Overall B+ |
| 设备特定 | ≥ 85% Overall A | ≥ 80% Overall B+ |
| 行动类型 | ≥ 90% Overall A | ≥ 85% Overall B+ |
| 复杂场景 | ≥ 80% Overall A | ≥ 75% Overall B+ |
| 边界情况 | ≥ 75% Overall A | ≥ 70% Overall B+ |
| 专业术语 | ≥ 85% Overall A | ≥ 80% Overall B+ |
| 多模态输入 | ≥ 80% Overall A | ≥ 75% Overall B+ |
| 音频输入 | ≥ 75% Overall A | ≥ 70% Overall B+ |

---

### 4. 评估工具使用

#### 4.1 自动化评估

使用 `evaluate_test_samples.py` 进行自动化评估：

```bash
# 运行完整评估
python tests/test_samples/evaluate_test_samples.py

# 评估特定类别
python tests/test_samples/evaluate_test_samples.py --category "基础场景"

# 导出评估报告
python tests/test_samples/evaluate_test_samples.py --output report.json
```

#### 4.2 手动评估

参考 `test_instruction_samples.py` 中的期望输出，与实际输出对比：

```python
from tests.test_samples.test_instruction_samples import TestSample

sample = TestSample(
    category="基础场景",
    scenario="简单的备件名称+数量",
    input_text="需要5个电机",
    expected_output={...}
)

# 运行你的VLM系统
actual_output = your_vlm_system.parse(sample.input_text)

# 对比评估
evaluation = evaluate_output(actual_output, sample.expected_output)
print(evaluation.report)
```

---

### 5. 常见问题和解决方案

#### 5.1 location 字段混淆

**问题**: 将库存位置放入 location 字段

**错误示例**:
```json
{
  "part_name": "主起升钢丝绳",
  "location": "仓库A区-01架-01层"  // ❌ 这是库存位置
}
```

**正确示例**:
```json
{
  "part_name": "主起升钢丝绳",
  "location": "仓库A区",  // ✅ 用户指定的地理位置
  "description": "从01架-01层取"  // ✅ 库存位置放描述
}
```

**解决方案**: 在 system prompt 中明确说明 location 字段含义

#### 5.2 缩写未展开

**问题**: 未展开专业缩写

**错误示例**:
```json
{
  "part_name": "MHWR"  // ❌ 未展开
}
```

**正确示例**:
```json
{
  "part_name": "主起升钢丝绳"  // ✅ 已展开
}
```

**解决方案**: 使用 RAG 系统提供缩写对照表

#### 5.3 行动类型未归并

**问题**: 输出原始行动而非标准类型

**错误示例**:
```json
{
  "action_required": "需要更换"  // ❌ 未归并
}
```

**正确示例**:
```json
{
  "action_required": "更换"  // ✅ 已归并
}
```

**解决方案**: 在 system prompt 中明确要求标准行动类型

#### 5.4 技术参数放错字段

**问题**: 将技术参数放入 model 字段而非 description

**错误示例**:
```json
{
  "model": "75kW,380V,0-200Hz"  // ❌ 技术参数不是型号
}
```

**正确示例**:
```json
{
  "model": "SEW-KA157",
  "description": "功率75kW，输入电压380V，输出频率0-200Hz"  // ✅
}
```

**解决方案**: 在 system prompt 中明确区分型号和技术参数

---

### 6. 改进建议

#### 6.1 短期改进

1. **优化 System Prompt**:
   - 明确 location 字段定义
   - 提供行动归并规则
   - 区分型号和技术参数

2. **增强 RAG 知识库**:
   - 添加缩写对照表
   - 添加常见错别字纠正
   - 添加设备-备件关联

3. **优化规则解析**:
   - 改进数量提取（支持中文数字）
   - 改进行动识别和归并

#### 6.2 长期改进

1. **多模态融合**:
   - 提升图片中型号识别准确率
   - 提升位置标签识别能力

2. **上下文理解**:
   - 改进口语停顿过滤
   - 改进模糊数量处理

3. **知识图谱**:
   - 使用 GraphRAG 提供设备-备件关联
   - 自动推断安装设备

---

## 附录：快速参考

### 字段优先级

1. **必须字段**:
   - `part_name`（备件名称）- 最高优先级

2. **重要字段**:
   - `quantity`（数量）
   - `action_required`（行动类型）

3. **辅助字段**:
   - `model`（型号）
   - `installation_equipment`（安装设备）
   - `location`（地理位置）

4. **可选字段**:
   - `description`（描述信息）

### 常见行动归并

| 原始表达 | 标准类型 |
|---------|---------|
| 更换、需要更换、要更换、更换为 | 更换 |
| 维修、需要维修、检修、保养、维护 | 维修 |
| 检查、需要检查、检验、定期检查、安全检查 | 检查 |
| 采购、需要采购、订购、买 | 采购 |
| 调拨、紧急调拨、调货 | 调拨 |
| 领用、领取 | 领用 |

### 常见缩写展开

| 缩写 | 全称 |
|-----|------|
| MHWR | Main Hoist Wire Rope → 主起升钢丝绳 |
| BSWR | Back Structure Wire Rope → 后臂架钢丝绳 |
| GTWB | Gantry Wheel → 龙门车轮 |
| TSC | Tie Spread Controller | 牵引小车控制器 |

### 评估清单

- [ ] part_name 准确且展开缩写
- [ ] quantity 为整数或 None
- [ ] model 格式正确且完整
- [ ] installation_equipment 包含设备和部位
- [ ] location 为地理位置而非库存位置
- [ ] description 包含补充信息
- [ ] action_required 为标准类型
- [ ] 无冗余或矛盾信息
