"""Đường dẫn dữ liệu người dùng và tài nguyên."""
from __future__ import annotations

import os
import sys

APP_NAME = "PDF-Read Pro"
APP_VERSION = "1.9.0"


def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "PDFReadPro")
    os.makedirs(d, exist_ok=True)
    return d


def data_file(name: str) -> str:
    return os.path.join(data_dir(), name)


def icon_path() -> str:
    """assets/app.ico – cạnh mã nguồn khi chạy py, trong thư mục giải nén khi chạy exe (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", "app.ico")
