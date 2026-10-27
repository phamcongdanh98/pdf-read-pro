"""Tự lưu lựa chọn trên giao diện (ô tích, nút chọn, danh sách chọn, ô số, ô chữ) và mở lại đúng như lần trước;
“Khôi phục cài đặt gốc” đưa mọi thứ về mặc định.

Mỗi widget đăng ký 1 khoá `ui/<nhóm>/<tên thuộc tính>`. Giá trị mặc định = giá trị lúc dựng giao diện (trước khi
nạp lại). Lưu ngay khi đổi (tắt app đột ngột cũng không mất) và lưu thêm lần cuối khi đóng app."""
from __future__ import annotations

from typing import Iterable, List, Tuple

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QAbstractButton, QComboBox, QLineEdit, QSpinBox, QWidget

PREFIX = "ui/"
# khoá cũ (trước v1.8) / cài đặt khác được xoá khi khôi phục cài đặt gốc – giữ thư mục gần nhất & dữ liệu
RESET_KEYS = ("theme", "show_log", "recursive", "compress_limit_kb", "compress_clean", "check_rotate", "check_sort",
              "check_blank")


def _get(w: QWidget):
    if isinstance(w, QAbstractButton):
        return w.isChecked()
    if isinstance(w, QComboBox):
        d = w.currentData()
        return d if isinstance(d, str) and d else w.currentIndex()
    if isinstance(w, QSpinBox):
        return w.value()
    if isinstance(w, QLineEdit):
        return w.text()
    raise TypeError(type(w).__name__)


def _put(w: QWidget, v) -> None:
    try:
        if isinstance(w, QAbstractButton):
            w.setChecked(v in (True, "true", 1, "1"))
        elif isinstance(w, QComboBox):
            i = w.findData(v) if isinstance(v, str) and not v.lstrip("-").isdigit() else int(v)
            if 0 <= i < w.count():
                w.setCurrentIndex(i)
        elif isinstance(w, QSpinBox):
            w.setValue(int(v))
        elif isinstance(w, QLineEdit):
            w.setText(str(v))
    except (TypeError, ValueError):
        pass


def _signal(w: QWidget):
    if isinstance(w, QAbstractButton):
        return w.toggled
    if isinstance(w, QComboBox):
        return w.currentIndexChanged
    if isinstance(w, QSpinBox):
        return w.valueChanged
    return w.editingFinished


class Persist:
    def __init__(self, settings: QSettings):
        self.st = settings
        self.items: List[Tuple[str, QWidget, object, object]] = []   # khoá, widget, mặc định, chủ (panel)

    def bind(self, group: str, owner, names: Iterable[str]) -> None:
        for n in names:
            w = getattr(owner, n)
            self.items.append((f"{PREFIX}{group}/{n}", w, _get(w), owner))

    def _each_owner(self, fn):
        """Gọi fn() trên từng nhóm; panel có cờ `_loading` (vd Tách trang) được bật cờ khi nạp để không tự đổi mẫu."""
        owners = []
        for _, _, _, o in self.items:
            if o not in owners:
                owners.append(o)
        for o in owners:
            flag = hasattr(o, "_loading")
            if flag:
                o._loading = True
            try:
                fn(o)
            finally:
                if flag:
                    o._loading = False

    def restore(self) -> None:
        def load(owner):
            for key, w, _, o in self.items:
                if o is owner and self.st.contains(key):
                    _put(w, self.st.value(key))
        self._each_owner(load)
        for key, w, _, _ in self.items:
            _signal(w).connect(lambda *_, k=key, ww=w: self.st.setValue(k, _get(ww)))

    def save(self) -> None:
        for key, w, _, _ in self.items:
            self.st.setValue(key, _get(w))
        self.st.sync()

    def reset(self) -> None:
        def load(owner):
            for _, w, d, o in self.items:
                if o is owner:
                    _put(w, d)
        self._each_owner(load)
        for k in self.st.allKeys():
            if k.startswith(PREFIX) or k in RESET_KEYS:
                self.st.remove(k)
        self.st.sync()
