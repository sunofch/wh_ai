"""
结构化解析器：定义数据模型和校验逻辑
"""
import json
import re
from typing import Any, Dict, Optional

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from src.common.config import config

# ── 规则解析词典（VLM降级时使用） ──────────────────────────────

_ACTION_KEYWORDS: list[tuple[str, str]] = sorted([
    ("调库", "调库"), ("调拨", "调库"), ("转移", "调库"),
    ("移库", "调库"), ("搬移", "调库"), ("转存", "调库"),
    ("入库", "入库"), ("存入", "入库"), ("放入", "入库"),
    ("归还", "入库"), ("回收", "入库"), ("放回", "入库"),
    ("出库", "出库"), ("领取", "出库"), ("提取", "出库"),
    ("发放", "出库"), ("出货", "出库"), ("领用", "出库"),
    ("领", "出库"), ("取", "出库"), ("拿", "出库"),
], key=lambda x: len(x[0]), reverse=True)

_URGENCY_KEYWORDS = frozenset(
    {"紧急", "加急", "尽快", "马上", "立刻", "优先", "十万火急", "特急", "急用"}
)

_QUANTITY_RE = re.compile(
    r'(\d+)\s*(个|件|套|台|只|把|箱|根|桶|副|双|条|卷|支|瓶|包)'
)
_MODEL_RE = re.compile(r'[A-Za-z0-9]{2,}(?:[-/][A-Za-z0-9]{1,}){2,}')


def _load_part_aliases(kb_dir: str = "data/knowledge_base") -> list[tuple[str, str]]:
    """从知识库 .md 文件提取别名→标准名映射，按别名长度降序排列。"""
    from pathlib import Path

    kb_path = Path(kb_dir)
    if not kb_path.exists():
        return []

    aliases: list[tuple[str, str]] = []
    for md_file in sorted(kb_path.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        for section in re.split(r'^## ', content, flags=re.MULTILINE)[1:]:
            title = section.split('\n', 1)[0].strip()
            canonical = re.sub(r'[（(].*?[）)]', '', title).strip()
            if not canonical:
                continue

            cn = re.search(r'\*\*中文名称\*\*\s*[:：]\s*(.+)', section)
            if cn:
                for name in cn.group(1).split('/'):
                    name = name.strip()
                    if name:
                        aliases.append((name, canonical))

            abbr = re.search(r'\*\*英文缩写\*\*\s*[:：]\s*(.+)', section)
            if abbr:
                abbr = abbr.group(1).strip()
                if abbr:
                    aliases.append((abbr, canonical))

    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for alias, canonical in aliases:
        if alias not in seen:
            seen.add(alias)
            unique.append((alias, canonical))
    return sorted(unique, key=lambda x: len(x[0]), reverse=True)


_PART_ALIASES = _load_part_aliases()


# 数据模型定义
class PortInstruction(BaseModel):
    part_name:       Optional[str] = Field(description="备件中文名称", default=None)
    quantity:        Optional[int] = Field(description="所需数量", default=None)
    model:           Optional[str] = Field(description="型号", default=None)
    action_required: Optional[str] = Field(
        description="行动：入库、出库、调库", default=None
    )
    is_urgent:       bool          = Field(description="是否紧急", default=False)
    description:     Optional[str] = Field(
        description="用户指令中的其他重要信息", default=None
    )

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
        """规则解析兜底：从文本中提取动作、备件名、数量、型号、紧急程度。"""
        # 1) 提取型号（优先匹配，避免数字与库存量混淆）
        model_match = _MODEL_RE.search(text)
        model = model_match.group(0) if model_match else None
        model_span = model_match.span() if model_match else (-1, -1)

        # 2) 提取数量（跳过与型号重叠的数字）
        quantity = None
        for m in _QUANTITY_RE.finditer(text):
            if not (model_span[0] <= m.start() < model_span[1]):
                quantity = int(m.group(1))
                break

        # 3) 提取动作、备件名、紧急程度
        action = self._match_action(text)
        part_name = self._match_part(text)
        is_urgent = any(kw in text for kw in _URGENCY_KEYWORDS)

        if not part_name:
            part_name = config.parser.fallback_part_name

        return PortInstruction(
            part_name=part_name,
            quantity=quantity,
            model=model,
            action_required=action,
            is_urgent=is_urgent,
            description=text,
        )

    @staticmethod
    def _match_action(text: str) -> str | None:
        for keyword, action in _ACTION_KEYWORDS:
            if keyword in text:
                return action
        return None

    @staticmethod
    def _match_part(text: str) -> str | None:
        text_lower = text.lower()
        for alias, canonical in _PART_ALIASES:
            if alias.isascii():
                if alias.lower() in text_lower:
                    return canonical
            elif alias in text:
                return canonical
        return None