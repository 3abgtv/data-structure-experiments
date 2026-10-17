"""调度算法的正确性测试。

不依赖 pytest，直接运行：

    py tests/test_scheduler.py

覆盖四类内容：

1. **手工推演核对** —— 用任务书给的示例数据逐项比对预期结果；
2. **边界规则** —— 特别是 RR 那条容易写反的"时间片结束时新任务先入队"；
3. **不变量检查** —— 用随机数据验证五条任何调度结果都必须满足的性质；
4. **输入校验** —— 重复编号、负数时间、零运行时长等等。
"""

from __future__ import annotations

import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engine import SimulationEngine, simulate        # noqa: E402
from src.loader import (DataError, check_quantum,        # noqa: E402
                        export_result, load_tasks, validate)
from src.models import ScheduleResult, Task, TaskState   # noqa: E402
from src.scheduler import (FCFSScheduler, PriorityScheduler,  # noqa: E402
                           RoundRobinScheduler, make_scheduler)

DATA = ROOT / "data"
_passed = 0


def check(condition: bool, message: str) -> None:
    global _passed
    if not condition:
        raise AssertionError(message)
    _passed += 1


def runs_of(result: ScheduleResult, task_id: str) -> list[tuple[int, int]]:
    return result.timeline.runs_of(task_id)


def make_tasks(*specs) -> list[Task]:
    rows = [{"task_id": tid, "name": name, "arrival_time": arrival,
             "burst_time": burst, "priority": priority}
            for tid, name, arrival, burst, priority in specs]
    return validate(rows)


def gantt(result: ScheduleResult) -> str:
    return " ".join(f"{seg.task_id or '空闲'}[{seg.start},{seg.end})"
                    for seg in result.timeline.segments)


# ======================================================================
# 一、手工推演核对
# ======================================================================
def test_sample_fcfs() -> None:
    """任务书给的示例数据 + FCFS，逐项比对任务书列出的预期结果。

    任务书原文（第四章第 2 节）给出的预期结果是：

        T1 [0,5)  T=5 W=0 R=0
        T2 [5,8)  T=7 W=4 R=4
        T3 [8,9)  T=7 W=6 R=6
        T4 [9,11) T=7 W=5 R=5
        平均值    T=6.50 W=3.75 R=3.75
    """
    result = simulate(load_tasks(DATA / "sample.csv"), "fcfs")

    check(gantt(result) == "T1[0,5) T2[5,8) T3[8,9) T4[9,11)",
          f"甘特图与预期不符：{gantt(result)}")

    expected = {
        "T1": ((0, 5), 5, 0, 0),
        "T2": ((5, 8), 7, 4, 4),
        "T3": ((8, 9), 7, 6, 6),
        "T4": ((9, 11), 7, 5, 5),
    }
    for task in result.tasks:
        interval, turn, wait, resp = expected[task.task_id]
        check(runs_of(result, task.task_id) == [interval],
              f"{task.task_id} 的执行区间应为 {interval}，"
              f"实际 {runs_of(result, task.task_id)}")
        check(task.turnaround_time == turn, f"{task.task_id} 周转时间应为 {turn}")
        check(task.waiting_time == wait, f"{task.task_id} 等待时间应为 {wait}")
        check(task.response_time == resp, f"{task.task_id} 响应时间应为 {resp}")

    check(abs(result.avg_turnaround - 6.50) < 1e-9, "平均周转时间应为 6.50")
    check(abs(result.avg_waiting - 3.75) < 1e-9, "平均等待时间应为 3.75")
    check(abs(result.avg_response - 3.75) < 1e-9, "平均响应时间应为 3.75")


