"""调度算法的对比实验。

用法::

    py tools/benchmark.py              # 跑全部数据集
    py tools/benchmark.py sample       # 只跑某一个

对每份任务数据，把三种算法（以及时间片轮转的多个时间片）各跑一遍，
列出平均周转 / 等待 / 响应时间、换人次数与空闲时长。报告第四章的
实验数据全部来自这个脚本的输出。

**为什么把"换人次数"也记下来**：任务书提示里提到"区分两类性能 ——
平均等待时间衡量调度策略的效果，程序实际运行耗时衡量实现效率"。
换人次数既不是等待时间，也不是程序耗时，它是**调度本身带来的开销**：
每换一个任务就要保存/恢复现场，时间片越小换得越频繁。这一列让
"时间片调小的代价"变得可以量化。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.loader import DataError, load_tasks          # noqa: E402
from src.scheduler import ALGORITHM_ORDER             # noqa: E402
from src.engine import simulate                       # noqa: E402

DATA = ROOT / "data"
WIDTH = 82
QUANTA = (1, 2, 4, 8)


def section(title: str) -> None:
    print()
    print("=" * WIDTH)
    print(title)
    print("=" * WIDTH)


def describe(tasks) -> str:
    total = sum(t.burst_time for t in tasks)
    arrivals = [t.arrival_time for t in tasks]
    priorities = {t.priority for t in tasks}
    same_arrival = len(set(arrivals)) == 1
    note = []
    if same_arrival:
        note.append("同时到达")
    if max(arrivals) > 0:
        note.append(f"到达时刻 {min(arrivals)}~{max(arrivals)}")
    note.append(f"优先级 {min(priorities)}~{max(priorities)}")
    return (f"{len(tasks)} 个任务，总运行时长 B = {total}，"
            f"到达时间跨度 {max(arrivals)}；" + "，".join(note))


def run_dataset(name: str) -> None:
    path = next((p for p in [DATA / f"{name}.csv", DATA / f"{name}.json"] if p.exists()),
                None)
    if path is None:
        print(f"找不到数据集 {name}")
        return
    try:
        tasks = load_tasks(path)
    except DataError as exc:
        print(f"{name}：{exc}")
        return

    section(f"数据集 {name}")
    print(describe(tasks))
    print()
    print(f"{'算法':<12}{'时间片':>6}{'平均周转':>10}{'平均等待':>10}"
          f"{'平均响应':>10}{'换人':>6}{'空闲':>6}{'总时长':>8}")
    print("-" * WIDTH)

    best = {}

    def show(result, label: str, quantum) -> None:
        print(f"{label:<12}{(quantum if quantum else '—'):>6}"
              f"{result.avg_turnaround:>10.2f}{result.avg_waiting:>10.2f}"
              f"{result.avg_response:>10.2f}{result.context_switches:>6}"
              f"{result.idle_units:>6}{result.makespan:>8}")
        for key, value in (("turnaround", result.avg_turnaround),
                           ("waiting", result.avg_waiting),
                           ("response", result.avg_response)):
            if key not in best or value < best[key][0]:
                best[key] = (value, label)

    for key in ALGORITHM_ORDER:
        if key == "rr":
            for quantum in QUANTA:
                show(simulate(tasks, key, quantum), f"RR", quantum)
        else:
            result = simulate(tasks, key)
            show(result, result.algorithm, None)

    print()
    print(f"周转最短：{best['turnaround'][1]}（{best['turnaround'][0]:.2f}）   "
          f"等待最短：{best['waiting'][1]}（{best['waiting'][0]:.2f}）   "
          f"响应最快：{best['response'][1]}（{best['response'][0]:.2f}）")


def main() -> int:
    names = sys.argv[1:]
    if not names:
        # 同一份数据可能同时存在 .csv 与 .json 两个版本（内容相同），
        # 按 stem 去重，保证每个数据集只跑一次
        names = sorted({p.stem for p in DATA.glob("*")
                        if p.suffix in (".csv", ".json")})

    for name in names:
        run_dataset(name)

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
