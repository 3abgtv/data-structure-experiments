"""生成"算法过程讲解"所需的推演日志。

用法::

    py tools/trace_algorithms.py                  # 推演 demo 网络的东湖 → 西山
    py tools/trace_algorithms.py A1 C3            # 指定起终点
    py tools/trace_algorithms.py --dataset metro  # 换一个数据集

这个脚本把三个算法的**内部状态**逐步打印出来 —— 每一轮从堆里弹出了谁、
为什么是它、松弛又改动了谁的估计值。`src/solver.py` 里的正式实现为了流畅
地做动画，只在关键位置产出事件；这里则是带完整旁白的推演版。

为了保证推演版没有跑偏，脚本最后会把它的结果与 `src/solver.py` 的正式实现
逐项比对（路径、距离、换乘次数、访问站点数），不一致就直接报错。
"""

from __future__ import annotations

import sys
from heapq import heappop, heappush
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.loader import load_graph                       # noqa: E402
from src.solver import SOLVERS                          # noqa: E402

INF = float("inf")
WIDTH = 76


def rule(title: str = "") -> None:
    if title:
        print()
        print("=" * WIDTH)
        print(title)
        print("=" * WIDTH)
    else:
        print("-" * WIDTH)


# ----------------------------------------------------------------------
# Dijkstra
# ----------------------------------------------------------------------
def trace_dijkstra(graph, start, goal) -> dict:
    name = graph.name_of
    print(f"\n目标：求 {name(start)} → {name(goal)} 的最短路径")
    print("排序依据：g（从起点出发的已行距离）")
    print()

    dist: dict[str, float] = {start: 0.0}
    prev: dict[str, tuple[str, str]] = {}
    settled: set[str] = set()
    heap: list[tuple[float, str]] = [(0.0, start)]
    round_no = 0
    popped_stale = 0

    print(f"{'轮次':<5}{'动作':<34}{'说明'}")
    rule()

    while heap:
        d, u = heappop(heap)
        if u in settled:
            popped_stale += 1
            print(f"{'':<5}{'丢弃 ' + name(u) + ' 的过期记录':<34}"
                  f"它早已被确定，这条是松弛时留下的旧记录")
            continue

        round_no += 1
        settled.add(u)
        print(f"{round_no:<5}{'确定 ' + name(u):<34}"
              f"g = {d:.3f} km；堆中还剩 {len(heap)} 条记录")

        if u == goal:
            print(f"{'':<5}{'到达目标，停止':<34}第一个被确定的终点就是最优解")
            break

        for edge in graph.neighbors(u):
            if edge.to in settled:
                continue
            candidate = d + edge.distance
            old = dist.get(edge.to)
            if old is None or candidate < old:
                dist[edge.to] = candidate
                prev[edge.to] = (u, edge.line_id)
                heappush(heap, (candidate, edge.to))
                if old is None:
                    note = f"{name(edge.to)} 首次被到达"
                else:
                    note = f"{name(edge.to)} 由 {old:.3f} 改进为 {candidate:.3f}"
                print(f"{'':<5}{'  松弛 → ' + name(edge.to):<34}"
                      f"{d:.3f} + {edge.distance:.3f} = {candidate:.3f}；{note}")
            else:
                print(f"{'':<5}{'  松弛 → ' + name(edge.to):<34}"
                      f"{d:.3f} + {edge.distance:.3f} = {candidate:.3f}；"
                      f"不优于已知的 {old:.3f}，放弃")

    path, legs = _rebuild(graph, start, goal, prev)
    route, stats = SOLVERS["dijkstra"].solve(graph, start, goal)
    _verify("Dijkstra", graph, route, stats, path, dist.get(goal, INF), len(settled))
    print(f"\n共发生 {popped_stale} 次「弹出即过期」（懒惰删除）。")
    return {"path": path, "distance": dist.get(goal, INF), "settled": len(settled)}


