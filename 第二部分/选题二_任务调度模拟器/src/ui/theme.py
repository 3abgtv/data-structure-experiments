"""界面配色与字体常量。

集中放在一处，界面代码里不再出现散落的颜色字面量。
当前为浅色主题。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 底色
BG = "#ffffff"
BG_WINDOW = "#f6f8fa"
BG_PANEL = "#ffffff"
BG_INPUT = "#f6f8fa"
BG_STRIPE = "#f6f8fa"      # 表格斑马纹
BORDER = "#d0d7de"

# ---------------------------------------------------------------- 文字
TEXT = "#1f2328"
TEXT_MUTED = "#59636e"
TEXT_FAINT = "#8c959f"

# ---------------------------------------------------------------- 强调
ACCENT = "#0969da"
ACCENT_DARK = "#0550ae"
SUCCESS = "#1a7f37"
DANGER = "#cf222e"
WARNING = "#9a6700"

# ---------------------------------------------------------------- 任务与状态
# 每个任务按输入顺序取一个颜色，用于甘特图与状态点。
# 取值都在中等明度，白色底图上看得清，其上压深色编号也读得出来。
TASK_COLORS = [
    "#54aeff", "#4ac26b", "#d4a72c", "#ff7b72", "#b083f0",
    "#39c5cf", "#db61a2", "#e3b341", "#7ee787", "#ff9bce",
    "#79c0ff", "#56d364", "#ffa657", "#ff9c8a", "#d2a8ff",
]
ON_TASK = "#1f2328"         # 色块上叠加的任务编号 / 时间段文字

IDLE = "#eaeef2"            # 处理器空闲
IDLE_HATCH = "#f6f8fa"
GRID = "#eaeef2"            # 时间刻度线
AXIS = "#8c959f"

STATE_COLORS = {
    "未到达": TEXT_FAINT,
    "就绪": ACCENT,
    "运行": SUCCESS,
    "完成": TEXT_MUTED,
}

# 表格里"运行 / 就绪"两行的底色
ROW_RUNNING_BG = "#dafbe1"
ROW_READY_BG = "#ddf4ff"

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
