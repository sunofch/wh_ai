# 地图重构实施计划 — 行列式货架仓

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 50×50 仓库地图从 12 个 6×5 小区域重构为 9 个 14×10 行列式货架区域，引入巷道/子通道概念，6 端口对称布局。

**Architecture:** 自底向上重构——先改数据模型，再改地图构建器，再改寻路方向约束，最后适配 WMS/WES/Simulation 层。所有旧测试删除重写。

**Tech Stack:** Python, Pydantic v2, NumPy, OR-Tools, SciPy, Matplotlib

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `src/warehouse/models.py` | 新增 RackZoneConfig/RackRow/AisleConfig 模型，修改 MapConfig |
| 重写 | `src/warehouse/maps/medium_50x50.py` | 新对称布局：9 区域 + 6 端口 |
| 删除 | `src/warehouse/maps/large_100x100.py` | 旧地图不再适配 |
| 删除 | `src/warehouse/maps/extreme.py` | 旧极端地图不再适配 |
| 重写 | `src/warehouse/fleet/map_builder.py` | 新增货架/巷道构建逻辑，格子类型扩展，方向感知 is_passable |
| 修改 | `src/warehouse/fleet/pathfinding.py` | _is_passable 加入巷道方向约束 |
| 修改 | `src/warehouse/wms/inventory.py` | 适配新储位命名（Zone_Rn_Bn 格式） |
| 修改 | `src/warehouse/wes/clustering.py` | _get_zone 适配新区域名 |
| 修改 | `src/warehouse/simulation/visualizer.py` | 绘制新布局（货架+巷道） |
| 修改 | `main_simulation.py` | 移除旧地图导入 |
| 删除+重写 | `tests/warehouse/test_*.py` | 全部旧测试删除，按模块重写 |

---

### Task 1: 数据模型 — models.py

**Files:**
- Modify: `src/warehouse/models.py`

- [ ] **Step 1: 在 MapConfig 之前新增 3 个模型类**

在 `AblationFlags` 类之后、`MapConfig` 类之前，新增：

```python
class RackRow(BaseModel):
    """一行货架"""
    row_id: str
    positions: list[str]
    y_offset: int


class AisleConfig(BaseModel):
    """巷道配置"""
    aisle_id: str
    direction: str           # "down" | "up"
    y_offset: int


class RackZoneConfig(BaseModel):
    """货架区域配置"""
    zone_id: str
    zone_type: str           # "mechanical" | "electrical" | "consumable" | "safety" | "tool"
    pos: tuple[int, int]
    width: int = 14
    height: int = 10
    num_rows: int = 5
    bays_per_row: int = 10
    sub_aisle_cols: list[int] = Field(default_factory=lambda: [3, 6, 9, 12])
    color: str = ""
```

- [ ] **Step 2: 修改 MapConfig，替换 warehouse_zones 为 rack_zones**

将 `MapConfig` 的 `warehouse_zones: dict[str, dict] = {}` 替换为：

```python
class MapConfig(BaseModel):
    name: str
    display_name: str
    grid_size: int
    description: str = ""
    rack_zones: dict[str, RackZoneConfig] = {}
    main_aisle_width: int = 3
    sub_aisle_width: int = 1
    ports: dict[str, dict] = {}
    agv_init_positions: list[tuple[int, int]] = []
    agv_count: int = 8
    conflict_segments: dict[str, dict] = {}
    yield_points: dict[str, tuple[int, int]] = {}
    charging_points: list[tuple[int, int]] = []
    main_channels_x: list[int] = []
    main_channels_y: list[int] = []
```

注意删除 `warehouse_zones` 字段，新增 `rack_zones`、`main_aisle_width`、`sub_aisle_width`。

- [ ] **Step 3: 提交**

```bash
git add src/warehouse/models.py
git commit -m "refactor(models): 新增 RackZoneConfig/RackRow/AisleConfig，MapConfig 用 rack_zones 替代 warehouse_zones"
```

---

### Task 2: 地图构建器 — map_builder.py

**Files:**
- Rewrite: `src/warehouse/fleet/map_builder.py`

- [ ] **Step 1: 重写整个 map_builder.py**

