"""图结构层（Graph）：以邻接表存储的城市轨道交通网络。

选型理由（对应实验报告第二章）：

真实城市交通图是典型的**稀疏图** —— 站点数 n 远大于每个站的平均度数，
地铁站通常只与 2~4 个相邻站相连。若使用邻接矩阵，空间开销是 O(n^2)：
本站示例网络有 65 个站，就要维护 4225 个格子，而其中有边的格子只占 3.4%，
绝大多数空间被浪费；此外每扩展一个站点都要扫描整行 O(n) 才能找到它的邻居。
改用邻接表后，空间降为 O(n + e)，扩展一个站只需遍历 deg(v) 条边。

邻接表按"出边"存储：由于地铁双向通行，线路中相邻的两站在表中会各有一条
指向对方的边。同一对站点之间可能存在多条分属不同线路的边（并行边），
这正是换乘判定所依赖的信息 —— 顶点的"线路 ID 集合"由这些并行边得来。
"""

from __future__ import annotations

from collections import deque

from .models import Edge, Line, Vertex


class Graph:
    """城市轨道交通网络。

    内部维护三份索引：
        _vertices  vid -> Vertex
        _adj       vid -> [Edge, ...]    邻接表
        _lines     lid -> Line
    """

    def __init__(self) -> None:
        self._vertices: dict[str, Vertex] = {}
        self._adj: dict[str, list[Edge]] = {}
        self._lines: dict[str, Line] = {}

    # ------------------------------------------------------------------
    # 顶点
    # ------------------------------------------------------------------
    def add_vertex(self, vertex: Vertex) -> None:
        """新增一个站点。"""
        self._vertices[vertex.vid] = vertex
        self._adj.setdefault(vertex.vid, [])

    def remove_vertex(self, vid: str) -> None:
        """删除一个站点，以及它关联的全部边。

        删除会**断开**经过该站的线路：断点前后的两个站不会因此直接相连
        （现实中列车不可能跳过一座车站）。于是一条线路可能被切成若干段，
        其中每一段长度不少于 2 的会以新的线路 ID 保留下来，例如原「1 号线」
        被切成 "L1" 与 "L1#2" 两条（对应任务书"支持动态增删"的要求）。
        """
        if vid not in self._vertices:
            return

        for line in list(self._lines.values()):
            if vid not in line.stations:
                continue
            self.remove_line(line.lid)

            segments: list[list[str]] = []
            current: list[str] = []
            for sid in line.stations:
                if sid == vid:
                    if len(current) >= 2:
                        segments.append(current)
                    current = []
                else:
                    current.append(sid)
            if len(current) >= 2:
                segments.append(current)

            for index, segment in enumerate(segments):
                suffix = "" if index == 0 else f"#{index + 1}"
                self.add_line(Line(
                    lid=line.lid + suffix,
                    name=line.name if index == 0 else f"{line.name}（续 {index}）",
                    color=line.color,
                    stations=segment,
                    speed_kmh=line.speed_kmh,
                    detour=line.detour,
                ))

        self._vertices.pop(vid, None)
        self._adj.pop(vid, None)

        # 清理其它站点指向它的残余边
        for u in self._adj:
            self._adj[u] = [e for e in self._adj[u] if e.to != vid]

    def has_vertex(self, vid: str) -> bool:
        return vid in self._vertices

    def vertex(self, vid: str) -> Vertex:
        return self._vertices[vid]

    def name_of(self, vid: str) -> str:
        """站点 ID -> 站名，找不到时原样返回 ID。"""
        v = self._vertices.get(vid)
        return v.name if v is not None else vid

    @property
    def vertices(self) -> dict[str, Vertex]:
        return self._vertices

    # ------------------------------------------------------------------
    # 线路与边
    # ------------------------------------------------------------------
    def add_line(self, line: Line) -> None:
        """把一条线路展开成若干条双向边写入邻接表。

        边长 = 两站直线距离 × 该线路的绕行系数；耗时 = 边长 / 旅行速度。
        绕行系数不小于 1，这一约束保证了"边长 ≥ 直线距离"，
        也就保证了 A* 的启发函数 h 不会高估真实代价。

        Raises:
            ValueError: 线路的站点不足两个，无法构成通路。
            KeyError: 线路引用了尚未登记的站点。
        """
        if len(line.stations) < 2:
            raise ValueError(
                f"线路「{line.name}」至少需要两个站点才能构成通路，"
                f"实际只有 {len(line.stations)} 个"
            )
        missing = [s for s in line.stations if s not in self._vertices]
        if missing:
            raise KeyError(f"线路「{line.name}」引用了不存在的站点：{missing}")

        for a, b in zip(line.stations, line.stations[1:]):
            if a == b:
                continue            # 零长自环对最短路径没有意义，直接跳过
            va, vb = self._vertices[a], self._vertices[b]
            distance = va.straight_distance_to(vb) * line.detour
            minutes = distance / line.speed_kmh * 60.0
            self._adj[a].append(Edge(b, line.lid, distance, minutes))
            self._adj[b].append(Edge(a, line.lid, distance, minutes))

        self._lines[line.lid] = line

    def remove_line(self, lid: str) -> None:
        """删除一条线路及其全部边。"""
        self._lines.pop(lid, None)
        for vid in self._adj:
            self._adj[vid] = [e for e in self._adj[vid] if e.line_id != lid]

    @property
    def lines(self) -> dict[str, Line]:
        return self._lines

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def neighbors(self, vid: str) -> list[Edge]:
        """某站的邻边表。"""
        return self._adj.get(vid, [])

    def edge_between(self, u: str, v: str, lid: str | None = None) -> Edge | None:
        """取出 u -> v 的边；给定线路 ID 时只在该线路上查找。

        同一对相邻站点可能同时属于多条线路，因此回放路径时必须带上
        线路 ID 才能取到正确的那条边。
        """
        for edge in self._adj.get(u, ()):
            if edge.to == v and (lid is None or edge.line_id == lid):
                return edge
        return None

    def lines_of(self, vid: str) -> list[str]:
        """经过该站的所有线路 ID（去重，顺序稳定，便于结果复现）。"""
        result: list[str] = []
        for e in self._adj.get(vid, ()):
            if e.line_id not in result:
                result.append(e.line_id)
        return result

    def is_transfer(self, vid: str) -> bool:
        """该站是否为换乘站（被两条及以上线路经过）。"""
        return len(self.lines_of(vid)) >= 2

    def transfer_stations(self) -> list[str]:
        return [vid for vid in self._vertices if self.is_transfer(vid)]

    @property
    def vertex_count(self) -> int:
        return len(self._vertices)

    @property
    def line_count(self) -> int:
        return len(self._lines)

    @property
    def edge_count(self) -> int:
        """无向边条数（= 有向出边数 / 2）。"""
        return sum(len(es) for es in self._adj.values()) // 2

    def bounds(self) -> tuple[float, float, float, float]:
        """返回整张图的坐标范围 (min_x, min_y, max_x, max_y)。"""
        if not self._vertices:
            return 0.0, 0.0, 1.0, 1.0
        xs = [v.x for v in self._vertices.values()]
        ys = [v.y for v in self._vertices.values()]
        return min(xs), min(ys), max(xs), max(ys)

    # ------------------------------------------------------------------
    # 连通性
    # ------------------------------------------------------------------
    def reachable_from(self, start: str) -> set[str]:
        """从 start 出发能到达的全部站点（BFS，用作算法结果的独立校验）。

        异常处理的基础：当终点不在这个集合里时，说明两站不连通。
        """
        if start not in self._vertices:
            return set()
        seen = {start}
        queue = deque([start])
        while queue:
            u = queue.popleft()
            for e in self._adj.get(u, ()):
                if e.to not in seen:
                    seen.add(e.to)
                    queue.append(e.to)
        return seen

    def is_connected(self) -> bool:
        """整张图是否连通。"""
        if not self._vertices:
            return True
        first = next(iter(self._vertices))
        return len(self.reachable_from(first)) == len(self._vertices)
