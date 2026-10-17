"""模拟引擎。

引擎负责"时间怎么走"，调度器负责"下一个跑谁"，两者分工明确。采用
**逐时间单位模拟**（而不是事件驱动）：每调用一次 ``step()`` 就把模拟时钟
往前拨一个单位，恰好对应任务书对"单步执行"的定义 —— 推进一个模拟时间单位。

一个时间单位之内要做四件事，**顺序不能变**：

1. **处理到达**。本时刻到达的任务按输入顺序进入就绪集合。
2. **处理"时间片耗尽"**。上一个单位结束时刚好用完时间片的任务，此刻回到队尾。
3. **调度**。如果处理器空着，向调度器要一个任务。
4. **运行**。执行一个单位，扣减剩余时长，检查是否完成。

第 1 步排在第 2 步之前的理由，正是任务书 §3.2 里那条容易写反的边界规则：

> 时间片内新到达的任务按到达顺序进入队尾；**恰好在时间片结束时到达的任务，
> 先入队，再将未完成的当前任务放回队尾**。

"回队尾"被刻意延后到了下一个单位的开头（记在 ``_pending_requeue`` 里），
这样它自然就排在新到达的任务后面。若把两者调换顺序，同一组数据会算出
完全不同的甘特图。

复杂度：设任务数为 n、总运行时长为 B = ΣBᵢ，则一共推进 B 个单位（加上
处理空闲的时间，不超过 B + 最大到达时刻）。每个单位里，处理到达是均摊
O(1)（到达序列已预先排好），入队和取出的代价取决于调度器 —— FCFS 与 RR
是 O(1)，优先级调度是 O(log n)。因此整体是 **O(B)**（FCFS/RR）或
**O(B log n)**（优先级调度），空间 O(n)。
"""

from __future__ import annotations

from .models import ScheduleResult, Task, TaskState, Timeline
from .scheduler import Scheduler, make_scheduler


