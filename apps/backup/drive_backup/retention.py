"""Имена файлов копий и правило хранения."""

from __future__ import annotations

import datetime as dt
import re

FILE_RE = re.compile(r"^cats-house-(\d{4}-\d{2}-\d{2})T(\d{4})Z\.dump$")


def backup_name(moment: dt.datetime) -> str:
    utc = moment.astimezone(dt.timezone.utc)
    return f"cats-house-{utc:%Y-%m-%dT%H%M}Z.dump"


def names_to_trash(names: list[str], today: dt.date, keep_days: int = 30, keep_months: int = 12) -> list[str]:
    """Оставляем самую новую копию, последнюю за каждый из keep_days дней и за каждый из keep_months месяцев."""
    parsed = sorted((name, dt.date.fromisoformat(m.group(1))) for name in names if (m := FILE_RE.match(name)))
    if not parsed:
        return []
    keep = {parsed[-1][0]}
    latest_by_day: dict[dt.date, str] = {}
    latest_by_month: dict[tuple[int, int], str] = {}
    for name, day in parsed:
        latest_by_day[day] = name
        latest_by_month[(day.year, day.month)] = name
    for day, name in latest_by_day.items():
        if (today - day).days < keep_days:
            keep.add(name)
    this_month = today.year * 12 + today.month
    for (year, month), name in latest_by_month.items():
        if this_month - (year * 12 + month) < keep_months:
            keep.add(name)
    return [name for name, _ in parsed if name not in keep]
