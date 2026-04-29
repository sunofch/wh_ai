# 地图重构设计文档 — 行列式货架仓

> 日期：2026-04-29
> 分支：feature/map-refactor
> 状态：已批准

---

## 1. 背景

当前仓库建模（50×50 网格，12 个 6×5 小区域，每个 4 储位）存在以下问题：

- 储位容量严重不足（48 储位 / 192 料箱 vs 需求 3000+）
- 缺少货架/巷道概念，不符合真实港口备件仓库
- 通道只有 1 格宽，无主通道/巷道区分
- 区域分类（Raw/Finished/Spare）不符合港口备件标准

## 2. 设计目标

- 贴近真实港口备件仓库的平面货架仓结构
- 引入货架行（Rack Row）、巷道（Aisle）、纵向子通道（Sub-Aisle）
- 主通道双向 3 格宽 + 巷道单向 1 格宽
- 按用途分类 5 类备件区域

## 3. 总体布局

### 3.1 网格尺寸

50×50 网格，3 列 × 3 行 = **9 个等大区域**，每个 14(宽) × 10(高)。

### 3.2 通道体系

| 通道 | 位置 | 宽度 | 方向 |
|------|------|------|------|
| H1 | Y: 5-7 | 3 格 | 双向 |
| H2 | Y: 18-20 | 3 格 | 双向 |
| H3 | Y: 31-33 | 3 格 | 双向 |
| H4 | Y: 44-46 | 3 格 | 双向 |
| V1 | X: 16-18 | 3 格 | 双向 |
| V2 | X: 32-34 | 3 格 | 双向 |

6 条主通道形成网格，区域分布在网格单元中。

### 3.3 区域分配

| 行 | 左列 (X:2-15) | 中列 (X:19-31) | 右列 (X:35-47) |
|----|---------------|---------------|---------------|
| **上行** (Y:8-17) | 机械类 1 | 电气类 1 | 机械类 2 |
| **中行** (Y:21-30) | 电气类 2 | 消耗品 1 | 消耗品 2 |
| **下行** (Y:35-44) | 安全防护 | 工具类 | 消耗品 3 |

5 类备件 × 9 个区域：
- 机械类 × 2（轴承/齿轮/液压件）
- 电气类 × 2（电机/传感器/电缆）
- 消耗品 × 3（润滑油/密封件/滤芯）
- 安全防护 × 1（安全帽/手套）
- 工具类 × 1（手动/电动工具）

### 3.4 端口

6 个端口，上下对称：

| 端口名 | 类型 | 位置 | 区域 |
|--------|------|------|------|
| IN-L | INBOUND | (9, 3) | X:2-15, Y:2-4 |
| IN-C | INBOUND | (25, 3) | X:19-31, Y:2-4 |
| IN-R | INBOUND | (41, 3) | X:35-47, Y:2-4 |
| OUT-L | OUTBOUND | (9, 48) | X:2-15, Y:47-49 |
| OUT-C | OUTBOUND | (25, 48) | X:19-31, Y:47-49 |
| OUT-R | OUTBOUND | (41, 48) | X:35-47, Y:47-49 |

### 3.5 充电桩

4 个充电桩位于四角：(2, 2), (47, 2), (2, 47), (47, 47)。

### 3.6 AGV

8 台 AGV，初始分布在主通道交叉点附近。

## 4. 区域内部结构

每个 14×10 区域的内部结构（以机械类 1 为例，pos: (2, 8)）：

```
14 宽 × 10 高
┌──────────────────────────────────┐
│ [B1 ][B2 ][B3 ][|][B4 ][B5 ][|][B6 ][B7 ][|][B8 ][B9 ][|][B10] │ Row 1 (Y+0)  货架
│ [== ↓巷道1 ================== ] │ (Y+1)  单向↓
│ [B11][B12][B13][|][B14][B15][|][B16][B17][|][B18][B19][|][B20] │ Row 2 (Y+2)  货架
│ [== ↑巷道2 ================== ] │ (Y+3)  单向↑
│ [B21][B22][B23][|][B24][B25][|][B26][B27][|][B28][B29][|][B30] │ Row 3 (Y+4)  货架
│ [== ↓巷道3 ================== ] │ (Y+5)  单向↓
│ [B31][B32][B33][|][B34][B35][|][B36][B37][|][B38][B39][|][B40] │ Row 4 (Y+6)  货架
│ [== ↑巷道4 ================== ] │ (Y+7)  单向↑
│ [B41][B42][B43][|][B44][B45][|][B46][B47][|][B48][B49][|][B50] │ Row 5 (Y+8)  货架
│ [===== 区域出入口行 ========= ] │ (Y+9)  连接主通道
└──────────────────────────────────┘
```

