"""IoT 实时感知接入层测试。

对应 pj4 P4：MQTT 时序采集 + CSV 回放兜底，feed 进因果/预测模块。
真实 MQTT broker 集成用例在 paho-mqtt 未安装时自动跳过。
"""
import threading

import numpy as np
import pytest

from src.iot.buffer import TimeSeriesBuffer
from src.iot.replay import replay_csv
from src.iot.schemas import SensorReading


class TestSensorReading:
    def test_valid_reading(self):
        r = SensorReading(sensor_id="s1", equipment_id="crane-01",
                          metric="vibration", value=1.5, ts="2026-06-10T00:00:00")
        assert r.metric == "vibration"

    def test_invalid_value_rejected(self):
        with pytest.raises(Exception):
            SensorReading(sensor_id="s1", equipment_id="e1",
                          metric="temp", value="not-a-number", ts="t")


class TestTimeSeriesBuffer:
    def test_append_and_series(self):
        buf = TimeSeriesBuffer(maxlen=100)
        for i in range(5):
            buf.append(SensorReading(sensor_id="s", equipment_id="crane-01",
                                     metric="temp", value=float(i), ts=f"t{i}"))
        series = buf.series("crane-01", "temp")
        assert isinstance(series, np.ndarray)
        assert series.tolist() == [0.0, 1.0, 2.0, 3.0, 4.0]

    def test_ring_buffer_caps_length(self):
        buf = TimeSeriesBuffer(maxlen=3)
        for i in range(10):
            buf.append(SensorReading(sensor_id="s", equipment_id="e",
                                     metric="m", value=float(i), ts=f"t{i}"))
        assert buf.series("e", "m").tolist() == [7.0, 8.0, 9.0]

    def test_unknown_key_returns_empty(self):
        buf = TimeSeriesBuffer()
        assert buf.series("nope", "nope").size == 0

    def test_thread_safe_append(self):
        buf = TimeSeriesBuffer(maxlen=10000)

        def worker(tid):
            for i in range(200):
                buf.append(SensorReading(sensor_id=f"s{tid}", equipment_id="e",
                                         metric="m", value=1.0, ts=str(i)))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert buf.series("e", "m").size == 1600

    def test_as_causal_input(self):
        """缓冲区可直接产出动态因果图的多源输入。"""
        buf = TimeSeriesBuffer()
        for i in range(60):
            buf.append(SensorReading(sensor_id="s", equipment_id="e",
                                     metric="load", value=float(i % 7), ts=str(i)))
            buf.append(SensorReading(sensor_id="s", equipment_id="e",
                                     metric="demand", value=float((i + 1) % 7), ts=str(i)))
        data = buf.as_dict("e", ["load", "demand"])
        assert set(data) == {"load", "demand"}
        assert len(data["load"]) == len(data["demand"]) == 60


class TestCSVReplay:
    def test_replay_feeds_buffer(self, tmp_path):
        csv_file = tmp_path / "sensors.csv"
        csv_file.write_text(
            "sensor_id,equipment_id,metric,value,ts\n"
            "s1,crane-01,vibration,0.5,2026-06-01T00:00:00\n"
            "s1,crane-01,vibration,0.7,2026-06-01T00:01:00\n"
            "s2,crane-01,temp,42.0,2026-06-01T00:00:00\n",
            encoding="utf-8",
        )
        buf = TimeSeriesBuffer()
        count = replay_csv(str(csv_file), buf)
        assert count == 3
        assert buf.series("crane-01", "vibration").tolist() == [0.5, 0.7]
        assert buf.series("crane-01", "temp").tolist() == [42.0]

    def test_bad_rows_skipped_not_fatal(self, tmp_path):
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text(
            "sensor_id,equipment_id,metric,value,ts\n"
            "s1,e1,m,not-a-number,t1\n"
            "s1,e1,m,1.0,t2\n",
            encoding="utf-8",
        )
        buf = TimeSeriesBuffer()
        count = replay_csv(str(csv_file), buf)
        assert count == 1
        assert buf.series("e1", "m").tolist() == [1.0]


class TestMQTTAdapter:
    def test_topic_parsing(self):
        from src.iot.mqtt_adapter import parse_topic

        assert parse_topic("port/crane-01/vibration") == ("crane-01", "vibration")
        assert parse_topic("bad-topic") is None

    def test_payload_to_reading(self):
        from src.iot.mqtt_adapter import payload_to_reading

        reading = payload_to_reading(
            "port/crane-01/temp",
            b'{"sensor_id": "s9", "value": 36.5, "ts": "2026-06-10T08:00:00"}',
        )
        assert reading.equipment_id == "crane-01"
        assert reading.value == 36.5

    def test_invalid_payload_returns_none(self):
        from src.iot.mqtt_adapter import payload_to_reading

        assert payload_to_reading("port/e/m", b"not json") is None

    def test_ingestor_requires_paho(self):
        pytest.importorskip("paho.mqtt")
        from src.iot.mqtt_adapter import MQTTIngestor

        ingestor = MQTTIngestor(broker="localhost", buffer=TimeSeriesBuffer())
        assert ingestor is not None
