"""界面交互的状态机测试。

直接运行：  py tests/test_ui.py

这些用例检查的都是"点了没反应"或"状态对不上"一类的问题 —— 它们不会让
程序崩溃，只有真的去点一遍才暴露得出来。测试驱动真实窗口，用 update()
推进事件循环，不进入 mainloop。

主要覆盖：

* "单步"确实只推进一个模拟时间单位（任务书对它的定义）；
* 开始 / 暂停 / 继续 / 重置的状态流转，以及动画进行中做别的操作不会卡死；
* 时间片只在选中 RR 时可用；
* 任务编辑的时机限制（模拟开始前或重置后才允许改）；
* 算法对比与结果导出。
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tkinter as tk                       # noqa: E402

from src.ui.app import SchedulerApp        # noqa: E402

_passed = 0


def check(condition: bool, message: str) -> None:
    global _passed
    if not condition:
        raise AssertionError(message)
    _passed += 1


def build() -> tuple[tk.Tk, SchedulerApp]:
    root = tk.Tk()
    root.geometry("1280x800+30+30")
    app = SchedulerApp(root, ROOT / "data")
    root.update_idletasks()
    root.update()
    return root, app


def pump(root: tk.Tk, times: int = 10) -> None:
    for _ in range(times):
        root.update()
        time.sleep(0.01)


# ----------------------------------------------------------------------
def test_single_step_semantics() -> None:
    """单步必须恰好推进一个模拟时间单位。"""
    root, app = build()
    try:
        app._reset_engine()
        check(app.engine.now == 0, "重置后时钟应为 0")

        for expected in range(1, 6):
            app._single_step()
            check(app.engine.now == expected,
                  f"第 {expected} 次单步后时钟应为 {expected}，实际 {app.engine.now}")

        # 单步推进的结果，与一次 step() 完全等价
        app._reset_engine()
        for _ in range(3):
            app.engine.step()
        manual = app.engine.now
        app._reset_engine()
        for _ in range(3):
            app._single_step()
        check(app.engine.now == manual, "单步与直接调用 step() 的结果应当一致")
    finally:
        root.destroy()


def test_run_pause_resume_reset() -> None:
    """开始 / 暂停 / 继续 / 重置的状态流转。"""
    root, app = build()
    try:
        app._reset_engine()
        app.speed = 1
        app._start_or_resume()
        pump(root, 8)
        check(app._job is not None, "开始之后应当有动画在跑")
        check(app.run_button["text"] == "运行中…", "运行时按钮文字不对")
        check(str(app.pause_button["state"]) == "normal", "运行时暂停按钮应可用")

        paused_at = app.engine.now
        app._pause()
        check(app._job is None, "暂停后不应再有动画回调")
        check(app.run_button["text"] == "继续", "暂停后按钮应变成「继续」")
        check(app._paused, "应当记录暂停状态")

        pump(root, 6)
        check(app.engine.now == paused_at, f"暂停期间时钟不应走动（{paused_at} → {app.engine.now}）")

        app._start_or_resume()
        pump(root, 8)
        check(app.engine.now > paused_at, "继续之后时钟应当继续前进")
        app._pause()

        app._reset()
        check(app.engine.now == 0, "重置后时钟应回到 0")
        check(not app.engine.finished, "重置后不应处于完成状态")
        check(app.run_button["text"] == "开始", "重置后按钮应回到「开始」")
        check(app.last_result is None, "重置后不应还留着上一次的结果")
        for task in app.engine.tasks:
            check(task.remaining_time == task.burst_time,
                  f"重置后 {task.task_id} 的剩余时长应复原")
    finally:
        root.destroy()


def test_interrupt_during_animation() -> None:
    """动画进行中切换参数或点对比，都不能把按钮卡死。"""
    root, app = build()
    try:
        def running() -> bool:
            return app._job is not None

        # 切换算法
        app._reset_engine()
        app.speed = 1
        app._start_or_resume()
        pump(root, 6)
        app.algo_box.set("优先级调度")
        app._on_algorithm_change()
        pump(root)
        check(not running(), "切换算法后动画应当停下")
        check(str(app.run_button["state"]) == "normal",
              f"切换算法后「开始」应可用，实际 {app.run_button['state']}")

        # 改时间片
        app.algo_box.set("时间片轮转")
        app._on_algorithm_change()
        app._start_or_resume()
        pump(root, 6)
        app.quantum_box.set("4")
        app._on_quantum_change()
        pump(root)
        check(not running(), "改时间片后动画应当停下")
        check(str(app.run_button["state"]) == "normal", "改时间片后「开始」应可用")
        check(app.quantum == 4, "时间片应当被更新为 4")

        # 动画中开始对比
        app._start_or_resume()
        pump(root, 6)
        app._compare()
        pump(root)
        check(not running(), "对比之后动画应当停下")
        check(str(app.run_button["state"]) == "normal", "对比之后「开始」应可用")

        # 换数据集
        other = next(label for label in app._datasets if label.startswith("batch"))
        app.dataset_box.set(other)
        app._load_dataset()
        pump(root)
        check(not running(), "换数据集后不应还有动画在跑")
        check(app.engine.now == 0, "换数据集后应回到 t=0")
    finally:
        root.destroy()


def test_quantum_field_state() -> None:
    """时间片只在对 RR 时可用。"""
    root, app = build()
    try:
        app.algo_box.set("FCFS")
        app._on_algorithm_change()
        check(str(app.quantum_box["state"]) == "disabled", "FCFS 下时间片应禁用")

        app.algo_box.set("优先级调度")
        app._on_algorithm_change()
        check(str(app.quantum_box["state"]) == "disabled", "优先级调度下时间片应禁用")

        app.algo_box.set("时间片轮转")
        app._on_algorithm_change()
        check(str(app.quantum_box["state"]) == "readonly", "RR 下时间片应可用")

        # 非法时间片要被挡回去
        original = app.quantum
        app.quantum_var.set("0")
        messagebox.showwarning = lambda *a, **k: None
        app._on_quantum_change()
        check(app.quantum == original, f"非法时间片不应生效，仍应为 {original}")
        check(app.quantum_var.get() == str(original), "非法输入后下拉框应恢复原值")
    finally:
        root.destroy()


def test_edit_timing_restriction() -> None:
    """任务数据只能在模拟开始前或重置之后修改。"""
    root, app = build()
    try:
        app._reset_engine()
        check(app._can_edit(), "刚重置完应当可以编辑")
        check(str(app.add_button["state"]) == "normal", "添加按钮应可用")

        app.speed = 1
        app._start_or_resume()
        pump(root, 6)
        check(not app._can_edit(), "动画运行中不应允许编辑")
        check(str(app.add_button["state"]) == "disabled", "运行中「添加任务」应禁用")
        check(str(app.remove_button["state"]) == "disabled", "运行中「删除」应禁用")

        app._pause()
        check(not app._can_edit(), "暂停但仍未重置时也不应允许编辑")

        app._reset()
        check(app._can_edit(), "重置之后应当重新允许编辑")
        check(str(app.add_button["state"]) == "normal", "重置后「添加任务」应可用")

        # 跑到推进一步之后，又不可编辑
        app._single_step()
        check(not app._can_edit(), "已经推进过时间就不应再改任务数据")
    finally:
        root.destroy()


def test_remove_task() -> None:
    """删除任务后，任务表、甘特图与引擎都要同步。"""
    root, app = build()
    try:
        app._reset_engine()
        app.algo_box.set("FCFS")
        app._on_algorithm_change()
        original = len(app.tasks)
        victim = app.tasks[1].task_id
        app.table.tree.selection_set(victim)

        original_ask = messagebox.askyesno
        messagebox.askyesno = lambda *a, **k: True
        try:
            app._remove_selected()
        finally:
            messagebox.askyesno = original_ask

        pump(root)
        check(len(app.tasks) == original - 1, "任务应当被删掉一个")
        check(not any(t.task_id == victim for t in app.tasks), f"{victim} 应当已被删除")
        check(not app.table.tree.exists(victim), "任务表里不应还有被删的行")
        check(len(app.engine.tasks) == original - 1, "引擎里的任务数应当同步")
        check(app.engine.now == 0, "删除后应当回到 t=0")
        check([t.seq for t in app.tasks] == list(range(len(app.tasks))),
              "删除后输入序号应当重新排好")
    finally:
        root.destroy()


def test_compare_and_export() -> None:
    """对比表填充与结果导出。"""
    root, app = build()
    try:
        app._reset_engine()
        app._compare()
        pump(root)
        rows = app.panel._compare.get_children()
        # FCFS + 优先级 + RR 的三个时间片
        check(len(rows) == 5, f"对比表应有 5 行，实际 {len(rows)}")

        labels = [app.panel._compare.item(iid)["values"][0] for iid in rows]
        check(labels[:2] == ["FCFS", "优先级"], f"前两行应当是 FCFS 与优先级：{labels}")
        check(all(str(label).startswith("RR") for label in labels[2:]),
              f"后三行应当是 RR 的不同时间片：{labels}")

        # 导出
        target = Path(tempfile.mkstemp(suffix=".csv")[1])
        app.engine.run_to_end()
        app._finish()
        from src.loader import export_result
        export_result(app.last_result, target)
        text = target.read_text(encoding="utf-8-sig")
        check("turnaround_time" in text, "导出的 CSV 应带表头")
        check("平均值" in text, "导出的 CSV 应带平均值行")
    finally:
        root.destroy()


def test_gantt_tracks_engine() -> None:
    """甘特图的段数应随模拟推进而增加，并与引擎的执行记录一致。"""
    root, app = build()
    try:
        app._reset_engine()
        app.algo_box.set("FCFS")
        app._on_algorithm_change()
        check(len(app.gantt._timeline.segments) == 0, "初始时甘特图应当是空的")

        for _ in range(6):
            app._single_step()
        check(app.gantt._now == app.engine.now, "甘特图的当前时刻应与引擎一致")
        check(len(app.gantt._timeline.segments) == len(app.engine.timeline.segments),
              "甘特图与引擎的执行记录应当同步")

        # 跑完之后每个任务都应当有一段
        app.engine.run_to_end()
        app._finish()
        for task in app.engine.tasks:
            runs = app.engine.timeline.runs_of(task.task_id)
            check(len(runs) == 1,
                  f"FCFS 下 {task.task_id} 应当只有一段执行区间，实际 {runs}")
    finally:
        root.destroy()


def main() -> int:
    tests = [
        ("单步的语义", test_single_step_semantics),
        ("开始 / 暂停 / 继续 / 重置", test_run_pause_resume_reset),
        ("动画中打断操作", test_interrupt_during_animation),
        ("时间片输入框状态", test_quantum_field_state),
        ("编辑时机限制", test_edit_timing_restriction),
        ("删除任务", test_remove_task),
        ("算法对比与导出", test_compare_and_export),
        ("甘特图跟随引擎", test_gantt_tracks_engine),
    ]

    failed = 0
    for name, func in tests:
        try:
            func()
            print(f"  [通过] {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  [失败] {name}\n         {exc}")
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            print(f"  [异常] {name}\n         {type(exc).__name__}: {exc}")

    print()
    print(f"{failed} 项失败，{_passed} 个断言通过" if failed
          else f"全部通过（{len(tests)} 组测试，{_passed} 个断言）")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
