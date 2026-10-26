"""Nhật ký thao tác (ghi file, xem trong menu Hệ thống)."""
from __future__ import annotations

import os
from datetime import datetime
from typing import List

from ..paths import data_file

_MAX_BYTES = 1_000_000
_listeners = []


def add_listener(fn) -> None:
    """fn(thời_gian, thao_tác, chi_tiết) được gọi mỗi khi ghi nhật ký."""
    _listeners.append(fn)


def _path() -> str:
    return data_file("activity.log")


def log(action: str, detail: str = "") -> None:
    now = datetime.now()
    for fn in list(_listeners):
        try:
            fn(now, action, detail)
        except Exception:
            pass
    try:
        p = _path()
        if os.path.exists(p) and os.path.getsize(p) > _MAX_BYTES:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                tail = fh.readlines()[-2000:]
            with open(p, "w", encoding="utf-8") as fh:
                fh.writelines(tail)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now():%d/%m/%Y %H:%M:%S} | {action} | {detail}\n")
    except OSError:
        pass


def read_lines(limit: int = 500) -> List[str]:
    try:
        with open(_path(), "r", encoding="utf-8", errors="replace") as fh:
            return fh.readlines()[-limit:]
    except OSError:
        return []


def clear() -> None:
    try:
        open(_path(), "w", encoding="utf-8").close()
    except OSError:
        pass