- 5 行货架 × 10 储位/行 = **50 储位/区**
- 4 条水平巷道（1 格宽），方向交替 ↓↑↓↑
- 4 条纵向子通道（X+3, X+6, X+9, X+12），连接各巷道
- 上下两端都有开口连接主通道（AGV 从上方主通道或下方主通道进出）
- 9 区总计 **450 储位**

### 4.1 储位命名

格式：`{ZoneName}_R{Row}_B{Bay}`

示例：`Mech1_R1_B1`, `Elec2_R3_B7`, `Safety_R5_B10`

## 5. 格子类型扩展

| 值 | 常量 | 说明 |
|----|------|------|
| 0 | MAP_OBSTACLE | 墙/障碍 |
| 1 | MAP_PASSABLE | 主通道 |
| 2 | MAP_STORAGE | 储位 |
| 3 | MAP_PORT | 端口 |
| 4 | MAP_YIELD_POINT | 避让点 |
| 5 | MAP_CHARGING | 充电桩 |
| 6 | MAP_AISLE_DOWN | 巷道↓（单向向下） |
| 7 | MAP_AISLE_UP | 巷道↑（单向向上） |
| 8 | MAP_SUB_AISLE | 纵向子通道（双向） |

## 6. 数据模型变更

### 6.1 新增模型

```python
class RackRow(BaseModel):
    """一行货架"""
    row_id: str              # "Mech1_R1"
    positions: list[str]     # ["Mech1_R1_B1", ..., "Mech1_R1_B10"]
    y_offset: int            # 相对于区域 pos 的 Y 偏移

class AisleConfig(BaseModel):
    """巷道配置"""
    aisle_id: str            # "Mech1_A1"
    direction: str           # "down" | "up"
    y_offset: int            # 相对于区域 pos 的 Y 偏移

class RackZoneConfig(BaseModel):
    """货架区域配置（替代原 warehouse_zones）"""
    zone_id: str             # "Mech1"
    zone_type: str           # "mechanical" | "electrical" | "consumable" | "safety" | "tool"
    pos: tuple[int, int]     # 左上角坐标
    width: int = 14
    height: int = 10
    num_rows: int = 5        # 货架行数
    bays_per_row: int = 10   # 每行储位数
    sub_aisle_cols: list[int] = [3, 6, 9, 12]  # 纵向子通道的 X 偏移
    color: str = ""
```

### 6.2 MapConfig 变更

```python
class MapConfig(BaseModel):
    name: str
    display_name: str
    grid_size: int
    description: str = ""
    rack_zones: dict[str, RackZoneConfig] = {}    # 替代 warehouse_zones
    main_aisle_width: int = 3                       # 主通道宽度
    sub_aisle_width: int = 1                        # 巷道宽度
    ports: dict[str, dict] = {}
    agv_init_positions: list[tuple[int, int]] = []
    agv_count: int = 8
    conflict_segments: dict[str, dict] = {}
    yield_points: dict[str, tuple[int, int]] = {}
    charging_points: list[tuple[int, int]] = []
    main_channels_x: list[int] = []
    main_channels_y: list[int] = []
```

## 7. 寻路系统变更

### 7.1 方向约束

`is_passable(x, y, dx=0, dy=0)` 新增方向参数：

- MAP_AISLE_DOWN (6)：只允许 dy=+1（向下移动）
- MAP_AISLE_UP (7)：只允许 dy=-1（向上移动）
- MAP_SUB_AISLE (8)：允许任意方向
- MAP_STORAGE (2)：AGV 可进入但不可作为过境通道
- MAP_PASSABLE (1)：任意方向

### 7.2 A* 寻路

- `get_neighbors(x, y)` 需检查目标格子的方向约束
- 时空 A* 的 (x, y, t) 模型不变
- 路径缓存机制不变

