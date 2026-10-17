"""算法与数据结构的正确性测试。

不依赖 pytest 等第三方库，直接运行即可：

    py tests/test_algorithms.py

覆盖的内容：

1. 文件加载与图的基本统计；
2. 三条路径的**逐项手工核对**（对应报告第四章的正确性验证）；
3. 路径合法性：每一步都必须是线路上真实相邻的两站；
4. Dijkstra 与 A* 必须给出同样长度的最短路（A* 的启发函数可采纳的直接体现）；
5. 用**朴素的枚举法**在小图上独立求最短路，与 Dijkstra 的结果交叉验证；
6. 边界与异常：起点等于终点、两站不连通、不存在的站点、空图；
7. 图结构本身：增删站点、增删线路后邻接表是否仍然自洽；
8. 加载器对格式错误的处理。
"""

from __future__ import annotations

import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph import Graph                      # noqa: E402
from src.loader import DataError, load_graph     # noqa: E402
from src.models import Line, Vertex              # noqa: E402
from src.solver import ALGORITHM_ORDER, SOLVERS  # noqa: E402

DEMO = ROOT / "data" / "demo" / "network.json"
METRO = ROOT / "data" / "metro" / "network.json"

_passed = 0


def check(condition: bool, message: str) -> None:
    global _passed
    if not condition:
        raise AssertionError(message)
    _passed += 1


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


# ----------------------------------------------------------------------
# 通用校验
# ----------------------------------------------------------------------
def validate_route(graph: Graph, route, start: str, goal: str) -> None:
    """任何一条返回的路径都必须是"真的能走通"的。"""
    check(route.found, f"{start}->{goal} 应当有解")
    check(route.path[0] == start, "路径必须从起点出发")
    check(route.path[-1] == goal, "路径必须到达终点")
    check(len(route.path) == len(set(route.path)), "最短路径不应重复经过同一站点")

    for a, b in zip(route.path, route.path[1:]):
        check(graph.edge_between(a, b) is not None,
              f"路径中出现不相邻的两站：{graph.name_of(a)} -> {graph.name_of(b)}")

    # legs 必须无缝拼接成 path，且总距离等于各段之和
    joined: list[str] = []
    for leg in route.legs:
        joined.extend(leg.stations if not joined else leg.stations[1:])
    if len(route.path) == 1:
        check(not route.legs, "只有一个站点时不应存在乘车分段")
    else:
        check(joined == route.path, "换乘分段拼接后应与完整路径一致")
    check(close(sum(leg.distance for leg in route.legs), route.distance, 1e-9),
          "各段距离之和应等于总距离")
    check(route.transfers == max(0, len(route.legs) - 1),
          "换乘次数应等于分段数减一")


def brute_force_shortest(graph: Graph, start: str, goal: str) -> float:
    """朴素枚举所有简单路径求最短距离 —— 只在小图上用，作为独立参照。"""
    best = float("inf")

    def walk(node: str, visited: set[str], cost: float) -> None:
        nonlocal best
        if cost >= best:
            return
        if node == goal:
            best = cost
            return
        for edge in graph.neighbors(node):
            if edge.to not in visited:
                visited.add(edge.to)
                walk(edge.to, visited, cost + edge.distance)
                visited.remove(edge.to)

    walk(start, {start}, 0.0)
    return best


# ----------------------------------------------------------------------
# 1. 加载与基本统计
# ----------------------------------------------------------------------
def test_loading() -> None:
    demo = load_graph(DEMO)
    check(demo.vertex_count == 14, f"demo 应有 14 个站点，实际 {demo.vertex_count}")
    check(demo.line_count == 4, "demo 应有 4 条线路")
    check(demo.edge_count == 13, f"demo 应有 13 段区间，实际 {demo.edge_count}")
    check(not demo.is_connected(), "demo 中的孤岛站应当使整图不连通")
    check(set(demo.transfer_stations()) == {"A3", "A5", "B4", "C3"},
          "demo 的换乘站应为中转站 / 新港 / 北苑 / 西山")

    metro = load_graph(METRO)
    check(metro.vertex_count == 65, "metro 应有 65 个站点")
    check(metro.line_count == 9, "metro 应有 9 条线路")
    check(metro.is_connected(), "metro 应当是连通的")
    check(len(metro.transfer_stations()) == 13, "metro 应有 13 个换乘站")

    # 绕行系数 ≥ 1 保证了边长不小于直线距离，这是 A* 启发函数可采纳的前提
    for lid, line in metro.lines.items():
        check(line.detour >= 1.0, f"线路 {line.name} 的绕行系数小于 1")
        for a, b in zip(line.stations, line.stations[1:]):
            edge = metro.edge_between(a, b, lid)
            straight = metro.vertex(a).straight_distance_to(metro.vertex(b))
            check(edge.distance >= straight - 1e-9,
                  f"{line.name} 上 {metro.name_of(a)}->{metro.name_of(b)} 的边长小于直线距离")