class SimulationEngine:
    """单处理器、单段计算任务的调度模拟。"""

    # 防御性上限：正常数据远达不到，只用来兜住异常输入造成的死循环
    MAX_STEPS = 5_000_000

    def __init__(self, tasks: list[Task], scheduler: Scheduler) -> None:
        self.scheduler = scheduler
        self.tasks = tasks
        self.now = 0
        self.timeline = Timeline()

        # 到达序列：按 (到达时刻, 输入顺序) 排好，保证"同时到达按输入顺序"
        self._arrivals = sorted(tasks, key=lambda t: (t.arrival_time, t.seq))
        self._next_arrival = 0
        self._finished = 0

        self.running: Task | None = None
        self._pending_requeue: Task | None = None

    # ------------------------------------------------------------------
    @property
    def finished(self) -> bool:
        return self._finished >= len(self.tasks)

    @property
    def ready_queue(self) -> list[Task]:
        return self.scheduler.snapshot()

    @property
    def waiting(self) -> list[Task]:
        """还没到达的任务（用于界面展示）。"""
        return [t for t in self.tasks if t.state is TaskState.NOT_ARRIVED]

    def snapshot(self) -> dict:
        """当前状态的只读快照，供界面刷新使用。

        ``_pending_requeue`` 里的任务此刻还没有真正回到就绪队列（它要等到
        下一个时间单位开头，好让新到达的任务排在它前面），但它确实已经在
        等待了 —— 所以这里把它一并算进就绪队列，界面看到的三个状态
        （运行 / 就绪 / 未到达）才不会漏掉它。
        """
        ready = self.scheduler.snapshot()
        if self._pending_requeue is not None:
            ready = ready + [self._pending_requeue]
        return {
            "now": self.now,
            "running": self.running,
            "ready": ready,
            "finished": self._finished,
            "total": len(self.tasks),
        }

    # ------------------------------------------------------------------
    def step(self) -> bool:
        """推进一个模拟时间单位。已经全部完成时返回 False。"""
        if self.finished:
            return False

        # (1) 本时刻到达的任务先入队 —— 必须早于下面的"回队尾"
        self._admit_arrivals()

        # (2) 上一个单位结束时用完时间片的任务，现在回到队尾
        if self._pending_requeue is not None:
            requeued, self._pending_requeue = self._pending_requeue, None
            self.running = None
            requeued.state = TaskState.READY     # 它已经不在运行了
            self.scheduler.enqueue(requeued)

        # (3) 处理器空着就调度一个
        if self.running is None:
            self.running = self.scheduler.pick()

        task = self.running

        # (4) 没人可跑 —— 处理器空闲，记下这一格，时钟照常前进
        if task is None:
            self.timeline.append(None, self.now)
            self.now += 1
            return True

        # (5) 运行一个单位
        if task.start_time is None:
            task.start_time = self.now          # 首次获得处理器
        task.state = TaskState.RUNNING
        self.timeline.append(task.task_id, self.now)

        task.remaining_time -= 1
        task.slice_used += 1
        self.now += 1

        # (6) 完成，还是时间片用尽？
        if task.remaining_time == 0:
            task.finish_time = self.now
            task.state = TaskState.FINISHED
            self._finished += 1
            self.running = None
        elif self.scheduler.quantum is not None and task.slice_used >= self.scheduler.quantum:
            task.slice_used = 0
            # 时间片用完：它已经不在运行了，但"回队尾"这个动作要延到下一个
            # 时间单位的开头（这样新到达的任务能排在它前面）。这里先把状态
            # 改回就绪并把处理器让出来，避免界面上出现"任务既在运行、
            # 又不在就绪队列里"的中间态。
            task.state = TaskState.READY
            self._pending_requeue = task
            self.running = None

        return True

    def _admit_arrivals(self) -> None:
        """把到达时刻已到的任务按输入顺序送进就绪集合。"""
        while (self._next_arrival < len(self._arrivals)
               and self._arrivals[self._next_arrival].arrival_time <= self.now):
            task = self._arrivals[self._next_arrival]
            task.state = TaskState.READY
            self.scheduler.enqueue(task)
            self._next_arrival += 1

    # ------------------------------------------------------------------
    def run_to_end(self) -> None:
        """一口气跑到所有任务完成。

        Raises:
            RuntimeError: 推进步数超过安全上限仍未结束。正常情况下不可能
                发生（总步数不会超过 B + 最大到达时刻），一旦发生说明数据
                异常 —— 此时宁可报错，也**不能**返回一份"还有任务没跑完"
                的结果：那样平均值会悄悄把未完成的任务排除掉，看起来一切
                正常，其实是错的。
        """
        steps = 0
        while not self.finished:
            if steps >= self.MAX_STEPS:
                raise RuntimeError(
                    f"模拟推进了 {steps} 步仍未结束，"
                    f"请检查任务的到达时间是否过大（当前时刻 {self.now}，"
                    f"仍有 {len(self.tasks) - self._finished} 个任务未完成）")
            self.step()
            steps += 1

    def run_until(self, moments: int) -> None:
        """连续推进若干个时间单位（界面按速度批量前进时使用）。"""
        for _ in range(moments):
            if not self.step():
                break

    def result(self, description: str = "") -> ScheduleResult:
        return ScheduleResult(
            algorithm=self.scheduler.name,
            tasks=self.tasks,
            timeline=self.timeline,
            quantum=self.scheduler.quantum,
            description=description,
        )


# ----------------------------------------------------------------------
def simulate(tasks: list[Task], algorithm: str, quantum: int = 2) -> ScheduleResult:
    """跑一次完整模拟。

    每次调用都用任务定义**重新克隆**一批实例，所以同一组任务可以反复用
    不同算法跑，互不影响 —— 这就是任务书要求的"每次运行前恢复任务初始
    状态，保证比较公平"。
    """
    instances = [task.clone() for task in tasks]
    scheduler = make_scheduler(algorithm, quantum)
    engine = SimulationEngine(instances, scheduler)
    engine.run_to_end()
    return engine.result()
