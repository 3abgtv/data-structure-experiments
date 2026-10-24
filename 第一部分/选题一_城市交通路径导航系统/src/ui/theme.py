"""界面配色与字体常量。

集中放在一处，界面代码里不再出现散落的颜色字面量。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 底色
BG = "#0d1117"            # 画布底色
BG_WINDOW = "#0d1117"     # 窗口底色
BG_PANEL = "#161b22"      # 侧栏 / 工具栏
BG_INPUT = "#21262d"      # 输入控件
BORDER = "#30363d"        # 分隔线

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

# ---------------------------------------------------------------- 站点状态
NODE_IDLE = "#3a4250"
NODE_SOURCE = "#3fb950"     # 起点
NODE_TARGET = "#f85149"     # 终点
NODE_SETTLED = "#d29922"    # 已被算法确定
NODE_FRONTIER = "#4493f8"   # 位于前沿（堆 / 队列中）
NODE_ON_PATH = "#ffffff"    # 落在最终路径上
NODE_OUTLINE = "#0d1117"

# ---------------------------------------------------------------- 地图
EDGE_DIM = "#2b3138"        # 未被路径经过的线路
LABEL = "#a9b4c0"

# ---------------------------------------------------------------- 结果路径
# 高亮分四层叠画：亮色光晕 → 深色缝隙 → 线路色主芯 → 同色系高光。
# 每一层都用"提亮后"的线路色：像 21 号线（#201747 深紫）这种
# 在深色底图上几乎看不见的线，算出的路径也能一眼跳出来。
PATH_HALO_WIDTH = 17
PATH_GAP_WIDTH = 12
PATH_CORE_WIDTH = 8
PATH_HIGHLIGHT_WIDTH = 2.4
PATH_MIN_LUMA = 160.0       # 主芯线路色的最低感知亮度
PATH_HALO_MIN_LUMA = 205.0  # 光晕的最低感知亮度
PATH_HIGHLIGHT_MIN_LUMA = 235.0  # 中心高光：同色系里最亮的一档
PATH_STATION_RADIUS = 2.0   # 结果态路径上的站点缩成小铆钉
NODE_DIM = "#39414d"        # 结果模式下没被路径经过的站点

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
STATION_RADIUS = 4.5
TRANSFER_RADIUS = 7.0
# 站点密集时把所有站名都画出来会糊成一片，所以按缩放级别分流：
# 全览时只标注换乘站与起终点，放大到一定程度才显示全部站名。
LABEL_MIN_SCALE = 24.0
CORE_LABEL_MIN_SCALE = 2.0
