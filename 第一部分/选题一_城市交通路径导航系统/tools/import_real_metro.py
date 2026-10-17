"""把真实城市的地铁站点数据转换成程序使用的 network.json。

用法::

    py tools/import_real_metro.py

输入是 `tools/source/beijing_subway_station.csv` —— 一份公开的北京地铁站点
数据（来自 Wikipedia / OpenStreetMap，见文件末尾的来源说明），每行一个站点：

    纬度, 经度, osm_id, 英文名, 中文名, 开通日期, 线路颜色, 线路名

它有两个特点需要处理：

**一、没有给出站点在线路上的先后顺序。** 原始数据是按站名字母序排列的。
这里用「最近邻链」把它还原出来：先找出该线上相距最远的一对站点作为两端，
然后从一端出发，每次走向最近的未访问站点。地铁线路大多近似一条一维曲线，
这个方法能相当准确地还原出真实顺序 —— 1 号线、2 号线（环线）、4 号线、
10 号线（环线）的还原结果都与实际站序一致。

**二、换乘站在数据里只出现一次。** 一个换乘站（例如西直门，同时属于 2、
4、13 号线）在原始数据里只归给了其中一条线，其余线路的记录中直接没有它。
结果是线路的相邻站间距出现异常空缺。这里用**几何插值**把它补回来：如果
某个已知站点的坐标恰好落在该线路相邻两站的连线上（偏离小于 300 米），
就说明它本来就在这条线上，把它插进去。

坐标统一换算成以市中心为原点的等距圆柱投影（单位 km）。这个投影在
一座城市的尺度上足够精确，而且能保证"直线距离不超过实际走行距离"——
A* 的启发函数因此仍然可采纳。

来源：ajduberstein/data_sets (GitHub)，数据取自 Wikipedia 与 OpenStreetMap。
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "source" / "beijing_subway_station.csv"
TARGET = ROOT / "data" / "beijing" / "network.json"

# 北京大致中心，作为投影原点
ORIGIN_LAT, ORIGIN_LON = 39.90, 116.40
KM_PER_LAT = 110.57
KM_PER_LON = 111.32 * math.cos(math.radians(ORIGIN_LAT))     # ≈ 85.4

DETOUR = 1.15          # 地铁线路相对直线距离的绕行系数（须 ≥ 1）
SNAP_KM = 0.45         # 判定"某站就在这条线上"的距离阈值
MAX_GAP_KM = 3.2       # 插值时允许的最大站间距

# 线路配色：按线路号取一个稳定的颜色
PALETTE = [
    "#E4002B", "#0072CE", "#00A551", "#FF9E1B", "#8A3FFC",
    "#00B5AD", "#D6267A", "#B7791F", "#2D9CDB", "#6B7A8F",
    "#C8102E", "#0F7B6C", "#E36C0A", "#5C2D91", "#00843D",
    "#B7312C", "#2E5EAA", "#A05EB5", "#7A9A01", "#D45D00",
]

SPEED_BY_KIND = {"airport": 80.0, "suburban": 55.0, "urban": 40.0}


# ----------------------------------------------------------------------
def project(lat: float, lon: float) -> tuple[float, float]:
    """经纬度 -> 以市中心为原点的平面坐标（km，y 轴朝北）。"""
    return (lon - ORIGIN_LON) * KM_PER_LON, (lat - ORIGIN_LAT) * KM_PER_LAT


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_to_segment(p, a, b) -> tuple[float, float]:
    """点 p 到线段 ab 的距离，以及投影参数 t（0 表示落在 a 上）。"""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return dist(p, a), 0.0
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    proj = (ax + t * dx, ay + t * dy)
    return dist(p, proj), t


# ----------------------------------------------------------------------
def chain_from(start: int, points: list[tuple]) -> list[tuple]:
    """从指定站点出发的最近邻链。"""
    chain = [points[start]]
    remaining = [p for k, p in enumerate(points) if k != start]
    while remaining:
        last = chain[-1][1]
        nxt = min(remaining, key=lambda p: dist(last, p[1]))
        chain.append(nxt)
        remaining.remove(nxt)
    return chain


def path_length(chain: list[tuple]) -> float:
    return sum(dist(chain[i][1], chain[i + 1][1]) for i in range(len(chain) - 1))


def two_opt(chain: list[tuple]) -> list[tuple]:
    """2-opt 局部优化：反复反转一段子路径，直到再也消除不了交叉。"""
    n = len(chain)
    improved = True
    while improved:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                head_before = dist(chain[i - 1][1], chain[i][1])
                head_after = dist(chain[i - 1][1], chain[j][1])
                if j + 1 < n:
                    tail_before = dist(chain[j][1], chain[j + 1][1])
                    tail_after = dist(chain[i][1], chain[j + 1][1])
                else:
                    tail_before = tail_after = 0.0
                if head_after + tail_after < head_before + tail_before - 1e-9:
                    chain[i:j + 1] = reversed(chain[i:j + 1])
                    improved = True
    return chain


def nearest_chain(points: list[tuple]) -> list[tuple]:
    """还原站点在线路上的先后顺序。

    最近邻链本身是贪心的，起点选得不好会走出很长的回头路。这里穷举
    每一个站点作为起点，各跑一遍最近邻链再用 2-opt 消除交叉，最后取
    总长度最短的那条 —— 地铁线路是近似一维的曲线，最短的那条链就是
    它的真实站序。
    """
    if len(points) <= 2:
        return list(points)

    best: list[tuple] | None = None
    best_length = float("inf")
    for start in range(len(points)):
        candidate = two_opt(chain_from(start, points))
        length = path_length(candidate)
        if length < best_length - 1e-9:
            best, best_length = candidate, length
    return best if best is not None else list(points)


def clean_line(points: list[tuple], min_stations: int = 4,
               factor: float = 4.0, floor_km: float = 2.5):
    """还原站序，并剔除坐标明显有误的站点。

    公开数据里难免有坏坐标 —— 例如八通线的"高碑店"被记成了
    (39.333, 115.85)，离最近的同线车站有 50 多公里，整条线路的顺序
    都会被它带偏。判据是：先跑一遍链，若某一段的跨度远超该线正常站距
    （中位数的 factor 倍），就看这一段的两端谁离其余各站更远，把那一端
    剔除，然后重新还原。反复进行，直到没有异常跨度为止。

    Returns:
        (还原后的站序, 被剔除的站名列表)
    """
    pool = list(points)
    dropped: list[str] = []

    while len(pool) >= min_stations:
        chain = nearest_chain(pool)
        gaps = [dist(chain[i][1], chain[i + 1][1]) for i in range(len(chain) - 1)]
        median = sorted(gaps)[len(gaps) // 2]
        limit = max(median * factor, floor_km)
        worst = max(range(len(gaps)), key=lambda i: gaps[i])
        if gaps[worst] <= limit:
            return chain, dropped

        left, right = chain[worst], chain[worst + 1]

        def isolation(point) -> float:
            return min(dist(point[1], q[1]) for q in pool if q is not point)

        outlier = left if isolation(left) > isolation(right) else right
        pool.remove(outlier)
        dropped.append(outlier[0])

    return nearest_chain(pool), dropped


def fill_gaps(chain: list[tuple], all_points: list[tuple]) -> list[tuple]:
    """把"本该在这条线上、却被归到别的线路"的换乘站插回原位。

    对每个不在链上的站点，求它到链上每一段的距离；只要落在某一段附近
    （小于 SNAP_KM），就说明它本来就在这条线上，按投影位置插进去。
    """
    if len(chain) < 2:
        return chain

    present = {p[0] for p in chain}
    insertions: dict[tuple[int, float], tuple] = {}

    for point in all_points:
        if point[0] in present:
            continue
        best = None
        for index in range(len(chain) - 1):
            a, b = chain[index][1], chain[index + 1][1]
            if dist(a, b) > MAX_GAP_KM:
                continue                      # 跨度过大的段不参与插值
            d, t = point_to_segment(point[1], a, b)
            if d <= SNAP_KM and (best is None or d < best[0]):
                best = (d, index, t)
        if best is not None:
            insertions[(best[1], best[2])] = point

    if not insertions:
        return chain

    result: list[tuple] = []
    for index in range(len(chain) - 1):
        result.append(chain[index])
        # 同一段内按投影位置 t 排序，保证插入后仍然是从前往后
        for (seg, _t), point in sorted(insertions.items()):
            if seg == index:
                result.append(point)
    result.append(chain[-1])
    return result


def largest_component(stations: list[dict], lines: list[dict]):
    """只保留最大的连通分量。

    公开数据还原出来的网络里，远郊线（S1 线、西郊线、燕房线等）与主网之间
    的换乘关系往往没能完整恢复，会形成若干互不相连的小块。为了得到一张
    能完整演示的连通网络，这里取其中最大的一块，其余整体丢弃。
    """
    neighbours: dict[str, set[str]] = {s["id"]: set() for s in stations}
    for line in lines:
        for a, b in zip(line["stations"], line["stations"][1:]):
            neighbours[a].add(b)
            neighbours[b].add(a)

    best: set[str] = set()
    seen: set[str] = set()
    for start in neighbours:
        if start in seen:
            continue
        group = {start}
        stack = [start]
        while stack:
            node = stack.pop()
            for nxt in neighbours[node]:
                if nxt not in group:
                    group.add(nxt)
                    stack.append(nxt)
        seen |= group
        if len(group) > len(best):
            best = group

    kept_stations = [s for s in stations if s["id"] in best]
    kept_lines = []
    for line in lines:
        sequence = [sid for sid in line["stations"] if sid in best]
        if len(sequence) >= 2:
            kept_lines.append({**line, "stations": sequence})
    dropped_stations = len(stations) - len(kept_stations)
    dropped_lines = len(lines) - len(kept_lines)
    return kept_stations, kept_lines, dropped_stations, dropped_lines


def parse_color(raw: str, fallback: str) -> str:
    try:
        values = json.loads(raw.replace(" ", ""))
        if isinstance(values, list) and len(values) >= 3:
            r, g, b = (int(v) for v in values[:3])
            return f"#{r:02X}{g:02X}{b:02X}"
    except (ValueError, TypeError):
        pass
    return fallback


DISPLAY_NAMES = {
    "Baton Line": "八通线", "Changping Line": "昌平线", "Daxing Line": "大兴线",
    "Fangshan Line": "房山线", "Yizhuang Line": "亦庄线", "Yanfang Line": "燕房线",
    "S1 Line": "S1 线", "Xijiao Line": "西郊线", "Airport Express": "机场快轨",
}


def display_name(raw: str) -> str:
    """把 "Line 10" 这类英文线路名换成中文习惯的写法。"""
    if raw in DISPLAY_NAMES:
        return DISPLAY_NAMES[raw]
    if raw.startswith("Line ") and raw[5:].isdigit():
        return f"{raw[5:]} 号线"
    return raw


def line_kind(name: str) -> str:
    lowered = name.lower()
    if "airport" in lowered or "机场" in name:
        return "airport"
    if any(k in lowered for k in ("changping", "fangshan", "yizhuang", "daxing",
                                  "baton", "yanfang", "s1", "xijiao", "line 15")):
        return "suburban"
    return "urban"


# ----------------------------------------------------------------------
def main() -> int:
    if not SOURCE.exists():
        print(f"找不到数据源：{SOURCE}", file=sys.stderr)
        return 1

    rows = list(csv.DictReader(SOURCE.open(encoding="utf-8")))
    print(f"读到 {len(rows)} 条站点记录")

    # ---- 汇集所有站点（按中文名去重，一个物理站点只保留一份坐标）----
    all_points: list[tuple[str, tuple[float, float]]] = []
    seen: set[str] = set()
    for row in rows:
        name = row["chinese_name"].strip()
        if name in seen:
            continue
        seen.add(name)
        all_points.append((name, project(float(row["lat"]), float(row["lng"]))))

    # ---- 按线路分组（把 "Line 8 (North section)" 这种分段合并回 "Line 8"）----
    by_line: dict[str, list[tuple]] = defaultdict(list)
    colors: dict[str, str] = {}
    for index, row in enumerate(rows):
        raw_name = row["line_name"].strip()
        name = raw_name.split("(")[0].strip()          # 去掉 (North section) 之类的后缀
        point = (row["chinese_name"].strip(),
                 project(float(row["lat"]), float(row["lng"])))
        if point not in by_line[name]:
            by_line[name].append(point)
        colors.setdefault(name, parse_color(row["color"],
                                            PALETTE[len(colors) % len(PALETTE)]))

    # ---- 逐条线路还原顺序 ----
    stations: list[dict] = []
    station_index: dict[str, str] = {}
    lines: list[dict] = []

    def station_id(name: str, point) -> str:
        if name not in station_index:
            sid = f"S{len(station_index) + 1:03d}"
            station_index[name] = sid
            stations.append({"id": sid, "name": name,
                             "x": round(point[0], 3), "y": round(point[1], 3)})
        return station_index[name]

    total_inserted = 0
    all_dropped: list[str] = []
    for order, (line_name, points) in enumerate(
            sorted(by_line.items(), key=lambda kv: -len(kv[1]))):
        chain, dropped = clean_line(points)
        all_dropped.extend(dropped)
        before = len(chain)
        chain = fill_gaps(chain, all_points)
        total_inserted += len(chain) - before

        sequence = [station_id(name, point) for name, point in chain]
        # 环线：首尾站相距很近时把它们接起来
        kind = line_kind(line_name)

        lines.append({
            "id": f"L{order + 1:02d}",
            "name": display_name(line_name),
            "color": colors.get(line_name, PALETTE[order % len(PALETTE)]),
            "speed": SPEED_BY_KIND[kind],
            "detour": DETOUR,
            "stations": sequence,
        })

    if all_dropped:
        print(f"剔除坐标异常的站点 {len(all_dropped)} 个：{'、'.join(all_dropped)}")
    print(f"几何插值补回换乘记录 {total_inserted} 处")

    stations, lines, lost_stations, lost_lines = largest_component(stations, lines)
    if lost_stations:
        print(f"只保留最大连通分量，丢弃 {lost_stations} 个站点、{lost_lines} 条线路")

    network = {"city": "北京地铁（公开站点数据还原，已取最大连通部分）",
               "stations": stations, "lines": lines}
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(network, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"生成 {TARGET.relative_to(ROOT)}：{len(stations)} 站 / {len(lines)} 线")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
