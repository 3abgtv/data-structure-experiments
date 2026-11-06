"""网络图画布：坐标变换、缩放平移、路径高亮。"""

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
    """Rec. 709 感知亮度，0 ~ 255。"""
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def tone(color: str, target: float) -> str:
    """把颜色亮度调向目标值，色相保持不变。

    浅色主题只压暗过亮色，深色主题只提亮过暗色；只动 HLS 明度通道，
    避免等比放大 RGB 产生假色。
    """
    rgb = _parse_color(color)
    if rgb is None:
        return color
    lum = _luma(rgb)
    if theme.LIGHT:
        if lum <= target:
            return color if color.startswith("#") else f"#{color}"
    else:
        if lum >= target:
            return color if color.startswith("#") else f"#{color}"
    r, g, b = (ch / 255.0 for ch in rgb)
    h, _l, s = colorsys.rgb_to_hls(r, g, b)
    s = min(1.0, s * 1.08)
    r, g, b = colorsys.hls_to_rgb(h, target / 255.0, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


class NetworkView(tk.Canvas):
    """站点网络的可视化画布。"""

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
        self._auto_fit = True

        self._line_items: dict[str, int] = {}
        self._route_items: list[int] = []
        self._station_items: dict[str, int] = {}
        self._label_items: dict[str, int] = {}

        self._settled: set[str] = set()
        self._frontier: set[str] = set()
        self._path_nodes: list[str] = []
        self._path_segments: list[tuple[str, str, str]] = []
        self._source: str | None = None
        self._target: str | None = None
        self._show_result = False

        self.on_pick: Callable[[str, str], None] | None = None
        self.on_context: Callable[[str, int, int], None] | None = None

        self._press_pos: tuple[int, int] | None = None
        self._dragged = False
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
        """把整张网络缩放到铺满画布。"""
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
        self._ox = width / 2 - (min_x + max_x) / 2 * self._scale
        self._oy = height / 2 + (min_y + max_y) / 2 * self._scale
        self._labels_dirty = True
        self._layout()

    def reset_view(self) -> None:
        self._auto_fit = True
        self.fit()

    def _zoom_at(self, sx: float, sy: float, factor: float) -> None:
        """以鼠标位置为锚点缩放。"""
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

        for lid, line in graph.lines.items():
            if len(line.stations) < 2:
                continue
            coords: list[float] = []
            for vid in line.stations:
                v = graph.vertex(vid)
                coords.extend(self.to_screen(v.x, v.y))
            self._line_items[lid] = self.create_line(
                *coords, fill=tone(line.color, theme.EDGE_MAX_LUMA), width=3,
                capstyle=tk.ROUND, joinstyle=tk.ROUND, tags=("line", lid),
            )

        for vid, v in graph.vertices.items():
            sx, sy = self.to_screen(v.x, v.y)
            radius = self._radius_of(vid)
            self._station_items[vid] = self.create_oval(
                sx - radius, sy - radius, sx + radius, sy + radius,
                fill=theme.NODE_IDLE, outline=theme.NODE_OUTLINE, width=1.4,
                tags=("station", vid),
            )

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
        # 结果态把路径站点缩成小铆钉，避免白点切断彩色路径；起终点保持原尺寸。
        if self._show_result and vid in self._path_nodes \
                and vid not in (self._source, self._target):
            return theme.PATH_STATION_RADIUS
        return radius

    def _layout_stations(self) -> None:
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
        """缩放/平移后重算所有图元的屏幕坐标。"""
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
        """路径确定后压暗底图线路，让结果跳出来。"""
        graph = self.graph
        if graph is None:
            return
        active = bool(self._path_segments)
        for lid, item in self._line_items.items():
            line = graph.lines.get(lid)
            if line is None:
                continue
            if active:
                self.itemconfig(item, fill=theme.EDGE_DIM, width=2)
            else:
                self.itemconfig(item, fill=tone(line.color, theme.EDGE_MAX_LUMA),
                                width=3)

    def _destroy_route_items(self) -> None:
        for item in self._route_items:
            self.delete(item)
        self._route_items.clear()

    def _route_runs(self) -> list[tuple[str, list[str]]]:
        """把路径拆成同一线路上的连续区段，避免逐段绘制产生白色圆环。"""
        runs: list[tuple[str, list[str]]] = []
        for a, b, lid in self._path_segments:
            if runs and runs[-1][0] == lid and runs[-1][1][-1] == a:
                runs[-1][1].append(b)
            else:
                runs.append((lid, [a, b]))
        return runs

    def _redraw_route(self) -> None:
        """按层绘制路径高亮：轮廓 → 底色缝 → 线路色芯。

        必须按层而不是按线路绘制，否则换乘站处会出现圆环。
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

        halo = (lambda c: theme.PATH_OUTLINE if theme.PATH_OUTLINE
                else tone(c, theme.PATH_HALO_MIN_LUMA))
        layer_specs = [
            (theme.PATH_HALO_WIDTH, halo),
            (theme.PATH_GAP_WIDTH, lambda c: theme.BG),
            (theme.PATH_CORE_WIDTH, lambda c: tone(c, theme.PATH_MIN_LUMA)),
        ]
        if not theme.LIGHT:
            layer_specs.append(
                (theme.PATH_HIGHLIGHT_WIDTH,
                 lambda c: tone(c, theme.PATH_HIGHLIGHT_MIN_LUMA)))
        for width, color_of in layer_specs:
            for coords, base in runs:
                self._route_items.append(self.create_line(
                    *coords, fill=color_of(base), width=width,
                    capstyle=tk.ROUND, joinstyle=tk.ROUND, tags=("route",),
                ))

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
            fill, outline, width = (theme.NODE_ON_PATH,
                                    theme.NODE_ON_PATH_OUTLINE, 1.2)
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
        """按重要性放置站名，重叠的隐藏。"""
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
        """双击空白回到全览；双击站点视为选站，不重置视图。"""
        if self._station_at(event.x, event.y) is None:
            self.reset_view()

    def _on_right_press(self, event: tk.Event) -> None:
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
