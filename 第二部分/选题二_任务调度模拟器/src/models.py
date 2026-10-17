"""数据模型层。

只描述"任务长什么样、一次调度留下了什么记录"，不含任何调度策略，
也不含任何界面代码 —— 对应任务书"任务模型、调度算法、统计分析与界面
逻辑应相互分离"的模块划分要求。

任务书规定每个任务至少包含七个属性，这里的对应关系是：

    task_id          唯一标识              Task.task_id
    name             描述性名称            Task.name
    arrival_time     到达时刻（非负整数）   Task.arrival_time
    burst_time       运行时长（正整数）     Task.burst_time
    priority         优先级（越小越高）     Task.priority
    remaining_time   剩余时长              Task.remaining_time
    state            当前所处阶段          Task.state

除了这七项，还有一个不在要求里、但决定"结果能否复现"的东西：**输入顺序**
（`Task.seq`）。任务书规定"到达时间相同时按数据输入顺序处理"、"优先级相同时
按到达时间和输入顺序决定执行顺序"，所以必须把这个顺序显式记下来，不能依赖
容器的遍历次序。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskState(Enum):
    """任务状态。四种取值与任务书一致。"""

    NOT_ARRIVED = "未到达"
    READY = "就绪"
    RUNNING = "运行"
    FINISHED = "完成"

    def __str__(self) -> str:                      # 便于直接显示
        return self.value


@dataclass
class Task:
    """一个任务实例。

    同一个任务定义会在每次模拟开始前被重新克隆一份，因此这里的
    ``remaining_time`` / ``state`` / ``start_time`` / ``finish_time``
    都是**运行期状态**，不影响原始定义 —— 这正是任务书要求的
    "每次运行前恢复任务初始状态，保证比较公平"。
    """

    task_id: str
    name: str
    arrival_time: int
    burst_time: int
    priority: int
    seq: int = 0                       # 输入顺序，用于打破平局

    # ---- 运行期状态 ----
    remaining_time: int = 0
    state: TaskState = TaskState.NOT_ARRIVED
    start_time: int | None = None      # 首次获得处理器的时刻 S_i
    finish_time: int | None = None     # 完成的时刻 C_i
    slice_used: int = 0                # 本次已连续占用的时间片长度（仅 RR 使用）

    def __post_init__(self) -> None:
        self.remaining_time = self.burst_time

    def __str__(self) -> str:
        return f"{self.task_id}({self.name})"

    # ------------------------------------------------------------------
    def clone(self) -> Task:
        """复制一份全新的运行实例，回到未到达的初始状态。"""
        return Task(
            task_id=self.task_id,
            name=self.name,
            arrival_time=self.arrival_time,
            burst_time=self.burst_time,
            priority=self.priority,
            seq=self.seq,
        )

    def reset(self) -> None:
        """就地恢复初始状态。"""
        self.remaining_time = self.burst_time
        self.state = TaskState.NOT_ARRIVED
        self.start_time = None
        self.finish_time = None
        self.slice_used = 0

    # ------------------------------------------------------------------
    # 统计指标（任务书给出的三个公式）
    # ------------------------------------------------------------------
    @property
    def turnaround_time(self) -> int | None:
        """周转时间 T = C - A：从到达到完成经历了多久。"""
        if self.finish_time is None:
            return None
        return self.finish_time - self.arrival_time

    @property
    def waiting_time(self) -> int | None:
        """等待时间 W = T - B：在就绪队列中一共等了多久。"""
        turnaround = self.turnaround_time
        return None if turnaround is None else turnaround - self.burst_time

    @property
    def response_time(self) -> int | None:
        """响应时间 R = S - A：从到达到第一次拿到处理器隔了多久。"""
        if self.start_time is None:
            return None
        return self.start_time - self.arrival_time


# ----------------------------------------------------------------------
@dataclass
class Segment:
    """甘特图上的一段：某个任务（或空闲）占用了 [start, end) 这段时间。"""

    task_id: str | None                # None 表示处理器空闲
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


class Timeline:
    """执行记录（甘特图的数据来源）。

    每次模拟中都恰好推进一个时间单位，每个单位记一条；相邻且属于
    同一任务的单位会自动合并成一段，因此"连续执行 5 个单位"在
    ``segments`` 里是一条长度为 5 的记录，而不是 5 条。
    """

    def __init__(self) -> None:
        self.segments: list[Segment] = []

    def append(self, task_id: str | None, moment: int) -> None:
        """记录一个时间单位 [moment, moment+1) 由谁占用。"""
        if self.segments:
            last = self.segments[-1]
            if last.task_id == task_id and last.end == moment:
                last.end = moment + 1
                return
        self.segments.append(Segment(task_id, moment, moment + 1))

    def clear(self) -> None:
        self.segments.clear()

    @property
    def total_idle(self) -> int:
        """处理器一共空闲了多少个时间单位。"""
        return sum(seg.length for seg in self.segments if seg.task_id is None)

    @property
    def makespan(self) -> int:
        """最后一个时间单位的结束时刻。"""
        return self.segments[-1].end if self.segments else 0

    def idle_ranges(self) -> list[tuple[int, int]]:
        return [(seg.start, seg.end) for seg in self.segments if seg.task_id is None]

    def runs_of(self, task_id: str) -> list[tuple[int, int]]:
        """某个任务的所有执行区间（RR 下会被切成好几段）。"""
        return [(seg.start, seg.end) for seg in self.segments if seg.task_id == task_id]


# ----------------------------------------------------------------------
@dataclass
class ScheduleResult:
    """一次模拟的完整结果。"""

    algorithm: str
    tasks: list[Task]
    timeline: Timeline
    quantum: int | None = None
    description: str = ""
    extra: dict = field(default_factory=dict)

    # ---- 汇总指标 ----
    def _average(self, values: list[int | None]) -> float:
        usable = [v for v in values if v is not None]
        return sum(usable) / len(usable) if usable else 0.0

    @property
    def avg_turnaround(self) -> float:
        return self._average([t.turnaround_time for t in self.tasks])

    @property
    def avg_waiting(self) -> float:
        return self._average([t.waiting_time for t in self.tasks])

    @property
    def avg_response(self) -> float:
        return self._average([t.response_time for t in self.tasks])

    @property
    def idle_units(self) -> int:
        return self.timeline.total_idle

    @property
    def makespan(self) -> int:
        return self.timeline.makespan

    @property
    def context_switches(self) -> int:
        """发生了多少次"换人"（不含空闲，也不含最后收尾）。"""
        switches = 0
        previous: str | None = None
        for seg in self.timeline.segments:
            if seg.task_id is None:
                continue
            if previous is not None and seg.task_id != previous:
                switches += 1
            previous = seg.task_id
        return switches

    def rows(self) -> list[dict]:
        """整理成便于写 CSV 或填表格的形式。"""
        out = []
        for task in sorted(self.tasks, key=lambda t: t.seq):
            runs = self.timeline.runs_of(task.task_id)
            out.append({
                "task_id": task.task_id,
                "name": task.name,
                "arrival_time": task.arrival_time,
                "burst_time": task.burst_time,
                "priority": task.priority,
                "start_time": task.start_time,
                "finish_time": task.finish_time,
                "turnaround_time": task.turnaround_time,
                "waiting_time": task.waiting_time,
                "response_time": task.response_time,
                "runs": runs,
            })
        return out
