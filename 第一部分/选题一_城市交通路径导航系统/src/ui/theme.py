"""界面配色与字体常量。"""

from __future__ import annotations

LIGHT = True               # 浅色主题标记

# 底色
BG = "#ffffff"
BG_WINDOW = "#f6f8fa"
BG_PANEL = "#ffffff"
BG_INPUT = "#f6f8fa"
BORDER = "#d0d7de"
BG_STRIPE = "#f6f8fa"

# 文字
TEXT = "#1f2328"
TEXT_MUTED = "#59636e"
TEXT_FAINT = "#8c959f"

# 强调色
ACCENT = "#0969da"
ACCENT_DARK = "#0550ae"
SUCCESS = "#1a7f37"
DANGER = "#cf222e"
WARNING = "#9a6700"

# 站点状态
NODE_IDLE = "#c9d1d9"
NODE_SOURCE = "#1a7f37"
NODE_TARGET = "#cf222e"
NODE_SETTLED = "#bf8700"
NODE_FRONTIER = "#0969da"
NODE_ON_PATH = "#ffffff"
NODE_OUTLINE = "#ffffff"
NODE_ON_PATH_OUTLINE = "#1f2328"

# 地图
EDGE_DIM = "#d8dee4"
EDGE_MAX_LUMA = 165.0
LABEL = "#59636e"

# 结果路径（分层叠画：轮廓 → 底色缝 → 线路色芯）
PATH_HALO_WIDTH = 16
PATH_GAP_WIDTH = 11.5
PATH_CORE_WIDTH = 8
PATH_HIGHLIGHT_WIDTH = 2.0
PATH_MIN_LUMA = 155.0
PATH_HALO_MIN_LUMA = 95.0
PATH_HIGHLIGHT_MIN_LUMA = 235.0
PATH_OUTLINE = "#1f2328"
PATH_STATION_RADIUS = 2.0
NODE_DIM = "#c9d1d9"

# 字体
FAMILY = "Microsoft YaHei UI"
FONT_UI = (FAMILY, 10)
FONT_UI_BOLD = (FAMILY, 10, "bold")
FONT_SMALL = (FAMILY, 9)
FONT_TINY = (FAMILY, 8)
FONT_TITLE = (FAMILY, 13, "bold")
FONT_SECTION = (FAMILY, 10, "bold")
FONT_MONO = ("Consolas", 10)

# 尺寸
STATION_RADIUS = 4.5
TRANSFER_RADIUS = 7.0
LABEL_MIN_SCALE = 24.0
CORE_LABEL_MIN_SCALE = 2.0