新内容要点：
- 格子类型常量新增 `MAP_STORAGE=2`, `MAP_AISLE_DOWN=6`, `MAP_AISLE_UP=7`, `MAP_SUB_AISLE=8`（删除 `MAP_WAREHOUSE`）
- `WarehouseMap.__init__` 中新增 `aisle_info: dict[str, AisleConfig]`
- `_build()` 方法：
  1. 主通道：用 `main_channels_x` 和 `main_channels_y`，宽度取自 `config.main_aisle_width`
  2. 端口：遍历 `config.ports`
  3. 充电桩：遍历 `config.charging_points`
  4. 避让点：遍历 `config.yield_points`
  5. 货架区域：遍历 `config.rack_zones`，调用 `_build_rack_zone(zone_cfg)`
  6. `_build_rack_zone(zone_cfg)` 内部逻辑：
     - 遍历 zone 的行（0..num_rows-1），y_offset = row_idx * 2（每行1格货架+1格巷道交替）
     - 偶数行偏移 = 行号*2，绘制该行的储位格子（跳过 sub_aisle_cols 列）
     - 奇数偏移 = 行号*2+1，绘制巷道（AISLE_DOWN 或 AISLE_UP 交替）
     - 最后 y_offset=height-1 绘制区域出入口行（PASSABLE）
     - 在每个 sub_aisle_col 位置，贯穿所有行绘制 SUB_AISLE
     - 生成储位名 `ZoneName_R{row+1}_B{bay+1}` 并记录到 `zone_pos` 和 `storage_list`
- `is_passable(x, y, dx=0, dy=0)` 方法：
  - 获取 `cell = grid[y][x]`
  - `MAP_AISLE_DOWN`: 只允许 `dy > 0`（向下）或 `dx != 0`（横向进出子通道）
  - `MAP_AISLE_UP`: 只允许 `dy < 0`（向上）或 `dx != 0`
  - `MAP_STORAGE`: 视为可通过（AGV 进入取货），但检查 boundary
  - `MAP_SUB_AISLE`, `MAP_PASSABLE`, `MAP_PORT`, `MAP_CHARGING`, `MAP_YIELD_POINT`: 自由通过
  - `MAP_OBSTACLE`: 不可通过
  - 越界检查

- [ ] **Step 2: 提交**

```bash
git add src/warehouse/fleet/map_builder.py
git commit -m "refactor(map_builder): 行列式货架构建，新增巷道/子通道格子类型，方向感知 is_passable"
```

---

### Task 3: 地图预设 — medium_50x50.py

**Files:**
- Rewrite: `src/warehouse/maps/medium_50x50.py`

- [ ] **Step 1: 重写整个 medium_50x50.py**

使用 `RackZoneConfig` 定义 9 个区域：

