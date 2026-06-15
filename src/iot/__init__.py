"""IoT 实时感知接入层。

pj4 P4 阶段（2028 现场部署）的软件侧先行实现：
  - schemas.py       传感读数统一结构（PLC/SCADA/视频抽帧统一入口）
  - buffer.py        线程安全时序环形缓冲，产出因果/预测模块的输入
  - mqtt_adapter.py  MQTT 订阅采集（paho-mqtt 惰性导入）
  - replay.py        CSV 历史数据回放（无 broker 环境的兜底数据源）

边缘-中心两级架构中本层位于中心侧；边缘侧网关只需把读数发布到
`port/{equipment_id}/{metric}` 主题。
"""
