"""主窗口：把任务模型、调度引擎与各个视图组装起来。

界面层只做三件事：接收用户操作、按节拍推进引擎、把状态交给各个视图渲染。
所有调度逻辑都在 `scheduler.py` 与 `engine.py` 里，窗口本身不含任何
"下一个该跑谁"的判断。

关于动画：任务书规定"单步执行统一定义为推进一个模拟时间单位"，所以界面
上的"单步"按钮就是调用一次 `engine.step()`；而"开始"按钮只是按演示速度
连续调用同一个方法。两者推进的是同一个引擎，结果完全一致。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..engine import SimulationEngine, simulate
from ..loader import (DataError, check_quantum, export_result, export_tasks,
                      load_tasks, validate)
from ..models import ScheduleResult, Task
from ..scheduler import ALGORITHM_ORDER, make_scheduler
from . import theme
from .gantt import GanttChart
from .report_panel import ReportPanel
from .task_table import TaskTable

TICK_MS = 55                     # 动画节拍
RR_QUANTA = (1, 2, 4)            # 对比实验里要试的时间片


class SchedulerApp:
    """应用主控制器。"""

    def __init__(self, root: tk.Tk, data_root: Path) -> None:
        self.root = root
        self.data_root = data_root

        self.tasks: list[Task] = []          # 任务定义（不含运行期状态）
        self.engine: SimulationEngine | None = None
        self.algorithm = "fcfs"
        self.quantum = 2
        self.speed = 4
        self.last_result: ScheduleResult | None = None
        self._datasets: dict[str, Path] = {}

        self._job: str | None = None
        self._paused = False

        self._setup_window()
        self._setup_style()
        self._build_ui()
        self._load_datasets()

    # ==================================================================
    # 窗口与样式
    # ==================================================================
    def _setup_window(self) -> None:
        self.root.title("任务调度模拟器 —— FCFS / 优先级调度 / 时间片轮转")
        self.root.geometry("1320x820")
        self.root.minsize(1080, 680)
        self.root.configure(background=theme.BG_WINDOW)
        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0, weight=1)

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(".", background=theme.BG_PANEL, foreground=theme.TEXT,
                        font=theme.FONT_UI, borderwidth=0)
        for name in ("TFrame", "Card.TFrame", "CardBody.TFrame", "Panel.TFrame",
                     "Toolbar.TFrame"):
            style.configure(name, background=theme.BG_PANEL)
        style.configure("Card.TFrame", relief="solid", borderwidth=1,
                        bordercolor=theme.BORDER)

        style.configure("TLabel", background=theme.BG_PANEL, foreground=theme.TEXT)
        style.configure("Dim.TLabel", foreground=theme.TEXT_MUTED, font=theme.FONT_SMALL)
        style.configure("Value.TLabel", foreground=theme.TEXT, font=theme.FONT_SMALL)
        style.configure("Section.TLabel", foreground=theme.ACCENT, font=theme.FONT_SECTION)
        style.configure("Warn.TLabel", foreground=theme.WARNING, font=theme.FONT_SMALL)
        style.configure("Status.TLabel", background=theme.BG_WINDOW,
                        foreground=theme.TEXT_MUTED, font=theme.FONT_SMALL)

        style.configure("TButton", background=theme.BG_INPUT, foreground=theme.TEXT,
                        padding=(9, 4), relief="flat", font=theme.FONT_SMALL)
        style.map("TButton",
                  background=[("active", theme.BORDER), ("disabled", theme.BG_PANEL)],
                  foreground=[("disabled", theme.TEXT_FAINT)])
        style.configure("Accent.TButton", background=theme.ACCENT_DARK,
                        foreground="#ffffff", font=theme.FONT_UI_BOLD)
        style.map("Accent.TButton",
                  background=[("active", theme.ACCENT), ("disabled", theme.BG_INPUT)],
                  foreground=[("disabled", theme.TEXT_FAINT)])

        style.configure("TCombobox", fieldbackground=theme.BG_INPUT,
                        background=theme.BG_INPUT, foreground=theme.TEXT,
                        arrowcolor=theme.TEXT, bordercolor=theme.BORDER,
                        lightcolor=theme.BG_INPUT, darkcolor=theme.BG_INPUT, padding=4)
        style.map("TCombobox",
                  fieldbackground=[("readonly", theme.BG_INPUT)],
                  foreground=[("readonly", theme.TEXT)],
                  selectbackground=[("readonly", theme.BG_INPUT)],
                  selectforeground=[("readonly", theme.TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", theme.BG_INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", theme.TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", theme.ACCENT_DARK)

        for name in ("Task.Treeview", "Compare.Treeview"):
            style.configure(name, background=theme.BG_PANEL,
                            fieldbackground=theme.BG_PANEL, foreground=theme.TEXT,
                            rowheight=22, borderwidth=0, font=theme.FONT_SMALL)
            style.configure(f"{name}.Heading", background=theme.BG_INPUT,
                            foreground=theme.TEXT_MUTED, font=theme.FONT_TINY,
                            relief="flat", padding=3)
            style.map(f"{name}.Heading", background=[("active", theme.BORDER)])
            style.map(name, background=[("selected", theme.BORDER)])
        style.configure("Task.Treeview", rowheight=22)
        # 任务表用 tag 上色，需要让 selected 状态也保留前景色
        style.map("Task.Treeview", foreground=[("selected", theme.TEXT)])

        style.configure("TNotebook", background=theme.BG_PANEL, borderwidth=0)
        style.configure("Panel.TNotebook", background=theme.BG_PANEL, borderwidth=0)
        style.configure("TNotebook.Tab", background=theme.BG_INPUT,
                        foreground=theme.TEXT_MUTED, padding=(12, 5),
                        font=theme.FONT_SMALL)
        style.map("TNotebook.Tab",
                  background=[("selected", theme.BG_PANEL)],
                  foreground=[("selected", theme.ACCENT)])
        style.configure("TSeparator", background=theme.BORDER)
        style.configure("TScale", background=theme.BG_PANEL, troughcolor=theme.BG_INPUT)

    # ==================================================================
    # 界面搭建
    # ==================================================================
    def _build_ui(self) -> None:
        self._build_toolbar()

        body = ttk.Frame(self.root, style="TFrame")
        body.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))
        body.rowconfigure(0, weight=3)
        body.rowconfigure(1, weight=2)
        body.columnconfigure(0, weight=1)

        # 左上：任务列表
        table_card = ttk.Frame(body, style="Card.TFrame", padding=(10, 8))
        table_card.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        table_card.rowconfigure(1, weight=1)
        table_card.columnconfigure(0, weight=1)
        ttk.Label(table_card, text="任务列表", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 5))
        # 接上选中回调：否则「修改」按钮永远不会因为选中某一行而启用
        self.table = TaskTable(table_card, on_select=lambda _tid: self._update_edit_buttons())
        self.table.grid(row=1, column=0, sticky="nsew")

        # 左下：甘特图
        gantt_card = ttk.Frame(body, style="Card.TFrame", padding=(10, 8))
        gantt_card.grid(row=1, column=0, sticky="nsew")
        gantt_card.rowconfigure(1, weight=1)
        gantt_card.columnconfigure(0, weight=1)
        ttk.Label(gantt_card, text="甘特图", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 5))
        self.gantt = GanttChart(gantt_card)
        self.gantt.grid(row=1, column=0, sticky="nsew")

        # 右：状态与结果
        self.panel = ReportPanel(body, on_pick_task=self._focus_task)
        self.panel.grid(row=0, column=1, rowspan=2, sticky="ns", padx=(8, 0))
        self.panel.configure(width=396)
        self.panel.grid_propagate(False)

        self.status = ttk.Label(self.root, text="就绪", style="Status.TLabel",
                                anchor="w", padding=(12, 4))
        self.status.grid(row=3, column=0, sticky="ew")

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(10, 8, 10, 2))
        bar.grid(row=0, column=0, sticky="ew")

        def label(text: str) -> None:
            ttk.Label(bar, text=text, style="Dim.TLabel").pack(side="left", padx=(6, 3))

        label("数据集")
        self.dataset_var = tk.StringVar()
        self.dataset_box = ttk.Combobox(bar, textvariable=self.dataset_var,
                                        state="readonly", width=24)
        self.dataset_box.pack(side="left")
        self.dataset_box.bind("<<ComboboxSelected>>", lambda e: self._load_dataset())

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)

        label("算法")
        self.algo_var = tk.StringVar()
        self.algo_box = ttk.Combobox(bar, textvariable=self.algo_var,
                                     state="readonly", width=12)
        self.algo_box.pack(side="left")
        self.algo_box.bind("<<ComboboxSelected>>", lambda e: self._on_algorithm_change())

        label("时间片 q")
        self.quantum_var = tk.StringVar(value=str(self.quantum))
        self.quantum_box = ttk.Combobox(bar, textvariable=self.quantum_var,
                                        state="readonly", width=4,
                                        values=["1", "2", "3", "4", "5", "8", "10"])
        self.quantum_box.pack(side="left")
        self.quantum_box.bind("<<ComboboxSelected>>", lambda e: self._on_quantum_change())

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)

        label("速度")
        self.speed_scale = ttk.Scale(bar, from_=1, to=20, orient="horizontal",
                                     length=130, command=self._on_speed)
        self.speed_scale.set(self.speed)
        self.speed_scale.pack(side="left")

        # ---------------- 第二行：操作 ----------------
        bar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(10, 0, 10, 8))
        bar.grid(row=1, column=0, sticky="ew")

        self.run_button = ttk.Button(bar, text="开始", style="Accent.TButton",
                                     command=self._start_or_resume)
        self.run_button.pack(side="left", padx=(0, 4))
        self.pause_button = ttk.Button(bar, text="暂停", command=self._pause,
                                       state="disabled")
        self.pause_button.pack(side="left", padx=(0, 4))
        self.step_button = ttk.Button(bar, text="单步", command=self._single_step)
        self.step_button.pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="重置", command=self._reset).pack(side="left", padx=(0, 14))

        self.add_button = ttk.Button(bar, text="＋ 添加任务",
                                     command=lambda: self._edit_task(None))
        self.add_button.pack(side="left", padx=(0, 4))
        self.modify_button = ttk.Button(bar, text="修改", command=self._modify_selected,
                                        state="disabled")
        self.modify_button.pack(side="left", padx=(0, 4))
        self.remove_button = ttk.Button(bar, text="删除", command=self._remove_selected,
                                        state="disabled")
        self.remove_button.pack(side="left", padx=(0, 14))

        ttk.Button(bar, text="导入数据…", command=self._import_tasks).pack(
            side="left", padx=(0, 4))
        ttk.Button(bar, text="另存任务…", command=self._export_tasks).pack(
            side="left", padx=(0, 4))
        ttk.Button(bar, text="导出结果…", command=self._export_result).pack(
            side="left", padx=(0, 4))
        ttk.Button(bar, text="对比三种算法", command=self._compare).pack(
            side="left", padx=(0, 4))
        ttk.Button(bar, text="清空", command=self._clear_tasks).pack(side="left")

        self.algo_box.configure(values=[self._algorithm_label(k) for k in ALGORITHM_ORDER])
        self.algo_var.set(self._algorithm_label(self.algorithm))
        # 初始算法不是 RR 时时间片应当直接禁用；否则用户会在 FCFS 下改时间片，
        # 触发一次对结果毫无影响的引擎重置
        self.quantum_box.configure(
            state="readonly" if self.algorithm == "rr" else "disabled")

    @staticmethod
    def _algorithm_label(key: str) -> str:
        return {"fcfs": "FCFS", "priority": "优先级调度", "rr": "时间片轮转"}[key]

    @staticmethod
    def _algorithm_key(label: str) -> str:
        return {"FCFS": "fcfs", "优先级调度": "priority", "时间片轮转": "rr"}.get(label, "fcfs")

    # ==================================================================
    # 数据
    # ==================================================================
    def _load_datasets(self) -> None:
        candidates = sorted(list(self.data_root.glob("*.csv")) +
                            list(self.data_root.glob("*.json")))
        for path in candidates:
            try:
                tasks = load_tasks(path)
            except DataError as exc:
                self.status.configure(text=f"跳过 {path.name}：{exc}")
                continue
            # 下拉框里带上扩展名：同一份数据常常同时有 .csv 与 .json 两个版本，
            # 只用文件名的话两个条目会重名，后读到的会把先读到的覆盖掉
            self._datasets[f"{path.name}（{len(tasks)} 个任务）"] = path

        if not self._datasets:
            messagebox.showerror("数据缺失", f"在 {self.data_root} 下没有找到可用的任务数据")
            return

        self.dataset_box.configure(values=list(self._datasets))
        # 默认载入任务书给的示例数据
        preferred = next((k for k in self._datasets if k.startswith("sample.csv")), None)
        self.dataset_box.set(preferred or next(iter(self._datasets)))
        self._load_dataset()

    def _load_dataset(self) -> None:
        path = self._datasets.get(self.dataset_var.get())
        if path is None:
            return
        try:
            self.tasks = load_tasks(path)
        except DataError as exc:
            messagebox.showerror("加载失败", str(exc))
            return
        self._stop_animation()
        self._reset_engine()
        self.status.configure(
            text=f"已载入 {path.name}：{len(self.tasks)} 个任务，"
                 f"总运行时长 {sum(t.burst_time for t in self.tasks)} 个单位")

    def _refresh_task_views(self) -> None:
        """任务定义变了之后重建表格与甘特图。"""
        self.table.set_tasks(self.tasks)
        self.gantt.set_tasks(self.tasks)
        self.panel.clear_result()
        self.panel.clear_comparison()
        self.last_result = None
        self._update_edit_buttons()

    def _update_edit_buttons(self) -> None:
        """只有"模拟开始前或重置后"才允许改任务数据。"""
        editable = "normal" if self._can_edit() else "disabled"
        self.add_button.configure(state=editable)
        self.remove_button.configure(state=editable)
        self.modify_button.configure(
            state=editable if self.table.selected_task_id() else "disabled")

    def _can_edit(self) -> bool:
        if self._job is not None or self._paused:
            return False
        if self.engine is None:
            return True
        return self.engine.now == 0        # 重置之后、还没开始推进

    # ==================================================================
    # 参数变化
    # ==================================================================
    def _on_algorithm_change(self) -> None:
        self.algorithm = self._algorithm_key(self.algo_var.get())
        self.quantum_box.configure(
            state="readonly" if self.algorithm == "rr" else "disabled")
        self._stop_animation()
        self._reset_engine()
        self.status.configure(text=self._describe_algorithm())

    def _on_quantum_change(self) -> None:
        try:
            self.quantum = check_quantum(self.quantum_var.get())
        except DataError as exc:
            messagebox.showwarning("时间片不合法", str(exc))
            self.quantum_var.set(str(self.quantum))
            return
        self._stop_animation()
        self._reset_engine()
        self.status.configure(text=self._describe_algorithm())

    def _describe_algorithm(self) -> str:
        if self.algorithm == "fcfs":
            return "FCFS：按到达顺序排队，后到达的任务不能插队，一旦开始就运行到完成"
        if self.algorithm == "priority":
            return "非抢占式优先级调度：每次从就绪任务中选优先级最高者（数值越小越高）"
        return f"时间片轮转：每个任务最多连续运行 {self.quantum} 个单位，未完成则回到队尾"

    def _on_speed(self, value: str) -> None:
        self.speed = max(1, int(float(value)))

    # ==================================================================
    # 引擎与动画
    # ==================================================================
    def _reset_engine(self) -> None:
        """把引擎恢复到 t=0（任务定义不变）。"""
        self._stop_animation()
        instances = [task.clone() for task in self.tasks]
        scheduler = make_scheduler(self.algorithm, self.quantum)
        self.engine = SimulationEngine(instances, scheduler)
        self.gantt.set_tasks(self.tasks)
        self.table.set_tasks(self.tasks)
        # 上次的结果与对比表都必须一起清掉：换了算法、改了时间片、换过数据集
        # 之后，旧结果已经不对应当前的选择，留着会误导，也会让「导出结果」
        # 写出上一轮的数据
        self.last_result = None
        self.panel.clear_result()
        self.panel.clear_comparison()
        self._refresh_views()
        self._reset_buttons()

    def _refresh_views(self) -> None:
        if self.engine is None:
            return
        self.panel.show_state(self.engine.snapshot())
        self.table.refresh(self.engine.tasks)
        self.gantt.update_timeline(self.engine.timeline, self.engine.now)

    def _start_or_resume(self) -> None:
        if self.engine is None or self.engine.finished:
            self._reset_engine()
        if self._job is not None:
            return
        self._paused = False
        self.run_button.configure(text="运行中…", state="disabled")
        self.pause_button.configure(state="normal")
        self.step_button.configure(state="disabled")
        self._tick()                        # 先让动画跑起来（此时才设上 _job）
        self._update_edit_buttons()         # 再按"正在运行"的状态刷新编辑按钮

    def _tick(self) -> None:
        if self.engine is None:
            return
        for _ in range(self.speed):
            if not self.engine.step():
                self._finish()
                return
        self._refresh_views()
        self._job = self.root.after(TICK_MS, self._tick)

    def _pause(self) -> None:
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None
            self._paused = True
            self.run_button.configure(text="继续", state="normal")
            self.pause_button.configure(state="disabled")
            self.step_button.configure(state="normal")
            self._update_edit_buttons()
            self.status.configure(text=f"已暂停在 t = {self.engine.now}")

    def _single_step(self) -> None:
        """推进一个模拟时间单位 —— 这正是任务书对"单步执行"的定义。"""
        if self.engine is None or self.engine.finished:
            return
        if self._job is not None:
            self._pause()
        self.engine.step()
        self._refresh_views()
        if self.engine.finished:
            self._finish()
        else:
            self._update_edit_buttons()     # 已经推进过时间，不能再改任务数据了
            self.status.configure(text=f"单步：t = {self.engine.now}")

    def _finish(self) -> None:
        self._job = None
        self._paused = False
        self._refresh_views()
        self.last_result = self.engine.result(self._describe_algorithm())
        self.panel.show_result(self.last_result)
        self._reset_buttons()
        result = self.last_result
        self.status.configure(
            text=f"完成：{len(result.tasks)} 个任务全部结束于 t = {result.makespan}，"
                 f"平均周转 {result.avg_turnaround:.2f}、等待 {result.avg_waiting:.2f}、"
                 f"响应 {result.avg_response:.2f}；换人 {result.context_switches} 次")

    def _stop_animation(self) -> None:
        """中止动画并把按钮恢复成可再次开始的状态。

        按钮的重置必须放在这里：切换算法、改时间片、换数据集、开始对比
        等操作都会经由这个方法停下来，如果只在 _finish() 里恢复按钮，
        动画进行中做上述任何一件事都会让「开始」永远停在禁用状态。
        """
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None
        self._paused = False
        self._reset_buttons()

    def _reset(self) -> None:
        self._reset_engine()
        self.status.configure(text="已重置到 t = 0")

    def _reset_buttons(self) -> None:
        self.run_button.configure(text="开始", state="normal")
        self.pause_button.configure(state="disabled")
        self.step_button.configure(state="normal")
        self._update_edit_buttons()

    # ==================================================================
    # 任务编辑
    # ==================================================================
    def _focus_task(self, task_id: str) -> None:
        self.table.focus_task(task_id)

    def _modify_selected(self) -> None:
        task_id = self.table.selected_task_id()
        if task_id:
            self._edit_task(task_id)

    def _remove_selected(self) -> None:
        task_id = self.table.selected_task_id()
        if not task_id:
            return
        task = next((t for t in self.tasks if t.task_id == task_id), None)
        if task is None:
            return
        if not messagebox.askyesno("删除任务",
                                   f"确定要删除任务「{task.task_id} {task.name}」吗？",
                                   parent=self.root):
            return
        self.tasks = [t for t in self.tasks if t.task_id != task_id]
        for index, item in enumerate(self.tasks):
            item.seq = index
        self._stop_animation()
        self._reset_engine()
        self.status.configure(text=f"已删除任务「{task.task_id}」")

    def _clear_tasks(self) -> None:
        if not self.tasks:
            return
        if not messagebox.askyesno("清空任务", "确定要清空全部任务吗？", parent=self.root):
            return
        self.tasks = []
        self._stop_animation()
        self._reset_engine()
        self.status.configure(text="任务列表已清空")

    def _edit_task(self, task_id: str | None) -> None:
        """添加（task_id=None）或修改一个任务。"""
        if not self._can_edit():
            messagebox.showinfo("暂时不能修改",
                                "任务数据只能在模拟开始前或重置之后修改。", parent=self.root)
            return

        editing = task_id is not None
        current = next((t for t in self.tasks if t.task_id == task_id), None)

        dialog = tk.Toplevel(self.root)
        dialog.title("修改任务" if editing else "添加任务")
        dialog.configure(background=theme.BG_PANEL)
        dialog.transient(self.root)
        dialog.resizable(False, False)

        body = ttk.Frame(dialog, style="TFrame", padding=(16, 14))
        body.pack(fill="both", expand=True)

        defaults = {
            "task_id": current.task_id if current else f"T{len(self.tasks) + 1}",
            "name": current.name if current else f"任务{len(self.tasks) + 1}",
            "arrival_time": str(current.arrival_time) if current else "0",
            "burst_time": str(current.burst_time) if current else "3",
            "priority": str(current.priority) if current else "1",
        }
        specs = [
            ("task_id", "任务编号", "唯一，不允许重复"),
            ("name", "任务名称", "非空"),
            ("arrival_time", "到达时间", "非负整数"),
            ("burst_time", "运行时长", "正整数"),
            ("priority", "优先级", "非负整数，数值越小优先级越高"),
        ]
        fields: dict[str, tk.StringVar] = {}
        for row, (key, label, hint) in enumerate(specs):
            ttk.Label(body, text=label, style="Dim.TLabel").grid(
                row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=defaults[key])
            ttk.Entry(body, textvariable=var, width=20).grid(
                row=row, column=1, sticky="ew", padx=(12, 8), pady=4)
            ttk.Label(body, text=hint, style="Dim.TLabel").grid(
                row=row, column=2, sticky="w")
            fields[key] = var

        def confirm() -> None:
            payload = {key: var.get() for key, var in fields.items()}
            others = [t for t in self.tasks if t.task_id != task_id]
            if any(t.task_id == payload["task_id"].strip() for t in others):
                messagebox.showwarning("编号重复",
                                       f"任务编号「{payload['task_id']}」已被占用。",
                                       parent=dialog)
                return
            try:
                tasks = validate([payload])
            except DataError as exc:
                messagebox.showwarning("数据不合法", str(exc), parent=dialog)
                return

            task = tasks[0]
            if editing:
                task.seq = current.seq
                self.tasks = [task if t.task_id == task_id else t for t in self.tasks]
            else:
                task.seq = len(self.tasks)
                self.tasks = self.tasks + [task]
            dialog.destroy()
            self._refresh_task_views()
            self._reset_engine()
            self.status.configure(
                text=f"已{'修改' if editing else '添加'}任务「{task.task_id} {task.name}」："
                     f"到达 {task.arrival_time}，时长 {task.burst_time}，"
                     f"优先级 {task.priority}")

        buttons = ttk.Frame(body, style="TFrame")
        buttons.grid(row=len(specs), column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="确定", style="Accent.TButton", command=confirm).pack(
            side="left", padx=(0, 6))
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left")

        dialog.bind("<Return>", lambda e: confirm())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 3
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dialog.grab_set()

    # ==================================================================
    # 导入导出
    # ==================================================================
    def _import_tasks(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, title="导入任务数据",
            filetypes=[("任务数据", "*.csv *.json"), ("CSV", "*.csv"),
                       ("JSON", "*.json"), ("全部文件", "*.*")])
        if not path:
            return
        try:
            tasks = load_tasks(path)
        except DataError as exc:
            messagebox.showerror("导入失败", str(exc), parent=self.root)
            return
        self.tasks = tasks
        self._stop_animation()
        self._refresh_task_views()
        self._reset_engine()
        self.status.configure(text=f"已从 {Path(path).name} 导入 {len(tasks)} 个任务")

    def _export_tasks(self) -> None:
        """把当前任务表另存为 CSV（在界面上改完任务后可以留存下来）。"""
        if not self.tasks:
            messagebox.showinfo("没有任务", "任务列表是空的。", parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="另存任务数据", defaultextension=".csv",
            initialfile="任务数据.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            export_tasks(self.tasks, path)
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.root)
            return
        self.status.configure(text=f"任务已保存到 {path}")

    def _export_result(self) -> None:
        if self.last_result is None:
            messagebox.showinfo(
                "还没有结果",
                "请先用当前算法完整运行一次模拟。\n\n"
                "「对比三种算法」给出的是多种算法的汇总指标，"
                "不含每个任务的明细，所以不能代替这里要导出的结果。",
                parent=self.root)
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="导出调度结果", defaultextension=".csv",
            initialfile=f"调度结果_{self.last_result.algorithm}.csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            export_result(self.last_result, path)
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc), parent=self.root)
            return
        self.status.configure(text=f"结果已导出到 {path}")

    # ==================================================================
    # 算法对比
    # ==================================================================
    def _compare(self) -> None:
        if not self.tasks:
            messagebox.showinfo("没有任务", "请先添加或导入任务。", parent=self.root)
            return
        self._stop_animation()

        rows: list[dict] = []
        results: list[ScheduleResult] = []
        for key in ALGORITHM_ORDER:
            if key == "rr":
                # 任务书要求比较 RR 在不同时间片下的表现
                for quantum in RR_QUANTA:
                    result = simulate(self.tasks, key, quantum)
                    rows.append(self._comparison_row(result, f"RR q={quantum}"))
                    results.append(result)
            else:
                result = simulate(self.tasks, key)
                rows.append(self._comparison_row(result, result.algorithm))
                results.append(result)

        best = min(range(len(rows)), key=lambda i: rows[i]["turnaround"])
        rows[best]["best"] = True
        # 连同每个算法的完整结果一起交给面板：选中对比表的一行就能看到它的甘特图
        self.panel.show_comparison(rows, results)
        self.panel.show_tab("comparison")

        winner = rows[best]
        self.status.configure(
            text=f"对比完成：平均周转最短的是 {winner['algo']}"
                 f"（{winner['turnaround']:.2f}）；"
                 f"平均响应最快的是 {min(rows, key=lambda r: r['response'])['algo']}；"
                 f"换人次数最少的是 {min(rows, key=lambda r: r['switches'])['algo']}")

    @staticmethod
    def _comparison_row(result: ScheduleResult, label: str) -> dict:
        return {
            "algo": label,
            "quantum": result.quantum if result.quantum else None,
            "turnaround": result.avg_turnaround,
            "waiting": result.avg_waiting,
            "response": result.avg_response,
            "switches": result.context_switches,
            "idle": result.idle_units,
        }