```python
from src.warehouse.maps.base import MapRegistry, BaseMap
from src.warehouse.models import MapConfig, RackZoneConfig


@MapRegistry.register("medium_50x50")
class Medium50x50(BaseMap):
    def build(self) -> MapConfig:
        return MapConfig(
            name="medium_50x50",
            display_name="港口备件仓库 (50×50)",
            grid_size=50,
            description="行列式货架仓，9区域，6端口，主通道3格双向+巷道1格单向",
            main_aisle_width=3,
            sub_aisle_width=1,
            main_channels_x=[16, 17, 18, 32, 33, 34],
            main_channels_y=[5, 6, 7, 18, 19, 20, 31, 32, 33, 44, 45, 46],
            rack_zones={
                "Mech1": RackZoneConfig(zone_id="Mech1", zone_type="mechanical", pos=(2, 8), color="#FF7F0E"),
                "Elec1": RackZoneConfig(zone_id="Elec1", zone_type="electrical", pos=(19, 8), color="#4FC3F7"),
                "Mech2": RackZoneConfig(zone_id="Mech2", zone_type="mechanical", pos=(35, 8), color="#FF9E4A"),
                "Elec2": RackZoneConfig(zone_id="Elec2", zone_type="electrical", pos=(2, 21), color="#0288D1"),
                "Cons1": RackZoneConfig(zone_id="Cons1", zone_type="consumable", pos=(19, 21), color="#2CA02C"),
                "Cons2": RackZoneConfig(zone_id="Cons2", zone_type="consumable", pos=(35, 21), color="#54C954"),
                "Safety": RackZoneConfig(zone_id="Safety", zone_type="safety", pos=(2, 35), color="#9467BD"),
                "Tool": RackZoneConfig(zone_id="Tool", zone_type="tool", pos=(19, 35), color="#8C564B"),
                "Cons3": RackZoneConfig(zone_id="Cons3", zone_type="consumable", pos=(35, 35), color="#7CD97C"),
            },
            ports={
                "IN-L": {"pos": (9, 3), "area": (2, 15, 2, 4), "type": "INBOUND"},
                "IN-C": {"pos": (25, 3), "area": (19, 31, 2, 4), "type": "INBOUND"},
                "IN-R": {"pos": (41, 3), "area": (35, 47, 2, 4), "type": "INBOUND"},
                "OUT-L": {"pos": (9, 48), "area": (2, 15, 47, 49), "type": "OUTBOUND"},
                "OUT-C": {"pos": (25, 48), "area": (19, 31, 47, 49), "type": "OUTBOUND"},
                "OUT-R": {"pos": (41, 48), "area": (35, 47, 47, 49), "type": "OUTBOUND"},
            },
            agv_init_positions=[
                (9, 6), (25, 6), (41, 6),
                (9, 19), (25, 19), (41, 19),
                (9, 45), (25, 45),
            ],
            agv_count=8,
            conflict_segments={},
            yield_points={},
            charging_points=[(2, 2), (47, 2), (2, 47), (47, 47)],
        )
```

注意：`conflict_segments` 和 `yield_points` 设为空，因为新布局通过单向巷道解决冲突，不再需要旧式冲突段。主通道十字路口的冲突由时空 A* 自然处理。

- [ ] **Step 2: 提交**

```bash
git add src/warehouse/maps/medium_50x50.py
git commit -m "refactor(maps): 新对称 50x50 预设 — 9货架区域 + 6端口"
```

---

### Task 4: 清理旧地图预设

**Files:**
- Delete: `src/warehouse/maps/large_100x100.py`
- Delete: `src/warehouse/maps/extreme.py`

- [ ] **Step 1: 删除旧地图文件**

```bash
rm src/warehouse/maps/large_100x100.py
rm src/warehouse/maps/extreme.py
```

- [ ] **Step 2: 提交**

```bash
git add -A src/warehouse/maps/
git commit -m "chore: 删除旧地图预设 (large_100x100, extreme)"
```

---

### Task 5: 寻路方向约束 — pathfinding.py

**Files:**
- Modify: `src/warehouse/fleet/pathfinding.py`

- [ ] **Step 1: 更新导入**

将第 11-13 行的导入改为：

```python
from src.warehouse.fleet.map_builder import (
    MAP_PASSABLE, MAP_STORAGE, MAP_PORT, MAP_YIELD_POINT, MAP_CHARGING,
    MAP_AISLE_DOWN, MAP_AISLE_UP, MAP_SUB_AISLE,
)
```

- [ ] **Step 2: 重写 `_is_passable` 方法**

将 `_is_passable` 方法（约第 99-117 行）替换为：

```python
def _is_passable(self, cur: tuple[int, int], nxt: tuple[int, int],
                 cur_dir_str: str, move_dir_str: str) -> bool:
    gs = self.wmap.config.grid_size
    nx, ny = nxt
    if not (0 <= nx < gs and 0 <= ny < gs):
        return False
    cell = self.grid[ny][nx]
    # 不可通过
    if cell == 0:  # MAP_OBSTACLE
        return False
    # 单向巷道方向约束
    if cell == MAP_AISLE_DOWN:
        dx, dy = nx - cur[0], ny - cur[1]
        if dy < 0:  # 禁止向上进入/穿过 ↓ 巷道
            return False
    if cell == MAP_AISLE_UP:
        dx, dy = nx - cur[0], ny - cur[1]
        if dy > 0:  # 禁止向下进入/穿过 ↑ 巷道
            return False
    # 储位可进入但不可穿越（仅当目标或来源时通过）
    if cell == MAP_STORAGE:
        pass  # 允许 AGV 进入储位
    return True
```