def test_sample_priority() -> None:
    """同一组数据换成非抢占式优先级调度的手工推演结果。

    T1 在 t=0 开始，之后 T2(优先级 1)、T4(优先级 1) 陆续到达，但**不抢占**，
    所以 T1 一直跑到 t=5。此后就绪集合里 T2(1) 与 T4(1) 优先级相同，
    按到达时间早的 T2 先跑。
    """
    result = simulate(load_tasks(DATA / "sample.csv"), "priority")

    check(gantt(result) == "T1[0,5) T2[5,8) T4[8,10) T3[10,11)",
          f"甘特图与手工推演不符：{gantt(result)}")

    numbers = {t.task_id: (runs_of(result, t.task_id), t.turnaround_time,
                           t.waiting_time, t.response_time)
               for t in result.tasks}
    check(numbers["T1"] == ([(0, 5)], 5, 0, 0), f"T1 不对：{numbers['T1']}")
    check(numbers["T2"] == ([(5, 8)], 7, 4, 4), f"T2 不对：{numbers['T2']}")
    check(numbers["T4"] == ([(8, 10)], 6, 4, 4), f"T4 不对：{numbers['T4']}")
    check(numbers["T3"] == ([(10, 11)], 9, 8, 8), f"T3 不对：{numbers['T3']}")
    check(abs(result.avg_turnaround - 6.75) < 1e-9, "平均周转时间应为 6.75")

    # 非抢占的一个直接体现：T2 的优先级比 T1 高，但它到达时 T1 没有被打断
    check(runs_of(result, "T2")[0][0] >= 5,
          "高优先级任务到达时不应打断正在运行的任务")


def test_sample_rr() -> None:
    """时间片 q=1 时的手工推演结果。

    推演的关键在 t=1 和 t=2：T2、T3 分别在 t=1、t=2 到达，而这两个时刻
    恰好都是 T1、T2 的时间片结束点，因此它们要排在被放回的任务前面。
    """
    result = simulate(load_tasks(DATA / "sample.csv"), "rr", quantum=1)

    check(gantt(result) ==
          "T1[0,1) T2[1,2) T1[2,3) T3[3,4) T2[4,5) T1[5,6) "
          "T4[6,7) T2[7,8) T1[8,9) T4[9,10) T1[10,11)",
          f"甘特图与手工推演不符：{gantt(result)}")

    check(runs_of(result, "T3") == [(3, 4)], "T3 只运行一个单位就该完成")
    check(result.tasks[2].response_time == 1, "T3 的响应时间应为 1")

    # RR 的意义就在这里：三个短任务都在很早的阶段拿到了处理器
    responses = {t.task_id: t.response_time for t in result.tasks}
    check(responses["T2"] == 0 and responses["T3"] == 1,
          f"RR 下短任务的响应时间应当很小，实际 {responses}")


def test_rr_boundary_rule() -> None:
    """任务书那条边界规则：恰好在时间片结束时到达的任务，**先入队**，
    再把未完成的当前任务放回队尾。

    用一个最小例子把它逼出来：A 从 0 开始跑、时间片 q=1，B 恰好在 t=1
    到达。两种实现的区别一目了然：

        正确：B 先入队 → [B]；A 再回队尾 → [B, A]；于是 B 在 [1,2) 运行
        写反：A 先回队尾 → [A]；B 再入队   → [A, B]；于是 A 在 [1,2) 继续

    所以只要检查 [1,2) 这一格是谁，就能判定实现是否正确。
    """
    tasks = make_tasks(("A", "甲", 0, 2, 0), ("B", "乙", 1, 1, 0))
    result = simulate(tasks, "rr", quantum=1)

    check(runs_of(result, "A") == [(0, 1), (2, 3)],
          f"A 应当在 [0,1) 和 [2,3) 运行，实际 {runs_of(result, 'A')}")
    check(runs_of(result, "B") == [(1, 2)],
          f"B 应当抢在 A 前面运行 [1,2)，实际 {runs_of(result, 'B')}")
    check(result.tasks[1].response_time == 0,
          "B 恰好在时间片结束时刻到达，应当立刻获得处理器")

    # 再加一个任务，确认这条规则在多个到达者时同样成立
    tasks = make_tasks(("A", "甲", 0, 3, 0), ("B", "乙", 1, 1, 0), ("C", "丙", 1, 1, 0))
    result = simulate(tasks, "rr", quantum=1)
    check(runs_of(result, "B") == [(1, 2)] and runs_of(result, "C") == [(2, 3)],
          f"同时到达的 B、C 应按输入顺序排在 A 前面，实际 {gantt(result)}")


