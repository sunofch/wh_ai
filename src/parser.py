"""
结构化解析器：定义数据模型和校验逻辑
"""
import json
import re
from typing import Any, Dict, Optional

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from src.config import config

# 数据模型定义
class PortInstruction(BaseModel):
    part_name: Optional[str] = Field(description="备件名称", default=None)
    quantity: Optional[int] = Field(description="所需数量", default=None)
    model: Optional[str] = Field(description="型号", default=None)
    installation_equipment: Optional[str] = Field(description="安装设备", default=None)
    location: Optional[str] = Field(description="地点", default=None)
    description: Optional[str] = Field(description="详细描述", default=None)
    action_required: Optional[str] = Field(description="行动：更换、维修、检查等", default=None)
    
    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
    
    def to_json(self) -> str:
        return self.model_dump_json()

class PortInstructionParser:
    """仅负责 Schema 提供和数据校验"""
    
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=PortInstruction)
    
    def get_format_instructions(self) -> str:
        """
        [优化] 获取自定义的中文格式提示，去除 LangChain 默认的 'foo' 示例噪音
        """
        # 获取 Pydantic V2 的 JSON Schema
        schema = PortInstruction.model_json_schema(union_format='primitive_type_array')
        # 序列化为 JSON 字符串，确保中文不乱码
        schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
        # 返回纯净的中文指令
        return f"""请确保输出的 JSON 符合以下 Schema 定义：
```json
{schema_str}
```"""
    
    def parse_output(self, vlm_result: Dict[str, Any], raw_text: str = "") -> PortInstruction:
        """
        验证 VLM 输出，如果失败则回退到规则解析
        """
        # 1. 尝试直接转换
        if "raw_response" not in vlm_result:
            try:
                # 兼容处理：如果 vlm_result 本身就是 dict，直接解包
                return PortInstruction(**vlm_result)
            except Exception as e:
                print(f"VLM输出格式校验失败: {e}，尝试规则解析")
        
        # 2. 失败或 VLM 未输出 JSON，使用规则解析兜底
        fallback_text = vlm_result.get("raw_response", "") + " " + raw_text
        return self._rule_based_parse(fallback_text)
    
    def _rule_based_parse(self, text: str) -> PortInstruction:
        """
        规则解析兜底
        """
        # 提取数量
        quantity = None
        qty_match = re.search(r'(\d+)\s*(个|件|套|台|只|把|箱|根)', text)
        if qty_match:
            quantity = int(qty_match.group(1))

        # 从配置读取默认值
        fallback_part_name = config.parser.fallback_part_name
        fallback_desc_prefix = config.parser.fallback_description_prefix

        return PortInstruction(
            part_name=fallback_part_name,
            quantity=quantity,
            description=f"{fallback_desc_prefix}: {text}"
        )