注意：删除旧的 `conflict_segments` 单向约束逻辑，改为基于格子类型的方向检查。`MAP_STORAGE` 允许 AGV 进入（用于取放货）。

- [ ] **Step 3: 更新 `find_path` 中的冲突路段检测**

在 `find_path` 方法中（约第 239-252 行），将 `conflict_segments` 检测逻辑简化。因为新地图 `conflict_segments` 为空，这段代码自然不会触发，但保留结构以便未来扩展：

```python
# 冲突路段检测（保留，新地图中 conflict_segments 为空）
if self.config.ablation.enable_conflict_avoid:
    seg_id, seg_dir = self._is_in_conflict_segment(nxt)
    if seg_id:
        seg_free, _ = self.st_table.check_segment(seg_id, seg_dir, cur_t + 1, next_t, agv_id)
        if not seg_free:
            yp_id = self.wmap.config.conflict_segments[seg_id]["yield_points"][0]
            yp_free, _ = self.st_table.check_yield_point(yp_id, cur_t + 1, cur_t + 15, agv_id)
            if yp_free:
                self.st_table.lock_yield_point(yp_id, cur_t + 1, cur_t + 15, agv_id)
                yp_pos = self.wmap.config.yield_points[yp_id]
                nxt = yp_pos
                next_t = cur_t + 15
            else:
                continue
```

这段代码不变，只是在新地图中 `conflict_segments` 为空所以 `_is_in_conflict_segment` 永远返回 `(None, None)`。

- [ ] **Step 4: 更新 `precompute_all_paths`**

将 `precompute_all_paths` 方法中（约第 274-285 行）对 `self.wmap.warehouse_zones` 的引用改为：

```python
def precompute_all_paths(self) -> None:
    if not self.config.ablation.enable_path_cache:
        return
    key_points = []
    key_points.extend([self.wmap.zone_pos[z] for z in self.wmap.rack_zone_names])
    key_points.extend([pcfg["pos"] for pcfg in self.wmap.port_info.values()])
    key_points.extend(self.wmap.config.agv_init_positions)
    for i, start in enumerate(key_points):
        for j, end in enumerate(key_points):
            if i != j:
                self.find_base_path(start, end)
```

- [ ] **Step 5: 提交**

```bash
git add src/warehouse/fleet/pathfinding.py
git commit -m "refactor(pathfinding): 基于格子类型的巷道方向约束，替代旧 conflict_segments 方向检查"
```

---

### Task 6: WMS 层适配

**Files:**
- Modify: `src/warehouse/wms/inventory.py`
- Modify: `src/warehouse/wms/order_manager.py`

- [ ] **Step 1: 重写 `inventory.py` 的 `_init_inventory`**

将 `_init_inventory` 方法改为遍历 `rack_zones` 而非 `warehouse_zones`：

```python
def _init_inventory(self, seed: int):
    rng = random.Random(seed)
    model_names = [f"M{i * 100}" for i in range(1, 50)]
    part_names = {
        "mechanical": ["轴承", "齿轮", "液压泵", "联轴器", "制动器"],
        "electrical": ["电机", "传感器", "电缆", "控制器", "继电器"],
        "consumable": ["密封件", "润滑油", "滤芯", "阀门", "油管"],
        "safety": ["安全帽", "手套", "护目镜", "安全带", "防护服"],
        "tool": ["扳手", "万用表", "电钻", "螺丝刀", "钳子"],
    }
    idx = 0
    for zone_name, zone_cfg in self.config.rack_zones.items():
        zone_type = zone_cfg.zone_type
        parts = part_names.get(zone_type, ["备件"])
        for row in range(1, zone_cfg.num_rows + 1):
            for bay in range(1, zone_cfg.bays_per_row + 1):
                sname = f"{zone_name}_R{row}_B{bay}"
                qty = rng.randint(0, 3)
                model = model_names[idx % len(model_names)]
                self._storage_status[sname] = qty
                if model not in self._items:
                    self._items[model] = InventoryItem(
                        model=model,
                        part_name=parts[idx % len(parts)],
                        quantity=qty,
                        location=sname,
                        zone=zone_name,
                    )
                idx += 1
```

同时更新 `get_all_zone_names`：

