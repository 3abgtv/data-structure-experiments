"""性能对比实验。

直接运行：  py tests/benchmark.py

三组实验：

一、**三种算法在实测网络上的横向对比**。分别在规模较小的示例市地铁网
    （65 站）和真实的北京地铁主干网络（224 站）上取样，统计路径长度、
    换乘次数、访问站点数、松弛次数与耗时。耗时取多次重复的平均值 ——
    单次只有几毫秒，测一次会被系统调度的噪声淹没。

二、**启发函数的放大系数对搜索规模的影响**。h 越接近真实剩余代价，
    被"带偏"去探索的分支就越少；但一旦放大系数超过 1，h 不再可采纳，
    搜索会更快，代价却可能不再是最短路径。

三、**规则网格的对角路径 —— A* 失效的特例**。这个例子里所有单调路径
    都是最短路径，"任意"可采纳的启发函数都会让 f 值恒定，A* 因此退化
    成 Dijkstra，必须扩展全部站点。

衡量搜索效率时"访问站点数"比"耗时"更稳定：耗时受实现细节影响很大
（例如 A* 每弹出一个站点都要多算一次距离），在小网络上未必反映搜索规模。
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph import Graph                      # noqa: E402
from src.loader import load_graph                # noqa: E402
from src.models import Line, Vertex              # noqa: E402
from src.solver import ALGORITHM_ORDER, SOLVERS, AStarSolver  # noqa: E402

WIDTH = 78
NETWORKS = [
    ("示例市地铁网（构造）", ROOT / "data" / "metro" / "network.json", 60),
    ("北京地铁主干（真实数据还原）", ROOT / "data" / "beijing" / "network.json", 30),
]


def build_grid(width: int, height: int, spacing: float = 1.0) -> Graph:
    """生成一张 width × height 的规则网格网络（四邻接）。"""
    graph = Graph()
    for r in range(height):
        for c in range(width):
            graph.add_vertex(Vertex(f"N{r}_{c}", f"{r}-{c}", c * spacing, r * spacing))
    for r in range(height):
        graph.add_line(Line(f"R{r}", f"横线 {r}", "#666666",
                            [f"N{r}_{c}" for c in range(width)],
                            speed_kmh=40.0, detour=1.0))
    for c in range(width):
        graph.add_line(Line(f"C{c}", f"竖线 {c}", "#666666",
                            [f"N{r}_{c}" for r in range(height)],
                            speed_kmh=40.0, detour=1.0))
    return graph


def measure(solver, graph: Graph, start: str, goal: str, repeat: int):
    """重复求解，返回 (结果, 去重后的访问站点数, 平均耗时毫秒)。"""
    route, stats = solver.solve(graph, start, goal)
    samples = []
    for _ in range(repeat):
        _, s = solver.solve(graph, start, goal)
        samples.append(s.milliseconds)
    return route, stats.unique_settled, statistics.mean(samples)


def section(title: str) -> None:
    print()
    print("=" * WIDTH)
    print(title)
    print("=" * WIDTH)


def sample_pairs(graph: Graph, count: int = 12) -> list[tuple[str, str]]:
    ids = sorted(graph.vertices)
    pairs = [(ids[(i * 11) % len(ids)], ids[(i * 29 + 17) % len(ids)]) for i in range(count)]
    return [(a, b) for a, b in pairs if a != b]


# ----------------------------------------------------------------------
def bench_algorithms(title: str, path: Path, repeat: int, verbose: bool) -> None:
    graph = load_graph(path)
    pairs = sample_pairs(graph)

    section(f"{title}：{graph.vertex_count} 站 / {graph.line_count} 线 / "
            f"{graph.edge_count} 段区间 / {len(graph.transfer_stations())} 个换乘站"
            f"（每组重复 {repeat} 次取平均）")

    totals = {key: {"settled": [], "elapsed": []} for key in ALGORITHM_ORDER}

    if verbose:
        print(f"{'起点':<9}{'终点':<9}{'算法':<9}{'距离km':>9}{'换乘':>5}"
              f"{'路径站数':>9}{'访问站点':>9}{'耗时ms':>9}")
        print("-" * WIDTH)

    for start, goal in pairs:
        for key in ALGORITHM_ORDER:
            route, settled, elapsed = measure(SOLVERS[key], graph, start, goal, repeat)
            totals[key]["settled"].append(settled)
            totals[key]["elapsed"].append(elapsed)
            if verbose:
                print(f"{graph.name_of(start):<9}{graph.name_of(goal):<9}{SOLVERS[key].name:<9}"
                      f"{route.distance:>9.2f}{route.transfers:>5}{route.stops:>9}"
                      f"{settled:>9}{elapsed:>9.3f}")
        if verbose:
            print("-" * WIDTH)

    print(f"\n汇总（{len(pairs)} 组起终点的平均值）")
    print(f"{'算法':<14}{'平均访问站点':>14}{'平均耗时 ms':>14}{'访问站点相对值':>16}")
    print("-" * WIDTH)
    base = statistics.mean(totals["dijkstra"]["settled"])
    for key in ALGORITHM_ORDER:
        avg_settled = statistics.mean(totals[key]["settled"])
        avg_elapsed = statistics.mean(totals[key]["elapsed"])
        print(f"{SOLVERS[key].name:<14}{avg_settled:>14.1f}{avg_elapsed:>14.3f}"
              f"{avg_settled / base:>15.2f}×")


# ----------------------------------------------------------------------
def bench_heuristic_weight(title: str, path: Path, repeat: int = 20) -> None:
    """h 的放大系数：搜索规模与最优性之间的权衡。"""
    graph = load_graph(path)
    pairs = sample_pairs(graph)
    reference = {pair: measure(SOLVERS["dijkstra"], graph, *pair, repeat=1)[0].distance
                 for pair in pairs}

    section(f"启发函数的放大系数：weight × 直线距离（{title}）")
    print("weight <= 1 时 h 可采纳，结果保证最优；weight > 1 会高估真实代价。\n")
    print(f"{'weight':<9}{'平均访问站点':>14}{'平均耗时 ms':>14}"
          f"{'仍为最短路径':>16}{'平均超出':>12}")
    print("-" * WIDTH)

    for weight in (0.0, 0.5, 0.8, 1.0, 1.1, 1.3):
        solver = AStarSolver(weight=weight)
        settled, elapsed, optimal, overshoot = [], [], 0, []
        for pair in pairs:
            route, s, e = measure(solver, graph, *pair, repeat)
            settled.append(s)
            elapsed.append(e)
            if abs(route.distance - reference[pair]) < 1e-9:
                optimal += 1
            else:
                overshoot.append(100 * (route.distance - reference[pair]) / reference[pair])
        label = "=0（退化为 Dijkstra）" if weight == 0.0 else f"{weight:.1f}"
        shown = f"{statistics.mean(overshoot):.1f}%" if overshoot else "—"
        print(f"{label:<9}{statistics.mean(settled):>14.1f}{statistics.mean(elapsed):>14.3f}"
              f"{optimal:>12}/{len(pairs):<4}{shown:>12}")


# ----------------------------------------------------------------------
def bench_grid() -> None:
    section("规则网格的对角路径 —— A* 失效的特例")
    print("从网格左上角走到右下角，所有「只向右、只向下」的路径都是最短路径，")
    print("任意可采纳的 h 都会让沿途各点的 f 值恒等于最优代价，A* 因此退化")
    print("为 Dijkstra，必须扩展全部站点。换用曼哈顿距离结果完全一样。\n")
    print(f"{'规模':<9}{'站点数':>7}{'算法':<12}{'距离':>8}{'路径站数':>10}"
          f"{'访问站点':>10}{'访问占比':>10}{'耗时ms':>10}")
    print("-" * WIDTH)

    variants = [
        SOLVERS["dijkstra"],
        SOLVERS["astar"],
        AStarSolver(metric="manhattan", name="A*(曼哈顿)"),
    ]

    for side in (10, 16, 22, 28):
        graph = build_grid(side, side)
        start, goal = "N0_0", f"N{side - 1}_{side - 1}"
        for solver in variants:
            route, settled, elapsed = measure(solver, graph, start, goal, repeat=10)
            print(f"{side}×{side:<6}{graph.vertex_count:>7}{solver.name:<12}"
                  f"{route.distance:>8.1f}{route.stops:>10}{settled:>10}"
                  f"{100 * settled / graph.vertex_count:>9.1f}%{elapsed:>10.3f}")
        print("-" * WIDTH)


def main() -> int:
    for index, (title, path, repeat) in enumerate(NETWORKS):
        bench_algorithms(title, path, repeat, verbose=(index == 0))
    bench_heuristic_weight("北京地铁主干", NETWORKS[1][1])
    bench_grid()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
