#!/usr/bin/env python3
# main_api.py
"""AGV 仓储调度 API 服务启动入口

启动方式:
    python main_api.py                    # 默认 0.0.0.0:8000
    python main_api.py --port 9000        # 自定义端口
"""
import argparse
import logging

import uvicorn

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def build_app():
    import src.warehouse.maps.medium_57x47  # noqa: F401
    from src.warehouse.maps.base import MapRegistry
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.fleet.fleet_manager import FleetManager
    from src.warehouse.wms.config import WarehouseConfig
    from src.warehouse.wms.order_manager import OrderManager
    from src.warehouse.wms.inventory_db import InventoryDB
    from src.api.app import create_app

    wh_config = WarehouseConfig()
    map_config = MapRegistry.get(wh_config.MAP_NAME)
    wmap = WarehouseMap(map_config)

    logger.info("预计算路径缓存（首次启动较慢）...")
    fleet = FleetManager(wmap, wh_config)
    fleet.precompute()
    logger.info("路径缓存完成。")

    inv_db = InventoryDB()
    inv_db.seed_from_map(map_config, seed=wh_config.RANDOM_SEED)
    logger.info("库存数据库就绪。")

    om = OrderManager(map_config, seed=wh_config.RANDOM_SEED)

    # 尝试初始化 VLM（允许失败）
    parser = None
    vlm_available = False
    try:
        from src.vlm.server import get_vlm_server_manager
        if not get_vlm_server_manager().is_server_running():
            raise RuntimeError("vLLM 服务器未运行")
        from main_interaction import InstructionParser
        parser = InstructionParser()
        vlm_available = True
        logger.info("VLM 解析器初始化成功。")
    except (SystemExit, RuntimeError):
        logger.warning("vLLM 服务未运行，将使用规则解析降级。")
    except Exception as e:
        logger.warning("VLM 初始化失败: %s，将使用规则解析降级。", e)

    if not vlm_available:
        from src.parser.parser import PortInstructionParser

        class _RuleParser:
            def __init__(self):
                self._p = PortInstructionParser()

            def parse(self, text=None, audio=None, image=None):
                return self._p._rule_based_parse(text or "")

        parser = _RuleParser()

    return create_app(
        parser=parser,
        inv_db=inv_db,
        vlm_available=vlm_available,
        wmap=wmap,
        fleet=fleet,
        wh_config=wh_config,
        inbound_ports=om.inbound_ports,
        outbound_ports=om.outbound_ports,
    )


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--host", default="0.0.0.0")
    arg_parser.add_argument("--port", type=int, default=8000)
    args = arg_parser.parse_args()

    app = build_app()
    uvicorn.run(app, host=args.host, port=args.port)
