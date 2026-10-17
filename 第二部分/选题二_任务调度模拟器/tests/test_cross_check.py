"""交叉验证：用一个刻意笨拙的参考实现对随机数据独立复算。

直接运行：  py tests/test_cross_check.py

`test_scheduler.py` 里的不变量检查关心的是"结果自不自洽"，它不关心实现
怎么写的。这里补上一层更强的验证：**把同一套调度规则用完全不同的代码
路径再实现一遍**，然后逐格比对两张甘特图。

参考实现（`naive_reference`）故意写得和正式实现不一样：

======================  ==========================  ==========================
                        src/engine.py（正式）        naive_reference（参考）
======================  ==========================  ==========================
就绪集合                 deque / heapq               普通 list
选下一个（优先级）        堆顶 O(log n)               线性扫描取最小 O(n)
到达处理                 预排序 + 游标                每个时间单位全表扫描
任务对象                  Task 实例                   字典
======================  ==========================  ==========================

两条路写出来的东西只有"规则"是共用的，任何一处编码疏漏都会让某组随机
数据上的甘特图对不上。
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engine import simulate          # noqa: E402
from src.loader import validate          # noqa: E402
from src.models import ScheduleResult    # noqa: E402

_passed = 0


def check(condition: bool, message: str) -> None:
    global _passed
    if not condition:
        raise AssertionError(message)
    _passed += 1


# ----------------------------------------------------------------------
def naive_reference(specs: list[dict], algorithm: str, quantum: int = 2):
    """参考实现：全部用线性扫描，不借助任何"聪明"的容器。

    Returns:
        (每条执行记录 [(task_id 或 None, 起始时刻), ...], 每个任务的三个时刻)
    """
    tasks = [
        {
            "task_id": s["task_id"],
            "arrival": s["arrival_time"],
            "burst": s["burst_time"],
            "priority": s["priority"],
            "seq": index,
            "remaining": s["burst_time"],
            "state": "未到达",
            "start": None,
            "finish": None,
            "slice_used": 0,
        }
        for index, s in enumerate(specs)
    ]

    ready: list[dict] = []
    timeline: list[tuple[str | None, int]] = []
    now = 0
    done = 0
    running: dict | None = None
    pending: dict | None = None

    while done < len(tasks):
        # ① 本时刻到达的全部入队（全表扫描，顺便保证按输入顺序）
        for task in tasks:
            if task["state"] == "未到达" and task["arrival"] <= now:
                task["state"] = "就绪"
                ready.append(task)

        # ② 上一格用尽时间片的任务，现在回队尾
        if pending is not None:
            pending["state"] = "就绪"
            ready.append(pending)
            pending = None
            running = None

        # ③ 调度
        if running is None and ready:
            if algorithm == "priority":
                best = 0
                for i in range(1, len(ready)):
                    a, b = ready[i], ready[best]
                    if (a["priority"], a["arrival"], a["seq"]) < \
                       (b["priority"], b["arrival"], b["seq"]):
                        best = i
                running = ready.pop(best)
            else:
                running = ready.pop(0)

        # ④ 运行
        if running is None:
            timeline.append((None, now))
            now += 1
            continue

        if running["start"] is None:
            running["start"] = now
        running["state"] = "运行"
        timeline.append((running["task_id"], now))
        running["remaining"] -= 1
        running["slice_used"] += 1
        now += 1

        if running["remaining"] == 0:
            running["finish"] = now
            running["state"] = "完成"
            done += 1
            running = None
        elif algorithm == "rr" and running["slice_used"] >= quantum:
            running["slice_used"] = 0
            pending = running

    moments = {t["task_id"]: (t["start"], t["finish"]) for t in tasks}
    return timeline, moments


def expand(result: ScheduleResult) -> list[tuple[str | None, int]]:
    """把合并过的甘特图展开成逐时间单位的列表，便于与参考实现比对。"""
    out: list[tuple[str | None, int]] = []
    for seg in result.timeline.segments:
        for moment in range(seg.start, seg.end):
            out.append((seg.task_id, moment))
    return out


# ----------------------------------------------------------------------
def test_cross_check() -> None:
    """对随机任务集，参考实现与正式实现必须逐格一致。"""
    rng = random.Random(20261017)
    checked = 0

    for round_no in range(80):
        count = rng.randint(1, 7)
        specs = []
        for i in range(count):
            specs.append({
                "task_id": f"R{i}",
                "name": f"任务{i}",
                "arrival_time": rng.randint(0, 10),
                "burst_time": rng.randint(1, 7),
                "priority": rng.randint(0, 3),
            })

        tasks = validate(specs)
        for algorithm in ("fcfs", "priority", "rr"):
            for quantum in ((1, 2, 3, 5) if algorithm == "rr" else (2,)):
                result = simulate(tasks, algorithm, quantum)
                expected_timeline, expected_moments = naive_reference(
                    specs, algorithm, quantum)

                actual = expand(result)
                check(actual == expected_timeline,
                      f"第 {round_no} 轮 {algorithm}(q={quantum})：甘特图不一致\n"
                      f"  正式：{[(t, m) for t, m in actual][:24]}\n"
                      f"  参考：{expected_timeline[:24]}")

                for task in result.tasks:
                    start, finish = expected_moments[task.task_id]
                    check(task.start_time == start and task.finish_time == finish,
                          f"第 {round_no} 轮 {algorithm}(q={quantum})："
                          f"{task.task_id} 的时刻不一致 —— "
                          f"正式 (S={task.start_time}, C={task.finish_time})，"
                          f"参考 (S={start}, C={finish})")
                checked += 1

    check(checked > 0, "应当至少比对过一次")
    print(f"        （共比对 {checked} 组随机用例）")


def test_cross_check_on_sample_data() -> None:
    """用任务书的示例数据也走一遍，结果应与手工推演一致。"""
    specs = [
        {"task_id": "T1", "name": "任务A", "arrival_time": 0, "burst_time": 5, "priority": 2},
        {"task_id": "T2", "name": "任务B", "arrival_time": 1, "burst_time": 3, "priority": 1},
        {"task_id": "T3", "name": "任务C", "arrival_time": 2, "burst_time": 1, "priority": 3},
        {"task_id": "T4", "name": "任务D", "arrival_time": 4, "burst_time": 2, "priority": 1},
    ]
    tasks = validate(specs)

    for algorithm in ("fcfs", "priority", "rr"):
        for quantum in ((1, 2, 4) if algorithm == "rr" else (2,)):
            result = simulate(tasks, algorithm, quantum)
            timeline, moments = naive_reference(specs, algorithm, quantum)
            check(expand(result) == timeline,
                  f"{algorithm}(q={quantum}) 在示例数据上两份实现的甘特图不一致")
            for task in result.tasks:
                check((task.start_time, task.finish_time) == moments[task.task_id],
                      f"{algorithm}(q={quantum})：{task.task_id} 的时刻不一致")


def test_timeline_expansion() -> None:
    """展开函数本身要正确（合并过的段展开后应当还原成逐个时间单位）。"""
    specs = [
        {"task_id": "A", "name": "甲", "arrival_time": 0, "burst_time": 3, "priority": 0},
        {"task_id": "B", "name": "乙", "arrival_time": 5, "burst_time": 2, "priority": 0},
    ]
    result = simulate(validate(specs), "fcfs", 2)
    expanded = expand(result)
    check(len(expanded) == result.makespan,
          f"展开后应当有 {result.makespan} 条，实际 {len(expanded)} 条")
    check([tid for tid, _ in expanded] == ["A", "A", "A", None, None, "B", "B"],
          f"展开结果不对：{expanded}")
    check([m for _, m in expanded] == list(range(result.makespan)),
          "展开后的时刻应当从 0 连续递增")


# ----------------------------------------------------------------------
def main() -> int:
    tests = [
        ("随机数据交叉验证", test_cross_check),
        ("示例数据交叉验证", test_cross_check_on_sample_data),
        ("甘特图展开", test_timeline_expansion),
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
    print(f"{failed} 项失败，{_passed} 个断言通过" if failed
          else f"全部通过（{len(tests)} 组测试，{_passed} 个断言）")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
