"""数据层：CSV / JSON 读写、字段校验与结果导出。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import ScheduleResult, Task

REQUIRED_FIELDS = ("task_id", "name", "arrival_time", "burst_time", "priority")

# 逐时间单位模拟，到达时刻过大只会让时钟空转。
MAX_ARRIVAL = 1_000_000


class DataError(ValueError):
    """任务数据不合法。"""


def _as_int(value, what: str):
    """转成整数；bool 是 int 的子类，要单独挡掉。"""
    if isinstance(value, bool):
        raise DataError(f"{what}必须是整数，实际为 {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise DataError(f"{what}必须是整数，实际为 {value}")
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError as exc:
            raise DataError(f"{what}必须是整数，实际为 {value!r}") from exc
    raise DataError(f"{what}必须是整数，实际为 {value!r}")


def validate(rows: list[dict], allow_duplicate_names: bool = True) -> list[Task]:
    """逐条校验并转换成 Task 列表。"""
    tasks: list[Task] = []
    seen: dict[str, int] = {}

    for index, row in enumerate(rows):
        missing = [f for f in REQUIRED_FIELDS if f not in row or row[f] in (None, "")]
        if missing:
            raise DataError(f"第 {index + 1} 条任务缺少字段：{'、'.join(missing)}")

        task_id = str(row["task_id"]).strip()
        name = str(row["name"]).strip()
        if not task_id:
            raise DataError(f"第 {index + 1} 条任务的编号为空")
        if not name:
            raise DataError(f"任务「{task_id}」的名称为空")
        if task_id in seen:
            raise DataError(
                f"任务编号重复：{task_id}（第 {seen[task_id] + 1} 条与第 {index + 1} 条）")

        arrival = _as_int(row["arrival_time"], f"任务「{task_id}」的到达时间")
        burst = _as_int(row["burst_time"], f"任务「{task_id}」的运行时长")
        priority = _as_int(row["priority"], f"任务「{task_id}」的优先级")

        if arrival < 0:
            raise DataError(f"任务「{task_id}」的到达时间不能为负：{arrival}")
        if arrival > MAX_ARRIVAL:
            raise DataError(
                f"任务「{task_id}」的到达时间过大：{arrival}"
                f"（上限 {MAX_ARRIVAL}）。模拟是逐时间单位推进的，"
                f"过大的到达时刻只会让时钟空转。")
        if burst <= 0:
            raise DataError(f"任务「{task_id}」的运行时长必须为正整数：{burst}")
        if priority < 0:
            raise DataError(f"任务「{task_id}」的优先级不能为负：{priority}")

        seen[task_id] = index
        tasks.append(Task(task_id=task_id, name=name, arrival_time=arrival,
                          burst_time=burst, priority=priority, seq=index))

    if not tasks:
        raise DataError("任务列表为空")
    return tasks


def check_quantum(value) -> int:
    """校验时间片：必须是正整数。"""
    quantum = _as_int(value, "时间片")
    if quantum <= 0:
        raise DataError(f"时间片必须是正整数，实际为 {quantum}")
    return quantum


def load_csv(path: str | Path) -> list[Task]:
    path = Path(path)
    try:
        # utf-8-sig 兼容 Excel 另存 CSV 时写在开头的 BOM。
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = [row for row in csv.DictReader(handle)
                    if any((v or "").strip() for v in row.values())]
    except FileNotFoundError as exc:
        raise DataError(f"找不到文件：{path}") from exc
    except OSError as exc:
        raise DataError(f"无法读取 {path}：{exc}") from exc

    if not rows:
        raise DataError(f"{path.name} 中没有任何任务")
    return validate(rows)


def load_json(path: str | Path) -> list[Task]:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"{path.name} 不是合法的 JSON：{exc}") from exc
    except OSError as exc:
        raise DataError(f"无法读取 {path}：{exc}") from exc

    items = raw.get("tasks") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise DataError("JSON 里应当是任务数组，或含 tasks 数组的对象")
    return validate(items)


def load_tasks(path: str | Path) -> list[Task]:
    """按扩展名自动选择读取方式。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return load_csv(path)
    if suffix == ".json":
        return load_json(path)
    raise DataError(f"不支持的文件类型：{suffix}（只支持 .csv 与 .json）")


# ----------------------------------------------------------------------
# 写出
# ----------------------------------------------------------------------
RESULT_HEADER = [
    "task_id", "name", "arrival_time", "burst_time", "priority",
    "start_time", "finish_time", "turnaround_time", "waiting_time", "response_time",
]


def export_result(result: ScheduleResult, path: str | Path) -> Path:
    """把统计结果写成 CSV，末尾追加平均值。"""
    path = Path(path)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(RESULT_HEADER)
        for row in result.rows():
            writer.writerow([
                row["task_id"], row["name"], row["arrival_time"], row["burst_time"],
                row["priority"], row["start_time"], row["finish_time"],
                row["turnaround_time"], row["waiting_time"], row["response_time"],
            ])
        writer.writerow([])
        writer.writerow(["平均值", "", "", "", "", "", "",
                         f"{result.avg_turnaround:.2f}",
                         f"{result.avg_waiting:.2f}",
                         f"{result.avg_response:.2f}"])
    return path


def export_tasks(tasks: list[Task], path: str | Path) -> Path:
    """把当前任务表写回 CSV。"""
    path = Path(path)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(REQUIRED_FIELDS))
        for task in tasks:
            writer.writerow([task.task_id, task.name, task.arrival_time,
                             task.burst_time, task.priority])
    return path