# ----------------------------------------------------------------------
# 2. 手工核对：三条路径的逐项验证
# ----------------------------------------------------------------------
def test_hand_verified_routes() -> None:
    """对应报告第四章的正确性验证。

    demo 网络的 1 号线把"山前"抬高到 y=2.5 故意绕了一段远路，于是
    「东湖 → 西山」同时存在两条有意思的走法：

        乙路（换乘 2 次）：东湖→文化路→中转站→[2 号线]→北苑
                          →[4 号线]→亭子桥→西山      14.300 km
        甲路（换乘 1 次）：东湖→文化路→中转站→山前→新港
                          →[3 号线]→西山               16.291 km

    最短的是乙路，换乘最少的却是甲路 —— 两个准则在这里给出不同答案。
    """
    graph = load_graph(DEMO)

    dijkstra, _ = SOLVERS["dijkstra"].solve(graph, "A1", "C3")
    validate_route(graph, dijkstra, "A1", "C3")
    check(close(dijkstra.distance, 14.300, 1e-3),
          f"Dijkstra 应为 14.300 km，实际 {dijkstra.distance:.3f}")
    check(dijkstra.transfers == 2, f"Dijkstra 应换乘 2 次，实际 {dijkstra.transfers}")
    check(dijkstra.path == ["A1", "A2", "A3", "B1", "B2", "B3", "B4", "D1", "C3"],
          "Dijkstra 的路径与手工推演不符")

    bfs, _ = SOLVERS["bfs"].solve(graph, "A1", "C3")
    validate_route(graph, bfs, "A1", "C3")
    check(bfs.transfers == 1, f"最少换乘应只换乘 1 次，实际 {bfs.transfers}")
    check(close(bfs.distance, 16.291, 1e-3),
          f"最少换乘路径应为 16.291 km，实际 {bfs.distance:.3f}")
    check(bfs.path == ["A1", "A2", "A3", "A4", "A5", "C1", "C2", "C3"],
          "最少换乘的路径与手工推演不符")

    # 换乘最少反而路程更长，这正是两种准则的分歧所在
    check(bfs.distance > dijkstra.distance,
          "本例中最少换乘的路径应当比最短路径更长")

    # 「东湖 → 新港」两个准则一致，都走 1 号线直达
    for key in ALGORITHM_ORDER:
        route, _ = SOLVERS[key].solve(graph, "A1", "A5")
        validate_route(graph, route, "A1", "A5")
        check(route.transfers == 0, f"{key} 在东湖->新港上不应换乘")
        check(close(route.distance, 11.891, 1e-3),
              f"{key} 在东湖->新港上的距离应为 11.891 km，实际 {route.distance:.3f}")


