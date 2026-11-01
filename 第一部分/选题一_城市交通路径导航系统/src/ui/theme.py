"""界面配色与字体常量。

集中放在一处，界面代码里不再出现散落的颜色字面量。
当前为浅色主题；`LIGHT` 供画布判断"该提亮还是压暗"。
"""

from __future__ import annotations

LIGHT = True               # 浅色主题标记（路径高亮按此选择调色方向）

# ---------------------------------------------------------------- 底色
BG = "#ffffff"            # 画布底色
BG_WINDOW = "#f6f8fa"     # 窗口底色
BG_PANEL = "#ffffff"      # 侧栏 / 工具栏
BG_INPUT = "#f6f8fa"      # 输入控件
BORDER = "#d0d7de"        # 分隔线
BG_STRIPE = "#f6f8fa"     # 表格斑马纹

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

# ---------------------------------------------------------------- 站点状态
NODE_IDLE = "#c9d1d9"
NODE_SOURCE = "#1a7f37"     # 起点
NODE_TARGET = "#cf222e"     # 终点
NODE_SETTLED = "#bf8700"    # 已被算法确定
NODE_FRONTIER = "#0969da"   # 位于前沿（堆 / 队列中）
NODE_ON_PATH = "#ffffff"    # 落在最终路径上
NODE_OUTLINE = "#ffffff"    # 站点描边取底色，把站点从线路上"切"出来
NODE_ON_PATH_OUTLINE = "#1f2328"   # 路径上的白点用深色描边，白底上也看得清

# ---------------------------------------------------------------- 地图
EDGE_DIM = "#d8dee4"        # 未被路径经过的线路
EDGE_MAX_LUMA = 165.0       # 底图线路的亮度上限：白底上也要看得见浅色线
LABEL = "#59636e"

# ---------------------------------------------------------------- 结果路径
# 高亮分四层叠画：深色轮廓 → 底色缝隙 → 线路色主芯 → 亮色高光。
# 浅色主题下把过亮的线路色压暗（`LIGHT=True` 时 tone() 只压不亮），
# 黄色、橙色线路在白色底图上也能看清；深色线路本身已经足够醒目。
PATH_HALO_WIDTH = 16
PATH_GAP_WIDTH = 11.5
PATH_CORE_WIDTH = 8
PATH_HIGHLIGHT_WIDTH = 2.0
PATH_MIN_LUMA = 155.0       # 主芯线路色的亮度上限（浅色主题）
PATH_HALO_MIN_LUMA = 95.0   # 轮廓的亮度上限：外圈更深，衬出彩色主芯
PATH_HIGHLIGHT_MIN_LUMA = 235.0  # 深色主题下中心高光的亮度下限
# 浅色主题下路径外圈统一用深灰，与任何线路色都能拉开对比；
# 深色主题置 None，让外圈改用提亮后的线路色。
PATH_OUTLINE = "#1f2328"
PATH_STATION_RADIUS = 2.0   # 结果态路径上的站点缩成小铆钉
NODE_DIM = "#c9d1d9"        # 结果模式下没被路径经过的站点（与常态同色，只是去掉彩）

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
