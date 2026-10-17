"""数据加载层：从外部文件读入站点与线路，对应任务书"地图加载与存储"模块。

支持两种外部格式，数据一律来自文件，程序中不含任何硬编码的网络数据。

1) JSON（推荐，一个文件装下整张网）::

       {
         "city": "星城",
         "stations": [{"id": "S001", "name": "中央广场", "x": 0.0, "y": 0.0}, ...],
         "lines": [
           {"id": "L1", "name": "1 号线", "color": "#E4002B",
            "speed": 45, "detour": 1.10, "stations": ["S001", "S002", ...]},
           ...
         ]
       }

2) 纯文本（一对 .txt 文件，便于手工编辑）::

       stations.txt   每行： id,name,x,y
       lines.txt      每行： line_id,line_name,color,speed,detour,S001>S002>S003

   两种文件均以 # 开头的行为注释，空行忽略。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .graph import Graph
from .models import Line, Vertex

DEFAULT_COLORS = [
    "#E4002B", "#0072CE", "#00A551", "#FF9E1B", "#8A3FFC",
    "#00B5AD", "#D6267A", "#6B7A8F", "#B7791F", "#2D9CDB",
]


class DataError(ValueError):
    """数据文件格式或内容不合法。"""


# ----------------------------------------------------------------------
# 数值校验
#
# 三个算法各自依赖一条数据不变量，一旦被破坏就会**静默**给出错误答案，
# 而不是报错，所以必须在数据入口处挡住：
#
#   * 坐标必须是有限数 —— 含 NaN 时松弛比较 `candidate < dist.get(...)`
#     恒为 False，可达的站点会被误判成不可达；
#   * 速度必须为正 —— 否则算乘车时间时除零；
#   * 绕行系数必须 ≥ 1 —— 它保证"边长 ≥ 两站直线距离"，这正是 A* 启发
#     函数可采纳的全部依据（见 models.Vertex.straight_distance_to）；
#     系数小于 1 会让 h 高估真实代价、A* 返回次优解，取负值更会让边权
#     变负，直接破坏 Dijkstra 的非负权前提。
# ----------------------------------------------------------------------
def _finite(value, what: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DataError(f"{what}必须是数字，实际为 {value!r}") from exc
    if not math.isfinite(number):
        raise DataError(f"{what}必须是有限数，实际为 {value!r}")
    return number


def _positive(value, what: str) -> float:
    number = _finite(value, what)
    if number <= 0:
        raise DataError(f"{what}必须大于 0，实际为 {number}")
    return number


def _detour(value, what: str) -> float:
    number = _finite(value, what)
    if number < 1.0:
        raise DataError(
            f"{what}必须不小于 1，实际为 {number}。"
            "绕行系数小于 1 意味着区间里程短于两站的直线距离，"
            "这会让 A* 的启发函数高估真实剩余代价（不再可采纳），"
            "取负值还会让边权变负、破坏 Dijkstra 的非负权前提。"
        )
    return number


# ----------------------------------------------------------------------
# JSON
# ----------------------------------------------------------------------
def load_json(path: str | Path) -> Graph:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DataError(f"{path.name} 不是合法的 JSON：{exc}") from exc
    except OSError as exc:
        raise DataError(f"无法读取 {path}：{exc}") from exc

    graph = Graph()
    stations = raw.get("stations")
    lines = raw.get("lines")
    if not isinstance(stations, list) or not isinstance(lines, list):
        raise DataError("JSON 中必须同时包含 stations 与 lines 两个数组")

    seen: set[str] = set()
    for item in stations:
        vid = str(item.get("id", "")).strip()
        if not vid:
            raise DataError("存在缺少 id 的站点")
        if vid in seen:
            raise DataError(f"站点 ID 重复：{vid}")
        seen.add(vid)
        name = str(item.get("name", vid))
        graph.add_vertex(
            Vertex(
                vid=vid,
                name=name,
                x=_finite(item.get("x", 0.0), f"站点「{name}」的 x 坐标"),
                y=_finite(item.get("y", 0.0), f"站点「{name}」的 y 坐标"),
            )
        )

    for index, item in enumerate(lines):
        lid = str(item.get("id", f"L{index + 1}")).strip()
        lname = str(item.get("name", lid))
        seq = item.get("stations") or []
        if len(seq) < 2:
            raise DataError(f"线路「{lname}」至少需要两个站点，实际只有 {len(seq)} 个")
        graph.add_line(
            Line(
                lid=lid,
                name=lname,
                color=str(item.get("color") or DEFAULT_COLORS[index % len(DEFAULT_COLORS)]),
                stations=[str(s) for s in seq],
                speed_kmh=_positive(item.get("speed", 45.0), f"线路「{lname}」的旅行速度"),
                detour=_detour(item.get("detour", 1.12), f"线路「{lname}」的绕行系数"),
            )
        )

    return graph


# ----------------------------------------------------------------------
# 纯文本
# ----------------------------------------------------------------------
def _rows(path: Path) -> list[list[str]]:
    if not path.exists():
        raise DataError(f"找不到文件：{path}")
    rows: list[list[str]] = []
    for lineno, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = text.strip()
        if not text or text.startswith("#"):
            continue
        cells = [c.strip() for c in text.split(",")]
        rows.append(cells)
    return rows


def load_txt(stations_path: str | Path, lines_path: str | Path) -> Graph:
    """从一对 .txt 文件构建图。"""
    stations_path, lines_path = Path(stations_path), Path(lines_path)
    graph = Graph()

    seen: set[str] = set()
    for row in _rows(stations_path):
        if len(row) < 4:
            raise DataError(f"站点行字段不足（需要 id,name,x,y）：{row}")
        vid, name, sx, sy = row[0], row[1], row[2], row[3]
        if vid in seen:
            raise DataError(f"站点 ID 重复：{vid}")
        seen.add(vid)
        graph.add_vertex(Vertex(
            vid=vid, name=name,
            x=_finite(sx, f"站点「{name}」的 x 坐标"),
            y=_finite(sy, f"站点「{name}」的 y 坐标"),
        ))

    for index, row in enumerate(_rows(lines_path)):
        if len(row) < 6:
            raise DataError(f"线路行字段不足（需要 id,name,color,speed,detour,站点序列）：{row}")
        lid, name, color, speed, detour, seq = row[:6]
        stations = [s for s in seq.split(">") if s]
        if len(stations) < 2:
            raise DataError(f"线路「{name}」至少需要两个站点，实际只有 {len(stations)} 个")
        graph.add_line(
            Line(
                lid=lid, name=name,
                color=color or DEFAULT_COLORS[index % len(DEFAULT_COLORS)],
                stations=stations,
                speed_kmh=_positive(speed, f"线路「{name}」的旅行速度"),
                detour=_detour(detour, f"线路「{name}」的绕行系数"),
            )
        )

    return graph


# ----------------------------------------------------------------------
# 统一入口
# ----------------------------------------------------------------------
def load_graph(path: str | Path, lines_path: str | Path | None = None) -> Graph:
    """按扩展名自动选择加载方式。

    load_graph("data/metro/network.json")               -> JSON
    load_graph("data/metro/stations.txt", "lines.txt")  -> TXT
    """
    path = Path(path)
    if lines_path is not None:
        return load_txt(path, lines_path)
    if path.suffix.lower() == ".json":
        return load_json(path)
    if path.suffix.lower() == ".txt":
        # 只给了一个 txt 时，约定同目录下的 stations.txt / lines.txt
        return load_txt(path.parent / "stations.txt", path.parent / "lines.txt")
    raise DataError(f"不支持的文件类型：{path.suffix}")
