"""结果面板：统计数字、换乘指引与算法对比表。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..graph import Graph
from ..models import Route, SearchStats
from . import theme


class _Card(ttk.Frame):
    """带标题的小卡片容器。"""

    def __init__(self, master: tk.Misc, title: str) -> None:
        super().__init__(master, style="Card.TFrame", padding=(12, 10))
        ttk.Label(self, text=title, style="Section.TLabel").pack(anchor="w")
        self.body = ttk.Frame(self, style="CardBody.TFrame")
        self.body.pack(fill="both", expand=True, pady=(6, 0))


class ResultPanel(ttk.Frame):
    """右侧信息面板。"""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, style="Panel.TFrame", padding=(10, 10))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=3)
        self.rowconfigure(2, weight=2)

        self._build_stats()
        self._build_itinerary()
        self._build_comparison()

    # ------------------------------------------------------------------
    def _build_stats(self) -> None:
        card = _Card(self, "搜索结果")
        card.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self._stats: dict[str, ttk.Label] = {}
        rows = [
            ("algorithm", "算法"), ("distance", "路径长度"), ("minutes", "预计耗时"),
            ("transfers", "换乘次数"), ("stops", "途经站数"), ("settled", "访问站点"),
            ("relaxed", "松弛次数"), ("elapsed", "搜索耗时"),
        ]
        for i, (key, label) in enumerate(rows):
            ttk.Label(card.body, text=label, style="Dim.TLabel").grid(
                row=i, column=0, sticky="w", pady=1)
            value = ttk.Label(card.body, text="—", style="Value.TLabel")
            value.grid(row=i, column=1, sticky="e", padx=(12, 0), pady=1)
            self._stats[key] = value
        card.body.columnconfigure(1, weight=1)

        self._message = ttk.Label(card.body, text="", style="Warn.TLabel",
                                  wraplength=300, justify="left")
        self._message.grid(row=len(rows), column=0, columnspan=2,
                           sticky="w", pady=(6, 0))

    # ------------------------------------------------------------------
    def _build_itinerary(self) -> None:
        card = _Card(self, "途经站点与换乘指引")
        card.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        card.body.rowconfigure(0, weight=1)
        card.body.columnconfigure(0, weight=1)

        self._text = tk.Text(
            card.body, wrap="none", height=10, bd=0, relief="flat",
            background=theme.BG_PANEL, foreground=theme.TEXT,
            font=theme.FONT_SMALL, highlightthickness=0, padx=2, pady=2,
            cursor="arrow",
        )
        self._text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(card.body, orient="vertical", command=self._text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._text.configure(yscrollcommand=scroll.set, state="disabled")

        self._text.tag_configure("station", foreground=theme.TEXT, font=theme.FONT_UI_BOLD)
        self._text.tag_configure("ride", foreground=theme.TEXT_MUTED, font=theme.FONT_TINY)
        self._text.tag_configure("index", foreground=theme.TEXT_FAINT, font=theme.FONT_TINY)

    # ------------------------------------------------------------------
    def _build_comparison(self) -> None:
        card = _Card(self, "算法对比")
        card.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        card.body.rowconfigure(0, weight=1)
        card.body.columnconfigure(0, weight=1)

        columns = ("algo", "dist", "time", "transfer", "settled", "elapsed")
        self._table = ttk.Treeview(
            card.body, columns=columns, show="headings", height=4,
            style="Compare.Treeview",
        )
        headings = {
            "algo": ("算法", 62), "dist": ("距离 km", 62), "time": ("分钟", 48),
            "transfer": ("换乘", 42), "settled": ("访问", 42), "elapsed": ("耗时 ms", 56),
        }
        for key, (text, width) in headings.items():
            self._table.heading(key, text=text)
            self._table.column(key, width=width, anchor="center", stretch=True)
        self._table.grid(row=0, column=0, sticky="nsew")
        self._table.tag_configure("best", foreground=theme.SUCCESS)

    # ==================================================================
    # 对外接口
    # ==================================================================
    def show_result(self, algorithm: str, route: Route, stats: SearchStats) -> None:
        self._stats["algorithm"].configure(text=algorithm)
        if route.found:
            self._stats["distance"].configure(text=f"{route.distance:.3f} km")
            self._stats["minutes"].configure(text=f"{route.minutes:.1f} 分钟")
            self._stats["transfers"].configure(text=f"{route.transfers} 次")
            self._stats["stops"].configure(text=f"{route.stops} 站")
        else:
            for key in ("distance", "minutes", "transfers", "stops"):
                self._stats[key].configure(text="—")
        self._stats["settled"].configure(text=str(stats.unique_settled))
        self._stats["relaxed"].configure(text=str(stats.relaxed))
        self._stats["elapsed"].configure(text=f"{stats.milliseconds:.3f} ms")
        self._message.configure(text="" if route.found else route.message,
                                style="Warn.TLabel" if not route.found else "Dim.TLabel")

    def clear(self) -> None:
        """清空结果；对比表也一起清，避免旧结果误导。"""
        for label in self._stats.values():
            label.configure(text="—")
        self._message.configure(text="")
        self._set_text("")
        self.clear_comparison()

    def show_itinerary(self, route: Route, graph: Graph | None) -> None:
        if not route.found:
            self._set_text("")
            return

        name = (lambda vid: graph.name_of(vid)) if graph else (lambda vid: vid)
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")

        self._text.insert("end", f"● {name(route.path[0])}\n", "station")
        for index, leg in enumerate(route.legs):
            arrow = "换乘" if index else "乘坐"
            self._text.insert(
                "end",
                f"  ↓ {arrow} {leg.line_name}  "
                f"（{len(leg.stations) - 1} 站 · {leg.distance:.2f} km）\n",
                "ride",
            )
            self._text.insert("end", f"● {name(leg.stations[-1])}\n", "station")

        if not route.legs and len(route.path) > 1:
            for vid in route.path[1:]:
                self._text.insert("end", f"● {name(vid)}\n", "station")

        self._text.configure(state="disabled")

    def _set_text(self, content: str) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        if content:
            self._text.insert("1.0", content)
        self._text.configure(state="disabled")

    def show_comparison(self, rows: list[dict]) -> None:
        def cell(value, pattern: str) -> str:
            return "—" if value is None else pattern.format(value)

        self._table.delete(*self._table.get_children())
        for row in rows:
            self._table.insert(
                "", "end",
                values=(
                    row["algo"],
                    cell(row["distance"], "{:.2f}"),
                    cell(row["minutes"], "{:.1f}"),
                    cell(row["transfers"], "{}"),
                    row["settled"],
                    f"{row['elapsed']:.2f}",
                ),
                tags=("best",) if row.get("best") else (),
            )

    def clear_comparison(self) -> None:
        self._table.delete(*self._table.get_children())
