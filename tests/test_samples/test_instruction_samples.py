'''
港口指令解析系统 - 完整测试样例集

包含各类真实场景的指令输入和对应的合格输出参考。
用于验证VLM解析质量和系统功能完整性。

测试样例分类：
1. 基础场景 (BASIC)
2. 设备特定 (DEVICE_SPECIFIC)
3. 行动类型 (ACTION_TYPES)
4. 复杂场景 (COMPLEX)
5. 边界情况 (EDGE_CASES)
6. 多模态输入 (MULTIMODAL)
7. 专业术语 (TERMINOLOGY)
8. 缩写场景 (ABBREVIATIONS)
'''

from typing import Dict, List, Any
from pydantic import BaseModel


class TestSample(BaseModel):
    '''单个测试样例'''
    category: str  # 分类
    scenario: str  # 场景描述
    input_text: str  # 输入文本
    image_description: str = ''  # 图片描述（可选）
    expected_output: Dict[str, Any]  # 期望输出
    notes: str = ''  # 备注


# ===== 基础场景测试样例 =====

BASIC_SAMPLES = [
    TestSample(
        category='基础场景',
        scenario='简单的备件名称+数量',
        input_text='需要5个电机',
        expected_output={
            'part_name': '电机',
            'quantity': 5,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': None
        },
        notes='最基本的备件需求'
    ),

    TestSample(
        category='基础场景',
        scenario='备件名称+型号',
        input_text='主起升钢丝绳，型号6×36WS+IWR-32mm-1870MPa',
        expected_output={
            'part_name': '主起升钢丝绳',
            'quantity': None,
            'model': '6×36WS+IWR-32mm-1870MPa',
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': None
        },
        notes='包含完整型号信息'
    ),

    TestSample(
        category='基础场景',
        scenario='备件名称+数量+行动',
        input_text='需要3个减速机，要更换',
        expected_output={
            'part_name': '减速机',
            'quantity': 3,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='明确指出更换需求'
    ),

    TestSample(
        category='基础场景',
        scenario='带位置的备件需求',
        input_text='仓库A区需要10个轴承',
        expected_output={
            'part_name': '轴承',
            'quantity': 10,
            'model': None,
            'installation_equipment': None,
            'location': '仓库A区',
            'description': None,
            'action_required': None
        },
        notes='location字段为用户指定的地理位置'
    ),

    TestSample(
        category='基础场景',
        scenario='带描述信息的需求',
        input_text='需要2个电机，紧急',
        expected_output={
            'part_name': '电机',
            'quantity': 2,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': '紧急',
            'action_required': None
        },
        notes='描述紧急程度'
    ),
]


# ===== 设备特定测试样例 =====

DEVICE_SPECIFIC_SAMPLES = [
    TestSample(
        category='设备特定',
        scenario='岸桥-主起升机构',
        input_text='岸桥主起升机构的钢丝绳需要更换',
        expected_output={
            'part_name': '钢丝绳',
            'quantity': None,
            'model': None,
            'installation_equipment': '岸桥主起升机构',
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='岸桥主起升机构专用'
    ),

    TestSample(
        category='设备特定',
        scenario='岸桥-前臂架拉索',
        input_text='岸桥前臂架拉索钢丝绳，型号6×36WS+IWR-28mm，需要2根',
        expected_output={
            'part_name': '前臂架拉索钢丝绳',
            'quantity': 2,
            'model': '6×36WS+IWR-28mm',
            'installation_equipment': '岸桥',
            'location': None,
            'description': None,
            'action_required': None
        },
        notes='岸桥前臂架专用部件'
    ),

    TestSample(
        category='设备特定',
        scenario='岸桥-行走机构',
        input_text='岸桥行走电机需要维修，型号Y3-315L-4，数量4台',
        expected_output={
            'part_name': '行走电机',
            'quantity': 4,
            'model': 'Y3-315L-4',
            'installation_equipment': '岸桥行走机构',
            'location': None,
            'description': None,
            'action_required': '维修'
        },
        notes='岸桥行走机构维护'
    ),

    TestSample(
        category='设备特定',
        scenario='RTG-行走轮',
        input_text='RTG行走轮需要更换，8个，型号φ610mm',
        expected_output={
            'part_name': '行走轮',
            'quantity': 8,
            'model': 'φ610mm',
            'installation_equipment': 'RTG',
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='RTG龙门吊行走部件'
    ),

    TestSample(
        category='设备特定',
        scenario='RTG-滑环箱',
        input_text='RTG滑环箱需要检查，电缆卷筒用',
        expected_output={
            'part_name': '滑环箱',
            'quantity': None,
            'model': None,
            'installation_equipment': 'RTG电缆卷筒',
            'location': None,
            'description': None,
            'action_required': '检查'
        },
        notes='RTG电缆卷筒系统'
    ),

    TestSample(
        category='设备特定',
        scenario='堆高机-门架油缸',
        input_text='堆高机门架油缸漏油，需要维修，2个',
        expected_output={
            'part_name': '门架油缸',
            'quantity': 2,
            'model': None,
            'installation_equipment': '堆高机',
            'location': None,
            'description': '漏油',
            'action_required': '维修'
        },
        notes='堆高机液压系统'
    ),

    TestSample(
        category='设备特定',
        scenario='堆高机-属具销轴',
        input_text='堆高机属具销轴需要更换，规格φ50×300mm，4根',
        expected_output={
            'part_name': '属具销轴',
            'quantity': 4,
            'model': 'φ50×300mm',
            'installation_equipment': '堆高机',
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='堆高机属具连接件'
    ),

    TestSample(
        category='设备特定',
        scenario='输送带-驱动滚筒',
        input_text='皮带输送机驱动滚筒轴承需要更换，型号INA/FAG-NU316，2套',
        expected_output={
            'part_name': '驱动滚筒轴承',
            'quantity': 2,
            'model': 'INA/FAG-NU316',
            'installation_equipment': '皮带输送机',
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='输送带驱动系统'
    ),
]


# ===== 行动类型测试样例 =====

ACTION_TYPE_SAMPLES = [
    TestSample(
        category='行动类型',
        scenario='更换-常规',
        input_text='主起升减速机需要更换',
        expected_output={
            'part_name': '主起升减速机',
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='标准更换需求'
    ),

    TestSample(
        category='行动类型',
        scenario='更换-紧急',
        input_text='紧急！钢丝绳需要立即更换，安全风险',
        expected_output={
            'part_name': '钢丝绳',
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': '紧急，安全风险',
            'action_required': '更换'
        },
        notes='紧急更换场景'
    ),

    TestSample(
        category='行动类型',
        scenario='维修-故障修复',
        input_text='岸桥电机故障，需要维修',
        expected_output={
            'part_name': '岸桥电机',
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': '故障',
            'action_required': '维修'
        },
        notes='设备故障维修'
    ),

    TestSample(
        category='行动类型',
        scenario='维修-预防性维护',
        input_text='减速机需要定期维护保养',
        expected_output={
            'part_name': '减速机',
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': '定期维护保养',
            'action_required': '维修'
        },
        notes='预防性维护'
    ),

    TestSample(
        category='行动类型',
        scenario='检查-定期检查',
        input_text='滑环箱需要定期检查',
        expected_output={
            'part_name': '滑环箱',
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': '定期检查',
            'action_required': '检查'
        },
        notes='定期检验需求'
    ),

    TestSample(
        category='行动类型',
        scenario='检查-安全检查',
        input_text='钢丝绳需要进行安全检查',
        expected_output={
            'part_name': '钢丝绳',
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': '安全检查',
            'action_required': '检查'
        },
        notes='安全检验需求'
    ),

    TestSample(
        category='行动类型',
        scenario='采购-库存不足',
        input_text='电机安全库存不足，需要采购补充',
        expected_output={
            'part_name': '电机',
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': '安全库存不足',
            'action_required': '采购'
        },
        notes='采购需求'
    ),

    TestSample(
        category='行动类型',
        scenario='调拨-紧急调拨',
        input_text='仓库B区轴承用完了，需要从A区紧急调拨',
        expected_output={
            'part_name': '轴承',
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': '仓库B区',
            'description': '用完了，需要从A区紧急调拨',
            'action_required': '调拨'
        },
        notes='仓库间调拨'
    ),

    TestSample(
        category='行动类型',
        scenario='领用-正常领用',
        input_text='需要领用5个螺栓用于日常维护',
        expected_output={
            'part_name': '螺栓',
            'quantity': 5,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': '日常维护',
            'action_required': '领用'
        },
        notes='正常领用流程'
    ),
]


# ===== 复杂场景测试样例 =====

COMPLEX_SAMPLES = [
    TestSample(
        category='复杂场景',
        scenario='完整信息-多字段',
        input_text='岸桥主起升机构的行星减速机需要更换，型号P4F-17-280-315，数量2台，放在仓库A区-01架-01层，已达到3000工作小时，需要紧急处理',
        expected_output={
            'part_name': '行星减速机',
            'quantity': 2,
            'model': 'P4F-17-280-315',
            'installation_equipment': '岸桥主起升机构',
            'location': '仓库A区-01架-01层',
            'description': '已达到3000工作小时，需要紧急处理',
            'action_required': '更换'
        },
        notes='包含所有字段的完整信息'
    ),

    TestSample(
        category='复杂场景',
        scenario='多备件组合',
        input_text='岸桥需要以下备件：主起升钢丝绳2根，型号6×36WS+IWR-32mm；减速机3台，型号P4F-17-280-315；电机5台，型号Y3-315L-4。紧急需求。',
        expected_output={
            'part_name': '主起升钢丝绳',  # 应提取主要备件
            'quantity': 2,
            'model': '6×36WS+IWR-32mm',
            'installation_equipment': '岸桥',
            'location': None,
            'description': '还需要：减速机3台（型号P4F-17-280-315）、电机5台（型号Y3-315L-4）。紧急需求。',
            'action_required': None
        },
        notes='多备件需求，提取主要备件，其他放入description'
    ),

    TestSample(
        category='复杂场景',
        scenario='带技术参数',
        input_text='需要采购变频器，功率75kW，输入电压380V，输出频率0-200Hz，型号SEW-KA157，数量1台',
        expected_output={
            'part_name': '变频器',
            'quantity': 1,
            'model': 'SEW-KA157',
            'installation_equipment': None,
            'location': None,
            'description': '功率75kW，输入电压380V，输出频率0-200Hz',
            'action_required': '采购'
        },
        notes='包含详细技术参数'
    ),

    TestSample(
        category='复杂场景',
        scenario='带原因说明',
        input_text='RTG行走轮磨损严重，测量值已低于安全标准φ610mm，需要立即更换8个，以保证作业安全',
        expected_output={
            'part_name': '行走轮',
            'quantity': 8,
            'model': 'φ610mm',
            'installation_equipment': 'RTG',
            'location': None,
            'description': '磨损严重，测量值已低于安全标准，需要立即更换以保证作业安全',
            'action_required': '更换'
        },
        notes='详细说明更换原因'
    ),

    TestSample(
        category='复杂场景',
        scenario='带位置和流程',
        input_text='仓库A区-02架的岸桥备件已用完，需要从仓库B区调拨5台电机到仓库A区，用于岸桥3号机的维修',
        expected_output={
            'part_name': '电机',
            'quantity': 5,
            'model': None,
            'installation_equipment': '岸桥3号机',
            'location': '仓库A区',
            'description': '仓库A区-02架的岸桥备件已用完，需要从仓库B区调拨',
            'action_required': '调拨'
        },
        notes='包含位置信息和调拨流程'
    ),
]


# ===== 边界情况测试样例 =====

EDGE_CASE_SAMPLES = [
    TestSample(
        category='边界情况',
        scenario='数量为0',
        input_text='需要0个电机',
        expected_output={
            'part_name': '电机',
            'quantity': 0,  # 或 None，根据业务逻辑
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': None
        },
        notes='边界情况：数量为0'
    ),

    TestSample(
        category='边界情况',
        scenario='大量级',
        input_text='需要1000个螺栓',
        expected_output={
            'part_name': '螺栓',
            'quantity': 1000,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': None
        },
        notes='边界情况：大量级'
    ),

    TestSample(
        category='边界情况',
        scenario='模糊数量',
        input_text='需要几个电机',
        expected_output={
            'part_name': '电机',
            'quantity': None,  # '几个'无法提取具体数字
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': '需要几个',
            'action_required': None
        },
        notes='模糊数量表达，无法提取具体数字'
    ),

    TestSample(
        category='边界情况',
        scenario='中英文混合',
        input_text='岸桥 Main Hoist Wire Rope 需要更换，需要5根',
        expected_output={
            'part_name': '岸桥主起升钢丝绳',  # 或保留英文
            'quantity': 5,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='中英文混合输入'
    ),

    TestSample(
        category='边界情况',
        scenario='口语化表达',
        input_text='那个...呃...岸桥的钢丝绳...嗯...好像需要换了',
        expected_output={
            'part_name': '钢丝绳',
            'quantity': None,
            'model': None,
            'installation_equipment': '岸桥',
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='口语化、停顿、犹豫'
    ),

    TestSample(
        category='边界情况',
        scenario='错别字',
        input_text='岸桥减数机需要更换，2台',  # 错别字：减数机
        expected_output={
            'part_name': '减速机',  # 应该纠正错别字
            'quantity': 2,
            'model': None,
            'installation_equipment': '岸桥',
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='VLM应该纠正常见错别字'
    ),

    TestSample(
        category='边界情况',
        scenario='空指令',
        input_text='',
        expected_output={
            'part_name': None,
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': None
        },
        notes='空输入'
    ),

    TestSample(
        category='边界情况',
        scenario='重复信息',
        input_text='需要5个电机，5个，要5个电机',
        expected_output={
            'part_name': '电机',
            'quantity': 5,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': None
        },
        notes='重复的信息，应该去重'
    ),
]


# ===== 专业术语测试样例 =====

TERMINOLOGY_SAMPLES = [
    TestSample(
        category='专业术语',
        scenario='岸桥术语-钢丝绳',
        input_text='MHWR需要更换，2根',  # MHWR = Main Hoist Wire Rope
        expected_output={
            'part_name': '主起升钢丝绳',  # 应该展开缩写
            'quantity': 2,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='缩写：MHWR'
    ),

    TestSample(
        category='专业术语',
        scenario='岸桥术语-后臂架',
        input_text='BSWR钢丝绳需要更换',  # BSWR = Back Structure Wire Rope
        expected_output={
            'part_name': '后臂架钢丝绳',  # 应该展开缩写
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='缩写：BSWR'
    ),

    TestSample(
        category='专业术语',
        scenario='液压术语',
        input_text='堆高机门架油缸需要维修，缸径φ160mm，行程1200mm',
        expected_output={
            'part_name': '门架油缸',
            'quantity': None,
            'model': '缸径φ160mm，行程1200mm',
            'installation_equipment': '堆高机',
            'location': None,
            'description': None,
            'action_required': '维修'
        },
        notes='液压缸技术参数'
    ),

    TestSample(
        category='专业术语',
        scenario='电气术语',
        input_text='岸桥主变频器故障，需要维修，型号SEW-KA157，功率75kW',
        expected_output={
            'part_name': '主变频器',
            'quantity': None,
            'model': 'SEW-KA157',
            'installation_equipment': '岸桥',
            'location': None,
            'description': '功率75kW',
            'action_required': '维修'
        },
        notes='变频器专业术语'
    ),

    TestSample(
        category='专业术语',
        scenario='轴承术语',
        input_text='需要采购轴承，型号INA/FAG-NU316，内径80mm，外径170mm，宽度39mm',
        expected_output={
            'part_name': '轴承',
            'quantity': None,
            'model': 'INA/FAG-NU316',
            'installation_equipment': None,
            'location': None,
            'description': '内径80mm，外径170mm，宽度39mm',
            'action_required': '采购'
        },
        notes='轴承详细规格'
    ),

    TestSample(
        category='专业术语',
        scenario='减速机术语',
        input_text='主起升行星减速机需要更换，型号P4F-17-280-315，传动比17，额定输出扭矩28000Nm',
        expected_output={
            'part_name': '主起升行星减速机',
            'quantity': None,
            'model': 'P4F-17-280-315',
            'installation_equipment': None,
            'location': None,
            'description': '传动比17，额定输出扭矩28000Nm',
            'action_required': '更换'
        },
        notes='减速机技术参数'
    ),
]


# ===== 多模态输入测试样例 =====

MULTIMODAL_SAMPLES = [
    TestSample(
        category='多模态输入',
        scenario='图片+文本-设备铭牌',
        input_text='这个设备的减速机坏了，需要更换',
        image_description='图片显示：岸桥主起升机构的减速机铭牌，清晰可见型号P4F-17-280-315和序列号',
        expected_output={
            'part_name': '减速机',
            'quantity': None,
            'model': 'P4F-17-280-315',  # 从图片识别
            'installation_equipment': '岸桥主起升机构',
            'location': None,
            'description': '设备坏了',
            'action_required': '更换'
        },
        notes='VLM从图片中识别型号'
    ),

    TestSample(
        category='多模态输入',
        scenario='图片+文本-备件外观',
        input_text='需要采购这种钢丝绳，10根',
        image_description='图片显示：一卷钢丝绳，标签上写着：6×36WS+IWR-32mm-1870MPa，主起升用',
        expected_output={
            'part_name': '主起升钢丝绳',
            'quantity': 10,
            'model': '6×36WS+IWR-32mm-1870MPa',  # 从图片识别
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': '采购'
        },
        notes='VLM从图片标签识别型号'
    ),

    TestSample(
        category='多模态输入',
        scenario='图片+文本-故障现象',
        input_text='这个电机烧坏了，需要维修',
        image_description='图片显示：岸桥行走电机，外壳有烧焦痕迹，铭牌可见Y3-315L-4',
        expected_output={
            'part_name': '行走电机',
            'quantity': None,
            'model': 'Y3-315L-4',  # 从图片识别
            'installation_equipment': '岸桥',
            'location': None,
            'description': '烧坏了',
            'action_required': '维修'
        },
        notes='VLM从图片识别故障和型号'
    ),

    TestSample(
        category='多模态输入',
        scenario='图片+文本-仓库场景',
        input_text='这里的轴承用完了，需要补充',
        image_description='图片显示：仓库货架，标签写着"仓库A区-01架-01层-轴承"，货架空空如也',
        expected_output={
            'part_name': '轴承',
            'quantity': None,
            'model': None,
            'installation_equipment': None,
            'location': '仓库A区-01架-01层',  # 从图片识别
            'description': '用完了',
            'action_required': None
        },
        notes='VLM从图片识别位置信息'
    ),

    TestSample(
        category='多模态输入',
        scenario='图片+文本-技术图纸',
        input_text='这个零件需要更换',
        image_description='图片显示：减速机装配图，标注显示"行星减速机 P4F-17-280-315"，序号5',
        expected_output={
            'part_name': '行星减速机',
            'quantity': None,
            'model': 'P4F-17-280-315',  # 从图纸识别
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='VLM从技术图纸识别零件'
    ),
]


# ===== 音频输入测试样例 =====

AUDIO_SAMPLES = [
    TestSample(
        category='音频输入',
        scenario='标准语音指令',
        input_text='需要5个电机，紧急',  # ASR转录结果
        expected_output={
            'part_name': '电机',
            'quantity': 5,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': '紧急',
            'action_required': None
        },
        notes='标准语音转录'
    ),

    TestSample(
        category='音频输入',
        scenario='带方言口音',
        input_text='岸桥的钢丝绳要换了，两根',  # ASR可能有误差
        expected_output={
            'part_name': '钢丝绳',
            'quantity': 2,
            'model': None,
            'installation_equipment': '岸桥',
            'location': None,
            'description': None,
            'action_required': '更换'
        },
        notes='ASR转录可能有小误差，VLM应容忍'
    ),

    TestSample(
        category='音频输入',
        scenario='嘈杂环境',
        input_text='（背景噪音）...需要...电机...3个...',  # ASR转录不完整
        expected_output={
            'part_name': '电机',
            'quantity': 3,
            'model': None,
            'installation_equipment': None,
            'location': None,
            'description': None,
            'action_required': None
        },
        notes='嘈杂环境下的语音识别'
    ),
]


# ===== 综合测试样例集合 =====

ALL_TEST_SAMPLES = (
    BASIC_SAMPLES +
    DEVICE_SPECIFIC_SAMPLES +
    ACTION_TYPE_SAMPLES +
    COMPLEX_SAMPLES +
    EDGE_CASE_SAMPLES +
    TERMINOLOGY_SAMPLES +
    MULTIMODAL_SAMPLES +
    AUDIO_SAMPLES
)


# ===== 辅助函数 =====

def get_samples_by_category(category: str) -> List[TestSample]:
    '''按类别获取测试样例'''
    return [s for s in ALL_TEST_SAMPLES if s.category == category]


def get_samples_by_scenario(scenario_keyword: str) -> List[TestSample]:
    '''按场景关键词搜索测试样例'''
    return [s for s in ALL_TEST_SAMPLES if scenario_keyword in s.scenario]


def print_sample_summary():
    '''打印测试样例统计摘要'''
    from collections import Counter

    print('=' * 80)
    print('港口指令解析系统 - 测试样例统计')
    print('=' * 80)

    # 分类统计
    categories = [s.category for s in ALL_TEST_SAMPLES]
    category_counts = Counter(categories)

    print('\n【分类统计】')
    for category, count in category_counts.most_common():
        print(f'  {category}: {count} 个样例')

    print(f'\n【总计】')
    print(f'  测试样例总数: {len(ALL_TEST_SAMPLES)}')

    # 场景分布
    print('\n【场景分布】')
    scenario_keywords = [
        '岸桥', 'RTG', '堆高机', '输送机',
        '更换', '维修', '检查', '采购',
        '图片', '音频'
    ]
    for keyword in scenario_keywords:
        count = len(get_samples_by_scenario(keyword))
        if count > 0:
            print(f'  {keyword}: {count} 个样例')

    print('\n' + '=' * 80)


def export_samples_to_json(filepath: str = 'test_samples.json'):
    '''导出测试样例到JSON文件'''
    import json

    samples_data = [s.model_dump() for s in ALL_TEST_SAMPLES]

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(samples_data, f, ensure_ascii=False, indent=2)

    print(f'测试样例已导出到: {filepath}')


def import_samples_from_json(filepath: str):
    '''从JSON文件导入测试样例'''
    import json

    with open(filepath, 'r', encoding='utf-8') as f:
        samples_data = json.load(f)

    return [TestSample(**data) for data in samples_data]


# ===== 命令行工具 =====

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'summary':
            print_sample_summary()
        elif command == 'export':
            filepath = sys.argv[2] if len(sys.argv) > 2 else 'test_samples.json'
            export_samples_to_json(filepath)
        elif command == 'list':
            category = sys.argv[2] if len(sys.argv) > 2 else None
            if category:
                samples = get_samples_by_category(category)
                print(f'\n【{category}】测试样例：\n')
                for i, sample in enumerate(samples, 1):
                    print(f'{i}. {sample.scenario}')
                    print(f'   输入: {sample.input_text}')
                    print(f'   输出: {sample.expected_output}')
                    print()
            else:
                print("请指定类别，例如: python test_samples.py list '基础场景'")
        else:
            print('未知命令。可用命令: summary, export, list')
    else:
        print_sample_summary()
