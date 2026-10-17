"""右侧信息面板：当前状态、统计结果、算法对比。

三块内容自上而下排列：

1. **当前状态** —— 模拟时间、正在运行的任务、就绪队列、完成进度。
   任务书要求界面必须展示这三项（§3.2 第 3 条）。
2. **统计结果** —— 平均周转 / 等待 / 响应时间，以及每个任务的明细。
3. **算法对比** —— 同一组任务在三种算法（以及不同时间片）下的横向比较。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..models import ScheduleResult
from . import theme
from .gantt import GanttChart


class _Card(ttk.Frame):
    """带标题的卡片容器。"""

    def __init__(self, master: tk.Misc, title: str) -> None:
        super().__init__(master, style="Card.TFrame", padding=(12, 9))
        ttk.Label(self, text=title, style="Section.TLabel").pack(anchor="w")
        self.body = ttk.Frame(self, style="CardBody.TFrame")
        self.body.pack(fill="both", expand=True, pady=(5, 0))


class ReportPanel(ttk.Frame):
    """状态与结果面板。"""

    def __init__(self, master: tk.Misc, on_pick_task=None) -> None:
        super().__init__(master, style="Panel.TFrame", padding=(10, 10))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=2)

        self._on_pick_task = on_pick_task
        self._build_state()
        self._build_notebook()

    # ------------------------------------------------------------------
    def _build_state(self) -> None:
        card = _Card(self, "当前状态")
        card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        card.body.columnconfigure(1, weight=1)

        self._state_labels: dict[str, ttk.Label] = {}
        rows = [("now", "模拟时间"), ("running", "正在运行"),
                ("ready", "就绪队列"), ("progress", "完成进度")]
        for index, (key, label) in enumerate(rows):
            ttk.Label(card.body, text=label, style="Dim.TLabel").grid(
                row=index, column=0, sticky="w", pady=1)
            value = ttk.Label(card.body, text="—", style="Value.TLabel",
                              anchor="w", justify="left")
            value.grid(row=index, column=1, sticky="ew", padx=(10, 0), pady=1)
            self._state_labels[key] = value

        self._state_labels["running"].configure(foreground=theme.SUCCESS)
        self._state_labels["ready"].configure(foreground=theme.ACCENT)

    def _build_notebook(self) -> None:
        self.notebook = ttk.Notebook(self, style="Panel.TNotebook")
        self.notebook.grid(row=1, column=0, rowspan=2, sticky="nsew")
        self._build_detail(self.notebook)
        self._build_comparison(self.notebook)

    def _build_detail(self, parent: ttk.Notebook) -> None:
        page = ttk.Frame(parent, style="Panel.TFrame", padding=(0, 6))
        parent.add(page, text="本次结果")
        page.rowconfigure(1, weight=1)
        page.columnconfigure(0, weight=1)

        # 汇总
        summary = _Card(page, "平均指标")
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        summary.body.columnconfigure(1, weight=1)
        summary.body.columnconfigure(3, weight=1)

        self._summary: dict[str, ttk.Label] = {}
        specs = [("turnaround", "平均周转"), ("waiting", "平均等待"),
                 ("response", "平均响应"), ("switches", "换人次数"),
                 ("idle", "空闲时长"), ("makespan", "总时长")]
        for index, (key, label) in enumerate(specs):
            row, col = divmod(index, 2)
            ttk.Label(summary.body, text=label, style="Dim.TLabel").grid(
                row=row, column=col * 2, sticky="w", pady=1)
            value = ttk.Label(summary.body, text="—", style="Value.TLabel")
            value.grid(row=row, column=col * 2 + 1, sticky="e", padx=(6, 14), pady=1)
            self._summary[key] = value

        # 明细表
        card = _Card(page, "每个任务的统计")
        card.grid(row=1, column=0, sticky="nsew")
        card.body.rowconfigure(0, weight=1)
        card.body.columnconfigure(0, weight=1)

        columns = ("task", "start", "finish", "turn", "wait", "resp")
        self._detail = ttk.Treeview(card.body, columns=columns, show="headings",
                                    height=6, style="Compare.Treeview")
        for key, title, width in (("task", "任务", 76), ("start", "开始", 48),
                                  ("finish", "完成", 48), ("turn", "周转", 48),
                                  ("wait", "等待", 48), ("resp", "响应", 48)):
            self._detail.heading(key, text=title)
            self._detail.column(key, width=width, anchor="center", stretch=True)
        self._detail.grid(row=0, column=0, sticky="nsew")
        if self._on_pick_task:
            self._detail.bind("<<TreeviewSelect>>", self._pick_task)

    def _build_comparison(self, parent: ttk.Notebook) -> None:
        page = ttk.Frame(parent, style="Panel.TFrame", padding=(0, 6))
        parent.add(page, text="算法对比")
        page.rowconfigure(1, weight=3)
        page.rowconfigure(2, weight=2)
        page.columnconfigure(0, weight=1)

        ttk.Label(page, text="同一组任务在各算法下的表现；选中某一行可看它的甘特图",
                  style="Dim.TLabel", wraplength=330).grid(
            row=0, column=0, sticky="w", pady=(0, 6))

        card = _Card(page, "对比表")
        card.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
        card.body.rowconfigure(0, weight=1)
        card.body.columnconfigure(0, weight=1)

        # 时间片不再单列一列 —— 算法名里已经写成 "RR q=1" 了
        columns = ("algo", "turn", "wait", "resp", "switch", "idle")
        self._compare = ttk.Treeview(card.body, columns=columns, show="headings",
                                     height=10, style="Compare.Treeview")
        headings = {
            "algo": ("算法", 78), "turn": ("平均周转", 60), "wait": ("平均等待", 60),
            "resp": ("平均响应", 60), "switch": ("换人", 44), "idle": ("空闲", 44),
        }
        for key, (title, width) in headings.items():
            self._compare.heading(key, text=title)
            self._compare.column(key, width=width, minwidth=40, anchor="center",
                                 stretch=True)
        self._compare.grid(row=0, column=0, sticky="nsew")
        self._compare.tag_configure("best", foreground=theme.SUCCESS)
        self._compare.bind("<<TreeviewSelect>>", self._show_comparison_gantt)

        # 对比表下方：选中哪一行，就展示那个算法的甘特图
        preview = _Card(page, "所选算法的甘特图")
        preview.grid(row=2, column=0, sticky="nsew")
        preview.body.rowconfigure(0, weight=1)
        preview.body.columnconfigure(0, weight=1)
        self._preview = GanttChart(preview.body)
        self._preview.grid(row=0, column=0, sticky="nsew")
        self._comparison_results: list[ScheduleResult] = []

    # ==================================================================
    # 对外接口
    # ==================================================================
    def show_state(self, snapshot: dict) -> None:
        """刷新"当前状态"卡片。动画每一步都会调用。"""
        running = snapshot.get("running")
        ready = snapshot.get("ready") or []
        names = "、".join(task.task_id for task in ready[:6])
        if len(ready) > 6:
            names += f" …（共 {len(ready)} 个）"

        self._state_labels["now"].configure(text=f"t = {snapshot.get('now', 0)}")
        self._state_labels["running"].configure(
            text=f"{running.task_id}  {running.name}" if running else "空闲")
        self._state_labels["ready"].configure(text=names or "（空）")
        self._state_labels["progress"].configure(
            text=f"{snapshot.get('finished', 0)} / {snapshot.get('total', 0)}")

    def show_result(self, result: ScheduleResult | None) -> None:
        """用一次完整模拟的结果填充统计区。"""
        self._detail.delete(*self._detail.get_children())
        if result is None:
            for label in self._summary.values():
                label.configure(text="—")
            return

        self._summary["turnaround"].configure(text=f"{result.avg_turnaround:.2f}")
        self._summary["waiting"].configure(text=f"{result.avg_waiting:.2f}")
        self._summary["response"].configure(text=f"{result.avg_response:.2f}")
        self._summary["switches"].configure(text=str(result.context_switches))
        self._summary["idle"].configure(text=str(result.idle_units))
        self._summary["makespan"].configure(text=str(result.makespan))

        for row in result.rows():
            self._detail.insert("", "end", iid=row["task_id"], values=(
                row["task_id"],
                row["start_time"] if row["start_time"] is not None else "—",
                row["finish_time"] if row["finish_time"] is not None else "—",
                row["turnaround_time"] if row["turnaround_time"] is not None else "—",
                row["waiting_time"] if row["waiting_time"] is not None else "—",
                row["response_time"] if row["response_time"] is not None else "—",
            ))

    def show_comparison(self, rows: list[dict],
                        results: list[ScheduleResult] | None = None) -> None:
        """填充算法对比表，并准备好每行对应的甘特图。

        每行形如 {'algo','turnaround','waiting','response','switches','idle','best'}；
        ``results`` 与 ``rows`` 一一对应，选中某一行时用它来渲染甘特图 ——
        任务书要求算法对比要同时展示"统计指标与甘特图"。
        """
        self._compare.delete(*self._compare.get_children())
        self._comparison_results = list(results or [])

        for index, row in enumerate(rows):
            self._compare.insert("", "end", iid=str(index), values=(
                row["algo"],
                f"{row['turnaround']:.2f}",
                f"{row['waiting']:.2f}",
                f"{row['response']:.2f}",
                row["switches"],
                row["idle"],
            ), tags=("best",) if row.get("best") else ())

        children = self._compare.get_children()
        if children:
            self._compare.selection_set(children[0])
            self._show_comparison_gantt()

    def _show_comparison_gantt(self, _event=None) -> None:
        """把对比表里选中的那一行渲染成甘特图。"""
        selection = self._compare.selection()
        if not selection:
            return
        try:
            index = int(selection[0])
        except ValueError:
            return
        if not (0 <= index < len(self._comparison_results)):
            return
        result = self._comparison_results[index]
        self._preview.set_tasks(result.tasks)
        self._preview.update_timeline(result.timeline, result.makespan)

    def clear_result(self) -> None:
        self._detail.delete(*self._detail.get_children())
        for label in self._summary.values():
            label.configure(text="—")

    def clear_comparison(self) -> None:
        self._compare.delete(*self._compare.get_children())

    def show_tab(self, name: str) -> None:
        self.notebook.select(0 if name == "detail" else 1)

    def _pick_task(self, _event=None) -> None:
        selection = self._detail.selection()
        if selection and self._on_pick_task:
            self._on_pick_task(selection[0])
