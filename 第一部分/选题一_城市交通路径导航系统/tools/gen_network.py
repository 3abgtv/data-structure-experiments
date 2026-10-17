"""生成实验用的城市轨道网络数据文件。

产出两份数据：

    data/metro/network.json   65 站 / 10 条线的完整网络，用于性能对比与演示
    data/demo/network.json    15 站 / 3 条线的小型网络，用于手工验证算法的正确性

之所以用脚本而不是直接手敲 JSON，是为了让拓扑约束由代码保证：

    * 直径线与环线的交点必须是**同一个站点 ID**（否则不成其为换乘站）；
    * 绕行系数 detour ≥ 1，保证"边长 ≥ 直线距离"，
      从而 A* 的启发函数 h 不会高估真实代价；
    * 随机抖动使用固定种子，任何人重跑都能得到完全相同的数据。

用法：  py tools/gen_network.py
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SEED = 20260117

# ----------------------------------------------------------------------
# 站名池：按线路语义分配，保证全局唯一
# ----------------------------------------------------------------------
RING_NAMES = [
    "中央广场", "东风路", "翠湖", "望江门", "青云路", "梅园", "金桥", "兰亭",
    "玉泉", "凤山", "静安寺", "桂香路", "松林", "月湖", "银都", "朝晖门",
]
SPOKE_NAMES = [  # 直径线由中心向外，四条线各 8 个独有站
    "西苑", "和平门", "文化宫", "西直门", "东直门", "体育馆", "朝阳门", "东苑",
    "南浦", "体育中心", "文昌阁", "南门口", "北门口", "钟鼓楼", "科技园", "北苑",
    "西码头", "白鹭洲", "图书馆", "西大桥", "东大桥", "锦江里", "青云塔", "东码头",
    "南庄", "海棠湾", "人民医院", "南湖桥", "北湖桥", "大学城", "银杏道", "北庄",
]
CENTER_NAME = "人民广场"
OUTER_NAMES = [  # 四条外围线各 4 个独有站
    "新港", "云台山", "航空港", "天工园",
    "白鹿原", "碧云谷", "清水河", "枫叶镇",
    "望山", "星湖", "玉屏峰", "鸣沙湾",
    "南屿", "潮音洞", "金沙滩", "海门港",
]

LINE_COLORS = [
    "#E4002B", "#0072CE", "#00A551", "#FF9E1B", "#8A3FFC",
    "#00B5AD", "#D6267A", "#6B7A8F", "#B7791F", "#2D9CDB",
]


def polar(r: float, degrees: float, jitter: float, rng: random.Random) -> tuple[float, float]:
    """极坐标转直角坐标，并加一点随机抖动，让布局不至于过分规整。"""
    rad = math.radians(degrees)
    rr = r + rng.uniform(-jitter, jitter)
    dx = rng.uniform(-jitter, jitter) * 0.5
    dy = rng.uniform(-jitter, jitter) * 0.5
    return round(rr * math.cos(rad) + dx, 3), round(rr * math.sin(rad) + dy, 3)


# ----------------------------------------------------------------------
# 大型网络：1 条环线 + 4 条穿心直径线 + 4 条外围线
# ----------------------------------------------------------------------
def build_metro() -> dict:
    rng = random.Random(SEED)
    stations: list[dict] = []
    lines: list[dict] = []
    used_names: set[str] = set()

    def take(pool: list[str], index: int) -> str:
        name = pool[index]
        if name in used_names:                     # 极小概率撞名时补后缀
            suffix = 2
            while f"{name}{suffix}" in used_names:
                suffix += 1
            name = f"{name}{suffix}"
        used_names.add(name)
        return name

    def add_station(vid: str, name: str, x: float, y: float) -> str:
        stations.append({"id": vid, "name": name,
                         "x": round(x, 3), "y": round(y, 3)})
        return vid

    # ---- 环线：半径 6 km，16 个站，每 22.5° 一个 ----
    ring_radius = 6.0
    ring_ids: list[str] = []
    for i in range(16):
        angle = 22.5 * i
        x, y = polar(ring_radius, angle, 0.22, rng)
        vid = f"R{i + 1:02d}"
        add_station(vid, take(RING_NAMES, i), x, y)
        ring_ids.append(vid)

    # ---- 中心枢纽 ----
    center_id = add_station("C01", CENTER_NAME, 0.0, 0.0)

    # ---- 4 条直径线：穿过中心，方向 0° / 45° / 90° / 135° ----
    spoke_radii = [3.0, 6.0, 9.0, 12.5, 16.0]           # 6.0 正好落在环线上
    spoke_angles = [0.0, 45.0, 90.0, 135.0]
    name_cursor = 0

    for s, angle in enumerate(spoke_angles):
        seq: list[str] = []
        # 负半轴方向与正半轴正好相差 180°，对应环线上的站点相隔 8 个
        # （环线每 22.5° 一站，180° / 22.5° = 8）。两个方向必须各自
        # 找到自己那一侧的环线站，否则直径线会在环线上折返。
        steps = int(round(angle / 22.5))
        back_index = (steps + 8) % 16
        front_index = steps % 16

        # 负方向：由远及近
        for k, r in enumerate(reversed(spoke_radii)):
            if abs(r - ring_radius) < 1e-6:
                # 与环线重合 —— 复用环线站点，形成换乘
                seq.append(ring_ids[back_index])
            else:
                x, y = polar(r, angle + 180, 0.25, rng)
                vid = f"S{s + 1}{k:02d}W"
                add_station(vid, take(SPOKE_NAMES, name_cursor), x, y)
                name_cursor += 1
                seq.append(vid)

        seq.append(center_id)          # 经过中心枢纽

        # 正方向：由近及远
        for k, r in enumerate(spoke_radii):
            if abs(r - ring_radius) < 1e-6:
                seq.append(ring_ids[front_index])
            else:
                x, y = polar(r, angle, 0.25, rng)
                vid = f"S{s + 1}{k:02d}E"
                add_station(vid, take(SPOKE_NAMES, name_cursor), x, y)
                name_cursor += 1
                seq.append(vid)

        lines.append({
            "id": f"D{s + 1}", "name": f"{s + 1} 号线",
            "color": LINE_COLORS[s], "speed": 46.0, "detour": 1.08,
            "stations": seq,
        })

    # ---- 4 条外围线：从环线上的站向外辐射，不经过中心 ----
    outer_angles = [22.5, 67.5, 112.5, 157.5]
    outer_radii = [9.0, 12.5, 16.0, 20.0]
    name_cursor = 0

    for o, angle in enumerate(outer_angles):
        index = int(round(angle / 22.5)) % 16
        seq = [ring_ids[index]]
        for k, r in enumerate(outer_radii):
            x, y = polar(r, angle, 0.3, rng)
            vid = f"O{o + 1}{k:02d}"
            add_station(vid, take(OUTER_NAMES, name_cursor), x, y)
            name_cursor += 1
            seq.append(vid)
        lines.append({
            "id": f"E{o + 1}", "name": f"{o + 5} 号线",
            "color": LINE_COLORS[o + 4], "speed": 52.0, "detour": 1.10,
            "stations": seq,
        })

    # ---- 环线本身 ----
    lines.append({
        "id": "R", "name": "环线", "color": LINE_COLORS[8], "speed": 44.0,
        "detour": 1.06, "stations": ring_ids + [ring_ids[0]],
    })

    return {"city": "示例市", "stations": stations, "lines": lines}


# ----------------------------------------------------------------------
# 小型网络：3 条线 15 站，拓扑简单，便于在报告里手工推演核对
# ----------------------------------------------------------------------
def build_demo() -> dict:
    """13 站 / 4 条线的小网络，拓扑经过专门设计。

    设计要点：从 A1 到 C3 存在两条走法 ——

        甲路：A1 —(1 号线)→ A5 —(3 号线)→ C3      换乘 1 次，16.29 km
        乙路：A1 —(1 号线)→ A3 —(2 号线)→ B4
                 —(4 号线)→ C3                     换乘 2 次，14.30 km

    1 号线故意把 A4 抬高到 y=2.5 绕了一段远路，使得"换乘多但路程短"
    与"换乘少但路程长"两种情况同时存在。Dijkstra 会选乙路，最少换乘
    BFS 会选甲路 —— 这正是报告第四章要对比的现象。

    E1「孤岛站」不与任何线路相连，用于验证不连通时的异常处理。
    """
    raw = [
        ("A1", "东湖", 0.0, 0.0),
        ("A2", "文化路", 1.5, 0.0),
        ("A3", "中转站", 3.0, 0.0),
        ("A4", "山前", 6.0, 2.5),          # 抬高，让 1 号线绕远
        ("A5", "新港", 9.0, 0.0),

        ("B1", "河西", 3.0, 1.0),
        ("B2", "开发区", 3.0, 2.0),
        ("B3", "科技园", 3.0, 3.0),
        ("B4", "北苑", 3.0, 4.0),

        ("C1", "南门", 9.0, 1.5),
        ("C2", "湖心岛", 9.0, 2.75),
        ("C3", "西山", 9.0, 4.0),

        ("D1", "亭子桥", 6.0, 4.0),

        ("E1", "孤岛站", 11.5, -1.5),      # 孤立站点，用于不连通测试
    ]
    stations = [{"id": i, "name": n, "x": x, "y": y} for i, n, x, y in raw]

    lines = [
        {"id": "L1", "name": "1 号线", "color": "#E4002B", "speed": 40.0,
         "detour": 1.10, "stations": ["A1", "A2", "A3", "A4", "A5"]},
        {"id": "L2", "name": "2 号线", "color": "#0072CE", "speed": 40.0,
         "detour": 1.10, "stations": ["A3", "B1", "B2", "B3", "B4"]},
        {"id": "L3", "name": "3 号线", "color": "#00A551", "speed": 40.0,
         "detour": 1.10, "stations": ["A5", "C1", "C2", "C3"]},
        {"id": "L4", "name": "4 号线", "color": "#FF9E1B", "speed": 40.0,
         "detour": 1.10, "stations": ["B4", "D1", "C3"]},
    ]
    return {"city": "演示市", "stations": stations, "lines": lines}


# ----------------------------------------------------------------------
def dump(network: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(network, ensure_ascii=False, indent=2), encoding="utf-8")
    stations, lines = network["stations"], network["lines"]
    hops = sum(len(l["stations"]) - 1 for l in lines)
    print(f"  {path.relative_to(ROOT)}  "
          f"{len(stations)} 站 / {len(lines)} 线 / {hops} 段")


def main() -> None:
    print("生成数据文件：")
    dump(build_metro(), ROOT / "data" / "metro" / "network.json")
    dump(build_demo(), ROOT / "data" / "demo" / "network.json")
    print("完成。随机种子 =", SEED)


if __name__ == "__main__":
    main()