```python
def get_all_zone_names(self) -> list[str]:
    return list(self.config.rack_zones.keys())
```

- [ ] **Step 2: order_manager.py 无需修改**

`order_manager.py` 通过 `map_config.ports` 动态获取端口列表，6 端口会自动适配。

- [ ] **Step 3: 提交**

```bash
git add src/warehouse/wms/inventory.py
git commit -m "refactor(inventory): 适配 rack_zones 储位命名 (Zone_Rn_Bn)"
```

---

### Task 7: WES 聚类适配

**Files:**
- Modify: `src/warehouse/wes/clustering.py`

- [ ] **Step 1: 修改 `_get_zone` 方法**

将 `_get_zone` 方法（第 24-31 行）改为从储位名中提取区域名：

```python
def _get_zone(self, location: str) -> str:
    # 从 "Mech1_R1_B1" 提取 "Mech1"
    parts = location.split("_")
    if parts:
        return parts[0]
    return "Unknown"
```

- [ ] **Step 2: 提交**

```bash
git add src/warehouse/wes/clustering.py
git commit -m "refactor(clustering): _get_zone 适配新储位命名格式"
```

---

### Task 8: Simulation 层适配

**Files:**
- Modify: `src/warehouse/simulation/visualizer.py`

- [ ] **Step 1: 更新 visualizer.py 的 zone 颜色映射**

找到 `VisualStyle` 类中的颜色定义，将旧 zone 颜色映射（Raw/Finished/Spare）替换为新区域类型颜色映射：

```python
ZONE_COLORS = {
    "Mech1": "#FF7F0E", "Mech2": "#FF9E4A",
    "Elec1": "#4FC3F7", "Elec2": "#0288D1",
    "Cons1": "#2CA02C", "Cons2": "#54C954", "Cons3": "#7CD97C",
    "Safety": "#9467BD", "Tool": "#8C564B",
}
```

同时更新 `plot_base_map` 方法中对 `warehouse_zones` 的引用为 `rack_zones`，绘制区域时使用新的 14×10 尺寸。

- [ ] **Step 2: 提交**

```bash
git add src/warehouse/simulation/visualizer.py
git commit -m "refactor(visualizer): 适配新区域布局和颜色"
```

---

### Task 9: 入口文件清理

**Files:**
- Modify: `main_simulation.py`

- [ ] **Step 1: 移除旧地图导入**

删除第 77-78 行的旧地图导入：

```python
import src.warehouse.maps.large_100x100  # noqa: F401
import src.warehouse.maps.extreme  # noqa: F401
```

只保留：

```python
import src.warehouse.maps.medium_50x50  # noqa: F401
```

- [ ] **Step 2: 提交**

```bash
git add main_simulation.py
git commit -m "chore: 移除旧地图导入，仅保留 medium_50x50"
```

---

### Task 10: 测试重写 — 地图构建

**Files:**
- Delete all: `tests/warehouse/test_*.py`
- Create: `tests/warehouse/test_models.py`
- Create: `tests/warehouse/test_map_builder.py`
- Create: `tests/warehouse/test_maps.py`

- [ ] **Step 1: 删除所有旧测试**

```bash
rm tests/warehouse/test_*.py
```

- [ ] **Step 2: 编写 test_models.py**

```python
from src.warehouse.models import (
    RackZoneConfig, RackRow, AisleConfig, MapConfig, TaskType,
)


def test_rack_zone_config_defaults():
    zone = RackZoneConfig(zone_id="Mech1", zone_type="mechanical", pos=(2, 8))
    assert zone.width == 14
    assert zone.height == 10
    assert zone.num_rows == 5
    assert zone.bays_per_row == 10
    assert zone.sub_aisle_cols == [3, 6, 9, 12]


def test_map_config_has_rack_zones():
    zone = RackZoneConfig(zone_id="Test", zone_type="tool", pos=(0, 0))
    cfg = MapConfig(
        name="test", display_name="test", grid_size=50,
        rack_zones={"Test": zone},
    )
    assert "Test" in cfg.rack_zones
    assert cfg.main_aisle_width == 3
    assert cfg.sub_aisle_width == 1
```

