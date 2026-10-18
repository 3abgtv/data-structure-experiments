"""把 OpenStreetMap 的广州地铁线路数据转换成程序使用的 network.json。

用法::

    py tools/import_guangzhou_metro.py

输入是 `tools/source/guangzhou_osm_stops.json` —— Overpass API 对下列查询的
原始响应（2026-10-18 抓取）：

    [out:json][timeout:120];
    rel["route"="subway"]["network"="广州地铁"](22.4,112.8,24.0,114.2);
    out body;
    node(r);
    out body;

每条线路在 OSM 中是一个 `route=subway` 关系，成员按行车顺序排列：
role 以 `stop` 开头的节点就是沿途站点，节点自身的 `name` 标签是站名。

数据里需要处理四件事：

**一、同一条线路有多个关系。** 上下行各一个，还有短交路、快车和分段运营。
这里先把方向无关的交路去重，再只保留**极大交路**——站点集合是另一条交路
真子集的短交路直接丢弃。于是 4 号线的「新造→黄村」被「南沙客运港→黄村」
吸收；而 3 号线的「天河客运站→海傍」含主线没有的天河客运站，不是任何
交路的子集，会作为一条贯通交路保留下来。这样建模的意义在于：天河客运站
到海傍在现实中确有直达列车，不能因为线路被拆成"主线 + 支线"而多算一次
换乘。14 号线知识城支线、12 号线东/西两段同理，各自保留为独立线路。

**二、环线首尾重名。** 11 号线外环的站点序列首尾都是赤沙，输出时保留这个
重复站，图里才会生成赤沙—龙潭的闭合边。

**三、换乘站是不同节点。** 同一座车站在不同线路、不同方向上各有一个
stop_position 节点，名称相同、坐标相差几十米。按站名合并成一个顶点，
坐标取平均。已校验同名节点的最大间距小于 500 米，可以安全合并。

**四、经纬度换平面坐标。** 以广州市中心为原点做等距圆柱投影（单位 km），
城市尺度上误差可以忽略，且保证"直线距离不超过实际走行距离"。

来源：OpenStreetMap 贡献者，数据许可 ODbL。线路颜色取自关系的 colour 标签。
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "source" / "guangzhou_osm_stops.json"
TARGET = ROOT / "data" / "guangzhou" / "network.json"

# 广州中心（公园前—北京路一带），作为投影原点
ORIGIN_LAT, ORIGIN_LON = 23.1291, 113.2644
KM_PER_LAT = 110.57
KM_PER_LON = 111.32 * math.cos(math.radians(ORIGIN_LAT))

DETOUR = 1.15            # 地铁线路相对直线距离的绕行系数（须 ≥ 1）
MAX_MERGE_KM = 0.5       # 同名站点合并时允许的最大坐标离散

# ref -> (线路 ID 前缀, 线路名, 旅行速度 km/h)
LINE_META = {
    "1":  ("1",  "1号线",  45.0),
    "2":  ("2",  "2号线",  45.0),
    "3":  ("3",  "3号线",  55.0),
    "4":  ("4",  "4号线",  45.0),
    "5":  ("5",  "5号线",  45.0),
    "6":  ("6",  "6号线",  45.0),
    "7":  ("7",  "7号线",  45.0),
    "8":  ("8",  "8号线",  45.0),
    "9":  ("9",  "9号线",  50.0),
    "10": ("10", "10号线", 45.0),
    "11": ("11", "11号线", 45.0),
    "12": ("12", "12号线", 45.0),
    "13": ("13", "13号线", 50.0),
    "14": ("14", "14号线", 60.0),
    "18": ("18", "18号线", 80.0),
    "21": ("21", "21号线", 60.0),
    "22": ("22", "22号线", 80.0),
    "GF": ("GF", "广佛线", 50.0),
}

PALETTE = [
    "#E4002B", "#0072CE", "#00A551", "#FF9E1B", "#8A3FFC",
    "#00B5AD", "#D6267A", "#B7791F", "#2D9CDB", "#6B7A8F",
    "#C8102E", "#0F7B6C", "#E36C0A", "#5C2D91", "#00843D",
    "#B7312C", "#2E5EAA", "#A05EB5", "#7A9A01", "#D45D00",
]


# ----------------------------------------------------------------------
def project(lat: float, lon: float) -> tuple[float, float]:
    """经纬度 -> 以市中心为原点的平面坐标（km，y 轴朝北）。"""
    return (lon - ORIGIN_LON) * KM_PER_LON, (lat - ORIGIN_LAT) * KM_PER_LAT


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def segment_label(relation_name: str) -> str:
    """从「地铁 12号线东段：…」中取出「东段」，取不到时返回空串。"""
    match = re.search(r"号线(.*?)[：:]", relation_name)
    return match.group(1).strip() if match else ""


def relation_endpoints(relation_name: str) -> tuple[str, str] | None:
    """从「地铁 3号线：天河客运站 → 海傍」中取出首末站名。"""
    match = re.search(r"[：:]\s*(.+?)\s*(?:→|->)\s*(.+?)\s*$", relation_name)
    return (match.group(1), match.group(2)) if match else None


def read_sequences(payload: dict) -> dict[str, list[tuple[str, list[str]]]]:
    """ref -> [(关系名, 站名序列), ...]，已排除快车、合并正反向。

    同一座车站的上下行站台是两个不同的节点，站名相同，所以用站名集合
    去重即可同时合并上下行、内环/外环这类只是方向或起点不同的同一交路。
    """
    nodes = {e["id"]: e for e in payload["elements"] if e["type"] == "node"}
    relations = [e for e in payload["elements"] if e["type"] == "relation"]

    problems: list[str] = []
    grouped: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for rel in relations:
        tags = rel.get("tags", {})
        if tags.get("network") != "广州地铁" or "快车" in tags.get("name", ""):
            continue
        if "ref" not in tags:
            continue

        seq: list[str] = []
        for member in rel["members"]:
            if member["type"] != "node" or not member.get("role", "").startswith("stop"):
                continue
            if member["ref"] not in nodes:
                problems.append(f"{tags.get('name')}：成员节点 {member['ref']} 不在响应中")
                continue
            name = nodes[member["ref"]].get("tags", {}).get("name")
            if not name:
                problems.append(f"{tags.get('name')}：节点 {member['ref']} 没有 name 标签")
                continue
            seq.append(name)
        if len(seq) >= 2:
            grouped[tags["ref"]].append((tags.get("name", ""), seq))

    if problems:
        raise SystemExit("源数据不完整，拒绝生成：\n  " + "\n  ".join(problems[:20]))

    seen: dict[str, set[frozenset[str]]] = defaultdict(set)
    result: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for ref, items in grouped.items():
        for name, seq in items:
            key = frozenset(seq)
            if key in seen[ref]:
                continue
            seen[ref].add(key)
            result[ref].append((name, seq))
    return result


def maximal(items: list[tuple[str, list[str]]]) -> list[tuple[str, list[str]]]:
    """只保留极大交路：站点集合是另一条交路真子集的，视为其短交路。

    例如 4 号线的「新造→黄村」是「南沙客运港→黄村」的子集，丢弃；
    3 号线的「天河客运站→海傍」含主线没有的天河客运站，不是子集，保留。
    """
    sets = [set(seq) for _, seq in items]
    kept: list[tuple[str, list[str]]] = []
    for index, item in enumerate(items):
        if any(sets[index] < other for other in sets):
            continue
        kept.append(item)
    return kept


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    grouped = read_sequences(payload)

    nodes = {e["id"]: e for e in payload["elements"] if e["type"] == "node"}
    relations = [
        e for e in payload["elements"]
        if e["type"] == "relation" and e["tags"].get("network") == "广州地铁"
    ]

    # 每条线路的 OSM 颜色
    colours: dict[str, str] = {}
    for rel in relations:
        tags = rel.get("tags", {})
        if "快车" in tags.get("name", "") or "ref" not in tags:
            continue
        if "colour" in tags:
            colours.setdefault(tags["ref"], tags["colour"])

    lines: list[tuple[str, str, str, float, list[str]]] = []
    for ref in sorted(grouped, key=lambda r: (len(r), r)):
        if ref not in LINE_META:
            print(f"跳过未配置的线路 ref={ref}", file=sys.stderr)
            continue
        prefix, base_name, speed = LINE_META[ref]
        color = colours.get(ref, PALETTE[len(lines) % len(PALETTE)])
        # 排序键包含站名序列，保证重新抓取的 JSON 元素顺序变化时输出不变
        items = sorted(grouped[ref], key=lambda it: (-len(it[1]), tuple(it[1])))
        items = maximal(items)
        main_name, main = items[0]
        main_label = segment_label(main_name)

        lines.append((
            f"L{prefix}{'A' if main_label else ''}",
            base_name + main_label,
            color, speed, main,
        ))

        for index, (name, seq) in enumerate(items[1:], 1):
            label = segment_label(name)
            if label:
                title = base_name + label
            else:
                ends = relation_endpoints(name)
                title = f"{base_name}（{ends[0]}—{ends[1]}）" if ends else f"{base_name}交路{index}"
            lines.append((f"L{prefix}{'BCDEFG'[index - 1]}", title, color, speed, seq))

    # ---- 站点合并：同名节点取平均坐标 --------------------------------
    used = {station for _, _, _, _, seq in lines for station in seq}
    groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for node in nodes.values():
        name = node.get("tags", {}).get("name")
        if name in used:
            groups[name].append(project(node["lat"], node["lon"]))

    missing = used - set(groups)
    if missing:
        raise SystemExit(f"以下站点没有坐标：{sorted(missing)}")

    for name, points in groups.items():
        # 逐对比较：质心距离会把两个相距接近 2×阈值 的异站误判为可合并
        spread = max(
            (dist(a, b) for i, a in enumerate(points) for b in points[i + 1:]),
            default=0.0,
        )
        if spread > MAX_MERGE_KM:
            raise SystemExit(f"同名站点「{name}」最大间距 {spread:.2f} km，拒绝合并")

    station_ids: dict[str, str] = {}
    stations: list[dict] = []
    for _, _, _, _, seq in lines:
        for name in seq:
            if name in station_ids:
                continue
            points = groups[name]
            x = sum(p[0] for p in points) / len(points)
            y = sum(p[1] for p in points) / len(points)
            sid = f"S{len(stations) + 1:03d}"
            station_ids[name] = sid
            stations.append({"id": sid, "name": name, "x": round(x, 4), "y": round(y, 4)})

    payload_out = {
        "city": "广州（OpenStreetMap 公开数据还原）",
        "stations": stations,
        "lines": [
            {
                "id": lid,
                "name": name,
                "color": color,
                "speed": speed,
                "detour": DETOUR,
                "stations": [station_ids[s] for s in seq],
            }
            for lid, name, color, speed, seq in lines
        ],
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(payload_out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"站点 {len(stations)} 个，线路 {len(lines)} 条 -> {TARGET}")
    for lid, name, color, speed, seq in lines:
        closed = "（环线闭合）" if len(seq) > 1 and seq[0] == seq[-1] else ""
        print(f"  {lid:6s} {name:12s} {len(seq):3d} 站 {color} {speed:.0f} km/h{closed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
