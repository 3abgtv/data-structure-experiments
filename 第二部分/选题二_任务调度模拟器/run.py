"""任务调度模拟器 —— 程序入口。

启动方式（不需要安装任何第三方库，只用 Python 自带的 Tkinter）：

    py run.py

操作提示：
    * 工具栏选择调度算法与时间片，点"开始"播放调度过程；
    * "单步"推进一个模拟时间单位（任务书对单步的定义），"暂停"停在当前时刻；
    * 任务列表支持添加 / 修改 / 删除，也可以在模拟开始前从文件导入；
    * "对比三种算法"会把同一组任务在 FCFS、优先级调度以及 RR 的多个时间片下
      各跑一遍并列成表格；
    * "导出结果"把每个任务的开始 / 完成时刻与三项统计指标写成 CSV。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tkinter as tk                            # noqa: E402

from src.ui.app import SchedulerApp             # noqa: E402


def main() -> int:
    try:
        root = tk.Tk()
    except tk.TclError as exc:                  # 没有可用的显示环境
        print(f"无法创建窗口：{exc}", file=sys.stderr)
        return 1

    SchedulerApp(root, ROOT / "data")
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
