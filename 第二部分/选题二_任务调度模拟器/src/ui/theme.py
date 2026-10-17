"""界面配色与字体常量。

集中放在一处，界面代码里不再出现散落的颜色字面量。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 底色
BG = "#0d1117"
BG_WINDOW = "#0d1117"
BG_PANEL = "#161b22"
BG_INPUT = "#21262d"
BG_STRIPE = "#1a1f27"      # 表格斑马纹
BORDER = "#30363d"

# ---------------------------------------------------------------- 文字
TEXT = "#e6edf3"
TEXT_MUTED = "#8b949e"
TEXT_FAINT = "#6e7681"

# ---------------------------------------------------------------- 强调
ACCENT = "#4493f8"
ACCENT_DARK = "#1f6feb"
SUCCESS = "#3fb950"
DANGER = "#f85149"
WARNING = "#d29922"

# ---------------------------------------------------------------- 任务与状态
# 每个任务按输入顺序取一个颜色，用于甘特图与状态点
TASK_COLORS = [
    "#4493f8", "#3fb950", "#d29922", "#f85149", "#a371f7",
    "#39c5cf", "#db61a2", "#e3b341", "#7ee787", "#ff9bce",
    "#79c0ff", "#56d364", "#ffa657", "#ff7b72", "#d2a8ff",
]

IDLE = "#2b3138"            # 处理器空闲
IDLE_HATCH = "#20252c"
GRID = "#262c35"            # 时间刻度线
AXIS = "#39404a"

STATE_COLORS = {
    "未到达": TEXT_FAINT,
    "就绪": ACCENT,
    "运行": SUCCESS,
    "完成": TEXT_MUTED,
}

# ---------------------------------------------------------------- 字体
FAMILY = "Microsoft YaHei UI"
FONT_UI = (FAMILY, 10)
FONT_UI_BOLD = (FAMILY, 10, "bold")
FONT_SMALL = (FAMILY, 9)
FONT_TINY = (FAMILY, 8)
FONT_TITLE = (FAMILY, 13, "bold")
FONT_SECTION = (FAMILY, 10, "bold")
FONT_MONO = ("Consolas", 10)

# ---------------------------------------------------------------- 尺寸
GANTT_ROW_HEIGHT = 26
GANTT_LABEL_WIDTH = 132
GANTT_PAD = 14
