"""调度算法层。

三种算法在这里被抽象成同一个接口：维护一个"就绪集合"，并在处理器空闲时
回答一个问题 —— **下一个该运行谁**。除此之外的一切（时间怎么走、任务何时
到达、什么时候算完成）都由 engine 负责，所以这个文件里没有任何计时逻辑。

    FCFSScheduler        先进先出：就绪集合是个 FIFO 队列，来得早的先跑
    PriorityScheduler    非抢占式优先级：就绪集合是个二叉堆，每次取优先级最高的
    RoundRobinScheduler  时间片轮转：就绪集合也是 FIFO 队列，但运行中的任务
                         用完一个时间片后要回到队尾

三者都是**非抢占式**的：高优先级任务到达时不会打断正在运行的任务，
调度决策只发生在处理器空闲下来的那一刻。

复杂度（n 为任务数）：

===================  ==============  ==============  ==================
算法                 入队            取下一个        底层结构
===================  ==============  ==============  ==================
FCFS                 O(1)            O(1)            collections.deque
非抢占式优先级        O(log n)        O(log n)        二叉堆 heapq
时间片轮转 RR         O(1)            O(1)            collections.deque
===================  ==============  ==============  ==================
"""

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
        """取出下一个要运行的任务；就绪集合为空时返回 None。"""

    @abstractmethod
    def clear(self) -> None:
        """清空就绪集合（每次模拟开始前调用）。"""

    @abstractmethod
    def snapshot(self) -> list[Task]:
        """就绪集合的当前内容，按"即将被选中的先后"排列，供界面展示。"""

    @property
    @abstractmethod
    def size(self) -> int:
        """就绪任务个数。"""

    # 便于界面统一处理
    def label(self) -> str:
        return self.name


# ----------------------------------------------------------------------
class FCFSScheduler(Scheduler):
    """先来先服务。

    就绪集合是一个 FIFO 队列：任务按"到达的先后"排队，队首的先运行，
    一旦开始就一直运行到完成。任务书对它的硬性规定是"**后到达的任务
    不能插队**"，FIFO 队列天然满足。

    选择 ``deque`` 而不是 ``list``：``list.pop(0)`` 需要把后面所有元素
    往前挪，是 O(n)；``deque.popleft()`` 是 O(1)。
    """

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


# ----------------------------------------------------------------------
class PriorityScheduler(Scheduler):
    """非抢占式优先级调度。

    就绪集合是一个二叉堆，每次取出优先级最高的任务。任务书规定
    **数值越小优先级越高**，所以堆的排序键是

        (priority, arrival_time, seq)

    后两项用来保证"优先级相同时按到达时间和输入顺序决定执行顺序"——
    如果只用 priority 做键，同优先级的任务取到哪个取决于堆的内部结构，
    结果就无法复现了。``seq`` 是输入顺序，全局唯一，因此这个键不会出现
    并列。

    "非抢占"体现在：高优先级任务到达时**不打断**正在运行的任务，
    它只是排进堆里，等当前任务跑完才轮到它。
    """

    key = "priority"
    name = "优先级"
    description = "非抢占式优先级调度：每次从就绪任务中选优先级最高者，执行到完成"

    def __init__(self) -> None:
        # 键的末尾原本直接放 Task 对象，这样当两个任务的 (priority, arrival,
        # seq) 完全相同时，元组比较会落到 Task 上 —— 而 Task 没有定义
        # __lt__，堆就会抛 TypeError。正常调用链里 seq 是唯一的，但 Task 是
        # 公开的数据模型，直接构造两个 seq 都为 0 的实例就能踩到。用一个
        # 自增的入队序号收尾，键就永远不会并列了。
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


# ----------------------------------------------------------------------
class RoundRobinScheduler(Scheduler):
    """时间片轮转。

    就绪集合同样是 FIFO 队列，但规则多了一条：正在运行的任务用完一个
    时间片（q 个单位）后，如果没有完成，就要回到**队尾**重新排队。
    队首的下一个任务接手处理器。

    任务书对入队顺序有一条特别的规定（§3.2 第 2 条）：

    > 时间片内新到达的任务按到达顺序进入队尾；**恰好在时间片结束时到达
    > 的任务，先入队，再将未完成的当前任务放回队尾**。

    也就是说，在时间片结束的同一时刻，"新到达的任务"排在"被放回的当前
    任务"前面。这条规则的实现在 `engine.SimulationEngine.step()` 里 ——
    引擎在推进一个时间单位时，先处理到达、再处理"回队尾"，顺序天然正确。
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


# ----------------------------------------------------------------------
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
