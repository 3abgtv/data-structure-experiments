"""任务列表：展示任务属性与当前状态。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..models import Task, TaskState
from . import theme

COLUMNS = [
    ("task_id", "编号", 74, "center"),
    ("name", "名称", 108, "w"),
    ("arrival_time", "到达", 62, "center"),
    ("burst_time", "运行时长", 74, "center"),
    ("priority", "优先级", 70, "center"),
    ("remaining_time", "剩余", 62, "center"),
    ("state", "状态", 74, "center"),
]


class TaskTable(ttk.Frame):
    """任务属性与状态的表格。"""

    def __init__(self, master: tk.Misc, on_select=None) -> None:
        super().__init__(master, style="Panel.TFrame")

        self.tree = ttk.Treeview(
            self, columns=[c[0] for c in COLUMNS], show="headings",
            height=8, style="Task.Treeview", selectmode="browse",
        )
        for key, title, width, anchor in COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=50, anchor=anchor, stretch=True)

        self.tree.tag_configure("running", background=theme.ROW_RUNNING_BG,
                                foreground=theme.SUCCESS)
        self.tree.tag_configure("ready", background=theme.ROW_READY_BG,
                                foreground=theme.TEXT)
        self.tree.tag_configure("finished", foreground=theme.TEXT_MUTED)
        self.tree.tag_configure("odd", background=theme.BG_STRIPE)

        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._tasks: list[Task] = []
        self._on_select = on_select
        self.tree.bind("<<TreeviewSelect>>", self._handle_select)

    # ------------------------------------------------------------------
    def set_tasks(self, tasks: list[Task]) -> None:
        """换一组任务：整表重建。"""
        self._tasks = tasks
        self.tree.delete(*self.tree.get_children())
        for index, task in enumerate(tasks):
            tags = ["odd"] if index % 2 else []
            self.tree.insert("", "end", iid=task.task_id, values=self._row(task),
                             tags=tags)
        self.refresh(tasks)

    def refresh(self, tasks: list[Task]) -> None:
        """原地刷新剩余时长与状态。

        tags 是整组替换的，刷新时要重新拼上斑马纹的 odd 标签。
        """
        for index, task in enumerate(tasks):
            if not self.tree.exists(task.task_id):
                continue
            tags = list(self._tags(task))
            if index % 2:
                tags.append("odd")
            self.tree.item(task.task_id, values=self._row(task), tags=tags)

    @staticmethod
    def _row(task: Task) -> tuple:
        return (task.task_id, task.name, task.arrival_time, task.burst_time,
                task.priority, task.remaining_time, str(task.state))

    @staticmethod
    def _tags(task: Task) -> tuple:
        if task.state is TaskState.RUNNING:
            return ("running",)
        if task.state is TaskState.READY:
            return ("ready",)
        if task.state is TaskState.FINISHED:
            return ("finished",)
        return ()

    # ------------------------------------------------------------------
    def selected_task_id(self) -> str | None:
        selection = self.tree.selection()
        return selection[0] if selection else None

    def _handle_select(self, _event=None) -> None:
        if self._on_select:
            self._on_select(self.selected_task_id())

    def focus_task(self, task_id: str | None) -> None:
        if task_id and self.tree.exists(task_id):
            self.tree.selection_set(task_id)
            self.tree.see(task_id)
