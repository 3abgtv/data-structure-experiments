"""任务列表控件。

以表格形式展示任务的属性和当前状态（任务书 §3.2 第 1 条的要求），
并提供添加 / 修改 / 删除的入口。表格本身不校验数据，校验由调用方
（`app.py` 里的对话框与 `loader.validate`）负责。

动画进行中每推进一个时间单位就会刷新一次，所以这里只做**原地更新**
（`item(iid, values=...)`），不重建整张表 —— 否则每次刷新都会闪一下。
"""

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
            # 所有列都参与拉伸：只让某一列拉伸的话，它会把后面的列远远推开，
            # 表格看起来就像错位了
            self.tree.column(key, width=width, minwidth=50, anchor=anchor, stretch=True)

        self.tree.tag_configure("running", background="#1f3b2a", foreground=theme.SUCCESS)
        self.tree.tag_configure("ready", background="#1b2a3d", foreground=theme.TEXT)
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
        """原地刷新剩余时长与状态（动画每一步都会调用）。

        注意 tags 是**整组替换**的，所以这里要把斑马纹的 odd 标签重新拼上，
        否则 set_tasks 铺好的隔行底色会在第一次刷新时全部丢掉。
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
        """把某一任务选中（用于在统计表里点一行就跳到任务表）。"""
        if task_id and self.tree.exists(task_id):
            self.tree.selection_set(task_id)
            self.tree.see(task_id)
