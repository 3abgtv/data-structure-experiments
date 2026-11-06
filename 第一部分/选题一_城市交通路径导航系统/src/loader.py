"""数据加载：从 JSON 或 TXT 构建图，并校验数据不变量。"""

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


# 三条不变量一旦被破坏，算法会静默算错而不是报错：
# 坐标有限、速度为正、绕行系数 >= 1（A* 可采纳的前提）。
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
    """从 stations.txt 与 lines.txt 构建图。"""
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


def load_graph(path: str | Path, lines_path: str | Path | None = None) -> Graph:
    """按扩展名选择加载方式。"""
    path = Path(path)
    if lines_path is not None:
        return load_txt(path, lines_path)
    if path.suffix.lower() == ".json":
        return load_json(path)
    if path.suffix.lower() == ".txt":
        return load_txt(path.parent / "stations.txt", path.parent / "lines.txt")
    raise DataError(f"不支持的文件类型：{path.suffix}")
