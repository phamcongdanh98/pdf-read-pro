"""Đường dẫn dữ liệu người dùng và tài nguyên."""
from __future__ import annotations

import os
import sys

APP_NAME = "PDF-Read Pro"
APP_VERSION = "1.9.1"


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


def make_settings():
    """QSettings của app (Registry). Biến môi trường PDFREADPRO_SETTINGS_INI trỏ tới 1 file .ini → dùng file đó
    (các bài test dùng để KHÔNG đụng vào cài đặt thật của người dùng)."""
    from PySide6.QtCore import QSettings
    ini = os.environ.get("PDFREADPRO_SETTINGS_INI")
    return QSettings(ini, QSettings.IniFormat) if ini else QSettings("PDFReadPro", "PDFReadPro")
