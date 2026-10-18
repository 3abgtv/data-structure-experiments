"""广州地铁数据集的不变量测试。

不依赖 pytest，直接运行：

    py tests/test_guangzhou.py

数据由 `tools/import_guangzhou_metro.py` 从 OpenStreetMap 生成。这里不重复
导入逻辑，只校验生成结果必须始终成立的性质：

1. 规模与连通性：站点、线路、区间数量，站名唯一，整图连通；
2. 线路自洽：每条线的站点都存在，相邻两站不同；
3. 边长不变量：每条边的里程不小于两站直线距离（A* 可采纳的前提）；
4. 环线：11 号线首尾是同一座车站，且首尾之间存在闭合边；
5. 算法一致性：Dijkstra 与 A* 在抽样起终点上给出等长的最短路，
   最少换乘 BFS 的结果同样必须是一条合法路径。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph import Graph                              # noqa: E402
from src.loader import load_graph                        # noqa: E402
from src.solver import AStarSolver, DijkstraSolver, TransferBFSSolver  # noqa: E402

DATA = ROOT / "data" / "guangzhou" / "network.json"

_passed = 0


def check(condition: bool, message: str) -> None:
    global _passed
    if not condition:
        raise AssertionError(message)
    _passed += 1


def close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def validate_path(graph: Graph, route, start: str, goal: str) -> None:
    check(route.found, f"{graph.name_of(start)}->{graph.name_of(goal)} 应当有解")
    check(route.path[0] == start and route.path[-1] == goal, "路径端点不匹配")
    check(len(route.path) == len(set(route.path)), "最短路径不应重复经过同一站点")
    for a, b in zip(route.path, route.path[1:]):
        check(graph.edge_between(a, b) is not None,
              f"路径中出现不相邻的两站：{graph.name_of(a)} -> {graph.name_of(b)}")


def main() -> int:
    graph = load_graph(DATA)

    # 1. 规模与连通性
    check(graph.vertex_count == 310, f"站点数应为 310，实际 {graph.vertex_count}")
    check(graph.line_count == 21, f"线路数应为 21，实际 {graph.line_count}")
    names = [v.name for v in graph.vertices.values()]
    check(len(names) == len(set(names)), "站名必须唯一，否则界面按名称选站会错位")
    check(graph.is_connected(), "整张广州地铁网络应当连通")
    check(len(graph.transfer_stations()) >= 60, "换乘站数量异常偏少")

    # 2. 线路自洽
    for line in graph.lines.values():
        check(len(line.stations) >= 2, f"线路「{line.name}」站点不足")
        for vid in line.stations:
            check(graph.has_vertex(vid), f"线路「{line.name}」引用了不存在的站点 {vid}")
        for a, b in zip(line.stations, line.stations[1:]):
            check(a != b, f"线路「{line.name}」中出现了连续重复站点")

    # 3. 边长不变量
    for vid, vertex in graph.vertices.items():
        for edge in graph.neighbors(vid):
            straight = vertex.straight_distance_to(graph.vertex(edge.to))
            check(edge.distance >= straight - 1e-9,
                  f"{graph.name_of(vid)}->{graph.name_of(edge.to)} 的边长小于直线距离")

    # 4. 11 号线环线闭合
    ring = next(line for line in graph.lines.values() if line.name.startswith("11号线"))
    check(ring.stations[0] == ring.stations[-1], "11 号线应当首尾闭合")
    check(len(ring.stations) == 31, "11 号线应为 31 个成员（30 站 + 闭合的赤沙）")
    check(graph.edge_between(ring.stations[-2], ring.stations[-1]) is not None,
          "11 号线缺少首尾之间的闭合边")

    # 4b. 3 号线保留天河客运站—海傍的贯通交路：
    #     这两站之间有直达列车，最少换乘不能因为拆成"主线 + 支线"而多算一次
    through = [
        line for line in graph.lines.values()
        if line.name.startswith("3号线") and len(line.stations) == 20
    ]
    check(len(through) == 1, "应保留一条 20 站的 3 号线贯通交路")

    # 5. 算法一致性（抽样）
    index = {v.name: vid for vid, v in graph.vertices.items()}
    samples = [
        ("广州南站", "机场北"),
        ("西塱", "万胜围"),
        ("体育西路", "大学城南"),
        ("天河客运站", "海傍"),
        ("新城东", "大学城南"),
    ]
    for start_name, goal_name in samples:
        start, goal = index[start_name], index[goal_name]
        dij_route, _ = DijkstraSolver().solve(graph, start, goal)
        astar_route, _ = AStarSolver().solve(graph, start, goal)
        bfs_route, _ = TransferBFSSolver().solve(graph, start, goal)

        validate_path(graph, dij_route, start, goal)
        validate_path(graph, astar_route, start, goal)
        validate_path(graph, bfs_route, start, goal)

        check(close(dij_route.distance, astar_route.distance),
              f"{start_name}->{goal_name}：A* 与 Dijkstra 距离不一致，启发函数不再可采纳")

    direct, _ = TransferBFSSolver().solve(graph, index["天河客运站"], index["海傍"])
    check(direct.transfers == 0, "天河客运站到海傍应当有 0 次换乘的直达交路")

    print(f"全部通过（6 组 {_passed} 断言）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