# ----------------------------------------------------------------------
# 3. 三种算法在可达性上必须一致
# ----------------------------------------------------------------------
def test_algorithm_agreement() -> None:
    graph = load_graph(METRO)
    ids = list(graph.vertices)
    pairs = [(ids[i * 7 % len(ids)], ids[(i * 13 + 5) % len(ids)]) for i in range(40)]

    for start, goal in pairs:
        results = {}
        for key in ALGORITHM_ORDER:
            route, stats = SOLVERS[key].solve(graph, start, goal)
            check(route.found, f"{key} 在 {start}->{goal} 上报告不可达，但图是连通的")
            validate_route(graph, route, start, goal)
            results[key] = route

        # Dijkstra 与 A* 的目标函数相同，必须给出同样长度的最短路
        check(close(results["dijkstra"].distance, results["astar"].distance, 1e-9),
              f"Dijkstra 与 A* 在 {start}->{goal} 上给出了不同的最短距离："
              f"{results['dijkstra'].distance:.6f} vs {results['astar'].distance:.6f}")

        # 最少换乘的换乘次数不可能比最短路的更多（它至少不劣于任何一条具体路径）
        check(results["bfs"].transfers <= results["dijkstra"].transfers,
              f"最少换乘给出的换乘次数（{results['bfs'].transfers}）"
              f"多于 Dijkstra 路径上的换乘次数（{results['dijkstra'].transfers}）")


def test_against_brute_force() -> None:
    """用朴素枚举独立验证 Dijkstra 的最优性。"""
    graph = load_graph(DEMO)
    ids = [v for v in graph.vertices if graph.neighbors(v)]     # 排除孤岛站

    for start, goal in itertools.permutations(ids, 2):
        expected = brute_force_shortest(graph, start, goal)
        route, _ = SOLVERS["dijkstra"].solve(graph, start, goal)
        check(route.found, f"{start}->{goal} 应当可达")
        check(close(route.distance, expected, 1e-9),
              f"{graph.name_of(start)}->{graph.name_of(goal)}：Dijkstra 得到 "
              f"{route.distance:.6f}，枚举法得到 {expected:.6f}")


# ----------------------------------------------------------------------
# 4. A* 启发函数的可采纳性
# ----------------------------------------------------------------------
def test_heuristic_admissibility() -> None:
    """h(n) 必须永远不高估 n 到终点的真实剩余代价。

    只要 h 可采纳，A* 就一定能找到最优解。这里对每个终点，把
    h(n) 与真实的剩余最短距离逐点比较。
    """
    graph = load_graph(METRO)
    ids = list(graph.vertices)

    for goal in ids[::5]:                        # 抽 13 个终点做全量检查
        goal_vertex = graph.vertex(goal)
        for vid in ids:
            h = graph.vertex(vid).straight_distance_to(goal_vertex)
            route, _ = SOLVERS["dijkstra"].solve(graph, vid, goal)
            check(h <= route.distance + 1e-9,
                  f"h({graph.name_of(vid)})={h:.4f} 超过了真实剩余距离 "
                  f"{route.distance:.4f}，启发函数不可采纳")


# ----------------------------------------------------------------------
# 5. 边界与异常
# ----------------------------------------------------------------------
def test_edge_cases() -> None:
    graph = load_graph(DEMO)

    for key in ALGORITHM_ORDER:
        solver = SOLVERS[key]

        # 起点等于终点
        route, stats = solver.solve(graph, "A1", "A1")
        check(route.found, f"{key}：起点与终点相同时应返回有解")
        check(route.path == ["A1"], f"{key}：起点与终点相同时路径应只含起点")
        check(route.distance == 0.0, f"{key}：起点与终点相同时距离应为 0")
        check(route.transfers == 0, f"{key}：起点与终点相同时不应换乘")

        # 不连通：孤岛站无法到达
        route, _ = solver.solve(graph, "A1", "E1")
        check(not route.found, f"{key}：孤立站不应可达")
        check("不存在通路" in route.message, f"{key}：应给出不连通的提示")

        route, _ = solver.solve(graph, "E1", "A1")
        check(not route.found, f"{key}：从孤立站出发也应报告不可达")

        # 不存在的站点
        route, _ = solver.solve(graph, "A1", "不存在的站")
        check(not route.found, f"{key}：不存在的站点应被拒绝")
        check("不存在" in route.message, f"{key}：应提示站点不存在")


