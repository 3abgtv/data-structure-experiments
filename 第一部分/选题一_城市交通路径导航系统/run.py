"""城市交通路径导航系统 —— 程序入口。用法：py run.py"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info < (3, 8):
    sys.stderr.write(
        "本项目需要 Python 3.8 或更高版本，当前版本为 "
        f"{sys.version_info.major}.{sys.version_info.minor}。\n"
    )
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

from src.ui.app import NavigationApp  # noqa: E402


def main() -> int:
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"无法创建窗口：{exc}", file=sys.stderr)
        return 1

    NavigationApp(root, ROOT / "data")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
