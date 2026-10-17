"""城市交通路径导航系统 —— 程序入口。

启动方式（无需安装任何第三方库，只需要 Python 自带的 Tkinter）：

    py run.py

操作提示：
    * 左键点击站点设为起点，右键点击设为终点；
    * 滚轮缩放，按住左键拖动平移，双击画布回到全览；
    * 工具栏可选择数据集、算法、起终点，并开始 / 暂停 / 重置搜索动画；
    * "对比三种算法"会一次性跑完 Dijkstra、A*、最少换乘 BFS 并列出对比表。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

from src.ui.app import NavigationApp  # noqa: E402


def main() -> int:
    try:
        root = tk.Tk()
    except tk.TclError as exc:                      # 极端情况下没有可用显示环境
        print(f"无法创建窗口：{exc}", file=sys.stderr)
        return 1

    NavigationApp(root, ROOT / "data")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
