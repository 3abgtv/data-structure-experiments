# HANDOFF —— 数据结构实践（两个选题）

> `数据结构实践[副本].docx` 是两份并列任务书，两个选题都已实现为独立项目。
> 选题一在 `第一部分/`，选题二在 `第二部分/`，课程资料在 `课程资料/`。
> 两份实验报告均已加统一封面（姓名/学号留空待填）与目录。

## 选题一：城市交通路径导航系统 —— 已完成

Python 3.14 + Tkinter，三层解耦（`graph.py` / `solver.py` / `ui/`），三种算法（Dijkstra、A\*、最少换乘 BFS）。界面支持缩放平移、搜索动画、路径高亮、换乘指引、三算法对比、不连通报错、动态增删站点/线路。

四份数据：`guangzhou`（310 站 / 21 线，真实广州地铁全网，OSM 还原）、`beijing`（224 站 / 11 线，真实北京地铁主干）、`metro`（65 站，构造）、`demo`（14 站，含孤立站）。

验证：`tests/test_algorithms.py`（9 组 3060 断言）、`tests/test_guangzhou.py`（6 组 1943 断言）、`tests/test_ui.py`（5 组 52 断言）全部通过。文档：`docs/实验报告.md`（五章）、`docs/算法过程讲解.md`（数据来自 `tools/trace_algorithms.py`）、7 张截图。

做过一轮 23 agent 独立审查，核心算法无缺陷，修复 8 个问题（含动画中切换算法会让按钮永久卡死、数据不变量未校验导致 A\* 静默次优）。

**浅色主题 + 路径高亮（2026-10-24 / 11-01）**：用户先要求"结果线路颜色明显一点"，后要求"两个的背景改成白色"。两个项目均改为 GitHub 风格浅色主题（`theme.py`：白底、`#1f2328` 文字、`#d0d7de` 边框）。

- 选题一新增 `tone(color, target)`：`theme.LIGHT=True` 时只压暗过亮色，否则只提亮；色相不动，避免等比放大把 5 号线打爆成 `#ff00ff`；
- 路径 = 深灰轮廓 → 白缝 → 线路色芯；浅色下不叠白高光（否则像双轨）；
- `_route_runs()` 合并同线路区段并**按层统一绘制**，否则换乘站处出现圆环；
- 结果态压暗底图线路、非路径站点变灰、路径站点缩成 2px 铆钉；底图线路统一 `tone(..., 165)`，浅色线不再消失；
- 选题二：任务色改中等明度、甘特条加边框、表格"运行/就绪"行用浅绿/浅蓝底。

文档与 13 张截图已同步；全部测试通过（3060/1943/52；30627/2567/64）。

**源码注释精简与解析文档（2026-11-06）**：按用户要求精简两个项目 `src/` 与 `run.py` 的注释——docstring 701→181 行、`#` 注释 199→127 行、总行数 4993→4326，代码逻辑未变；保留模块用途、公共接口一行说明与关键约束（懒惰删除、A\* 可采纳前提、`_pending_requeue` 顺序、堆键 `serial` 等）。复跑全部测试通过（3060/1943/52；30627/2567/64）。根目录新增 `代码结构与算法解析.md`：整体结构 + 六算法通俗原理，不含 UI/可视化。以上改动尚未提交。

**Word 实验报告（2026-11-01）**：`tools/build_word_reports.py` 把两份 `docs/实验报告.md` 排版为同名 `.docx`（各 25 页）：A4、2.54cm 页边距、宋体小四 + 1.5 倍行距、黑体标题、封面（姓名/学号留空横线）、Word 目录（已更新出页码）、页眉页码、表格 / 截图 / 代码块。依赖 `python-docx`；`--finalize` 用 Word COM 更新目录（需 `pywin32`）。

**按老师模板的合并报告**：`tools/build_template_report.py` 以 `tools/template.docx`（由 .doc 转出）为基底生成根目录 `校内实训报告.docx`（46 页）：保留封面 / 小组名单 / 实践计划 / 成绩评定，任务一填选题一、任务二填选题二；原「实践记录」大表格在单元格内不能分页，改为每章一个表格框。

## 选题二：任务调度模拟器 —— 已完成

同技术栈与分层（`models.py` / `scheduler.py` / `engine.py` / `ui/`），三种算法（FCFS、非抢占式优先级、时间片轮转），**逐时间单位模拟**（与任务书"单步"定义一致）。

界面：任务表格（实时刷新七个属性与状态，开始前可增删改）、甘特图（处理器时间线 + 每任务一行，含空闲区间）、当前状态面板（模拟时间 / 运行中任务 / 就绪队列）、统计结果（平均周转 / 等待 / 响应 + 每任务明细）、算法对比表（含 RR 多个时间片）、CSV 导入导出。