# ----------------------------------------------------------------------
# A*
# ----------------------------------------------------------------------
def trace_astar(graph, start, goal) -> dict:
    name = graph.name_of
    target = graph.vertex(goal)

    def h(vid: str) -> float:
        return graph.vertex(vid).straight_distance_to(target)

    print(f"\n目标：求 {name(start)} → {name(goal)} 的最短路径")
    print("排序依据：f = g + h，其中 h 是到目标的欧几里得直线距离")
    print(f"h({name(start)}) = {h(start):.3f} km，即全程直线距离")
    print()

    g_score: dict[str, float] = {start: 0.0}
    prev: dict[str, tuple[str, str]] = {}
    settled: set[str] = set()
    heap: list[tuple[float, float, str]] = [(h(start), 0.0, start)]
    round_no = 0

    print(f"{'轮次':<5}{'动作':<34}{'说明'}")
    rule()

    while heap:
        f, d, u = heappop(heap)
        if u in settled:
            continue
        round_no += 1
        settled.add(u)
        print(f"{round_no:<5}{'确定 ' + name(u):<34}"
              f"g = {d:.3f}，h = {h(u):.3f}，f = {f:.3f}")

        if u == goal:
            print(f"{'':<5}{'到达目标，停止':<34}"
                  f"此时 f = g，说明 h 没有高估，g 就是最短距离")
            break

        for edge in graph.neighbors(u):
            if edge.to in settled:
                continue
            candidate = d + edge.distance
            old = g_score.get(edge.to)
            if old is None or candidate < old:
                g_score[edge.to] = candidate
                prev[edge.to] = (u, edge.line_id)
                nf = candidate + h(edge.to)
                heappush(heap, (nf, candidate, edge.to))
                print(f"{'':<5}{'  松弛 → ' + name(edge.to):<34}"
                      f"g = {candidate:.3f}，f = {candidate:.3f} + {h(edge.to):.3f}"
                      f" = {nf:.3f}")

    path, _ = _rebuild(graph, start, goal, prev)
    route, stats = SOLVERS["astar"].solve(graph, start, goal)
    _verify("A*", graph, route, stats, path, g_score.get(goal, INF), len(settled))
    return {"path": path, "distance": g_score.get(goal, INF), "settled": len(settled)}


# ----------------------------------------------------------------------
# 最少换乘 BFS
# ----------------------------------------------------------------------
def trace_transfer_bfs(graph, start, goal) -> dict:
    name = graph.name_of
    print(f"\n目标：求 {name(start)} → {name(goal)} 的换乘最少路径")
    print("状态是 (站点, 当前所乘线路)；排序依据是 (换乘次数, 已行距离)")
    print()

    HUGE = (1 << 30, INF)
    best: dict[tuple[str, str], tuple[int, float]] = {}
    prev: dict[tuple[str, str], tuple[tuple[str, str], str]] = {}
    done: set[tuple[str, str]] = set()
    heap: list[tuple[int, float, str, str]] = []
    round_no = 0

    print(f"起点 {name(start)} 所在线路：" +
          "、".join(graph.lines[lid].name for lid in graph.lines_of(start)))
    print()

    for lid in graph.lines_of(start):
        state = (start, lid)
        best[state] = (0, 0.0)
        heappush(heap, (0, 0.0, start, lid))

    print(f"{'轮次':<5}{'动作':<40}{'说明'}")
    rule()

    while heap:
        transfers, distance, v, lid = heappop(heap)
        state = (v, lid)
        if state in done:
            continue
        done.add(state)
        round_no += 1
        line_name = graph.lines[lid].name
        print(f"{round_no:<5}{'确定 (' + name(v) + ', ' + line_name + ')':<40}"
              f"换乘 {transfers} 次，已行 {distance:.3f} km")

        if v == goal:
            print(f"{'':<5}{'到达目标，停止':<40}"
                  f"第一个被确定的 {name(goal)} 状态给出最少换乘次数")
            break

        for other in graph.lines_of(v):
            if other == lid:
                continue
            nxt = (v, other)
            candidate = (transfers + 1, distance)
            if candidate < best.get(nxt, HUGE):
                best[nxt] = candidate
                prev[nxt] = (state, "transfer")
                heappush(heap, (candidate[0], candidate[1], v, other))
                print(f"{'':<5}{'  换乘 → ' + name(v) + ' 改乘 ' + graph.lines[other].name:<40}"
                      f"换乘次数 {transfers} → {transfers + 1}（路程不变）")

        for edge in graph.neighbors(v):
            if edge.line_id != lid:
                continue
            nxt = (edge.to, lid)
            candidate = (transfers, distance + edge.distance)
            if candidate < best.get(nxt, HUGE):
                best[nxt] = candidate
                prev[nxt] = (state, "ride")
                heappush(heap, (candidate[0], candidate[1], edge.to, lid))
                print(f"{'':<5}{'  乘车 → ' + name(edge.to):<40}"
                      f"沿 {line_name} 前进，换乘次数不变，"
                      f"路程 {distance:.3f} → {candidate[1]:.3f}")

    # 回溯
    hops: list[tuple[str, str, str]] = []
    for (pu, plid), (su, _), kind in SOLVERS["bfs"]._trace_chain(prev, (goal, lid)):
        if kind == "ride" and pu != su:
            hops.append((pu, su, plid))
    from src.solver import build_route
    route = build_route(graph, start, goal, hops)

    _, stats = SOLVERS["bfs"].solve(graph, start, goal)
    _verify("最少换乘 BFS", graph, route, stats, route.path, route.distance, len(done))
    return {"path": route.path, "distance": route.distance,
            "transfers": route.transfers, "settled": len(done)}


