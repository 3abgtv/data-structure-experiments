"""算法引擎层（Solver）。

三个求解器共享同一套接口：

    run(graph, start, goal, animate=True) -> 生成器，逐步产出搜索事件
    solve(graph, start, goal)             -> (Route, SearchStats)

之所以把搜索过程写成生成器，是为了同时满足两个看似矛盾的需求：

* 界面上要做搜索动画 —— 需要"每确定一个站点就暂停一下让我重画"；
* 性能对比要测真实耗时 —— 不能为了让动画好看而拖慢算法。

两者在生成器里合为一体：``animate=True`` 时算法在关键位置 yield 出事件，
由界面的定时器逐个消费；``animate=False`` 时那些 yield 被短路掉，算法
一口气跑完，耗时就等于算法本身的开销。三个算法走的是同一条代码路径，
性能对比因此是公平的。

算法一览：

===================  ===============  ==========================================
求解器                优化目标          核心数据结构
===================  ===============  ==========================================
DijkstraSolver        最短距离          二叉堆（heapq）
AStarSolver           最短距离          二叉堆 + 可采纳启发函数 h(n)
TransferBFSSolver     最少换乘          双端队列（0-1 BFS）
===================  ===============  ==========================================
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from heapq import heappop, heappush
from time import perf_counter
from typing import Iterator

from .graph import Graph
from .models import Leg, Route, SearchStats

INF = float("inf")

# 搜索事件的类型
EVENT_VISIT = "visit"   # 一个站点被确定（在堆/队列中弹出）
EVENT_PUSH = "push"     # 一个站点被放入前沿
EVENT_DONE = "done"     # 搜索结束，携带 Route 与 SearchStats


# ----------------------------------------------------------------------
# 计时与事件包装
# ----------------------------------------------------------------------
class _AlgoClock:
    """只累计算法真正在运行的时间。

    搜索写成生成器之后会带来一个副作用：每次 yield 都把控制权交还给界面，
    界面渲染、等待下一帧动画的这段时间也会流逝。如果直接拿"开始时间戳减
    结束时间戳"，动画模式下量出来的就不再是算法耗时，而是用户设置的演示
    速度。这里改为在每次 next() 前后打点，只把两次打点之间的差累加起来，
    挂起等待的时间自然被排除在外。

    因此 animate=True 与 animate=False 量到的耗时可直接比较，性能对比表
    与界面上显示的耗时口径一致。
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
    """包住内部生成器：剔除挂起时间，并在结束事件发出前写好耗时。"""
    while True:
        clock.start()
        try:
            event = next(inner)
        except StopIteration:
            clock.stop()
            return
        clock.stop()
        if event.get("type") == EVENT_DONE:
            # 必须在 yield 之前写回，否则消费方拿到 done 时耗时还没结算
            event["stats"].seconds = clock.elapsed
        yield event


# ----------------------------------------------------------------------
# 结果装配
# ----------------------------------------------------------------------
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
    """把"每一跳"装配成完整的 Route。

    Args:
        hops: [(起点站, 终点站, 所用线路 ID), ...]，按行进顺序排列。
    """
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
        else:  # 理论上不会发生，兜底用直线距离
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


# ----------------------------------------------------------------------
# 抽象基类
# ----------------------------------------------------------------------
class Solver(ABC):
    """所有求解器的公共接口。"""

    key: str = ""
    name: str = ""
    description: str = ""
    cost_label: str = "代价"

    # ---------------- 对外接口 ----------------
    def run(self, graph: Graph, start: str, goal: str, animate: bool = True) -> Iterator[dict]:
        """执行搜索并逐步产出事件，最后一个事件的类型为 ``done``。

        ``animate=True`` 时可在任意两次事件之间暂停（界面据此刷新画面）；
        ``animate=False`` 时事件被快速消费掉，等价于一次性跑完。
        """
        stats = SearchStats()
        clock = _AlgoClock()
        yield from _timed(self._search(graph, start, goal, animate, stats), clock)

    def solve(self, graph: Graph, start: str, goal: str) -> tuple[Route, SearchStats]:
        """一次性跑完，返回最终结果与统计量（用于测试与性能对比）。"""
        route = Route(found=False, message="未执行")
        stats = SearchStats()
        for event in self.run(graph, start, goal, animate=False):
            if event["type"] == EVENT_DONE:
                route, stats = event["route"], event["stats"]
        return route, stats

    @abstractmethod
    def _search(self, graph: Graph, start: str, goal: str,
                animate: bool, stats: SearchStats) -> Iterator[dict]:
        """子类实现的搜索主体，逐步产出事件。"""
        raise NotImplementedError

    # ---------------- 公共辅助 ----------------
    def _guard(self, graph: Graph, start: str, goal: str) -> Route | None:
        """执行前的合法性检查，返回非 None 表示应当直接结束。"""
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
        """沿前驱指针回溯，返回从起点到 end 的状态序列。"""
        chain = []
        node = end
        while node is not None and node in prev:
            parent, payload = prev[node]
            chain.append((parent, node, payload))
            node = parent
        chain.reverse()
        return chain


