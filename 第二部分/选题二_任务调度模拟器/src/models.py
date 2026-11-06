"""数据模型：任务、执行记录与统计指标。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TaskState(Enum):
    """任务状态。"""

    NOT_ARRIVED = "未到达"
    READY = "就绪"
    RUNNING = "运行"
    FINISHED = "完成"

    def __str__(self) -> str:
        return self.value


@dataclass
class Task:
    """一个任务实例；运行期状态在每次模拟前由 clone() 重置。"""

    task_id: str
    name: str
    arrival_time: int
    burst_time: int
    priority: int
    seq: int = 0                       # 输入顺序，用于打破平局

    # 运行期状态
    remaining_time: int = 0
    state: TaskState = TaskState.NOT_ARRIVED
    start_time: int | None = None      # 首次获得处理器的时刻 S_i
    finish_time: int | None = None     # 完成时刻 C_i
    slice_used: int = 0                # RR 当前已连续占用的时间片长度

    def __post_init__(self) -> None:
        self.remaining_time = self.burst_time

    def __str__(self) -> str:
        return f"{self.task_id}({self.name})"

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
        self.remaining_time = self.burst_time
        self.state = TaskState.NOT_ARRIVED
        self.start_time = None
        self.finish_time = None
        self.slice_used = 0

    @property
    def turnaround_time(self) -> int | None:
        """周转时间 T = C - A。"""
        if self.finish_time is None:
            return None
        return self.finish_time - self.arrival_time

    @property
    def waiting_time(self) -> int | None:
        """等待时间 W = T - B。"""
        turnaround = self.turnaround_time
        return None if turnaround is None else turnaround - self.burst_time

    @property
    def response_time(self) -> int | None:
        """响应时间 R = S - A。"""
        if self.start_time is None:
            return None
        return self.start_time - self.arrival_time


@dataclass
class Segment:
    """甘特图上的一段：某个任务（或空闲）占用了 [start, end)。"""

    task_id: str | None
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


class Timeline:
    """执行记录；相邻且属于同一任务的单位会自动合并成一段。"""

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
        return sum(seg.length for seg in self.segments if seg.task_id is None)

    @property
    def makespan(self) -> int:
        return self.segments[-1].end if self.segments else 0

    def idle_ranges(self) -> list[tuple[int, int]]:
        return [(seg.start, seg.end) for seg in self.segments if seg.task_id is None]

    def runs_of(self, task_id: str) -> list[tuple[int, int]]:
        """某个任务的所有执行区间（RR 下会被切成多段）。"""
        return [(seg.start, seg.end) for seg in self.segments if seg.task_id == task_id]


@dataclass
class ScheduleResult:
    """一次模拟的完整结果。"""

    algorithm: str
    tasks: list[Task]
    timeline: Timeline
    quantum: int | None = None
    description: str = ""
    extra: dict = field(default_factory=dict)

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
        """换人次数（不计空闲段）。"""
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
