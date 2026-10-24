# HANDOFF —— 数据结构实践（两个选题）

> `数据结构实践[副本].docx` 是两份并列任务书，两个选题都已实现为独立项目。
> 选题一在 `第一部分/`，选题二在 `第二部分/`，课程资料在 `课程资料/`。
> 两份实验报告均已加统一封面（姓名/学号留空待填）与目录。

## 选题一：城市交通路径导航系统 —— 已完成

Python 3.14 + Tkinter，三层解耦（`graph.py` / `solver.py` / `ui/`），三种算法（Dijkstra、A\*、最少换乘 BFS）。界面支持缩放平移、搜索动画、路径高亮、换乘指引、三算法对比、不连通报错、动态增删站点/线路。

四份数据：`guangzhou`（310 站 / 21 线，真实的广州地铁全网含广佛线，由 OpenStreetMap 线路关系还原）、`beijing`（224 站 / 11 线，真实的北京地铁主干，由公开站点数据几何还原）、`metro`（65 站，构造）、`demo`（14 站，手工设计含孤立站）。

验证：`tests/test_algorithms.py`（9 组 3060 断言）、`tests/test_guangzhou.py`（6 组 1943 断言）、`tests/test_ui.py`（5 组 52 断言）全部通过。文档：`docs/实验报告.md`（五章）、`docs/算法过程讲解.md`（数据来自 `tools/trace_algorithms.py`）、7 张截图。

做过一轮 23 agent 独立审查，核心算法无缺陷，修复 8 个问题（含动画中切换算法会让按钮永久卡死、数据不变量未校验导致 A\* 静默次优）。

**路径高亮增强（2026-10-24）**：用户要求"最后计算出来的线路颜色明显一点"。`_redraw_route` 改为四层描边（17px 光晕 → 12px 深色缝隙 → 8px 色芯 → 2.4px 同色高光），颜色经 `brighten()` 在 HLS 空间提亮（只动明度，避免等比放大把 5 号线 `#AA0061` 打爆成 `#ff00ff`）。要点：

- `_route_runs()` 把同一线路的连续区段合并成折线，并**按层统一绘制**（先所有光晕、再所有缝隙……）；逐段/逐线路叠加会在换乘站处啃出白色圆环；
- 结果态把非路径站点压暗为 `NODE_DIM`、路径站点缩成 2px 小铆钉（起终点保持原尺寸），`clear_search` 恢复；
- 新增 `theme` 常量 `PATH_*`、`NODE_DIM`；`_layout` 与新增 `_layout_stations` 共用半径逻辑。

文档 README 与报告 4.1 已同步；`docs/screenshots/03/05/06` 已用新绘制重新截图。三组测试仍全部通过。

## 选题二：任务调度模拟器 —— 已完成

同技术栈与分层（`models.py` / `scheduler.py` / `engine.py` / `ui/`），三种算法（FCFS、非抢占式优先级、时间片轮转），**逐时间单位模拟**（与任务书"单步"定义一致）。

界面：任务表格（实时刷新七个属性与状态，开始前可增删改）、甘特图（处理器时间线 + 每任务一行，含空闲区间）、当前状态面板（模拟时间 / 运行中任务 / 就绪队列）、统计结果（平均周转 / 等待 / 响应 + 每任务明细）、算法对比表（含 RR 多个时间片）、CSV 导入导出。

五份数据：`sample`（任务书示例）、`simultaneous`、`mixed`、`batch`、`priority_mix`。

验证：`tests/test_scheduler.py`（17 组 30627 断言）、`tests/test_cross_check.py`（3 组，与独立参考实现比对 480 组随机用例）、`tests/test_ui.py`（8 组 64 断言）全部通过。任务书 FCFS 预期值 6.50 / 3.75 / 3.75 逐格吻合；有专门用例钉死 RR 边界规则；60 轮随机 × 3 算法 × 3 时间片的不变量检查。

文档：`docs/实验报告.md`（五章）、6 张截图、`README.md`。

做过一轮 26 agent 独立审查，修复 13 个确认问题，代表性几条：

- `last_result` 未清空导致「导出结果」写出上一轮数据（`_reset_engine` 统一清空）；
- RR 回队尾没把任务状态改回「就绪」，任务表出现多行"运行"；「修改」按钮因选中回调未接线而永远不启用；
- `run_to_end` 达到步数上限时静默返回含未完成任务的结果（改为抛 `RuntimeError`）；
- 堆键尾部放 `Task` 对象，seq 冲突时抛 `TypeError`；甘特图全量扫描改为索引；
- 报告补「算法对比结果截图」、甘特图与第二章链表对比。