## 8. 冲突消解变更

### 8.1 消除的冲突

- 巷道对向冲突：单向巷道天然无对撞
- 巷道超车冲突：1 格宽无法超车

### 8.2 保留/新增的冲突

- 主通道十字路口冲突：避让点机制保留
- 区域入口排队：多 AGV 同时进出同一区域需排队
- 巷道追尾：后车等待前车完成作业

## 9. 对现有模块的影响

| 模块 | 改动程度 | 说明 |
|------|---------|------|
| models.py | **中** | 新增 RackZoneConfig/AisleConfig/RackRow，修改 MapConfig |
| maps/medium_50x50.py | **重写** | 新的对称布局，9 区域 + 6 端口 |
| maps/base.py | **小** | 无需改动 |
| fleet/map_builder.py | **重写** | 新增 build_rack_zone()、build_aisles()，is_passable() 增加方向参数 |
| fleet/pathfinding.py | **中** | get_neighbors() 加入方向约束检查 |
| fleet/conflict.py | **小** | 更新冲突段定义 |
| wms/config.py | **小** | 更新区域名常量 |
| wms/inventory.py | **中** | 适配新储位命名格式 |
| wms/order_manager.py | **小** | 端口从 4 变 6 |
| wes/clustering.py | **小** | 区域名变更 |
| fleet/tsp.py | **无** | 只依赖坐标，无需改 |
| fleet/allocator.py | **无** | 只依赖任务和 AGV 状态 |
| simulation/simulator.py | **小** | 适配新储位名 |
| simulation/visualizer.py | **中** | 绘制货架和巷道 |
| simulation/metrics.py | **无** | 只依赖数值 |

## 10. 测试策略

- **全部重写**，不保留旧测试
- 按模块分文件组织
- 关键测试场景：
  - 地图构建：验证网格类型、储位坐标、通道连通性
  - 寻路：验证巷道方向约束、跨区路径
  - 冲突消解：验证单向巷道无对撞、区域入口排队
  - 调度：验证多 AGV 在新布局下的任务完成
  - 仿真：端到端冒烟测试

## 11. 精确坐标规划

### 11.1 区域坐标

| 区域 | pos (x,y) | 尺寸 | 类型 |
|------|-----------|------|------|
| Mech1 | (2, 8) | 14×10 | mechanical |
| Elec1 | (19, 8) | 14×10 | electrical |
| Mech2 | (35, 8) | 14×10 | mechanical |
| Elec2 | (2, 21) | 14×10 | electrical |
| Cons1 | (19, 21) | 14×10 | consumable |
| Cons2 | (35, 21) | 14×10 | consumable |
| Safety | (2, 35) | 14×10 | safety |
| Tool | (19, 35) | 14×10 | tool |
| Cons3 | (35, 35) | 14×10 | consumable |

### 11.2 主通道坐标

| 通道 | 方向 | 范围 |
|------|------|------|
| H1 | 横向 | Y:5-7, X:2-47 |
| H2 | 横向 | Y:18-20, X:2-47 |
| H3 | 横向 | Y:31-33, X:2-47 |
| H4 | 横向 | Y:44-46, X:2-47 |
| V1 | 纵向 | X:16-18, Y:2-48 |
| V2 | 纵向 | X:32-34, Y:2-48 |

### 11.3 端口坐标

| 端口 | pos | area (x1,x2,y1,y2) | 类型 |
|------|-----|---------------------|------|
| IN-L | (9, 3) | (2, 15, 2, 4) | INBOUND |
| IN-C | (25, 3) | (19, 31, 2, 4) | INBOUND |
| IN-R | (41, 3) | (35, 47, 2, 4) | INBOUND |
| OUT-L | (9, 48) | (2, 15, 47, 49) | OUTBOUND |
| OUT-C | (25, 48) | (19, 31, 47, 49) | OUTBOUND |
| OUT-R | (41, 48) | (35, 47, 47, 49) | OUTBOUND |

### 11.4 AGV 初始位置

分布在主通道交叉点：

```
(9, 6), (25, 6), (41, 6),
(9, 19), (25, 19), (41, 19),
(9, 45), (25, 45)
```

8 台 AGV 分布在上半部分和中段的主通道上。
