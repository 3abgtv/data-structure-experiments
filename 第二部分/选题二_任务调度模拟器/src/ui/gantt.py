"""甘特图画布：处理器一行 + 每任务一行。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..models import Timeline
from . import theme

STEP_CANDIDATES = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000)


class GanttChart(ttk.Frame):
    """任务执行甘特图。"""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, style="Panel.TFrame")

        self.canvas = tk.Canvas(
            self, background=theme.BG_PANEL, highlightthickness=0, bd=0,
            height=220,
        )
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._tasks: list = []
        self._timeline = Timeline()
        self._now = 0
        self._colors: dict[str, str] = {}

        self.canvas.bind("<Configure>", lambda _e: self.redraw())

    # ------------------------------------------------------------------
    def set_tasks(self, tasks: list) -> None:
        self._tasks = sorted(tasks, key=lambda t: t.seq)
        self._colors = {
            task.task_id: theme.TASK_COLORS[index % len(theme.TASK_COLORS)]
            for index, task in enumerate(self._tasks)
        }
        self._timeline = Timeline()
        self._now = 0
        self.redraw()

    def update_timeline(self, timeline: Timeline, now: int) -> None:
        self._timeline = timeline
        self._now = now
        self.redraw()

    def color_of(self, task_id: str | None) -> str:
        if task_id is None:
            return theme.IDLE
        return self._colors.get(task_id, theme.ACCENT)

    # ------------------------------------------------------------------
    def _span(self) -> int:
        return max(self._timeline.makespan, self._now, 1)

    @staticmethod
    def _step_for(span: int, width: float) -> int:
        """挑一个让刻度间距不小于约 44 像素的整数步长。"""
        if span <= 0:
            return 1
        target = span * 44.0 / max(width, 1.0)
        for step in STEP_CANDIDATES:
            if step >= target:
                return step
        return STEP_CANDIDATES[-1]

    def redraw(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 200)
        label_w = theme.GANTT_LABEL_WIDTH
        plot_x = label_w
        plot_w = max(width - plot_x - theme.GANTT_PAD, 80)

        if not self._tasks:
            self.canvas.create_text(width / 2, 40, text="尚未载入任务",
                                    fill=theme.TEXT_FAINT, font=theme.FONT_SMALL)
            self.canvas.configure(scrollregion=(0, 0, width, 100))
            return

        span = self._span()
        scale = plot_w / span
        row_h = theme.GANTT_ROW_HEIGHT
        head_h = row_h + 8
        axis_h = 24

        # 时间网格与刻度
        step = self._step_for(span, plot_w)
        top, bottom = 6, head_h + len(self._tasks) * row_h
        moment = 0
        while moment <= span:
            x = plot_x + moment * scale
            self.canvas.create_line(x, top, x, bottom, fill=theme.GRID)
            self.canvas.create_text(x, bottom + 12, text=str(moment),
                                    fill=theme.TEXT_FAINT, font=theme.FONT_TINY)
            moment += step

        # 处理器行
        self.canvas.create_text(label_w - 10, top + head_h / 2 - 4, anchor="e",
                                text="处理器", fill=theme.TEXT, font=theme.FONT_UI_BOLD)
        for seg in self._timeline.segments:
            x1 = plot_x + seg.start * scale
            x2 = plot_x + seg.end * scale
            color = self.color_of(seg.task_id)
            self._bar(x1, top, x2, top + head_h - 8, color,
                      filled=seg.task_id is not None)
            if seg.length * scale > 34 and seg.task_id:
                self.canvas.create_text((x1 + x2) / 2, (top + head_h - 8) / 2 + 3,
                                        text=seg.task_id, fill=theme.ON_TASK,
                                        font=theme.FONT_TINY)

        # 先建索引：逐任务扫描 segments 会让每帧变成 O(任务数 × 段数)。
        runs_by_task: dict[str, list[tuple[int, int]]] = {}
        for seg in self._timeline.segments:
            if seg.task_id is not None:
                runs_by_task.setdefault(seg.task_id, []).append((seg.start, seg.end))

        for index, task in enumerate(self._tasks):
            y1 = head_h + index * row_h
            y2 = y1 + row_h - 6
            color = self.color_of(task.task_id)

            label = f"{task.task_id}  {task.name}"
            self.canvas.create_text(label_w - 10, (y1 + y2) / 2, anchor="e",
                                    text=label, fill=theme.TEXT_MUTED,
                                    font=theme.FONT_SMALL)

            self.canvas.create_rectangle(plot_x, y1, plot_x + plot_w, y2,
                                         fill=theme.BG_STRIPE, outline="")

            for start, end in runs_by_task.get(task.task_id, ()):
                x1 = plot_x + start * scale
                x2 = plot_x + end * scale
                self._bar(x1, y1 + 2, x2, y2 - 2, color)
                if (end - start) * scale > 26:
                    self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2,
                                            text=f"{start}~{end}", fill=theme.ON_TASK,
                                            font=theme.FONT_TINY)

        if self._now > 0:
            x = plot_x + self._now * scale
            self.canvas.create_line(x, top - 2, x, bottom + 4,
                                    fill=theme.WARNING, width=2)
            self.canvas.create_text(x, top - 10, text=f"t={self._now}",
                                    fill=theme.WARNING, font=theme.FONT_TINY)

        self.canvas.create_line(plot_x, bottom, plot_x + plot_w, bottom,
                                fill=theme.AXIS, width=1)

        total_h = bottom + axis_h + 8
        self.canvas.configure(scrollregion=(0, 0, width, total_h))

    def _bar(self, x1: float, y1: float, x2: float, y2: float,
             color: str, filled: bool = True) -> None:
        """画一个执行片段；空闲段用虚线描边。"""
        if x2 - x1 < 1:
            x2 = x1 + 1
        if filled:
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=color,
                                         outline=theme.BORDER, width=1)
        else:
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=theme.IDLE,
                                         outline=theme.BORDER, dash=(3, 3))