def test_rr_quantum_variants() -> None:
    """运行时长与时间片相等的几种情形。"""
    # 时长恰好等于时间片：用完即完成，不应回到队尾
    tasks = make_tasks(("A", "甲", 0, 2, 0), ("B", "乙", 0, 1, 0))
    result = simulate(tasks, "rr", quantum=2)
    check(runs_of(result, "A") == [(0, 2)], "恰好用完时间片并完成，不应被切分")
    check(runs_of(result, "B") == [(2, 3)], "B 应当等 A 完成后运行")

    # 时长小于时间片
    tasks = make_tasks(("A", "甲", 0, 1, 0), ("B", "乙", 0, 1, 0))
    result = simulate(tasks, "rr", quantum=5)
    check(gantt(result) == "A[0,1) B[1,2)", f"甘特图不对：{gantt(result)}")

    # 时间片为 1 时，五个单位的任务应当被切成五段
    tasks = make_tasks(("A", "甲", 0, 5, 0), ("B", "乙", 1, 3, 0))
    result = simulate(tasks, "rr", quantum=1)
    check(len(runs_of(result, "A")) >= 4,
          f"q=1 时 A 应被切成多段，实际 {runs_of(result, 'A')}")

    # 时间片足够大时，RR 退化成 FCFS
    tasks = make_tasks(("A", "甲", 0, 3, 0), ("B", "乙", 1, 2, 0))
    rr = simulate(tasks, "rr", quantum=99)
    fcfs = simulate(tasks, "fcfs")
    check(gantt(rr) == gantt(fcfs), f"大时间片下 RR 应与 FCFS 相同：{gantt(rr)} vs {gantt(fcfs)}")


# ======================================================================
# 二、边界情形
# ======================================================================
def test_idle_gap() -> None:
    """分批到达：两批任务之间应当记录出完整的空闲区间。"""
    result = simulate(load_tasks(DATA / "batch.csv"), "fcfs")
    check(result.timeline.idle_ranges() == [(5, 12)],
          f"空闲区间应为 [(5, 12)]，实际 {result.timeline.idle_ranges()}")
    check(result.idle_units == 7, f"空闲时长应为 7，实际 {result.idle_units}")

    # 空闲区间里不应混进任务的执行记录
    for seg in result.timeline.segments:
        if seg.task_id is None:
            continue
        check(not any(seg.start < end and start < seg.end
                      for start, end in result.timeline.idle_ranges()),
              "任务的执行区间与空闲区间重叠了")


def test_first_task_arrives_late() -> None:
    """第一个任务在时间 0 之后到达：开头应当是一段空闲。"""
    tasks = make_tasks(("A", "甲", 3, 2, 0))
    result = simulate(tasks, "fcfs")
    check(gantt(result) == "空闲[0,3) A[3,5)", f"甘特图不对：{gantt(result)}")
    check(result.tasks[0].response_time == 0, "任务到达时处理器空闲，响应时间应为 0")
    check(result.tasks[0].turnaround_time == 2, "周转时间应为 2")


def test_simultaneous_and_ties() -> None:
    """同时到达且优先级相同 —— 必须严格按输入顺序，且结果可复现。"""
    rows = [{"task_id": f"S{i}", "name": f"任务{i}", "arrival_time": 0,
             "burst_time": 2, "priority": 5} for i in range(1, 5)]
    tasks = validate(rows)

    for key in ("fcfs", "priority", "rr"):
        result = simulate(tasks, key, quantum=2)
        order = [seg.task_id for seg in result.timeline.segments if seg.task_id]
        # 把合并后的区间展开成逐个时间单位，再压缩成"谁先谁后"
        sequence: list[str] = []
        for tid in order:
            if not sequence or sequence[-1] != tid:
                sequence.append(tid)
        check(sequence == ["S1", "S2", "S3", "S4"],
              f"{key} 在同时到达时应当按输入顺序执行，实际 {sequence}")

    # 同样输入跑十次，结果必须一模一样
    baseline = gantt(simulate(tasks, "priority"))
    for _ in range(10):
        check(gantt(simulate(tasks, "priority")) == baseline,
              "同样的输入应当得到完全相同的调度结果")


def test_single_task() -> None:
    """只有一个任务。"""
    tasks = make_tasks(("A", "甲", 0, 4, 1))
    for key in ("fcfs", "priority", "rr"):
        result = simulate(tasks, key, quantum=1)
        check(gantt(result) == "A[0,4)", f"{key} 在单任务时甘特图不对：{gantt(result)}")
        check(abs(result.avg_turnaround - 4) < 1e-9, f"{key} 平均周转时间应为 4")
        check(abs(result.avg_waiting) < 1e-9, f"{key} 平均等待时间应为 0")
    check(result.makespan == 4, "结束时刻应为 4")
    check(result.idle_units == 0, "不应有空闲")