# ----------------------------------------------------------------------
# 6. 图结构的增删
# ----------------------------------------------------------------------
def test_dynamic_editing() -> None:
    graph = Graph()
    for i in range(5):
        graph.add_vertex(Vertex(f"V{i}", f"站{i}", float(i), 0.0))
    graph.add_line(Line("L", "测试线", "#ffffff", [f"V{i}" for i in range(5)],
                        speed_kmh=60.0, detour=1.0))

    check(graph.vertex_count == 5 and graph.edge_count == 4, "建图后的规模不对")
    check(graph.is_connected(), "建图后应当连通")
    check(graph.transfer_stations() == [], "单条线路上不应有换乘站")

    length, _ = SOLVERS["dijkstra"].solve(graph, "V0", "V4")
    check(close(length.distance, 4.0), f"V0->V4 应为 4 km，实际 {length.distance}")

    # 删除中间站：线路在这一点断开，且断点前后不会自动接上
    graph.remove_vertex("V2")
    check(graph.vertex_count == 4, "删除站点后数量不对")
    check(not graph.has_vertex("V2"), "被删的站点仍存在")
    check(graph.edge_between("V1", "V3") is None, "断点两侧不应直接相连")
    route, _ = SOLVERS["dijkstra"].solve(graph, "V0", "V4")
    check(not route.found, "断开后不应再连通")

    # 原线路被切成两段：[V0,V1] 沿用原 ID，[V3,V4] 另起一个
    check(sorted(graph.lines) == ["L", "L#2"], f"线路应被切成两段，实际 {list(graph.lines)}")
    route, _ = SOLVERS["dijkstra"].solve(graph, "V0", "V1")
    check(route.found and close(route.distance, 1.0), "断开后的左半段仍应能通行")

    # 删除全部线路：所有边都应消失
    for lid in list(graph.lines):
        graph.remove_line(lid)
    check(graph.edge_count == 0, "删除线路后不应残留任何边")
    check(not graph.is_connected(), "无边时不应连通")

    # 并行边：两条线路共用同一对站点，换乘站判定要能看出来
    g2 = Graph()
    for vid, x in (("P", 0.0), ("Q", 1.0), ("R", 2.0)):
        g2.add_vertex(Vertex(vid, vid, x, 0.0))
    g2.add_line(Line("A", "甲线", "#ff0000", ["P", "Q"], speed_kmh=40, detour=1.0))
    g2.add_line(Line("B", "乙线", "#00ff00", ["Q", "R"], speed_kmh=40, detour=1.0))
    check(g2.transfer_stations() == ["Q"], "共用站应被识别为换乘站")
    check(g2.lines_of("Q") == ["A", "B"], "共用站应同时属于两条线路")


# ----------------------------------------------------------------------
# 7. 加载器的异常处理
# ----------------------------------------------------------------------
def test_loader_errors() -> None:
    import json
    import tempfile

    def write(payload: dict) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                             encoding="utf-8")
        json.dump(payload, handle, ensure_ascii=False)
        handle.close()
        return Path(handle.name)

    good_station = {"id": "X", "name": "测试", "x": 0, "y": 0}

    # 站点 ID 重复
    bad = write({"stations": [good_station, good_station], "lines": []})
    try:
        load_graph(bad)
        check(False, "重复的站点 ID 应当报错")
    except DataError as exc:
        check("重复" in str(exc), f"错误信息里应说明重复，实际：{exc}")

    # 线路引用了不存在的站点
    bad = write({"stations": [good_station],
                 "lines": [{"id": "L", "name": "线", "stations": ["X", "幽灵站"]}]})
    try:
        load_graph(bad)
        check(False, "引用不存在的站点应当报错")
    except KeyError as exc:
        check("幽灵站" in str(exc), f"错误信息应指出是哪个站，实际：{exc}")

    # 结构不完整
    bad = write({"stations": []})
    try:
        load_graph(bad)
        check(False, "缺少 lines 字段应当报错")
    except DataError as exc:
        check("lines" in str(exc), f"错误信息应提到 lines，实际：{exc}")

    # 不是 JSON
    broken = Path(tempfile.mkstemp(suffix=".json")[1])
    broken.write_text("这不是 JSON {{{", encoding="utf-8")
    try:
        load_graph(broken)
        check(False, "非法的 JSON 应当报错")
    except DataError as exc:
        check("JSON" in str(exc), f"错误信息应提到 JSON，实际：{exc}")


