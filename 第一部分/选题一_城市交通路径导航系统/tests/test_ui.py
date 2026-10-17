"""界面交互的状态机测试。

直接运行：  py tests/test_ui.py

这些用例覆盖的都是"点了没反应"或"画面和面板对不上"一类的问题，它们不会
让程序崩溃，所以只有真的去点一遍才暴露得出来。测试直接驱动真实窗口，
用 update() 推进事件循环，不进入 mainloop。

主要覆盖：

* 搜索动画进行中做别的操作（切算法 / 改起终点 / 点画布 / 开始对比 /
  删除站点），按钮必须回到可用状态，不能卡在"搜索中…"；
* 切换算法后结果面板要跟着清空，不能还留着上一个算法的结果；
* 双击站点只选站、不重置视图；双击空白处才回到全览；
* 删除起点/终点后，下拉框与画布要同步更新。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tkinter as tk                              # noqa: E402
from tkinter import messagebox                    # noqa: E402

from src.ui.app import NavigationApp              # noqa: E402

_passed = 0


def check(condition: bool, message: str) -> None:
    global _passed
    if not condition:
        raise AssertionError(message)
    _passed += 1


def build() -> tuple[tk.Tk, NavigationApp]:
    root = tk.Tk()
    root.geometry("1100x700+40+40")
    app = NavigationApp(root, ROOT / "data")
    root.update_idletasks()
    root.update()
    return root, app


def pump(root: tk.Tk, times: int = 12) -> None:
    import time
    for _ in range(times):
        root.update()
        time.sleep(0.01)


def animation_running(app: NavigationApp) -> bool:
    return app._events is not None or app._job is not None


def assert_idle(root: tk.Tk, app: NavigationApp, context: str) -> None:
    """动画停下后，按钮必须回到可以重新开始的状态。"""
    pump(root)
    check(not animation_running(app), f"{context} 之后动画应当已经停止")
    check(str(app.run_button["state"]) == "normal",
          f"{context} 之后「开始搜索」应可用，实际为 {app.run_button['state']}")
    check(app.run_button["text"] == "开始搜索",
          f"{context} 之后按钮文字应为「开始搜索」，实际为 {app.run_button['text']}")
    check(str(app.pause_button["state"]) == "disabled",
          f"{context} 之后「暂停」应禁用")


def start_animation(root: tk.Tk, app: NavigationApp) -> None:
    app._speed = 1                     # 每拍只推进一个事件，确保动画还在进行
    app._start_search()
    pump(root, 3)
    check(animation_running(app),
          f"动画应当已经开始（events={app._events!r}, job={app._job!r}, "
          f"paused={app._paused}, speed={app._speed}, algo={app.algorithm_key}, "
          f"button={app.run_button['text']!r}, 起终点={app.source}/{app.target}）")


# ----------------------------------------------------------------------
def test_interrupt_during_animation() -> None:
    """动画进行中做各种操作，按钮都不能卡死。"""
    root, app = build()
    try:
        # 1. 切换算法
        start_animation(root, app)
        app.algo_box.set("A*")
        app._on_algorithm_change()
        assert_idle(root, app, "动画中切换算法")

        # 2. 改起终点
        start_animation(root, app)
        names = list(app._name_to_id)
        app.source_var.set(names[3])
        app._on_endpoint_change()
        assert_idle(root, app, "动画中改起终点")

        # 3. 点画布选站（画布传来的参数是站点 ID，不是站名）
        start_animation(root, app)
        app._on_canvas_pick(app._name_to_id[names[5]], "left")
        assert_idle(root, app, "动画中点画布选站")
        check(app.source == app._name_to_id[names[5]], "画布选站应当生效")

        # 4. 交换起终点
        start_animation(root, app)
        app._swap_endpoints()
        assert_idle(root, app, "动画中交换起终点")

        # 5. 开始对比
        start_animation(root, app)
        app._compare()
        pump(root, 20)
        check(not animation_running(app), "对比应当结束")
        check(str(app.run_button["state"]) == "normal",
              f"对比之后「开始搜索」应可用，实际为 {app.run_button['state']}")

        # 6. 重置
        start_animation(root, app)
        app._reset()
        assert_idle(root, app, "动画中重置")
    finally:
        root.destroy()


def test_delete_station_during_animation() -> None:
    """动画进行中删除站点：先停动画，再弹确认框。"""
    root, app = build()
    original = messagebox.askyesno
    messagebox.askyesno = lambda *a, **k: True          # 自动确认
    try:
        target = app.source
        start_animation(root, app)
        app._delete_station(target)
        assert_idle(root, app, "动画中删除站点")
        check(not app.graph.has_vertex(target), "站点应当已被删除")
        check(app.source != target, "起点被删掉后应当自动改到别的站点")
        check(app.source_var.get() in app._name_to_id, "起点下拉框应当同步更新")
        check(app.graph.name_of(app.source) == app.source_var.get(),
              "下拉框显示的名字应与内部状态一致")
    finally:
        messagebox.askyesno = original
        root.destroy()


def test_panel_cleared_on_algorithm_change() -> None:
    """切换算法后不能还留着上一个算法的结果。"""
    root, app = build()
    try:
        app._speed = 80
        app._start_search()
        pump(root, 40)
        while animation_running(app):
            pump(root, 20)
        check(app.panel._stats["distance"]["text"] != "—", "应当先有结果")

        app.algo_box.set("BFS")
        app._on_algorithm_change()
        check(app.panel._stats["distance"]["text"] == "—",
              "切换算法后路径长度应当被清空")
        check(app.panel._stats["algorithm"]["text"] == "—",
              "切换算法后算法名应当被清空")
        check(not app.panel._table.get_children(), "切换算法后对比表应当被清空")

        # 旧的对比表也要一起清掉（换起终点同理）
        app._compare()
        pump(root, 20)
        check(bool(app.panel._table.get_children()), "对比后应当有数据")
        app.target_var.set(list(app._name_to_id)[7])
        app._on_endpoint_change()
        check(not app.panel._table.get_children(), "改起终点后对比表应当被清空")
    finally:
        root.destroy()


class _Click:
    """只带坐标的假事件：event_generate 不支持直接合成双击。"""

    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


def test_double_click_behaviour() -> None:
    """双击站点只选站；双击空白才回到全览。"""
    root, app = build()
    try:
        graph = app.graph
        vid = next(iter(graph.vertices))
        vertex = graph.vertex(vid)
        sx, sy = app.view.to_screen(vertex.x, vertex.y)

        before = (app.view._scale, app.view._ox, app.view._oy)
        app.view._on_double_click(_Click(int(sx), int(sy)))
        root.update()
        after = (app.view._scale, app.view._ox, app.view._oy)
        check(before == after, "双击站点不应当重置视图")

        app.view._zoom_at(300, 300, 2.0)
        app.view._ox += 60
        app.view._layout()
        app.view._on_double_click(_Click(4, 4))
        root.update()
        check(app.view._auto_fit, "双击空白处应当回到自动铺满的状态")
    finally:
        root.destroy()


def test_swap_and_selection() -> None:
    """交换起终点与画布选站都要真的换过来。"""
    root, app = build()
    try:
        names = list(app._name_to_id)
        app.source_var.set(names[1])
        app._on_endpoint_change()
        app.target_var.set(names[2])
        app._on_endpoint_change()
        old_source, old_target = app.source, app.target

        app._swap_endpoints()
        check(app.source == old_target and app.target == old_source, "起终点应当互换")
        check(app.source_var.get() == app.graph.name_of(old_target), "起点下拉框没更新")
        check(app.target_var.get() == app.graph.name_of(old_source), "终点下拉框没更新")

        app._on_canvas_pick(app._name_to_id[names[6]], "left")
        check(app.source == app._name_to_id[names[6]], "左键应设为起点")
        app._set_endpoint(app._name_to_id[names[6]], "target")
        check(app.target == app._name_to_id[names[6]], "右键应设为终点")

        # 无效的站点 ID 必须被忽略，不能把界面状态改坏
        before = app.source
        app._set_endpoint("不存在的站", "source")
        check(app.source == before, "无效站点不应改变起点")
    finally:
        root.destroy()


def main() -> int:
    tests = [
        ("动画中打断操作", test_interrupt_during_animation),
        ("动画中删除站点", test_delete_station_during_animation),
        ("切换算法清空面板", test_panel_cleared_on_algorithm_change),
        ("双击行为", test_double_click_behaviour),
        ("交换起终点与选站", test_swap_and_selection),
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