另有 3 条经核验为误报（时间片 int 截断、甘特图合并、"开始/继续"文字），未改。

## 关键决策与原因

**语言选 Python + Tkinter**：任务书推荐 Python (Tkinter/PyQt) 或 C++ (Qt)。本机 Python 3.14.3 + Tkinter 就绪，PATH 中无任何 C++ 编译器、Qt 未安装。若课程强制 C++/Qt，需先装工具链后重做。

**Python 3.8+ 兼容**：移除第一部分 6 处 `@dataclass(slots=True)`（3.10+ 特性，在 3.9/3.8 导入即报错）；其余 `list[str]` / `str | Path` 都在 `from __future__ import annotations` 之下，3.8 不求值。两个 `run.py` 启动时检查版本。两份 README 环境要求已改 3.8+。

**选题一：最少换乘排序键用 `(换乘次数, 路程)`**，否则同层解不唯一、随堆内顺序漂移。**生成器 + `_AlgoClock`** 解决动画与计时冲突（报告 3.5）。

**选题二：逐时间单位模拟**（非事件驱动），因为任务书定义"单步 = 推进一个时间单位"，空闲区间记录也变平凡。**RR 的"回队尾"延后**到下一时间单位开头（`_pending_requeue`），顺序写反会得到完全不同的甘特图（报告 3.3 有最小例子）。**优先级堆键取 `(priority, arrival_time, seq)`**，否则相同优先级弹出顺序不可复现。

## 待验证项 / 已知限制

- **Python 3.8.10 嵌入式发行版实测**：第一部分 3060 条、第二部分 30627 + 2567 条断言全部通过。该发行版不含 Tkinter，界面层未在 3.8 实跑，但已过 3.8 语法检查，界面测试在 3.14 通过。
- **两个项目的对话框只做过程序化冒烟测试**（右键菜单、添加线路、添加/修改任务），没有真实鼠标点过，建议人工过一遍。
- 截图在本机 Windows 11 自动截取，换机器字体渲染可能有差异。新路径高亮的四层宽度按屏幕像素固定，不同 DPI 下观感可能略有差异。
- 选题二按任务书要求不计上下文切换开销（但换人次数会统计）。
- 通用限制见两份报告"局限与改进方向"。

**广州数据集（2026-10-18）**：`tools/import_guangzhou_metro.py` 读取 `tools/source/guangzhou_osm_stops.json`（Overpass API 抓取的 `route=subway` + `network=广州地铁` 关系，ODbL），合并上下行、排除快车、只保留极大交路、按站名合并换乘站，输出 `data/guangzhou/network.json`（310 站 / 21 线 / 385 区间 / 78 换乘站）。分叉线路成为多条：3 号线主线 + 天河客运站—海傍贯通交路、14 号线 + 知识城支线、12 号线东/西段；11 号线为闭合环线。界面自动发现，默认数据集因站最多而变为广州。

广州数据一轮 4 agent 审查（2026-10-18）修复 15 条，关键：3 号线曾拆成"主线 + 支线"导致换乘数偏大（改为 20 站贯通交路）；支线剥离改"极大交路"模型；同名站合并改按最大两两距离；界面三处 bug（切换数据集不画起终点、BFS 状态栏误报站点数、对比摘要只比距离）。未修：绕行系数 1.15 使部分里程偏高约 10%；并行线路互相遮挡；等长并行边可能产生多余换乘指引。

## 复现命令

```bash
# 第一部分（选题一）
cd 第一部分/选题一_城市交通路径导航系统
py run.py && py tests/test_algorithms.py && py tests/test_guangzhou.py && py tests/test_ui.py && py tools/trace_algorithms.py

# 第二部分（选题二）
cd 第二部分/选题二_任务调度模拟器
py run.py && py tests/test_scheduler.py && py tests/test_cross_check.py && py tests/test_ui.py
```

## 目录结构

```
README.md                两个选题的索引
HANDOFF.md               本文件
第一部分/选题一_城市交通路径导航系统/   见该目录 README.md
第二部分/选题二_任务调度模拟器/         见该目录 README.md
课程资料/                 任务书原文、正文提取、逐条解读
```

## 代码仓库

GitHub **私有**仓库：**https://github.com/3abgtv/data-structure-experiments**（分支 `main`）。

- 未纳入仓库：`课程资料/`（见 `.gitignore`）、`__pycache__/`
- 改为公开：`gh repo edit 3abgtv/data-structure-experiments --visibility public --accept-visibility-change-consequences`
- 后续更新：根目录 `git add -A && git commit -m "..." && git push`
