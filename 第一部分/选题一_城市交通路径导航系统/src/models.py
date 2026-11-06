"""数据模型：顶点、边、线路、路径与统计量。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Vertex:
    """站点，即图 G=(V,E) 中的顶点。"""

    vid: str
    name: str
    x: float
    y: float

    def straight_distance_to(self, other: Vertex) -> float:
        """欧几里得直线距离（km），同时用作 A* 的启发函数 h(n)。"""
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass
class Edge:
    """邻接表中的一条出边。"""

    to: str
    line_id: str
    distance: float
    minutes: float


@dataclass
class Line:
    """一条地铁/公交线路。"""

    lid: str
    name: str
    color: str
    stations: list[str]
    speed_kmh: float = 45.0
    detour: float = 1.12


@dataclass
class Leg:
    """在同一线路上连续乘坐的一段。"""

    line_id: str
    line_name: str
    color: str
    stations: list[str]
    distance: float
    minutes: float


@dataclass
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


@dataclass
class SearchStats:
    """搜索过程的统计量。"""

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
        """去重后的站点数；最少换乘 BFS 的状态是 (站点, 线路)。"""
        return len(set(self.settle_order))