def test_priority_starvation() -> None:
    """优先级调度下低优先级任务会被一直压后 —— 这不是 bug，是特性。

    priority_mix.csv 里 Q3（优先级 1）与 Q4（优先级 8）到达时间只差 1，
    但 Q3 一到达就抢到了处理器，Q4 则被后面陆续到达的高优先级任务
    （Q5 优先级 2、Q2/Q6 优先级 5）一路推到 13 才开始。
    """
    result = simulate(load_tasks(DATA / "priority_mix.csv"), "priority")
    by_id = {t.task_id: t for t in result.tasks}

    check(by_id["Q4"].waiting_time > by_id["Q3"].waiting_time,
          f"低优先级任务应当等得更久：Q3={by_id['Q3'].waiting_time}，"
          f"Q4={by_id['Q4'].waiting_time}")
    check(by_id["Q4"].start_time == 13,
          f"Q4 应当被压到 t=13 才开始，实际 {by_id['Q4'].start_time}")
    check(by_id["Q5"].start_time < by_id["Q4"].start_time,
          "后到达但优先级更高的任务应当先运行")

    # 对照：同样这组数据换成 FCFS，Q4 不会被压那么久
    fcfs = simulate(load_tasks(DATA / "priority_mix.csv"), "fcfs")
    fcfs_q4 = next(t for t in fcfs.tasks if t.task_id == "Q4")
    check(fcfs_q4.start_time < by_id["Q4"].start_time,
          "FCFS 按到达顺序执行，Q4 不该被推到 13")


# ======================================================================
# 三、不变量：任何一次合法的调度都必须满足
# ======================================================================
def check_invariants(result: ScheduleResult, tasks: list[Task], label: str) -> None:
    segments = result.timeline.segments

    # (1) 甘特图连续覆盖 [0, makespan)，不留缝隙也不重叠
    cursor = 0
    for seg in segments:
        check(seg.start == cursor, f"{label}: 甘特图在 {cursor} 处不连续")
        check(seg.end > seg.start, f"{label}: 出现了长度为 0 的时间段")
        cursor = seg.end

    # (2) 每个任务的执行总量恰好等于它的运行时长
    for task in result.tasks:
        total = sum(end - start for start, end in result.timeline.runs_of(task.task_id))
        check(total == task.burst_time,
              f"{label}: {task.task_id} 被执行了 {total} 个单位，应为 {task.burst_time}")

    # (3) 任务不会在自己的到达时刻之前运行
    for task in result.tasks:
        for start, _end in result.timeline.runs_of(task.task_id):
            check(start >= task.arrival_time,
                  f"{label}: {task.task_id} 在到达前就被运行了")

    # (4) 每个任务最终都完成了，且统计公式自洽
    for task in result.tasks:
        check(task.state is TaskState.FINISHED, f"{label}: {task.task_id} 未完成")
        check(task.remaining_time == 0, f"{label}: {task.task_id} 剩余时长不为 0")
        check(task.turnaround_time == task.finish_time - task.arrival_time,
              f"{label}: {task.task_id} 的 T = C - A 不成立")
        check(task.waiting_time == task.turnaround_time - task.burst_time,
              f"{label}: {task.task_id} 的 W = T - B 不成立")
        check(task.response_time == task.start_time - task.arrival_time,
              f"{label}: {task.task_id} 的 R = S - A 不成立")
        check(task.waiting_time >= 0 and task.response_time >= 0,
              f"{label}: {task.task_id} 的等待或响应时间为负")

    # (5) 非抢占的两种算法里，每个任务只应有一整段执行区间
    if result.quantum is None:
        for task in result.tasks:
            check(len(result.timeline.runs_of(task.task_id)) == 1,
                  f"{label}: 非抢占式调度下 {task.task_id} 被打断成了多段")


def test_invariants_on_random_data() -> None:
    """用随机数据反复验证上面五条不变量。"""
    rng = random.Random(20260117)
    for round_no in range(60):
        count = rng.randint(1, 8)
        rows = []
        for i in range(count):
            rows.append({
                "task_id": f"R{i}",
                "name": f"随机任务{i}",
                "arrival_time": rng.randint(0, 12),
                "burst_time": rng.randint(1, 6),
                "priority": rng.randint(0, 4),
            })
        tasks = validate(rows)
        for key in ("fcfs", "priority", "rr"):
            for quantum in (1, 2, 3):
                result = simulate(tasks, key, quantum)
                check_invariants(result, tasks, f"第{round_no}轮 {key}(q={quantum})")


