"""算法引擎：Dijkstra、A*、最少换乘 BFS。

三个求解器都实现 run()（生成器，逐步产出事件）与 solve()（一次跑完）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from heapq import heappop, heappush
from time import perf_counter
from typing import Iterator

from .graph import Graph
from .models import Leg, Route, SearchStats

INF = float("inf")

EVENT_VISIT = "visit"   # 一个站点被确定
EVENT_PUSH = "push"     # 一个站点被放入前沿
EVENT_DONE = "done"     # 搜索结束，携带 Route 与 SearchStats


class _AlgoClock:
    """只累计算法运行时间。

    在每次 next() 前后打点，把生成器挂起等待（界面渲染）的时间排除在外。
    """

    __slots__ = ("elapsed", "_mark")

    def __init__(self) -> None:
        self.elapsed = 0.0
        self._mark = perf_counter()

    def start(self) -> None:
        self._mark = perf_counter()

    def stop(self) -> None:
        self.elapsed += perf_counter() - self._mark


def _timed(inner: Iterator[dict], clock: _AlgoClock) -> Iterator[dict]:
    while True:
        clock.start()
        try:
            event = next(inner)
        except StopIteration:
            clock.stop()
            return
        clock.stop()
        if event.get("type") == EVENT_DONE:
            # 必须在 yield 之前写回，消费方拿到 done 时耗时已结算。
            event["stats"].seconds = clock.elapsed
        yield event


def _make_leg(graph: Graph, lid: str, stations: list[str], distance: float, minutes: float) -> Leg:
    line = graph.lines.get(lid)
    return Leg(
        line_id=lid,
        line_name=line.name if line else lid,
        color=line.color if line else "#888888",
        stations=list(stations),
        distance=distance,
        minutes=minutes,
    )


def build_route(graph: Graph, start: str, goal: str, hops: list[tuple[str, str, str]]) -> Route:
    """把每一跳 (起点站, 终点站, 线路 ID) 装配成 Route。"""
    if not hops:
        return Route(found=True, path=[start], message="起点与终点相同")

    path = [hops[0][0]] + [h[1] for h in hops]
    legs: list[Leg] = []
    total_distance = total_minutes = 0.0

    cur_line = hops[0][2]
    cur_stations = [hops[0][0]]
    cur_distance = cur_minutes = 0.0

    for u, v, lid in hops:
        edge = graph.edge_between(u, v, lid)
        if edge is not None:
            d, m = edge.distance, edge.minutes
        else:  # 兜底：理论上不会发生
            d = graph.vertex(u).straight_distance_to(graph.vertex(v))
            m = 0.0

        total_distance += d
        total_minutes += m

        if lid != cur_line:
            legs.append(_make_leg(graph, cur_line, cur_stations, cur_distance, cur_minutes))
            cur_line, cur_stations = lid, [u]
            cur_distance = cur_minutes = 0.0

        cur_distance += d
        cur_minutes += m
        cur_stations.append(v)

    legs.append(_make_leg(graph, cur_line, cur_stations, cur_distance, cur_minutes))

    return Route(
        found=True,
        path=path,
        legs=legs,
        distance=total_distance,
        minutes=total_minutes,
        transfers=max(0, len(legs) - 1),
        message=f"共 {len(path) - 1} 站，换乘 {max(0, len(legs) - 1)} 次",
    )


class Solver(ABC):
    """所有求解器的公共接口。"""

    key: str = ""
    name: str = ""
    description: str = ""
    cost_label: str = "代价"

    def run(self, graph: Graph, start: str, goal: str, animate: bool = True) -> Iterator[dict]:
        """逐步产出搜索事件，最后一个事件类型为 done。"""
        stats = SearchStats()
        clock = _AlgoClock()
        yield from _timed(self._search(graph, start, goal, animate, stats), clock)

    def solve(self, graph: Graph, start: str, goal: str) -> tuple[Route, SearchStats]:
        """一次跑完，返回结果与统计量。"""
        route = Route(found=False, message="未执行")
        stats = SearchStats()
        for event in self.run(graph, start, goal, animate=False):
            if event["type"] == EVENT_DONE:
                route, stats = event["route"], event["stats"]
        return route, stats

    @abstractmethod
    def _search(self, graph: Graph, start: str, goal: str,
                animate: bool, stats: SearchStats) -> Iterator[dict]:
        raise NotImplementedError

    def _guard(self, graph: Graph, start: str, goal: str) -> Route | None:
        if not graph.has_vertex(start) or not graph.has_vertex(goal):
            return Route(found=False, message="指定的站点不存在于当前网络中")
        return None

    def _unreachable(self, graph: Graph, start: str, goal: str) -> Route:
        return Route(
            found=False,
            message=(
                f"「{graph.name_of(start)}」与「{graph.name_of(goal)}」之间不存在通路，"
                "请检查线路数据或改选其它站点"
            ),
        )

    @staticmethod
    def _trace_chain(prev: dict, end) -> list:
        chain = []
        node = end
        while node is not None and node in prev:
            parent, payload = prev[node]
            chain.append((parent, node, payload))
            node = parent
        chain.reverse()
        return chain


class DijkstraSolver(Solver):
    """最快路径：每次从二叉堆取出当前估计代价最小的站点。

    时间复杂度 O((n + e) log n)，空间 O(n + e)。
    """

    key = "dijkstra"
    name = "Dijkstra"
    description = "最快路径：按距离权重扩展，堆中每次取出代价最小的站点"
    cost_label = "已行距离"

    def _search(self, graph: Graph, start: str, goal: str,
                animate: bool, stats: SearchStats) -> Iterator[dict]:
        invalid = self._guard(graph, start, goal)
        if invalid is not None:
            yield {"type": EVENT_DONE, "route": invalid, "stats": stats}
            return

        if start == goal:
            yield {"type": EVENT_DONE,
                   "route": Route(found=True, path=[start], message="起点与终点相同"),
                   "stats": stats}
            return

        dist: dict[str, float] = {start: 0.0}
        prev: dict[str, tuple[str, str]] = {}
        settled: set[str] = set()
        heap: list[tuple[float, str]] = [(0.0, start)]

        reached = False
        while heap:
            d, u = heappop(heap)
            if u in settled:          # 懒惰删除：记录已过期
                continue
            settled.add(u)
            stats.settled += 1
            stats.settle_order.append(u)
            if animate:
                yield {"type": EVENT_VISIT, "node": u, "cost": d}

            if u == goal:
                reached = True
                break

            for edge in graph.neighbors(u):
                if edge.to in settled:
                    continue
                candidate = d + edge.distance
                if candidate < dist.get(edge.to, INF):      # 松弛
                    dist[edge.to] = candidate
                    prev[edge.to] = (u, edge.line_id)
                    heappush(heap, (candidate, edge.to))
                    stats.relaxed += 1
                    stats.pushed += 1
                    if animate:
                        yield {"type": EVENT_PUSH, "node": edge.to, "cost": candidate}

            if len(heap) > stats.peak_frontier:
                stats.peak_frontier = len(heap)

        if reached:
            route = self._rebuild(graph, start, goal, prev)
        else:
            route = self._unreachable(graph, start, goal)
        yield {"type": EVENT_DONE, "route": route, "stats": stats}

    @staticmethod
    def _rebuild(graph: Graph, start: str, goal: str, prev: dict[str, tuple[str, str]]) -> Route:
        hops: list[tuple[str, str, str]] = []
        cur = goal
        while cur != start:
            parent, lid = prev[cur]
            hops.append((parent, cur, lid))
            cur = parent
        hops.reverse()
        return build_route(graph, start, goal, hops)


class AStarSolver(Solver):
    """A*：f(n) = g(n) + h(n)，h 取到终点的欧几里得直线距离。

    边长 = 直线距离 × 绕行系数（>= 1），因此 h 不会高估真实剩余代价，
    可采纳且一致，仍能保证最优。
    """

    key = "astar"
    name = "A*"
    description = "启发式搜索：f(n)=g(n)+h(n)，h 取到终点的欧几里得直线距离"
    cost_label = "已行距离"

    def __init__(self, metric: str = "euclidean", name: str | None = None,
                 weight: float = 1.0) -> None:
        self.metric = metric
        self.weight = weight
        if name is not None:
            self.name = name

    def _search(self, graph: Graph, start: str, goal: str,
                animate: bool, stats: SearchStats) -> Iterator[dict]:
        invalid = self._guard(graph, start, goal)
        if invalid is not None:
            yield {"type": EVENT_DONE, "route": invalid, "stats": stats}
            return

        if start == goal:
            yield {"type": EVENT_DONE,
                   "route": Route(found=True, path=[start], message="起点与终点相同"),
                   "stats": stats}
            return

        target = graph.vertex(goal)
        manhattan = self.metric == "manhattan"
        weight = self.weight

        def h(vid: str) -> float:
            v = graph.vertex(vid)
            if manhattan:
                base = abs(v.x - target.x) + abs(v.y - target.y)
            else:
                base = v.straight_distance_to(target)
            return base * weight

        g_score: dict[str, float] = {start: 0.0}
        prev: dict[str, tuple[str, str]] = {}
        settled: set[str] = set()
        heap: list[tuple[float, float, str]] = [(h(start), 0.0, start)]

        reached = False
        while heap:
            _, d, u = heappop(heap)
            if u in settled:
                continue
            settled.add(u)
            stats.settled += 1
            stats.settle_order.append(u)
            if animate:
                yield {"type": EVENT_VISIT, "node": u, "cost": d}

            if u == goal:
                reached = True
                break

            for edge in graph.neighbors(u):
                if edge.to in settled:
                    continue
                candidate = d + edge.distance
                if candidate < g_score.get(edge.to, INF):
                    g_score[edge.to] = candidate
                    prev[edge.to] = (u, edge.line_id)
                    heappush(heap, (candidate + h(edge.to), candidate, edge.to))
                    stats.relaxed += 1
                    stats.pushed += 1
                    if animate:
                        yield {"type": EVENT_PUSH, "node": edge.to, "cost": candidate}

            if len(heap) > stats.peak_frontier:
                stats.peak_frontier = len(heap)

        route = (DijkstraSolver._rebuild(graph, start, goal, prev)
                 if reached else self._unreachable(graph, start, goal))
        yield {"type": EVENT_DONE, "route": route, "stats": stats}


class TransferBFSSolver(Solver):
    """最少换乘：在 (站点, 线路) 状态空间上配合 (换乘次数, 路程) 的堆键扩展。

    换乘 +1，沿当前线路前进 +0；第一关键字保证按换乘次数分层，
    第二关键字保证同层解唯一。
    """

    key = "bfs"
    name = "BFS"
    description = "最少换乘：在（站点×线路）状态空间上分层扩展，换乘次数优先、同层取路程最短"
    cost_label = "换乘次数"

    def _search(self, graph: Graph, start: str, goal: str,
                animate: bool, stats: SearchStats) -> Iterator[dict]:
        invalid = self._guard(graph, start, goal)
        if invalid is not None:
            yield {"type": EVENT_DONE, "route": invalid, "stats": stats}
            return

        if start == goal:
            yield {"type": EVENT_DONE,
                   "route": Route(found=True, path=[start], message="起点与终点相同"),
                   "stats": stats}
            return

        HUGE = (1 << 30, INF)
        best: dict[tuple[str, str], tuple[int, float]] = {}
        prev: dict[tuple[str, str], tuple[tuple[str, str], str]] = {}
        done: set[tuple[str, str]] = set()
        heap: list[tuple[int, float, str, str]] = []

        # 起点可以免费登上任意一条经过它的线路。
        for lid in graph.lines_of(start):
            state = (start, lid)
            best[state] = (0, 0.0)
            heappush(heap, (0, 0.0, start, lid))

        goal_state: tuple[str, str] | None = None

        while heap:
            transfers, distance, v, lid = heappop(heap)
            state = (v, lid)
            if state in done:
                continue
            done.add(state)
            stats.settled += 1
            stats.settle_order.append(v)
            if animate:
                yield {"type": EVENT_VISIT, "node": v, "cost": transfers}

            if v == goal:
                goal_state = state
                break

            # (a) 换乘：换乘 +1，路程不变
            for other in graph.lines_of(v):
                if other == lid:
                    continue
                nxt = (v, other)
                candidate = (transfers + 1, distance)
                if candidate < best.get(nxt, HUGE):
                    best[nxt] = candidate
                    prev[nxt] = (state, "transfer")
                    heappush(heap, (candidate[0], candidate[1], v, other))
                    stats.relaxed += 1
                    stats.pushed += 1
                    if animate:
                        yield {"type": EVENT_PUSH, "node": v, "cost": transfers + 1}

            # (b) 沿当前线路前进一站：换乘不变，路程增加
            for edge in graph.neighbors(v):
                if edge.line_id != lid:
                    continue
                nxt = (edge.to, lid)
                candidate = (transfers, distance + edge.distance)
                if candidate < best.get(nxt, HUGE):
                    best[nxt] = candidate
                    prev[nxt] = (state, "ride")
                    heappush(heap, (candidate[0], candidate[1], edge.to, lid))
                    stats.relaxed += 1
                    stats.pushed += 1
                    if animate:
                        yield {"type": EVENT_PUSH, "node": edge.to, "cost": transfers}

            if len(heap) > stats.peak_frontier:
                stats.peak_frontier = len(heap)

        if goal_state is None:
            route = self._unreachable(graph, start, goal)
        else:
            hops: list[tuple[str, str, str]] = []
            for (pu, plid), (su, _slid), kind in self._trace_chain(prev, goal_state):
                if kind == "ride" and pu != su:
                    hops.append((pu, su, plid))
            route = build_route(graph, start, goal, hops)

        yield {"type": EVENT_DONE, "route": route, "stats": stats}


SOLVERS: dict[str, Solver] = {
    solver.key: solver
    for solver in (DijkstraSolver(), AStarSolver(), TransferBFSSolver())
}

ALGORITHM_ORDER = ["dijkstra", "astar", "bfs"]
