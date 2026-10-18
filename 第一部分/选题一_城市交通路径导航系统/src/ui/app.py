"""主窗口：把图、求解器与各个视图组装起来，并负责搜索动画的调度。

界面层在这里只做三件事：转发用户的输入、按节拍消费求解器产出的事件、
把结果交给画布和面板渲染。所有算法逻辑都在 solver 里，窗口本身
不含任何最短路径计算 —— 这正是任务书要求的模块划分。

关于动画：搜索本身是瞬间完成的，"慢慢变色的过程"只是把求解器逐条
yield 出来的事件按时间铺开。因此演示速度只影响观感，不影响任何
调度结果或统计数字。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..graph import Graph
from ..loader import DEFAULT_COLORS, DataError, load_graph
from ..models import Line
from ..solver import ALGORITHM_ORDER, SOLVERS
from . import theme
from .canvas_view import NetworkView
from .control_panel import ResultPanel

TICK_MS = 24          # 动画节拍


class NavigationApp:
    """应用主控制器。"""

    def __init__(self, root: tk.Tk, data_root: Path) -> None:
        self.root = root
        self.data_root = data_root

        self.graph: Graph | None = None
        self.source: str | None = None
        self.target: str | None = None
        self.algorithm_key = "dijkstra"

        self._name_to_id: dict[str, str] = {}
        self._datasets: dict[str, Path] = {}

        self._events = None
        self._job: str | None = None
        self._paused = False
        self._speed = 6

        self._setup_window()
        self._setup_style()
        self._build_ui()
        self._load_datasets()

    # ==================================================================
    # 窗口与样式
    # ==================================================================
    def _setup_window(self) -> None:
        self.root.title("城市交通路径导航系统 —— Dijkstra / A* / 最少换乘 BFS")
        self.root.geometry("1240x780")
        self.root.minsize(1000, 640)
        self.root.configure(background=theme.BG_WINDOW)
        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0, weight=1)

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(".", background=theme.BG_PANEL, foreground=theme.TEXT,
                        font=theme.FONT_UI, borderwidth=0)
        style.configure("TFrame", background=theme.BG_PANEL)
        style.configure("Card.TFrame", background=theme.BG_PANEL, relief="solid",
                        borderwidth=1, bordercolor=theme.BORDER)
        style.configure("CardBody.TFrame", background=theme.BG_PANEL)
        style.configure("Panel.TFrame", background=theme.BG_PANEL)
        style.configure("Toolbar.TFrame", background=theme.BG_PANEL)

        style.configure("TLabel", background=theme.BG_PANEL, foreground=theme.TEXT)
        style.configure("Dim.TLabel", foreground=theme.TEXT_MUTED, font=theme.FONT_SMALL)
        style.configure("Value.TLabel", foreground=theme.TEXT, font=theme.FONT_SMALL)
        style.configure("Section.TLabel", foreground=theme.ACCENT, font=theme.FONT_SECTION)
        style.configure("Title.TLabel", foreground=theme.TEXT, font=theme.FONT_TITLE)
        style.configure("Warn.TLabel", foreground=theme.WARNING, font=theme.FONT_SMALL)
        style.configure("Status.TLabel", background=theme.BG_WINDOW,
                        foreground=theme.TEXT_MUTED, font=theme.FONT_SMALL)

        style.configure("TButton", background=theme.BG_INPUT, foreground=theme.TEXT,
                        padding=(10, 5), relief="flat", font=theme.FONT_SMALL)
        style.map("TButton",
                  background=[("active", theme.BORDER), ("disabled", theme.BG_PANEL)],
                  foreground=[("disabled", theme.TEXT_FAINT)])
        style.configure("Accent.TButton", background=theme.ACCENT_DARK,
                        foreground="#ffffff", font=theme.FONT_UI_BOLD)
        style.map("Accent.TButton",
                  background=[("active", theme.ACCENT), ("disabled", theme.BG_INPUT)],
                  foreground=[("disabled", theme.TEXT_FAINT)])

        style.configure("TCombobox",
                        fieldbackground=theme.BG_INPUT, background=theme.BG_INPUT,
                        foreground=theme.TEXT, arrowcolor=theme.TEXT,
                        bordercolor=theme.BORDER, lightcolor=theme.BG_INPUT,
                        darkcolor=theme.BG_INPUT, padding=4)
        style.map("TCombobox",
                  fieldbackground=[("readonly", theme.BG_INPUT)],
                  foreground=[("readonly", theme.TEXT)],
                  selectbackground=[("readonly", theme.BG_INPUT)],
                  selectforeground=[("readonly", theme.TEXT)])
        self.root.option_add("*TCombobox*Listbox.background", theme.BG_INPUT)
        self.root.option_add("*TCombobox*Listbox.foreground", theme.TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", theme.ACCENT_DARK)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        style.configure("Compare.Treeview",
                        background=theme.BG_PANEL, fieldbackground=theme.BG_PANEL,
                        foreground=theme.TEXT, rowheight=23, borderwidth=0,
                        font=theme.FONT_SMALL)
        style.configure("Compare.Treeview.Heading",
                        background=theme.BG_INPUT, foreground=theme.TEXT_MUTED,
                        font=theme.FONT_TINY, relief="flat", padding=3)
        style.map("Compare.Treeview.Heading", background=[("active", theme.BORDER)])
        style.map("Compare.Treeview", background=[("selected", theme.BORDER)])

        style.configure("TScale", background=theme.BG_PANEL, troughcolor=theme.BG_INPUT)
        style.configure("Horizontal.TSeparator", background=theme.BORDER)

    # ==================================================================
    # 界面搭建
    # ==================================================================
    def _build_ui(self) -> None:
        self._build_toolbar()

        body = ttk.Frame(self.root, style="TFrame")
        body.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self.view = NetworkView(body, width=820, height=620)
        self.view.grid(row=0, column=0, sticky="nsew")
        self.view.on_pick = self._on_canvas_pick
        self.view.on_context = self._on_canvas_context

        self.panel = ResultPanel(body)
        self.panel.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.panel.configure(width=372)
        self.panel.grid_propagate(False)

        self.status = ttk.Label(self.root, text=SOLVERS[self.algorithm_key].description,
                                style="Status.TLabel", anchor="w", padding=(12, 4))
        self.status.grid(row=3, column=0, sticky="ew")

    def _build_toolbar(self) -> None:
        # 控件较多，分两行摆放：上行是"选什么"，下行是"做什么"
        bar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(10, 8, 10, 2))
        bar.grid(row=0, column=0, sticky="ew")

        def label(text: str) -> None:
            ttk.Label(bar, text=text, style="Dim.TLabel").pack(side="left", padx=(6, 3))

        label("数据集")
        self.dataset_var = tk.StringVar()
        self.dataset_box = ttk.Combobox(bar, textvariable=self.dataset_var,
                                        state="readonly", width=22)
        self.dataset_box.pack(side="left")
        self.dataset_box.bind("<<ComboboxSelected>>", lambda e: self._on_dataset_change())

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)

        label("算法")
        self.algo_var = tk.StringVar()
        self.algo_box = ttk.Combobox(bar, textvariable=self.algo_var,
                                     state="readonly", width=14)
        self.algo_box.pack(side="left")
        self.algo_box.bind("<<ComboboxSelected>>", lambda e: self._on_algorithm_change())

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)

        label("起点")
        self.source_var = tk.StringVar()
        self.source_box = ttk.Combobox(bar, textvariable=self.source_var,
                                       state="readonly", width=12)
        self.source_box.pack(side="left")
        self.source_box.bind("<<ComboboxSelected>>", lambda e: self._on_endpoint_change())

        label("终点")
        self.target_var = tk.StringVar()
        self.target_box = ttk.Combobox(bar, textvariable=self.target_var,
                                       state="readonly", width=12)
        self.target_box.pack(side="left")
        self.target_box.bind("<<ComboboxSelected>>", lambda e: self._on_endpoint_change())

        ttk.Button(bar, text="⇄", width=3, command=self._swap_endpoints).pack(
            side="left", padx=(4, 14))

        # ---------------- 第二行：操作按钮 ----------------
        bar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(10, 0, 10, 8))
        bar.grid(row=1, column=0, sticky="ew")

        self.run_button = ttk.Button(bar, text="开始搜索", style="Accent.TButton",
                                     command=self._start_or_resume)
        self.run_button.pack(side="left", padx=(0, 4))

        self.pause_button = ttk.Button(bar, text="暂停", command=self._pause,
                                       state="disabled")
        self.pause_button.pack(side="left", padx=(0, 4))

        ttk.Button(bar, text="重置", command=self._reset).pack(side="left", padx=(0, 10))
        self.compare_button = ttk.Button(bar, text="对比三种算法", command=self._compare)
        self.compare_button.pack(side="left", padx=(0, 10))
        ttk.Button(bar, text="＋ 添加线路", command=self._open_line_dialog).pack(
            side="left", padx=(0, 10))

        label("速度")
        self.speed_var = tk.IntVar(value=self._speed)
        scale = ttk.Scale(bar, from_=1, to=10, orient="horizontal", length=110,
                          command=self._on_speed)
        scale.set(self._speed)
        scale.pack(side="left")

        self.algo_box.configure(values=[SOLVERS[k].name for k in ALGORITHM_ORDER])
        self.algo_var.set(SOLVERS[self.algorithm_key].name)

    # ==================================================================
    # 数据加载
    # ==================================================================
    def _load_datasets(self) -> None:
        candidates = sorted(self.data_root.glob("*/network.json"))
        if not candidates:
            messagebox.showerror("数据缺失",
                                 f"在 {self.data_root} 下没有找到任何 network.json")
            return

        sizes: dict[str, int] = {}
        for path in candidates:
            try:
                graph = load_graph(path)
            except (DataError, OSError) as exc:
                self.status.configure(text=f"跳过 {path.parent.name}：{exc}")
                continue
            label = f"{path.parent.name}（{graph.vertex_count} 站 / {graph.line_count} 线）"
            self._datasets[label] = path
            sizes[label] = graph.vertex_count

        if not self._datasets:
            messagebox.showerror("数据缺失", "所有数据文件都无法读取")
            return

        labels = list(self._datasets)
        self.dataset_box.configure(values=labels)
        # 默认加载站点最多的那张网
        self.dataset_box.set(max(sizes, key=sizes.get))
        self._on_dataset_change()

    def _on_dataset_change(self) -> None:
        label = self.dataset_var.get()
        path = self._datasets.get(label)
        if path is None:
            return
        self._stop_animation()
        try:
            self.graph = load_graph(path)
        except (DataError, OSError) as exc:
            messagebox.showerror("加载失败", str(exc))
            return

        self._name_to_id = {v.name: vid for vid, v in self.graph.vertices.items()}
        names = [v.name for v in self.graph.vertices.values()]
        self.source_box.configure(values=names)
        self.target_box.configure(values=names)

        # 默认起终点：用"两次最远扫描"挑出一对距离很远、而且确实连通的站点
        self.source, self.target = self._pick_endpoints()
        self.source_var.set(self.graph.name_of(self.source))
        self.target_var.set(self.graph.name_of(self.target))

        self.view.load(self.graph)
        # load() 会清空画布上的起终点标记，必须把刚选好的那对重新画上
        self.view.set_endpoints(self.source, self.target)
        self.panel.clear()
        self.panel.clear_comparison()
        self._reset_buttons()
        self.status.configure(
            text=f"{label}｜{self.graph.vertex_count} 个站点、{self.graph.line_count} 条线路、"
                 f"{self.graph.edge_count} 段区间、{len(self.graph.transfer_stations())} 个换乘站")

    def _pick_endpoints(self) -> tuple[str, str]:
        """挑一对"离得远且互相连通"的起终点作为初始演示。

        做法是两次最远扫描：先从任意站出发找离它最远的站 A，再从 A 出发
        找离 A 最远的站 B。第二次扫描限制在 A 的可达集合内，因此选出的
        两点之间一定存在通路，不会一上来就摆出"两站不连通"的界面。
        """
        graph = self.graph
        vertices = list(graph.vertices)
        if len(vertices) < 2:
            return vertices[0], vertices[0]

        def far_from(origin: str, pool) -> str:
            target_vertex = graph.vertex(origin)
            return max(pool, key=lambda vid: graph.vertex(vid).straight_distance_to(target_vertex))

        anchor = far_from(vertices[0], graph.reachable_from(vertices[0]))
        other = far_from(anchor, graph.reachable_from(anchor))
        return anchor, other

    # ==================================================================
    # 工具栏事件
    # ==================================================================
    def _on_algorithm_change(self) -> None:
        key = next((k for k in ALGORITHM_ORDER
                    if SOLVERS[k].name == self.algo_var.get()), None)
        if key is None:
            return
        self.algorithm_key = key
        self.status.configure(text=SOLVERS[key].description)
        self._stop_animation()
        self.view.clear_search()
        self.view.set_endpoints(self.source, self.target)
        self.panel.clear()          # 上一算法的结果已经不属于当前选择了

    def _on_endpoint_change(self) -> None:
        self.source = self._name_to_id.get(self.source_var.get())
        self.target = self._name_to_id.get(self.target_var.get())
        self._stop_animation()
        self.view.clear_search()
        self.view.set_endpoints(self.source, self.target)
        self.panel.clear()

    def _swap_endpoints(self) -> None:
        self.source_var.set(self.graph.name_of(self.target) if self.target else "")
        self.target_var.set(self.graph.name_of(self.source) if self.source else "")
        self._on_endpoint_change()

    def _on_speed(self, value: str) -> None:
        self._speed = max(1, int(float(value)))

    def _on_canvas_pick(self, vid: str, button: str) -> None:
        if self.graph is None:
            return
        self._set_endpoint(vid, "source" if button == "left" else "target")

    def _set_endpoint(self, vid: str, which: str) -> None:
        if self.graph is None or not self.graph.has_vertex(vid):
            return
        if which == "source":
            self.source = vid
            self.source_var.set(self.graph.name_of(vid))
        else:
            self.target = vid
            self.target_var.set(self.graph.name_of(vid))
        self._stop_animation()
        self.view.clear_search()
        self.view.set_endpoints(self.source, self.target)
        self.panel.clear()

    def _on_canvas_context(self, vid: str, x_root: int, y_root: int) -> None:
        """站点右键菜单。"""
        if self.graph is None:
            return
        name = self.graph.name_of(vid)
        menu = tk.Menu(
            self.root, tearoff=0,
            background=theme.BG_INPUT, foreground=theme.TEXT,
            activebackground=theme.ACCENT_DARK, activeforeground="#ffffff",
            borderwidth=1, relief="solid", font=theme.FONT_SMALL,
        )
        menu.add_command(label=f"把「{name}」设为起点",
                         command=lambda: self._set_endpoint(vid, "source"))
        menu.add_command(label=f"把「{name}」设为终点",
                         command=lambda: self._set_endpoint(vid, "target"))
        menu.add_separator()
        menu.add_command(label=f"删除站点「{name}」",
                         command=lambda: self._delete_station(vid))
        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()

    # ==================================================================
    # 网络编辑（动态增删）
    # ==================================================================
    def _delete_station(self, vid: str) -> None:
        if self.graph is None:
            return
        name = self.graph.name_of(vid)
        # 先停动画再弹框：模态对话框会开启嵌套事件循环，
        # 不先停下来的话，用户思考的这几秒里搜索动画仍在后台推进
        self._stop_animation()
        if not messagebox.askyesno(
            "删除站点",
            f"确定要从网络中删除「{name}」吗？\n\n"
            "经过该站的线路会在这一处断开，断点前后不会自动相连。",
            parent=self.root,
        ):
            return
        self.graph.remove_vertex(vid)
        self._after_graph_edit(f"已删除站点「{name}」")

    def _open_line_dialog(self) -> None:
        """弹出"添加线路"对话框。"""
        if self.graph is None:
            return
        names = [v.name for v in self.graph.vertices.values()]
        if len(names) < 2:
            messagebox.showinfo("无法添加线路", "网络中至少需要两个站点。", parent=self.root)
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("添加线路")
        dialog.configure(background=theme.BG_PANEL)
        dialog.transient(self.root)
        dialog.resizable(False, False)

        body = ttk.Frame(dialog, style="TFrame", padding=(16, 14))
        body.pack(fill="both", expand=True)

        specs = [
            ("name", "线路名称", f"新线 {len(self.graph.lines) + 1}", None),
            ("from", "起点站", names[0], names),
            ("to", "终点站", names[1], names),
            ("speed", "旅行速度 (km/h)", "40", None),
        ]
        fields: dict[str, tk.StringVar] = {}
        for row, (key, label, default, options) in enumerate(specs):
            ttk.Label(body, text=label, style="Dim.TLabel").grid(
                row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=default)
            if options:
                widget: tk.Widget = ttk.Combobox(body, textvariable=var, values=options,
                                                 state="readonly", width=18)
            else:
                widget = ttk.Entry(body, textvariable=var, width=20)
            widget.grid(row=row, column=1, sticky="ew", padx=(12, 0), pady=4)
            fields[key] = var

        ttk.Label(body, text="新线路将连接所选的这两个站点。", style="Dim.TLabel").grid(
            row=len(specs), column=0, columnspan=2, sticky="w", pady=(8, 10))

        def confirm() -> None:
            name = fields["name"].get().strip()
            start = self._name_to_id.get(fields["from"].get())
            goal = self._name_to_id.get(fields["to"].get())
            if not name:
                messagebox.showwarning("信息不完整", "请填写线路名称。", parent=dialog)
                return
            if start is None or goal is None or start == goal:
                messagebox.showwarning("信息不完整", "请选择两个不同的站点。", parent=dialog)
                return
            try:
                speed = float(fields["speed"].get())
                if speed <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("速度不合法", "旅行速度必须是正数。", parent=dialog)
                return

            lid = self._unique_line_id()
            self.graph.add_line(Line(
                lid=lid, name=name,
                color=DEFAULT_COLORS[len(self.graph.lines) % len(DEFAULT_COLORS)],
                stations=[start, goal], speed_kmh=speed, detour=1.10,
            ))
            dialog.destroy()
            self._after_graph_edit(
                f"已添加线路「{name}」：{self.graph.name_of(start)} — {self.graph.name_of(goal)}")

        buttons = ttk.Frame(body, style="TFrame")
        buttons.grid(row=len(specs) + 1, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="确定", style="Accent.TButton", command=confirm).pack(
            side="left", padx=(0, 6))
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left")

        dialog.bind("<Return>", lambda e: confirm())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.update_idletasks()
        # 居中到主窗口
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 3
        dialog.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dialog.grab_set()

    def _unique_line_id(self) -> str:
        index = 1
        while f"X{index}" in self.graph.lines:
            index += 1
        return f"X{index}"

    def _after_graph_edit(self, message: str) -> None:
        """图被修改之后统一刷新界面。"""
        graph = self.graph
        self._name_to_id = {v.name: vid for vid, v in graph.vertices.items()}
        names = [v.name for v in graph.vertices.values()]
        self.source_box.configure(values=names)
        self.target_box.configure(values=names)

        # 起点 / 终点可能刚好被删掉了，换成任意一个仍然存在的站点
        if self.source not in graph.vertices:
            self.source = next(iter(graph.vertices), None)
        if self.target not in graph.vertices:
            self.target = next(iter(graph.vertices), None)
        self.source_var.set(graph.name_of(self.source) if self.source else "")
        self.target_var.set(graph.name_of(self.target) if self.target else "")

        self.view.load(graph)
        self.view.set_endpoints(self.source, self.target)
        self.panel.clear()
        self.panel.clear_comparison()
        self._reset_buttons()
        self.status.configure(text=message)

    # ==================================================================
    # 搜索动画
    # ==================================================================
    def _ready(self) -> bool:
        if self.graph is None or self.source is None or self.target is None:
            messagebox.showinfo("请先选择站点", "请先选择起点与终点。")
            return False
        return True

    def _start_or_resume(self) -> None:
        if self._events is not None and self._paused:
            self._paused = False
            self.run_button.configure(text="搜索中…", state="disabled")
            self.pause_button.configure(state="normal")
            self._pump()
            return
        self._start_search()

    def _start_search(self) -> None:
        if not self._ready():
            return
        self._stop_animation()
        self.view.clear_search()
        self.view.set_endpoints(self.source, self.target)
        self.panel.clear()

        solver = SOLVERS[self.algorithm_key]
        self._events = solver.run(self.graph, self.source, self.target, animate=True)
        self._paused = False
        self.run_button.configure(text="搜索中…", state="disabled")
        self.pause_button.configure(state="normal")
        self.status.configure(text=f"正在用 {solver.name} 搜索…")
        self._pump()

    def _pump(self) -> None:
        if self._events is None:
            return
        try:
            for _ in range(self._speed):
                event = next(self._events)
                kind = event["type"]
                if kind == "visit":
                    self.view.mark_settled(event["node"])
                elif kind == "push":
                    self.view.mark_frontier(event["node"])
                elif kind == "done":
                    self._finish(event["route"], event["stats"])
                    return
        except StopIteration:
            self._reset_buttons()
            return
        except Exception as exc:                       # 算法内部出错时不让窗口崩掉
            self._stop_animation()
            self._reset_buttons()
            messagebox.showerror("搜索出错", f"{type(exc).__name__}: {exc}")
            return

        self._job = self.root.after(TICK_MS, self._pump)

    def _finish(self, route, stats) -> None:
        self._job = None
        self._events = None
        self._paused = False
        self.view.show_route(route)
        self.panel.show_result(SOLVERS[self.algorithm_key].name, route, stats)
        self.panel.show_itinerary(route, self.graph)
        self._reset_buttons()
        if route.found:
            self.status.configure(
                text=f"完成：{self.graph.name_of(route.path[0])} → "
                     f"{self.graph.name_of(route.path[-1])}，"
                     f"{route.distance:.3f} km，换乘 {route.transfers} 次，"
                     f"访问 {stats.unique_settled} 个站点，耗时 {stats.milliseconds:.3f} ms")
        else:
            self.status.configure(text=route.message)

    def _pause(self) -> None:
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None
            self._paused = True
            self.run_button.configure(text="继续", state="normal")
            self.pause_button.configure(state="disabled")
            self.status.configure(text="已暂停")

    def _stop_animation(self) -> None:
        """中止正在进行的搜索动画，并把按钮恢复成可再次开始的状态。

        按钮的重置必须放在这里：切换算法、改起终点、点画布选站、开始对比
        等操作都会经由这个方法停下来，如果只在 _finish() 里恢复按钮，
        动画进行中做上述任何一件事都会让"开始搜索"永远停在禁用状态。
        """
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None
        self._events = None
        self._paused = False
        self._reset_buttons()
        self.view.clear_search()

    def _reset(self) -> None:
        self._stop_animation()
        self.view.set_endpoints(self.source, self.target)
        self.panel.clear()
        self._reset_buttons()
        self.status.configure(text="已重置")

    def _reset_buttons(self) -> None:
        self.run_button.configure(text="开始搜索", state="normal")
        self.pause_button.configure(state="disabled")

    # ==================================================================
    # 算法对比
    # ==================================================================
    def _compare(self) -> None:
        if not self._ready():
            return
        self._stop_animation()
        self.view.clear_search()
        self.view.set_endpoints(self.source, self.target)

        rows = []
        for key in ALGORITHM_ORDER:
            solver = SOLVERS[key]
            route, stats = solver.solve(self.graph, self.source, self.target)
            rows.append({
                "algo": solver.name,
                "distance": route.distance if route.found else None,
                "minutes": route.minutes if route.found else None,
                "transfers": route.transfers if route.found else None,
                "settled": stats.unique_settled,
                "elapsed": stats.milliseconds,
                "_legs": tuple((leg.line_id, tuple(leg.stations)) for leg in route.legs),
            })

        reachable = [r for r in rows if r["distance"] is not None]
        if reachable:
            min(reachable, key=lambda r: r["distance"])["best"] = True

        self.panel.show_comparison(rows)
        if not reachable:
            self.status.configure(text="对比完成：起终点之间不存在通路")
            return

        shortest = min(reachable, key=lambda r: r["distance"])
        lightest = min(reachable, key=lambda r: r["settled"])
        heaviest = max(reachable, key=lambda r: r["settled"])
        fastest = min(reachable, key=lambda r: r["elapsed"])

        parts: list[str] = []
        distinct_distances = {round(r["distance"], 6) for r in reachable}
        distinct_paths = {r["_legs"] for r in reachable}
        if len(distinct_paths) == 1:
            parts.append(
                f"{len(reachable)} 种算法给出同一条路径（{shortest['distance']:.3f} km，"
                f"换乘 {shortest['transfers']} 次）—— 本例中最少换乘与最短路径恰好一致")
        elif len(distinct_distances) == 1:
            transfers = "、".join(f"{r['algo']} {r['transfers']} 次" for r in reachable)
            parts.append(
                f"{len(reachable)} 种算法路程相同（{shortest['distance']:.3f} km），"
                f"但路径不同：{transfers}换乘")
        else:
            parts.append(f"{shortest['algo']} 路程最短（{shortest['distance']:.3f} km）")

        if heaviest["settled"] > lightest["settled"]:
            saved = 100 * (heaviest["settled"] - lightest["settled"]) / heaviest["settled"]
            parts.append(f"{lightest['algo']} 只访问 {lightest['settled']} 个站点，"
                         f"比 {heaviest['algo']} 的 {heaviest['settled']} 个少 {saved:.0f}%")
        parts.append(f"{fastest['algo']} 用时最短（{fastest['elapsed']:.2f} ms）")

        self.status.configure(text="对比完成：" + "；".join(parts))