def test_reset_between_runs() -> None:
    """同一组任务连续跑多次，每次都必须从初始状态开始。"""
    tasks = load_tasks(DATA / "sample.csv")

    first = simulate(tasks, "fcfs")
    baseline = gantt(first)

    # 原始定义不能被模拟过程污染
    for task in tasks:
        check(task.state is TaskState.NOT_ARRIVED,
              f"原始任务 {task.task_id} 的状态被改成 {task.state} 了")
        check(task.remaining_time == task.burst_time,
              f"原始任务 {task.task_id} 的剩余时长被改动了")
        check(task.start_time is None and task.finish_time is None,
              f"原始任务 {task.task_id} 的统计字段被写入了")

    # 换几种算法跑过之后，再跑一次 FCFS，结果必须与第一次完全相同
    for key in ("priority", "rr", "rr"):
        simulate(tasks, key, quantum=1)
    again = simulate(tasks, "fcfs")
    check(gantt(again) == baseline, "重复模拟的结果应当完全一致")

    # 引擎也可以手工逐步推进，结果与一口气跑完相同
    instances = [t.clone() for t in tasks]
    engine = SimulationEngine(instances, FCFSScheduler())
    steps = 0
    while not engine.finished and steps < 1000:
        engine.step()
        steps += 1
    manual = engine.result()
    check(gantt(manual) == baseline, "逐步推进与一口气跑完应当得到相同结果")


# ======================================================================
# 四、输入校验与读写
# ======================================================================
def test_validation() -> None:
    def expect_error(rows, keyword: str, why: str) -> None:
        try:
            validate(rows)
            check(False, f"{why} 应当被拒绝")
        except DataError as exc:
            check(keyword in str(exc), f"{why} 的提示应含「{keyword}」，实际：{exc}")

    good = {"task_id": "T1", "name": "任务", "arrival_time": 0,
            "burst_time": 3, "priority": 1}

    expect_error([good, {**good}], "重复", "任务编号重复")
    expect_error([{**good, "arrival_time": -1}], "不能为负", "到达时间为负")
    expect_error([{**good, "burst_time": 0}], "正整数", "运行时长为 0")
    expect_error([{**good, "burst_time": -2}], "正整数", "运行时长为负")
    expect_error([{**good, "priority": -1}], "不能为负", "优先级为负")
    expect_error([{**good, "name": "  "}], "名称为空", "任务名称为空")
    expect_error([{**good, "arrival_time": 1.5}], "必须是整数", "到达时间不是整数")
    expect_error([{**good, "burst_time": "abc"}], "必须是整数", "运行时长不是数字")
    expect_error([{"task_id": "T1", "name": "甲"}], "缺少字段", "字段不全")
    expect_error([], "为空", "空任务列表")

    # 合法的边界值要能通过
    tasks = validate([{**good, "arrival_time": 0, "burst_time": 1, "priority": 0}])
    check(len(tasks) == 1 and tasks[0].seq == 0, "合法的边界值应当通过")

    # 时间片校验
    check(check_quantum("4") == 4, "时间片应当接受数字字符串")
    for bad in (0, -1, "x"):
        try:
            check_quantum(bad)
            check(False, f"时间片 {bad!r} 应当被拒绝")
        except DataError:
            check(True, "")


def test_loading_and_fields() -> None:
    """CSV 与 JSON 两种格式读出来的任务应当完全一致。"""
    csv_tasks = load_tasks(DATA / "sample.csv")
    json_tasks = load_tasks(DATA / "sample.json")
    check(len(csv_tasks) == len(json_tasks) == 4, "两个文件都应当有 4 个任务")
    for a, b in zip(csv_tasks, json_tasks):
        check((a.task_id, a.name, a.arrival_time, a.burst_time, a.priority)
              == (b.task_id, b.name, b.arrival_time, b.burst_time, b.priority),
              f"{a.task_id} 在两种格式下读出的内容不一致")

    # 输入顺序必须被记下来（seq 反映文件里的行序）
    check([t.seq for t in csv_tasks] == [0, 1, 2, 3], "输入顺序应当按文件行序记录")

    bad = Path(tempfile.mkstemp(suffix=".txt")[1])
    try:
        load_tasks(bad)
        check(False, "不支持的文件类型应当报错")
    except DataError as exc:
        check("不支持" in str(exc), f"提示应当说明类型不支持：{exc}")


