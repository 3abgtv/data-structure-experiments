"""模拟引擎：逐时间单位推进，调度器负责"下一个跑谁"。"""

from __future__ import annotations

from .models import ScheduleResult, Task, TaskState, Timeline
from .scheduler import Scheduler, make_scheduler


class SimulationEngine:
    """单处理器、单段计算任务的调度模拟。"""

    MAX_STEPS = 5_000_000      # 防御性上限，兜住异常输入造成的死循环

    def __init__(self, tasks: list[Task], scheduler: Scheduler) -> None:
        self.scheduler = scheduler
        self.tasks = tasks
        self.now = 0
        self.timeline = Timeline()

        # 按 (到达时刻, 输入顺序) 预排序，保证同时到达按输入顺序入队。
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
        return [t for t in self.tasks if t.state is TaskState.NOT_ARRIVED]

    def snapshot(self) -> dict:
        """当前状态的只读快照。"""
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

        # (1) 到达必须先于 (2) 回队尾：同一时刻到达的任务排在队尾任务前面。
        self._admit_arrivals()

        if self._pending_requeue is not None:
            requeued, self._pending_requeue = self._pending_requeue, None
            self.running = None
            requeued.state = TaskState.READY
            self.scheduler.enqueue(requeued)

        if self.running is None:
            self.running = self.scheduler.pick()

        task = self.running

        if task is None:
            self.timeline.append(None, self.now)
            self.now += 1
            return True

        if task.start_time is None:
            task.start_time = self.now
        task.state = TaskState.RUNNING
        self.timeline.append(task.task_id, self.now)

        task.remaining_time -= 1
        task.slice_used += 1
        self.now += 1

        # 先判完成，再判时间片：恰好用完时间片而完成的任务不回队尾。
        if task.remaining_time == 0:
            task.finish_time = self.now
            task.state = TaskState.FINISHED
            self._finished += 1
            self.running = None
        elif self.scheduler.quantum is not None and task.slice_used >= self.scheduler.quantum:
            task.slice_used = 0
            task.state = TaskState.READY
            self._pending_requeue = task
            self.running = None

        return True

    def _admit_arrivals(self) -> None:
        while (self._next_arrival < len(self._arrivals)
               and self._arrivals[self._next_arrival].arrival_time <= self.now):
            task = self._arrivals[self._next_arrival]
            task.state = TaskState.READY
            self.scheduler.enqueue(task)
            self._next_arrival += 1

    # ------------------------------------------------------------------
    def run_to_end(self) -> None:
        """跑到所有任务完成。

        Raises:
            RuntimeError: 推进步数超过安全上限仍未结束（数据异常）。
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


def simulate(tasks: list[Task], algorithm: str, quantum: int = 2) -> ScheduleResult:
    """跑一次完整模拟；每次都用 clone() 重建任务实例。"""
    instances = [task.clone() for task in tasks]
    scheduler = make_scheduler(algorithm, quantum)
    engine = SimulationEngine(instances, scheduler)
    engine.run_to_end()
    return engine.result()