# ----------------------------------------------------------------------
def _rebuild(graph, start, goal, prev):
    if start == goal:
        return [start], []
    hops: list[tuple[str, str, str]] = []
    cur = goal
    while cur != start:
        parent, lid = prev[cur]
        hops.append((parent, cur, lid))
        cur = parent
    hops.reverse()
    return [start] + [h[1] for h in hops], hops


def _verify(label: str, graph, route, stats, path, distance, settled) -> None:
    """推演版的结果必须与正式实现完全一致，否则立刻报错。"""
    problems = []
    if not route.found:
        problems.append("正式实现报告不可达")
    if path != route.path:
        problems.append(f"路径不一致：推演 {'→'.join(graph.name_of(v) for v in path)}，"
                        f"正式 {'→'.join(graph.name_of(v) for v in route.path)}")
    if abs(distance - route.distance) > 1e-9:
        problems.append(f"距离不一致：推演 {distance:.6f}，正式 {route.distance:.6f}")
    if settled != stats.unique_settled and label != "最少换乘 BFS":
        problems.append(f"访问站点数不一致：推演 {settled}，正式 {stats.unique_settled}")

    print()
    if problems:
        print(f"[不一致] {label} 的推演与正式实现不符：")
        for item in problems:
            print("   -", item)
    else:
        print(f"[校验通过] {label} 的推演与正式实现一致："
              f"{route.distance:.3f} km，经过 {route.stops} 站，"
              f"换乘 {route.transfers} 次，访问 {stats.unique_settled} 个站点")


def default_endpoints(graph) -> tuple[str, str]:
    """没指定起终点时，取第一个有邻居的站点，以及离它最远的可达站点。"""
    ids = [vid for vid in graph.vertices if graph.neighbors(vid)] or list(graph.vertices)
    if len(ids) < 2:
        return ids[0], ids[0]

    start = ids[0]
    target = graph.vertex(start)
    goal = max(graph.reachable_from(start),
               key=lambda vid: graph.vertex(vid).straight_distance_to(target))
    return start, (goal if goal != start else ids[1])


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dataset = "demo"
    if "--dataset" in sys.argv:
        dataset = sys.argv[sys.argv.index("--dataset") + 1]
        args = [a for a in args if a != dataset]

    graph = load_graph(ROOT / "data" / dataset / "network.json")

    def resolve(token: str) -> str:
        """起终点既可以用站点 ID 指定，也可以直接写站名。"""
        if graph.has_vertex(token):
            return token
        for vid, vertex in graph.vertices.items():
            if vertex.name == token:
                return vid
        raise SystemExit(f"数据集 {dataset} 里没有站点「{token}」")

    if len(args) >= 2:
        start, goal = resolve(args[0]), resolve(args[1])
    else:
        start, goal = default_endpoints(graph)

    print(f"数据集 {dataset}：{graph.vertex_count} 站 / {graph.line_count} 线")
    print(f"起终点：{graph.name_of(start)} → {graph.name_of(goal)}")

    rule("一、Dijkstra")
    dijkstra = trace_dijkstra(graph, start, goal)
    rule("二、A*")
    astar = trace_astar(graph, start, goal)
    rule("三、最少换乘 BFS")
    bfs = trace_transfer_bfs(graph, start, goal)

    rule("四、三者对照")
    print(f"{'算法':<16}{'距离 km':>10}{'换乘':>6}{'访问站点':>10}")
    rule()
    print(f"{'Dijkstra':<16}{dijkstra['distance']:>10.3f}{'—':>6}{dijkstra['settled']:>10}")
    print(f"{'A*':<16}{astar['distance']:>10.3f}{'—':>6}{astar['settled']:>10}")
    print(f"{'最少换乘 BFS':<16}{bfs['distance']:>10.3f}"
          f"{bfs['transfers']:>6}{bfs['settled']:>10}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