- [ ] **Step 3: 编写 test_map_builder.py**

关键测试点：
- 地图构建后 `storage_list` 长度 = 9 × 50 = 450
- 每个 `zone_pos` 中的储位坐标在网格范围内
- 主通道格子类型为 `MAP_PASSABLE`
- 端口格子类型为 `MAP_PORT`
- 充电桩格子类型为 `MAP_CHARGING`
- 巷道格子有 `MAP_AISLE_DOWN` 和 `MAP_AISLE_UP`
- 子通道格子为 `MAP_SUB_AISLE`
- `is_passable` 对 ↓ 巷道拒绝向上移动
- `is_passable` 对 ↑ 巷道拒绝向下移动
- `is_passable` 对 ↓ 巷道允许横向移动（进出子通道）
- 主通道所有格子 passable

```python
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import (
    WarehouseMap, MAP_PASSABLE, MAP_PORT, MAP_CHARGING,
    MAP_STORAGE, MAP_AISLE_DOWN, MAP_AISLE_UP, MAP_SUB_AISLE,
)
import src.warehouse.maps.medium_50x50


def test_storage_count():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    assert len(wmap.storage_list) == 450


def test_zone_names():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    expected = {"Mech1", "Elec1", "Mech2", "Elec2", "Cons1", "Cons2", "Safety", "Tool", "Cons3"}
    assert set(wmap.rack_zone_names) == expected


def test_port_cells():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    for name, pcfg in cfg.ports.items():
        px, py = pcfg["pos"]
        assert wmap.grid[py][px] == MAP_PORT


def test_charging_cells():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    for cx, cy in cfg.charging_points:
        assert wmap.grid[cy][cx] == MAP_CHARGING


def test_main_channels_passable():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    # H1 channel: y=6 should be passable
    assert wmap.grid[6][9] == MAP_PASSABLE
    # V1 channel: x=17 should be passable
    assert wmap.grid[10][17] == MAP_PASSABLE


def test_aisle_direction_cells():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    # Check that some AISLE_DOWN and AISLE_UP cells exist
    down_count = (wmap.grid == MAP_AISLE_DOWN).sum()
    up_count = (wmap.grid == MAP_AISLE_UP).sum()
    assert down_count > 0
    assert up_count > 0


def test_is_passable_aisle_down():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    # Find an AISLE_DOWN cell
    positions = list(zip(*((wmap.grid == MAP_AISLE_DOWN).nonzero())))
    if positions:
        y, x = positions[0]
        assert wmap.is_passable(x, y, dx=0, dy=1)   # down allowed
        assert not wmap.is_passable(x, y, dx=0, dy=-1)  # up blocked


def test_is_passable_aisle_up():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    positions = list(zip(*((wmap.grid == MAP_AISLE_UP).nonzero())))
    if positions:
        y, x = positions[0]
        assert wmap.is_passable(x, y, dx=0, dy=-1)  # up allowed
        assert not wmap.is_passable(x, y, dx=0, dy=1)   # down blocked
```

- [ ] **Step 4: 编写 test_maps.py**

```python
from src.warehouse.maps.base import MapRegistry
import src.warehouse.maps.medium_50x50


def test_medium_registered():
    cfg = MapRegistry.get("medium_50x50")
    assert cfg.grid_size == 50
    assert len(cfg.rack_zones) == 9
    assert len(cfg.ports) == 6
    assert cfg.agv_count == 8
    assert len(cfg.charging_points) == 4


def test_port_types():
    cfg = MapRegistry.get("medium_50x50")
    inbound = [n for n, c in cfg.ports.items() if c["type"] == "INBOUND"]
    outbound = [n for n, c in cfg.ports.items() if c["type"] == "OUTBOUND"]
    assert len(inbound) == 3
    assert len(outbound) == 3


def test_zone_types():
    cfg = MapRegistry.get("medium_50x50")
    types = [z.zone_type for z in cfg.rack_zones.values()]
    assert types.count("mechanical") == 2
    assert types.count("electrical") == 2
    assert types.count("consumable") == 3
    assert types.count("safety") == 1
    assert types.count("tool") == 1
```

- [ ] **Step 5: 运行测试验证**

