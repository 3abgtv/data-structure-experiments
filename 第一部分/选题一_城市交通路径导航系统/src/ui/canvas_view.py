"""网络图画布（View）。

职责边界：它只回答"怎么画"，不知道任何算法细节 —— 从外部接收一张
Graph 和当前的搜索状态（哪些站点已被确定、哪些还在前沿、最终路径是
什么），再把数据映射成图元。这正是任务书要求的
"图结构 / 算法引擎 / 界面逻辑解耦"在界面侧的落点。

坐标系：图的坐标以 km 为单位、y 轴向上；屏幕坐标以像素为单位、y 轴向下。
两者之间用一个仿射变换连接，缩放与平移都只改这个变换，不动数据。
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from ..graph import Graph
from ..models import Route
from . import theme


class NetworkView(tk.Canvas):
    """站点网络的可视化画布，支持缩放、平移与点击选站。"""

    MIN_SCALE = 1.5
    MAX_SCALE = 200.0

    def __init__(self, master: tk.Misc, **kwargs) -> None:
        super().__init__(
            master,
            background=theme.BG,
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self.graph: Graph | None = None

        # 世界坐标(km) -> 屏幕坐标(px)
        self._scale = 10.0
        self._ox = 0.0
        self._oy = 0.0
        # 用户还没手动缩放/平移过时，窗口尺寸变化后自动重新铺满
        self._auto_fit = True

        # 图元索引：数据 -> canvas item id，便于原地改属性而不整体重画
        self._line_items: dict[str, int] = {}
        self._route_items: list[int] = []
        self._station_items: dict[str, int] = {}
        self._label_items: dict[str, int] = {}

        # 搜索状态
        self._settled: set[str] = set()
        self._frontier: set[str] = set()
        self._path_nodes: list[str] = []
        self._path_segments: list[tuple[str, str, str]] = []   # (from, to, line_id)
        self._source: str | None = None
        self._target: str | None = None

        # 交互回调：on_pick(站点 ID, 鼠标按键)；on_context(站点 ID, 屏幕 x, 屏幕 y)
        self.on_pick: Callable[[str, str], None] | None = None
        self.on_context: Callable[[str, int, int], None] | None = None

        self._press_pos: tuple[int, int] | None = None
        self._dragged = False
        # 标签避让的结果只跟缩放有关；平移时相对位置不变，不必重算
        self._labels_dirty = True

        self.bind("<Configure>", self._on_resize)
        self.bind("<ButtonPress-1>", self._on_left_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_left_release)
        self.bind("<ButtonPress-3>", self._on_right_press)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, 1.14))
        self.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / 1.14))
        self.bind("<Double-Button-1>", self._on_double_click)

    # ==================================================================
    # 坐标变换
    # ==================================================================
    def to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return self._ox + wx * self._scale, self._oy - wy * self._scale

    def to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return (sx - self._ox) / self._scale, (self._oy - sy) / self._scale

    def fit(self) -> None:
        """把整张网络缩放到刚好铺满画布。"""
        if self.graph is None or self.graph.vertex_count == 0:
            return
        width = max(self.winfo_width(), 240)
        height = max(self.winfo_height(), 240)

        min_x, min_y, max_x, max_y = self.graph.bounds()
        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)
        margin = 58.0

        self._scale = max(
            self.MIN_SCALE,
            min(
                (width - 2 * margin) / span_x,
                (height - 2 * margin) / span_y,
                self.MAX_SCALE,
            ),
        )
        # 让图心落在画布中心
        self._ox = width / 2 - (min_x + max_x) / 2 * self._scale
        self._oy = height / 2 + (min_y + max_y) / 2 * self._scale
        self._labels_dirty = True
        self._layout()

    def reset_view(self) -> None:
        """回到"整张网铺满画布"的状态，并恢复自动适配。"""
        self._auto_fit = True
        self.fit()

    def _zoom_at(self, sx: float, sy: float, factor: float) -> None:
        """以鼠标所在位置为锚点缩放。"""
        new_scale = max(self.MIN_SCALE, min(self._scale * factor, self.MAX_SCALE))
        if abs(new_scale - self._scale) < 1e-9:
            return
        wx, wy = self.to_world(sx, sy)
        self._scale = new_scale
        self._ox = sx - wx * self._scale
        self._oy = sy + wy * self._scale
        self._auto_fit = False
        self._labels_dirty = True
        self._layout()

    # ==================================================================
    # 构建与布局
    # ==================================================================
    def load(self, graph: Graph | None) -> None:
        """换一张网络：清空画布并重建全部图元。"""
        self.delete("all")
        self._line_items.clear()
        self._station_items.clear()
        self._label_items.clear()
        self._route_items.clear()
        self._settled.clear()
        self._frontier.clear()
        self._path_nodes.clear()
        self._path_segments.clear()
        self._source = None
        self._target = None
        self._auto_fit = True
        self.graph = graph

        if graph is None:
            return

        # --- 线路折线 ---
        for lid, line in graph.lines.items():
            if len(line.stations) < 2:
                continue
            coords: list[float] = []
            for vid in line.stations:
                v = graph.vertex(vid)
                coords.extend(self.to_screen(v.x, v.y))
            self._line_items[lid] = self.create_line(
                *coords, fill=line.color, width=3,
                capstyle=tk.ROUND, joinstyle=tk.ROUND, tags=("line", lid),
            )

        # --- 站点 ---
        for vid, v in graph.vertices.items():
            sx, sy = self.to_screen(v.x, v.y)
            radius = self._radius_of(vid)
            self._station_items[vid] = self.create_oval(
                sx - radius, sy - radius, sx + radius, sy + radius,
                fill=theme.NODE_IDLE, outline=theme.NODE_OUTLINE, width=1.4,
                tags=("station", vid),
            )

        # --- 站名 ---
        for vid, v in graph.vertices.items():
            sx, sy = self.to_screen(v.x, v.y)
            self._label_items[vid] = self.create_text(
                sx, sy - theme.TRANSFER_RADIUS - 7, text=v.name,
                fill=theme.LABEL, font=theme.FONT_TINY, anchor="s",
                tags=("label", vid),
            )

        self.after_idle(self.fit)

    def _radius_of(self, vid: str) -> float:
        if self.graph is not None and self.graph.is_transfer(vid):
            return theme.TRANSFER_RADIUS
        return theme.STATION_RADIUS

    def _layout(self) -> None:
        """缩放 / 平移后重算所有图元的屏幕坐标。"""
        graph = self.graph
        if graph is None:
            return

        for lid, line in graph.lines.items():
            item = self._line_items.get(lid)
            if item is None:
                continue
            coords: list[float] = []
            for vid in line.stations:
                v = graph.vertex(vid)
                coords.extend(self.to_screen(v.x, v.y))
            self.coords(item, *coords)

        for vid, v in graph.vertices.items():
            sx, sy = self.to_screen(v.x, v.y)
            radius = self._radius_of(vid)
            item = self._station_items.get(vid)
            if item is not None:
                self.coords(item, sx - radius, sy - radius, sx + radius, sy + radius)
            label = self._label_items.get(vid)
            if label is not None:
                self.coords(label, sx, sy - theme.TRANSFER_RADIUS - 7)

        self._redraw_route()
        if self._labels_dirty:
            self._update_label_visibility()
            self._labels_dirty = False

    # ==================================================================
    # 搜索状态
    # ==================================================================
    def mark_settled(self, vid: str) -> None:
        self._settled.add(vid)
        self._frontier.discard(vid)
        self._paint_node(vid)

    def mark_frontier(self, vid: str) -> None:
        if vid not in self._settled:
            self._frontier.add(vid)
            self._paint_node(vid)

    def clear_search(self) -> None:
        self._settled.clear()
        self._frontier.clear()
        self._path_nodes.clear()
        self._path_segments.clear()
        self._destroy_route_items()
        self._update_line_emphasis()
        self._paint()
        self._update_label_visibility()

    def set_endpoints(self, source: str | None, target: str | None) -> None:
        self._source, self._target = source, target
        self._paint()
        self._update_label_visibility()

    def show_route(self, route: Route) -> None:
        """把最终路径铺到画布上。"""
        self._path_nodes = list(route.path) if route.found else []
        self._path_segments = []
        if route.found:
            for leg in route.legs:
                for a, b in zip(leg.stations, leg.stations[1:]):
                    self._path_segments.append((a, b, leg.line_id))
        self._redraw_route()
        self._paint()
        self._update_line_emphasis()
        self._update_label_visibility()

    def _update_line_emphasis(self) -> None:
        """路径确定后把没走到的线路压暗，让结果自己"跳"出来。"""
        graph = self.graph
        if graph is None:
            return
        active = {lid for _, _, lid in self._path_segments}
        for lid, item in self._line_items.items():
            line = graph.lines.get(lid)
            if line is None:
                continue
            if not active:
                self.itemconfig(item, fill=line.color, width=3)
            elif lid in active:
                self.itemconfig(item, fill=line.color, width=5)
            else:
                self.itemconfig(item, fill=theme.EDGE_DIM, width=2)

    def _destroy_route_items(self) -> None:
        for item in self._route_items:
            self.delete(item)
        self._route_items.clear()

    def _redraw_route(self) -> None:
        """重画路径高亮：深色描边 + 线路色主线 + 亮色高光，形成轨道质感。"""
        self._destroy_route_items()
        graph = self.graph
        if graph is None or not self._path_segments:
            return

        for a, b, lid in self._path_segments:
            if not graph.has_vertex(a) or not graph.has_vertex(b):
                continue
            line = graph.lines.get(lid)
            color = line.color if line else theme.ACCENT
            va, vb = graph.vertex(a), graph.vertex(b)
            x1, y1 = self.to_screen(va.x, va.y)
            x2, y2 = self.to_screen(vb.x, vb.y)
            self._route_items.append(self.create_line(
                x1, y1, x2, y2, fill=theme.BG, width=11,
                capstyle=tk.ROUND, tags=("route",),
            ))
            self._route_items.append(self.create_line(
                x1, y1, x2, y2, fill=color, width=6,
                capstyle=tk.ROUND, tags=("route",),
            ))
            self._route_items.append(self.create_line(
                x1, y1, x2, y2, fill=theme.NODE_ON_PATH, width=1.6,
                capstyle=tk.ROUND, tags=("route",),
            ))

        for item in self._route_items:
            self.tag_raise(item)
        self.tag_raise("station")
        self.tag_raise("label")

    # ==================================================================
    # 着色
    # ==================================================================
    def _paint(self) -> None:
        if self.graph is None:
            return
        for vid in self.graph.vertices:
            self._paint_node(vid)

    def _paint_node(self, vid: str) -> None:
        item = self._station_items.get(vid)
        if item is None:
            return

        if vid == self._source:
            fill, outline, width = theme.NODE_SOURCE, "#ffffff", 2.4
        elif vid == self._target:
            fill, outline, width = theme.NODE_TARGET, "#ffffff", 2.4
        elif vid in self._path_nodes:
            fill, outline, width = theme.NODE_ON_PATH, theme.NODE_OUTLINE, 1.4
        elif vid in self._settled:
            fill, outline, width = theme.NODE_SETTLED, theme.NODE_OUTLINE, 1.4
        elif vid in self._frontier:
            fill, outline, width = theme.NODE_FRONTIER, theme.NODE_OUTLINE, 1.4
        else:
            fill, outline, width = theme.NODE_IDLE, theme.NODE_OUTLINE, 1.2

        self.itemconfig(item, fill=fill, outline=outline, width=width)

    @staticmethod
    def _box_overlaps(a: tuple[float, float, float, float],
                      b: tuple[float, float, float, float]) -> bool:
        return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])

    def _update_label_visibility(self) -> None:
        """决定哪些站名该显示出来。

        真实网络的中心城区站点极密，把站名统统画出来会糊成一团。这里
        按重要性排序（起点终点 → 结果路径上的站 → 换乘站 → 其余），
        依次尝试放标签，与已放下的标签矩形重叠的就直接隐藏。缩放级别
        决定候选范围，碰撞检测决定最终谁留下。
        """
        graph = self.graph
        if graph is None:
            return

        show_all = self._scale >= theme.LABEL_MIN_SCALE
        show_core = self._scale >= theme.CORE_LABEL_MIN_SCALE
        path_nodes = set(self._path_nodes)

        def rank(vid: str) -> int:
            if vid in (self._source, self._target):
                return 0
            if vid in path_nodes:
                return 1
            if graph.is_transfer(vid):
                return 2
            return 3

        placed: list[tuple[float, float, float, float]] = []
        for vid in sorted(graph.vertices, key=rank):
            item = self._label_items.get(vid)
            if item is None:
                continue
            level = rank(vid)
            visible = show_all or (show_core and level <= 2)

            if visible:
                vertex = graph.vertex(vid)
                x, y = self.to_screen(vertex.x, vertex.y)
                half = (len(vertex.name) * 7.5 + 6) / 2
                box = (x - half, y - 17, x + half, y - 2)
                if any(self._box_overlaps(box, other) for other in placed):
                    visible = False
                else:
                    placed.append(box)

            self.itemconfig(item, state="normal" if visible else "hidden")

    # ==================================================================
    # 鼠标交互
    # ==================================================================
    def _on_resize(self, event: tk.Event) -> None:
        if self.graph is None:
            return
        # 首次布局完成、或用户没手动调过视图时，跟着窗口重新铺满
        if self._auto_fit:
            self.fit()
        else:
            self._layout()

    def _on_left_press(self, event: tk.Event) -> None:
        self._press_pos = (event.x, event.y)
        self._dragged = False

    def _on_drag(self, event: tk.Event) -> None:
        if self._press_pos is None:
            return
        px, py = self._press_pos
        if not self._dragged and abs(event.x - px) + abs(event.y - py) < 4:
            return
        self._dragged = True
        self._auto_fit = False
        self._ox += event.x - px
        self._oy += event.y - py
        self._press_pos = (event.x, event.y)
        self._layout()
        self.configure(cursor="fleur")

    def _on_left_release(self, event: tk.Event) -> None:
        self.configure(cursor="")
        was_drag = self._dragged
        self._press_pos = None
        self._dragged = False
        if was_drag:
            return
        vid = self._station_at(event.x, event.y)
        if vid and self.on_pick:
            self.on_pick(vid, "left")

    def _on_double_click(self, event: tk.Event) -> None:
        """双击空白处回到全览。

        双击**站点**时不触发 —— 那多半只是想选这个站。真实的双击会先产生
        一次完整的按下与抬起，若这时的双击又去重置视图，用户就会看到
        "选中的站没变，画面却跳走了"。
        """
        if self._station_at(event.x, event.y) is None:
            self.reset_view()

    def _on_right_press(self, event: tk.Event) -> None:
        """右键弹出上下文菜单（设为终点 / 删除站点等）。"""
        vid = self._station_at(event.x, event.y)
        if vid and self.on_context:
            self.on_context(vid, event.x_root, event.y_root)

    def _on_wheel(self, event: tk.Event) -> None:
        self._zoom_at(event.x, event.y, 1.14 if event.delta > 0 else 1 / 1.14)

    def _station_at(self, sx: float, sy: float, tolerance: float = 14.0) -> str | None:
        """屏幕坐标命中最接近的站点。"""
        graph = self.graph
        if graph is None:
            return None
        best: str | None = None
        best_dist = tolerance
        for vid, v in graph.vertices.items():
            vx, vy = self.to_screen(v.x, v.y)
            dist = ((vx - sx) ** 2 + (vy - sy) ** 2) ** 0.5
            if dist < best_dist:
                best, best_dist = vid, dist
        return best