# ----------------------------------------------------------------------
# 1. Dijkstra
# ----------------------------------------------------------------------
class DijkstraSolver(Solver):
    """最快路径：以距离为权重，每次从二叉堆中取出当前估计代价最小的站点。

    松弛（Relaxation）操作是它的核心 —— 若"经 u 到 v"比"已知的到 v 的
    最好走法"更短，就更新 v 的最短距离估计值并把 v 压入堆：

        if dist[u] + w(u, v) < dist[v]:
            dist[v] = dist[u] + w(u, v)
            prev[v] = u
            push(heap, (dist[v], v))

    配合懒惰删除（弹出时若已确定则跳过），堆中最多保留 O(e) 个元素。
    时间复杂度 O((n + e) log n)，空间复杂度 O(n + e)。
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
            if u in settled:          # 懒惰删除：这条记录已经过期
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


# ----------------------------------------------------------------------
# 2. A*
# ----------------------------------------------------------------------
class AStarSolver(Solver):
    """启发式搜索：在 Dijkstra 的代价函数上再加一项到终点的估计代价。

        f(n) = g(n) + h(n)

    其中 g(n) 是从起点到 n 的实际距离，h(n) 取 n 到终点的**欧几里得直线
    距离**。因为任何线路的实际走行距离都不小于直线距离，所以
    h(n) ≤ 真实的剩余距离，即 h 是可采纳的；又因为相邻两站的
    h 值之差不超过它们的直线距离（不超过边长），h 同时是一致的。
    可采纳且一致的启发函数保证 A* 第一次从堆中弹出终点时得到的
    就是最优解，且每个站点最多被确定一次。

    与 Dijkstra 的差别只在堆的排序键：Dijkstra 用 g，A* 用 f。
    启发式越贴近真实剩余距离，被"带偏"去探索的分支就越少，
    确定（settle）的站点数也就越少 —— 这正是实验要对比的指标。
    """

    key = "astar"
    name = "A*"
    description = "启发式搜索：f(n)=g(n)+h(n)，h 取到终点的欧几里得直线距离"
    cost_label = "已行距离"

    def __init__(self, metric: str = "euclidean", name: str | None = None,
                 weight: float = 1.0) -> None:
        """
        Args:
            metric: 启发函数所用的距离度量。``"euclidean"`` 是任务书指定
                的做法；``"manhattan"`` 仅用于实验对比 —— 它只在四邻接的
                规则网格上可采纳，用在一般的城市路网上会高估真实代价。
            name: 覆盖显示名称，便于在对比表里区分不同版本。
            weight: 启发函数的放大系数，用于实验对比。``weight <= 1`` 时
                h 仍然可采纳，算法保证最优；``weight > 1`` 会高估真实代价，
                搜索更快但可能不再是最短路径。
        """
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
            """启发函数：站点到终点的估计剩余距离。"""
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


# ----------------------------------------------------------------------
# 3. 最少换乘 BFS
# ----------------------------------------------------------------------
class TransferBFSSolver(Solver):
    """最少换乘：在「站点 × 线路」状态空间上按换乘次数分层扩展。

    BFS 的直接目标是"经过的站数最少"，但站数与换乘次数并不成正比 ——
    绕远但同线路直达，换乘次数反而更少。因此这里把搜索的状态定义为
    ``(站点, 当前所乘线路)``，并用两个量去衡量一条路径：

    * **换乘次数**（第一关键字）：同一线路内前进一站 +0，改乘另一条线路 +1；
    * **乘车路程**（第二关键字）：换乘不增加，前进一站增加该段长度。

    优先队列按 ``(换乘次数, 路程)`` 的字典序弹出状态，于是所有换乘次数为
    0 的状态必定先于换乘次数为 1 的状态被处理，换乘次数为 1 的又先于 2 的
    —— 这就是"按层级扩展"的 BFS 语义；而同一层内部再按路程择优。

    为什么需要第二个关键字：如果只按换乘次数扩展，换乘次数相同的路径并不
    唯一，取到哪一条取决于遍历顺序，结果会随数据顺序漂移。把路程作为次
    关键字后，"最少换乘"的解被唯一确定，且在换乘次数相同的前提下路程最短。

    与 Dijkstra / A* 的本质区别在于**代价的定义不同**：前者度量距离，本算法
    度量换乘。两者在"直达但绕远"与"换乘但抄近"并存时会给出不同答案，
    这正是实验第四章要对比的现象。
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

            # (a) 换乘到经过本站的另一条线路：换乘 +1，路程不变
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


# ----------------------------------------------------------------------
# 注册表
# ----------------------------------------------------------------------
SOLVERS: dict[str, Solver] = {
    solver.key: solver
    for solver in (DijkstraSolver(), AStarSolver(), TransferBFSSolver())
}

ALGORITHM_ORDER = ["dijkstra", "astar", "bfs"]