```bash
python -m pytest tests/warehouse/test_models.py tests/warehouse/test_map_builder.py tests/warehouse/test_maps.py -v
```

Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add tests/warehouse/
git commit -m "test: 重写地图构建测试 — 模型、构建器、预设验证"
```

---

### Task 11: 测试重写 — WMS/WES 层

**Files:**
- Create: `tests/warehouse/test_inventory.py`
- Create: `tests/warehouse/test_order_manager.py`
- Create: `tests/warehouse/test_task_decomposer.py`
- Create: `tests/warehouse/test_clustering.py`

- [ ] **Step 1: 编写 test_inventory.py**

```python
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.wms.inventory import InventoryManager
import src.warehouse.maps.medium_50x50


def test_inventory_storage_count():
    cfg = MapRegistry.get("medium_50x50")
    inv = InventoryManager(cfg)
    assert len(inv.get_storage_names()) == 450


def test_inventory_zone_names():
    cfg = MapRegistry.get("medium_50x50")
    inv = InventoryManager(cfg)
    zones = inv.get_all_zone_names()
    assert len(zones) == 9


def test_inventory_allocate():
    cfg = MapRegistry.get("medium_50x50")
    inv = InventoryManager(cfg)
    loc = inv.allocate_stock("M100", 1)
    # May or may not find it depending on random seed
    assert isinstance(loc, str)
```

- [ ] **Step 2: 编写 test_order_manager.py**

```python
from src.warehouse.maps.base import MapRegistry
from src.warehouse.wms.order_manager import OrderManager
import src.warehouse.maps.medium_50x50


def test_order_six_ports():
    cfg = MapRegistry.get("medium_50x50")
    om = OrderManager(cfg)
    assert len(om.inbound_ports) == 3
    assert len(om.outbound_ports) == 3


def test_random_orders():
    cfg = MapRegistry.get("medium_50x50")
    om = OrderManager(cfg)
    orders = om.from_random(10)
    assert len(orders) == 10
```

- [ ] **Step 3: 编写 test_clustering.py**

```python
from src.warehouse.models import TransportTask, TaskType, OrderPriority
from src.warehouse.wes.clustering import OrderClusterer


def test_get_zone_new_format():
    from src.warehouse.fleet.pathfinding import PathFinder
    from src.warehouse.maps.base import MapRegistry
    from src.warehouse.fleet.map_builder import WarehouseMap
    from src.warehouse.wms.config import WarehouseConfig
    import src.warehouse.maps.medium_50x50

    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig(ablation={"enable_path_cache": False})
    pf = PathFinder(wmap, config)
    clusterer = OrderClusterer(pf, config)
    assert clusterer._get_zone("Mech1_R1_B1") == "Mech1"
    assert clusterer._get_zone("Cons2_R3_B7") == "Cons2"
    assert clusterer._get_zone("Safety_R5_B10") == "Safety"
    assert clusterer._get_zone("Unknown") == "Unknown"
```

- [ ] **Step 4: 运行测试**

```bash
python -m pytest tests/warehouse/test_inventory.py tests/warehouse/test_order_manager.py tests/warehouse/test_clustering.py -v
```

- [ ] **Step 5: 提交**

```bash
git add tests/warehouse/
git commit -m "test: WMS/WES 层测试 — inventory/order/clustering"
```

---

### Task 12: 测试重写 — 寻路与 Fleet 层

**Files:**
- Create: `tests/warehouse/test_pathfinding.py`
- Create: `tests/warehouse/test_fleet_manager.py`
- Create: `tests/warehouse/test_config.py`

- [ ] **Step 1: 编写 test_pathfinding.py**

```python
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.pathfinding import PathFinder
from src.warehouse.wms.config import WarehouseConfig
import src.warehouse.maps.medium_50x50


def _make_pf():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    return PathFinder(wmap, config), wmap


def test_path_between_ports():
    pf, wmap = _make_pf()
    start = wmap.port_info["IN-L"]["pos"]
    end = wmap.port_info["OUT-L"]["pos"]
    path, dist = pf.find_base_path(start, end)
    assert len(path) > 1
    assert dist > 0


