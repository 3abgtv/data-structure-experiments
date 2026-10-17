"""数据模型层（Model）。

本模块只回答一个问题：图中的顶点和边长什么样。
它不含任何搜索算法，也不含任何界面代码，对应任务书
"将图结构（Graph）、算法引擎（Solver）与界面（UI）逻辑解耦"的编程规范。

对应实验报告第一章的建模结果：

    图 G = (V, E)
    顶点 v = (ID, 名称, 坐标)      —— Vertex
    边   e = (距离, 线路 ID)       —— Edge
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(slots=True)
class Vertex:
    """站点，即图 G=(V,E) 中的顶点 v。

    Attributes:
        vid:  站点 ID，唯一标识一个站点。
        name: 站名。
        x:    平面坐标 X，单位 km。
        y:    平面坐标 Y，单位 km。
    """

    vid: str
    name: str
    x: float
    y: float

    def straight_distance_to(self, other: Vertex) -> float:
        """两站之间的欧几里得直线距离（km）。

        这个函数同时就是 A* 的启发函数 h(n)。它可以直接拿来当 h 用，
        原因在于：任意一条线路在两个站点之间的实际走行距离都不小于
        两点间的直线距离，所以 h(n) 永远不会高估从 n 到终点的真实剩余
        代价 —— 即 h 是可采纳（admissible）的，A* 因此仍能求出最优解。
        """
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass(slots=True)
class Edge:
    """邻接表中的一条出边。

    Attributes:
        to:       该边指向的站点 ID。
        line_id:  该边所属的线路 ID（换乘判定依据）。
        distance: 边长，单位 km。
        minutes:  乘坐该边预计耗费的时间，单位分钟。
    """

    to: str
    line_id: str
    distance: float
    minutes: float


@dataclass(slots=True)
class Line:
    """一条地铁/公交线路。

    Attributes:
        lid:       线路 ID。
        name:      线路名，如"1 号线"。
        color:     绘制用的颜色（#RRGGBB）。
        stations:  按行车顺序排列的站点 ID 列表。
        speed_kmh: 该线路的平均旅行速度。
        detour:    绕行系数，实际走行距离相对直线距离的放大倍数。
    """

    lid: str
    name: str
    color: str
    stations: list[str]
    speed_kmh: float = 45.0
    detour: float = 1.12


@dataclass(slots=True)
class Leg:
    """路径中"在同一线路上连续乘坐"的一段，用于生成换乘指引。"""

    line_id: str
    line_name: str
    color: str
    stations: list[str]
    distance: float
    minutes: float


@dataclass(slots=True)
class Route:
    """一次搜索的最终结果。"""

    found: bool
    path: list[str] = field(default_factory=list)
    legs: list[Leg] = field(default_factory=list)
    distance: float = 0.0
    minutes: float = 0.0
    transfers: int = 0
    message: str = ""

    @property
    def stops(self) -> int:
        """乘坐的站数（不含起点站）。"""
        return max(0, len(self.path) - 1)


@dataclass(slots=True)
class SearchStats:
    """搜索过程的统计量，用于性能对比与搜索动画。"""

    settled: int = 0
    relaxed: int = 0
    pushed: int = 0
    peak_frontier: int = 0
    seconds: float = 0.0
    settle_order: list[str] = field(default_factory=list)

    @property
    def milliseconds(self) -> float:
        return self.seconds * 1000.0

    @property
    def unique_settled(self) -> int:
        """被确定的**去重站点数**。

        Dijkstra / A* 的状态就是站点本身，settled 与它相同；
        最少换乘 BFS 的状态是 (站点, 线路) 对，同一个站点可能在多条
        线路上各被展开一次，因此单独用去重后的站点数做横向对比。
        """
        return len(set(self.settle_order))
