# src/warehouse/maps/base.py
"""地图注册机制与基类

使用装饰器模式注册地图: @MapRegistry.register("name") 标记地图类,
运行时通过 MapRegistry.get("name") 获取MapConfig实例。
新增地图只需创建继承BaseMap的类并添加@register装饰器。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from src.warehouse.models import MapConfig


class MapRegistry:
    _maps: dict[str, type[BaseMap]] = {}

    @classmethod
    def register(cls, name: str):
        """装饰器：注册地图类"""
        def wrapper(map_cls: type[BaseMap]):
            cls._maps[name] = map_cls
            return map_cls
        return wrapper

    @classmethod
    def get(cls, name: str) -> MapConfig:
        """获取地图配置"""
        if name not in cls._maps:
            available = ", ".join(cls._maps.keys())
            raise ValueError(f"地图 '{name}' 未注册。可用地图: {available}")
        return cls._maps[name]().build()

    @classmethod
    def list_all(cls) -> list[tuple[str, str]]:
        """列出所有已注册地图 (name, display_name)"""
        result = []
        for name, map_cls in cls._maps.items():
            config = map_cls().build()
            result.append((name, config.display_name))
        return result


class BaseMap(ABC):
    @abstractmethod
    def build(self) -> MapConfig:
        ...