def test_export() -> None:
    """导出 CSV：表头、每行内容、末尾的平均值行。"""
    result = simulate(load_tasks(DATA / "sample.csv"), "fcfs")
    target = Path(tempfile.mkstemp(suffix=".csv")[1])
    export_result(result, target)

    text = target.read_text(encoding="utf-8-sig")
    lines = [line for line in text.splitlines() if line.strip()]
    check(lines[0].startswith("task_id,name,arrival_time,burst_time,priority"),
          f"表头不对：{lines[0]}")
    check(len(lines) == 6, f"应当是表头 + 4 行数据 + 1 行平均值，实际 {len(lines)} 行")
    check(lines[1].startswith("T1,任务A,0,5,2,0,5,5,0,0"), f"T1 那行不对：{lines[1]}")
    check(lines[-1].startswith("平均值") and "6.50" in lines[-1],
          f"平均值行不对：{lines[-1]}")


def test_timeline_merge() -> None:
    """连续相同的时间单位应当合并成一段，空闲也一样。"""
    tasks = make_tasks(("A", "甲", 0, 3, 0), ("B", "乙", 5, 2, 0))
    result = simulate(tasks, "fcfs")
    check(len(result.timeline.segments) == 3,
          f"应当是 A、空闲、B 共 3 段，实际 {len(result.timeline.segments)} 段：{gantt(result)}")
    check(gantt(result) == "A[0,3) 空闲[3,5) B[5,7)", f"甘特图不对：{gantt(result)}")
    check(result.makespan == 7, "结束时刻应为 7")
    check(result.context_switches == 1, "发生了一次换人（空闲之后切到 B）")


def test_scheduler_factories() -> None:
    check(isinstance(make_scheduler("fcfs"), FCFSScheduler), "工厂应返回 FCFS")
    check(isinstance(make_scheduler("priority"), PriorityScheduler), "工厂应返回优先级调度")
    rr = make_scheduler("rr", 3)
    check(isinstance(rr, RoundRobinScheduler) and rr.quantum == 3, "工厂应返回 RR")
    check(make_scheduler("rr", 0).quantum == 1, "非法时间片应当被夹到最小值 1")
    try:
        make_scheduler("unknown")
        check(False, "未知算法应当报错")
    except ValueError:
        check(True, "")

    # 就绪队列的快照：RR/FCFS 保持入队顺序，优先级调度按优先级排序
    a = Task("A", "甲", 0, 3, 5, seq=0)
    b = Task("B", "乙", 0, 3, 1, seq=1)
    c = Task("C", "丙", 0, 3, 3, seq=2)
    fcfs = FCFSScheduler()
    for t in (a, b, c):
        fcfs.enqueue(t)
    check([t.task_id for t in fcfs.snapshot()] == ["A", "B", "C"], "FCFS 快照应保持入队顺序")

    prio = PriorityScheduler()
    for t in (a, b, c):
        prio.enqueue(t)
    check([t.task_id for t in prio.snapshot()] == ["B", "C", "A"],
          f"优先级快照应当按优先级升序，实际 {[t.task_id for t in prio.snapshot()]}")


# ======================================================================
def main() -> int:
    tests = [
        ("示例数据 · FCFS（任务书预期）", test_sample_fcfs),
        ("示例数据 · 优先级调度", test_sample_priority),
        ("示例数据 · 时间片轮转", test_sample_rr),
        ("RR 边界规则", test_rr_boundary_rule),
        ("时间片与运行时长的几种关系", test_rr_quantum_variants),
        ("空闲区间", test_idle_gap),
        ("首个任务延迟到达", test_first_task_arrives_late),
        ("同时到达与平局", test_simultaneous_and_ties),
        ("单个任务", test_single_task),
        ("优先级导致的长等待", test_priority_starvation),
        ("随机数据的不变量", test_invariants_on_random_data),
        ("重复运行互不影响", test_reset_between_runs),
        ("输入校验", test_validation),
        ("文件读写", test_loading_and_fields),
        ("结果导出", test_export),
        ("甘特图合并", test_timeline_merge),
        ("调度器工厂与快照", test_scheduler_factories),
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