def test_data_invariant_guard() -> None:
    """三条数据不变量必须在加载时就被挡住。

    它们一旦被破坏，算法不会报错，而是**静默**给出错误答案：
    绕行系数 < 1 会让 A* 的启发函数高估代价、返回次优解（系数为负还会
    让边权变负，破坏 Dijkstra 的非负权前提）；速度为 0 会除零；坐标含
    NaN 会让松弛比较恒为假、把连通的站点误判成不可达。
    """
    import json
    import tempfile

    def write(payload: dict) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                             encoding="utf-8")
        json.dump(payload, handle, ensure_ascii=False)
        handle.close()
        return Path(handle.name)

    station = {"id": "A", "name": "甲", "x": 0.0, "y": 0.0}
    station2 = {"id": "B", "name": "乙", "x": 1.0, "y": 0.0}

    def expect_error(payload: dict, keyword: str, why: str) -> None:
        path = write(payload)
        try:
            load_graph(path)
            check(False, f"{why} 应当被拒绝")
        except DataError as exc:
            check(keyword in str(exc), f"{why} 的提示应含「{keyword}」，实际：{exc}")

    line = {"id": "L", "name": "测试线", "stations": ["A", "B"]}

    expect_error({"stations": [station, station2],
                  "lines": [{**line, "detour": 0.5}]},
                 "绕行系数", "绕行系数小于 1")
    expect_error({"stations": [station, station2],
                  "lines": [{**line, "detour": -1.0}]},
                 "绕行系数", "绕行系数为负")
    expect_error({"stations": [station, station2],
                  "lines": [{**line, "speed": 0}]},
                 "旅行速度", "旅行速度为 0")
    expect_error({"stations": [{**station, "x": float("nan")}, station2],
                  "lines": [line]},
                 "有限数", "坐标为 NaN")
    expect_error({"stations": [{**station, "y": float("inf")}, station2],
                  "lines": [line]},
                 "有限数", "坐标为无穷大")
    expect_error({"stations": [{**station, "x": "oops"}, station2],
                  "lines": [line]},
                 "必须是数字", "坐标不是数字")
    expect_error({"stations": [station, station2],
                  "lines": [{**line, "stations": ["A"]}]},
                 "至少需要两个站点", "线路只有一站")

    # 直接调用 Graph 时同样要拦住，并且跳过零长自环
    graph = Graph()
    graph.add_vertex(Vertex("A", "甲", 0.0, 0.0))
    try:
        graph.add_line(Line("ONE", "单站线", "#fff", ["A"]))
        check(False, "单站线路应被 Graph 拒绝")
    except ValueError as exc:
        check("至少需要两个站点" in str(exc), f"Graph 的提示不对：{exc}")

    graph.add_vertex(Vertex("B", "乙", 1.0, 0.0))
    graph.add_line(Line("LOOP", "自环线", "#fff", ["A", "A", "B"], detour=1.0))
    check(len(graph.neighbors("A")) == 1,
          f"零长自环不应产生边，实际有 {len(graph.neighbors('A'))} 条")
    route, _ = SOLVERS["dijkstra"].solve(graph, "A", "B")
    check(route.found and close(route.distance, 1.0), "跳过自环后仍应能求出最短路")


# ----------------------------------------------------------------------
def main() -> int:
    tests = [
        ("文件加载与图统计", test_loading),
        ("手工核对的路径", test_hand_verified_routes),
        ("三算法一致性", test_algorithm_agreement),
        ("与枚举法交叉验证", test_against_brute_force),
        ("A* 启发函数可采纳性", test_heuristic_admissibility),
        ("边界与异常", test_edge_cases),
        ("图的动态增删", test_dynamic_editing),
        ("加载器错误处理", test_loader_errors),
        ("数据不变量校验", test_data_invariant_guard),
    ]

    failed = 0
    for name, func in tests:
        try:
            func()
            print(f"  [通过] {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  [失败] {name}\n         {exc}")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  [异常] {name}\n         {type(exc).__name__}: {exc}")

    print()
    if failed:
        print(f"{failed} 项失败，{_passed} 个断言通过")
    else:
        print(f"全部通过（{len(tests)} 组测试，{_passed} 个断言）")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
