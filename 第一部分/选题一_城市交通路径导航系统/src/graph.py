"""图结构：以邻接表存储城市轨道交通网络。"""

from __future__ import annotations

from collections import deque

from .models import Edge, Line, Vertex


class Graph:
    """城市轨道交通网络。"""

    def __init__(self) -> None:
        self._vertices: dict[str, Vertex] = {}
        self._adj: dict[str, list[Edge]] = {}
        self._lines: dict[str, Line] = {}

    # ------------------------------------------------------------------
    # 顶点
    # ------------------------------------------------------------------
    def add_vertex(self, vertex: Vertex) -> None:
        self._vertices[vertex.vid] = vertex
        self._adj.setdefault(vertex.vid, [])

    def remove_vertex(self, vid: str) -> None:
        """删除站点及其关联边。

        经过该站的线路会在这一处断开，断点前后不会自动相连；长度不少于
        2 的剩余段各自保留为新线路。
        """
        if vid not in self._vertices:
            return

        # 先快照：循环体内会增删 _lines。
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

        for u in self._adj:
            self._adj[u] = [e for e in self._adj[u] if e.to != vid]

    def has_vertex(self, vid: str) -> bool:
        return vid in self._vertices

    def vertex(self, vid: str) -> Vertex:
        return self._vertices[vid]

    def name_of(self, vid: str) -> str:
        """站点 ID → 站名，找不到时原样返回 ID。"""
        v = self._vertices.get(vid)
        return v.name if v is not None else vid

    @property
    def vertices(self) -> dict[str, Vertex]:
        return self._vertices

    # ------------------------------------------------------------------
    # 线路与边
    # ------------------------------------------------------------------
    def add_line(self, line: Line) -> None:
        """把线路展开成双向边写入邻接表。

        边长 = 两站直线距离 × 绕行系数；绕行系数 >= 1 保证边长不小于
        直线距离，这是 A* 启发函数可采纳的前提。
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
                continue
            va, vb = self._vertices[a], self._vertices[b]
            distance = va.straight_distance_to(vb) * line.detour
            minutes = distance / line.speed_kmh * 60.0
            self._adj[a].append(Edge(b, line.lid, distance, minutes))
            self._adj[b].append(Edge(a, line.lid, distance, minutes))

        self._lines[line.lid] = line

    def remove_line(self, lid: str) -> None:
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
        return self._adj.get(vid, [])

    def edge_between(self, u: str, v: str, lid: str | None = None) -> Edge | None:
        """取 u → v 的边；同一对站点可能有并行边，需带线路 ID 才能取准。"""
        for edge in self._adj.get(u, ()):
            if edge.to == v and (lid is None or edge.line_id == lid):
                return edge
        return None

    def lines_of(self, vid: str) -> list[str]:
        """经过该站的线路 ID（去重，顺序稳定）。"""
        result: list[str] = []
        for e in self._adj.get(vid, ()):
            if e.line_id not in result:
                result.append(e.line_id)
        return result

    def is_transfer(self, vid: str) -> bool:
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
        """无向边条数（出边数折半）。"""
        return sum(len(es) for es in self._adj.values()) // 2

    def bounds(self) -> tuple[float, float, float, float]:
        if not self._vertices:
            return 0.0, 0.0, 1.0, 1.0
        xs = [v.x for v in self._vertices.values()]
        ys = [v.y for v in self._vertices.values()]
        return min(xs), min(ys), max(xs), max(ys)

    # ------------------------------------------------------------------
    # 连通性
    # ------------------------------------------------------------------
    def reachable_from(self, start: str) -> set[str]:
        """从 start 出发能到达的全部站点（BFS）。"""
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
        if not self._vertices:
            return True
        first = next(iter(self._vertices))
        return len(self.reachable_from(first)) == len(self._vertices)
