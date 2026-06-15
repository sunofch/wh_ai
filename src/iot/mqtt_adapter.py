"""MQTT 时序采集适配器。

主题约定：port/{equipment_id}/{metric}
负载约定：{"sensor_id": "...", "value": <number>, "ts": "..."}

paho-mqtt 为可选依赖，惰性导入：未安装时仅 MQTTIngestor 不可用，
解析函数与 CSV 回放路径不受影响。
"""
from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from src.iot.buffer import TimeSeriesBuffer
from src.iot.schemas import SensorReading

logger = logging.getLogger(__name__)

TOPIC_PREFIX = "port"


def parse_topic(topic: str) -> tuple[str, str] | None:
    """解析主题为 (equipment_id, metric)；不符合约定返回 None。"""
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != TOPIC_PREFIX or not all(parts):
        return None
    return parts[1], parts[2]


def payload_to_reading(topic: str, payload: bytes) -> SensorReading | None:
    """主题 + JSON 负载 → SensorReading；任何解析失败返回 None 并记日志。"""
    parsed = parse_topic(topic)
    if parsed is None:
        logger.warning("无法识别的 MQTT 主题: %s", topic)
        return None
    equipment_id, metric = parsed
    try:
        data = json.loads(payload)
        return SensorReading(
            sensor_id=str(data.get("sensor_id", "")),
            equipment_id=equipment_id,
            metric=metric,
            value=data["value"],
            ts=str(data.get("ts", "")),
        )
    except (json.JSONDecodeError, KeyError, ValidationError, TypeError) as exc:
        logger.warning("MQTT 负载解析失败 topic=%s: %s", topic, exc)
        return None


class MQTTIngestor:
    """订阅 port/+/+ 主题并把读数写入时序缓冲区。"""

    def __init__(
        self,
        broker: str,
        buffer: TimeSeriesBuffer,
        port: int = 1883,
        topic: str = f"{TOPIC_PREFIX}/+/+",
    ):
        try:
            import paho.mqtt.client as mqtt_client
        except ImportError as exc:  # pragma: no cover - 依赖未装时的防御
            raise ImportError(
                "MQTT 采集需要 paho-mqtt：pip install paho-mqtt"
            ) from exc

        self._buffer = buffer
        self._topic = topic
        self._broker = broker
        self._port = port
        try:  # paho-mqtt 2.x 需显式指定回调 API 版本，1.x 无此参数
            self._client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION1)
        except AttributeError:
            self._client = mqtt_client.Client()
        self._client.on_message = self._on_message

    def _on_message(self, _client, _userdata, message) -> None:
        reading = payload_to_reading(message.topic, message.payload)
        if reading is not None:
            self._buffer.append(reading)

    def start(self) -> None:
        """连接 broker 并在后台线程持续采集。"""
        self._client.connect(self._broker, self._port)
        self._client.subscribe(self._topic)
        self._client.loop_start()
        logger.info("MQTT 采集已启动 broker=%s topic=%s", self._broker, self._topic)

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
