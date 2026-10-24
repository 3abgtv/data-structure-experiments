"""网络图画布（View）。

职责边界：它只回答"怎么画"，不知道任何算法细节 —— 从外部接收一张
Graph 和当前的搜索状态（哪些站点已被确定、哪些还在前沿、最终路径是
什么），再把数据映射成图元。这正是任务书要求的
"图结构 / 算法引擎 / 界面逻辑解耦"在界面侧的落点。

坐标系：图的坐标以 km 为单位、y 轴向上；屏幕坐标以像素为单位、y 轴向下。
两者之间用一个仿射变换连接，缩放与平移都只改这个变换，不动数据。
"""

from __future__ import annotations

import colorsys
import tkinter as tk
from collections.abc import Callable

from ..graph import Graph
from ..models import Route
from . import theme


def _parse_color(color: str) -> tuple[int, int, int] | None:
    """把 "#RRGGBB" 解析成三元组；格式不认识时返回 None。"""
    text = color.lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return None
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return None


def _luma(rgb: tuple[int, int, int]) -> float:
    """感知亮度（Rec. 709 权重），0 ~ 255。"""
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def brighten(color: str, floor: float) -> str:
    """保证颜色至少有 ``floor`` 的亮度，不够就在 HLS 空间里提亮。

    只用 L（明度）通道提亮，色相和饱和度基本不动：深蓝仍是深蓝系的鲜蓝，
    而不是泛白的灰蓝，也不会像等比放大 RGB 那样把某个通道打爆、变成
    #ff00ff 这种刺眼的假色。
    """
    rgb = _parse_color(color)
    if rgb is None:
        return color
    if _luma(rgb) >= floor:
        return color if color.startswith("#") else f"#{color}"
    r, g, b = (ch / 255.0 for ch in rgb)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l = max(l, floor / 255.0)
    s = min(1.0, s * 1.05)          # 提亮会让人眼觉得"发灰"，补一点饱和度
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


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
        # 路径算完后的"结果态"：没走到的站点压暗，让结果自己跳出来
        self._show_result = False

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
        self._show_result = False
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
            radius = theme.TRANSFER_RADIUS
        else:
            radius = theme.STATION_RADIUS
        # 结果态把路径上的站点缩成小铆钉：沿线站点沿用了平时的大圆点
        # 时，会把高亮线切成一串白点，线路颜色就看不出来了。起终点
        # 保持原尺寸，否则一眼找不到两头。
        if self._show_result and vid in self._path_nodes \
                and vid not in (self._source, self._target):
            return theme.PATH_STATION_RADIUS
        return radius

    def _layout_stations(self) -> None:
        """按当前半径重排站点圆（结果态切换时站点大小会变）。"""
        graph = self.graph
        if graph is None:
            return
        for vid, v in graph.vertices.items():
            item = self._station_items.get(vid)
            if item is None:
                continue
            sx, sy = self.to_screen(v.x, v.y)
            radius = self._radius_of(vid)
            self.coords(item, sx - radius, sy - radius, sx + radius, sy + radius)

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

        self._layout_stations()
        for vid, v in graph.vertices.items():
            sx, sy = self.to_screen(v.x, v.y)
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
        self._show_result = False
        self._destroy_route_items()
        self._update_line_emphasis()
        self._layout_stations()
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
        self._show_result = route.found
        if route.found:
            for leg in route.legs:
                for a, b in zip(leg.stations, leg.stations[1:]):
                    self._path_segments.append((a, b, leg.line_id))
        self._layout_stations()
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

    def _route_runs(self) -> list[tuple[str, list[str]]]:
        """把路径拆成"同一线路上的连续区段"。

        同一条腿内的相邻区间合成一条折线再画：若逐区间画，各层（光晕
        与深色缝隙）会在每个站点处互相覆盖，连接点冒出一串白色圆环，
        看起来像路径被白点切断了。
        """
        runs: list[tuple[str, list[str]]] = []
        for a, b, lid in self._path_segments:
            if runs and runs[-1][0] == lid and runs[-1][1][-1] == a:
                runs[-1][1].append(b)
            else:
                runs.append((lid, [a, b]))
        return runs

    def _redraw_route(self) -> None:
        """重画路径高亮：光晕 + 深色缝隙 + 提亮线路色 + 同色系高光。

        线路本色直接画在深色底图上时，深色线（21 号线、12 号线等）几乎
        和背景融成一片；这里统一提亮，并在外面套一圈更亮的光晕，无论
        算出来的是哪条线，结果都能从密密麻麻的站点里跳出来。
        """
        self._destroy_route_items()
        graph = self.graph
        if graph is None or not self._path_segments:
            return

        runs: list[tuple[list[float], str]] = []
        for lid, stations in self._route_runs():
            coords: list[float] = []
            for vid in stations:
                if not graph.has_vertex(vid):
                    coords = []
                    break
                vertex = graph.vertex(vid)
                coords.extend(self.to_screen(vertex.x, vertex.y))
            if len(coords) < 4:
                continue
            line = graph.lines.get(lid)
            runs.append((coords, line.color if line else theme.ACCENT))

        # 按层而不是按线路绘制：先把所有光晕铺完，再统一铺深色缝隙、色芯
        # 和高光。若一条线画完四层再画下一条，换乘站处后一条线的深色
        # 缝隙会在换乘点上啃出一个个圆环。
        layer_specs = (
            (theme.PATH_HALO_WIDTH, lambda c: brighten(c, theme.PATH_HALO_MIN_LUMA)),
            (theme.PATH_GAP_WIDTH, lambda c: theme.BG),
            (theme.PATH_CORE_WIDTH, lambda c: brighten(c, theme.PATH_MIN_LUMA)),
            (theme.PATH_HIGHLIGHT_WIDTH,
             lambda c: brighten(c, theme.PATH_HIGHLIGHT_MIN_LUMA)),
        )
        for width, color_of in layer_specs:
            for coords, base in runs:
                self._route_items.append(self.create_line(
                    *coords, fill=color_of(base), width=width,
                    capstyle=tk.ROUND, joinstyle=tk.ROUND, tags=("route",),
                ))

        # 路径压在底图线路之上；站点再压回路径之上 —— 结果态的路径站点
        # 已缩成小铆钉，不会再变成一串白球，但沿线站点的位置仍看得见。
        for item in self._route_items:
            self.tag_raise(item)
        self.tag_raise("station")
        for vid in (self._source, self._target):
            item = self._station_items.get(vid) if vid else None
            if item is not None:
                self.tag_raise(item)
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
            fill, outline, width = theme.NODE_ON_PATH, theme.NODE_OUTLINE, 1.2
        elif self._show_result:
            fill, outline, width = theme.NODE_DIM, theme.NODE_OUTLINE, 1.0
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