def test_path_to_storage():
    pf, wmap = _make_pf()
    start = wmap.port_info["IN-C"]["pos"]
    end = wmap.zone_pos["Cons1_R1_B1"]
    path, dist = pf.find_base_path(start, end)
    assert len(path) > 1


def test_path_cross_zone():
    pf, wmap = _make_pf()
    start = wmap.zone_pos["Mech1_R1_B1"]
    end = wmap.zone_pos["Cons3_R5_B10"]
    path, dist = pf.find_base_path(start, end)
    assert len(path) > 1


def test_get_distance():
    pf, wmap = _make_pf()
    d = pf.get_distance(wmap.port_info["IN-L"]["pos"], wmap.port_info["OUT-R"]["pos"])
    assert d > 0
```

- [ ] **Step 2: 编写 test_fleet_manager.py**

```python
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.fleet_manager import FleetManager
from src.warehouse.wms.config import WarehouseConfig
import src.warehouse.maps.medium_50x50


def test_fleet_init():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    fleet = FleetManager(wmap, config)
    assert fleet.path_finder is not None


def test_precompute():
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig()
    fleet = FleetManager(wmap, config)
    fleet.precompute()
    assert len(fleet.path_finder._dist_cache) > 0
```

- [ ] **Step 3: 运行测试**

```bash
python -m pytest tests/warehouse/test_pathfinding.py tests/warehouse/test_fleet_manager.py tests/warehouse/test_config.py -v
```

- [ ] **Step 4: 提交**

```bash
git add tests/warehouse/
git commit -m "test: 寻路和 Fleet 层测试"
```

---

### Task 13: 端到端测试

**Files:**
- Create: `tests/warehouse/test_integration.py`
- Create: `tests/warehouse/test_simulator.py`

- [ ] **Step 1: 编写 test_integration.py**

```python
from src.warehouse.maps.base import MapRegistry
from src.warehouse.fleet.map_builder import WarehouseMap
from src.warehouse.fleet.fleet_manager import FleetManager
from src.warehouse.wms.config import WarehouseConfig
from src.warehouse.wms.order_manager import OrderManager
from src.warehouse.wes.task_decomposer import TaskDecomposer
from src.warehouse.wes.clustering import OrderClusterer
from src.warehouse.simulation.simulator import Simulator
import src.warehouse.maps.medium_50x50


def test_full_pipeline():
    """端到端：地图→订单→分解→聚类→调度→仿真"""
    cfg = MapRegistry.get("medium_50x50")
    wmap = WarehouseMap(cfg)
    config = WarehouseConfig(ORDER_NUM=10)

    fleet = FleetManager(wmap, config)
    fleet.precompute()

    om = OrderManager(cfg, seed=config.RANDOM_SEED)
    orders = om.from_random(10)
    assert len(orders) == 10

    td = TaskDecomposer(None, om.inbound_ports, om.outbound_ports, seed=config.RANDOM_SEED)
    tasks = td.decompose(orders, wmap.storage_list)
    assert len(tasks) > 0

    clusterer = OrderClusterer(fleet.path_finder, config)
    clusters = clusterer.cluster(tasks, config.AGV_MAX_TASK_CAPACITY, wmap.zone_pos)
    assert len(clusters) > 0

    agv_tasks, est = fleet.schedule(clusters)
    assert est > 0

    sim = Simulator(wmap, fleet, config)
    result = sim.run(agv_tasks, est)
    assert result.makespan > 0
    assert result.total_distance > 0
```

- [ ] **Step 2: 运行全部测试**

```bash
python -m pytest tests/warehouse/ -v
```

Expected: 全部 PASS

- [ ] **Step 3: 提交**

```bash
git add tests/warehouse/
git commit -m "test: 端到端集成测试 — 完整管道验证"
```

---

### Task 14: 运行消融实验验证

**Files:**
- No file changes

- [ ] **Step 1: 运行单次仿真**

```bash
python main_simulation.py medium_50x50 20
```

Expected: 正常输出 makespan、距离、利用率等指标。

- [ ] **Step 2: 运行消融实验**

```bash
python main_simulation.py --ablation medium_50x50 20
```

Expected: 6 组实验正常完成，输出对比表。

- [ ] **Step 3: 最终提交（如有修复）**

如有任何 bug 修复，在此提交。