五份数据：`sample`（任务书示例）、`simultaneous`、`mixed`、`batch`、`priority_mix`。

验证：`tests/test_scheduler.py`（17 组 30627 断言）、`tests/test_cross_check.py`（3 组 2567 断言，与独立参考实现比对 480 组随机用例）、`tests/test_ui.py`（8 组 64 断言）全部通过；任务书 FCFS 预期值 6.50 / 3.75 / 3.75 逐格吻合，RR 边界有专门用例。

文档：`docs/实验报告.md`（五章）、6 张截图、`README.md`。

做过一轮 26 agent 独立审查，修复 13 个确认问题，代表性几条：

- `last_result` 未清空导致「导出结果」写出上一轮数据；RR 回队尾没把状态改回「就绪」；「修改」按钮选中后不启用；
- `run_to_end` 达到步数上限时静默返回未完成任务（改为抛 `RuntimeError`）；堆键尾部放 `Task` 导致 seq 冲突；甘特图全量扫描改为索引；
- 报告补「算法对比结果截图」、甘特图与第二章链表对比。

另有 3 条经核验为误报（时间片 int 截断、甘特图合并、"开始/继续"文字），未改。

## 关键决策与原因

**语言选 Python + Tkinter**：任务书推荐 Python (Tkinter/PyQt) 或 C++ (Qt)；本机 Python 3.14.3 + Tkinter 就绪，PATH 无 C++ 编译器、Qt 未安装。若课程强制 C++/Qt，需先装工具链后重做。

**Python 3.8+ 兼容**：移除第一部分 6 处 `@dataclass(slots=True)`（3.10+ 特性）；其余 `list[str]` / `str | Path` 都在 `from __future__ import annotations` 之下。两个 `run.py` 启动时检查版本，README 已改 3.8+。

**选题一：最少换乘排序键用 `(换乘次数, 路程)`**，否则同层解不唯一、随堆内顺序漂移。**生成器 + `_AlgoClock`** 解决动画与计时冲突（报告 3.5）。

**选题二：逐时间单位模拟**（任务书定义"单步 = 推进一个时间单位"）。**RR 的回队尾延后**到下一时间单位开头（`_pending_requeue`），顺序写反会得到不同的甘特图（报告 3.3 有例子）；**优先级堆键取 `(priority, arrival_time, seq)`**，否则同优先级顺序不可复现。

## 待验证项 / 已知限制

- **Python 3.8.10 嵌入式发行版实测**：算法与数据测试全通过；该发行版无 Tkinter，界面层未在 3.8 实跑，但已过语法检查、在 3.14 通过界面测试。
- **两个项目的对话框只做过程序化冒烟测试**（右键菜单、添加线路、添加/修改任务），没有真实鼠标点过，建议人工过一遍。
- 截图在本机 Windows 11 截取，换机器字体渲染可能有差异；路径高亮宽度按屏幕像素固定，不同 DPI 观感可能不同。选题二按任务书不计上下文切换开销。
- 其余限制见两份报告"局限与改进方向"。

**广州数据集（2026-10-18）**：`tools/import_guangzhou_metro.py` 读取 Overpass 抓取的 `route=subway` + `network=广州地铁` 关系（ODbL），合并上下行、排除快车、保留极大交路、按站名合并换乘站，输出 `data/guangzhou/network.json`（310 站 / 21 线 / 385 区间 / 78 换乘站）。分叉线路成为多条（3 号线贯通交路、14 号线支线、12 号线东西段），11 号线为闭合环线；界面自动发现，默认数据集变为广州。

广州数据一轮 4 agent 审查（2026-10-18）修复 15 条，关键：3 号线拆错支线导致换乘数偏大（改为 20 站贯通交路）；支线剥离改"极大交路"；同名站合并改按最大两两距离；界面三处 bug。未修：绕行系数 1.15 使部分里程偏高约 10%；并行线路互相遮挡；等长并行边可能产生多余换乘指引。

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
README.md / HANDOFF.md   索引与交接
tools/                   Word 排版脚本（build_word_reports / build_template_report / template.docx）
第一部分/…               选题一，见该目录 README.md
第二部分/…               选题二，见该目录 README.md
课程资料/                 任务书原文、提取与解读
```

## 代码仓库

GitHub **私有**仓库：**https://github.com/3abgtv/data-structure-experiments**（分支 `main`）。

- 未纳入仓库：`课程资料/`（见 `.gitignore`）、`__pycache__/`
- 改为公开：`gh repo edit 3abgtv/data-structure-experiments --visibility public --accept-visibility-change-consequences`
- 后续更新：根目录 `git add -A && git commit -m "..." && git push`
