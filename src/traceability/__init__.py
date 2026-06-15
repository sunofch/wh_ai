"""备件全流程可信溯源（轻量级区块链原型）。

pj4 子课题 4.3 的"采集-预警-溯源"一体化中的溯源层：
  - ledger.py  哈希链上链存证（SQLite 同事务，原子性与业务数据一致）
  - merkle.py  默克尔根/证明，支持批量锚定与轻客户端校验
  - adapters.py 联盟链适配层协议（Hyperledger Fabric / FISCO BCOS 可替换）
"""
