"""调度算法：只维护就绪集合并回答"下一个跑谁"。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from heapq import heappop, heappush

from .models import Task


class Scheduler(ABC):
    """调度算法公共接口。"""

    key: str = ""
    name: str = ""
    description: str = ""
    quantum: int | None = None         # 只有 RR 用得到
    is_preemptive: bool = False

    @abstractmethod
    def enqueue(self, task: Task) -> None:
        """把一个就绪任务放进就绪集合。"""

    @abstractmethod
    def pick(self) -> Task | None:
        """取出下一个要运行的任务；为空时返回 None。"""

    @abstractmethod
    def clear(self) -> None:
        """清空就绪集合。"""

    @abstractmethod
    def snapshot(self) -> list[Task]:
        """就绪集合当前内容，按即将被选中的先后排列。"""

    @property
    @abstractmethod
    def size(self) -> int:
        """就绪任务个数。"""

    def label(self) -> str:
        return self.name


class FCFSScheduler(Scheduler):
    """先来先服务：FIFO 队列，开始后一直运行到完成。"""

    key = "fcfs"
    name = "FCFS"
    description = "先来先服务：按到达顺序排队，开始运行后一直执行到完成"

    def __init__(self) -> None:
        self._queue: deque[Task] = deque()

    def enqueue(self, task: Task) -> None:
        self._queue.append(task)

    def pick(self) -> Task | None:
        return self._queue.popleft() if self._queue else None

    def clear(self) -> None:
        self._queue.clear()

    def snapshot(self) -> list[Task]:
        return list(self._queue)

    @property
    def size(self) -> int:
        return len(self._queue)


class PriorityScheduler(Scheduler):
    """非抢占式优先级调度：二叉堆，数值越小优先级越高。

    堆键末尾的 serial 保证键永不并列，避免比较落到没有 __lt__ 的 Task。
    """

    key = "priority"
    name = "优先级"
    description = "非抢占式优先级调度：每次从就绪任务中选优先级最高者，执行到完成"

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, int, int, Task]] = []
        self._serial = 0

    def enqueue(self, task: Task) -> None:
        self._serial += 1
        heappush(self._heap,
                 (task.priority, task.arrival_time, task.seq, self._serial, task))

    def pick(self) -> Task | None:
        return heappop(self._heap)[4] if self._heap else None

    def clear(self) -> None:
        self._heap.clear()
        self._serial = 0

    def snapshot(self) -> list[Task]:
        return [item[4] for item in sorted(self._heap)]

    @property
    def size(self) -> int:
        return len(self._heap)


class RoundRobinScheduler(Scheduler):
    """时间片轮转：FIFO 队列，用完时间片未完成则回队尾。

    回队尾的时机由 engine 控制：推迟到下一时间单位开头，好让同时刻
    到达的任务先入队。
    """

    key = "rr"
    name = "时间片轮转"
    description = "RR：按队列顺序分配时间片，未完成的任务重新回到队尾"

    def __init__(self, quantum: int = 2) -> None:
        self.quantum = max(1, int(quantum))
        self._queue: deque[Task] = deque()

    def enqueue(self, task: Task) -> None:
        self._queue.append(task)

    def pick(self) -> Task | None:
        return self._queue.popleft() if self._queue else None

    def clear(self) -> None:
        self._queue.clear()

    def snapshot(self) -> list[Task]:
        return list(self._queue)

    @property
    def size(self) -> int:
        return len(self._queue)

    def label(self) -> str:
        return f"{self.name} (q={self.quantum})"


def make_scheduler(key: str, quantum: int = 2) -> Scheduler:
    """按标识创建调度器。"""
    if key == "fcfs":
        return FCFSScheduler()
    if key == "priority":
        return PriorityScheduler()
    if key == "rr":
        return RoundRobinScheduler(quantum)
    raise ValueError(f"未知的调度算法：{key}")


ALGORITHM_ORDER = ["fcfs", "priority", "rr"]
