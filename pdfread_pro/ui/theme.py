"""Giao diện TỐI cho các màu viết thẳng trong từng tab (chữ xanh/đỏ/cam, nền dòng bảng, HTML...).

Các tab vẫn viết màu theo giao diện sáng. Module này bọc các hàm đặt màu dùng chung của Qt
(QLabel.setText, QWidget.setStyleSheet, QTextEdit.setHtml, setForeground/setBackground của dòng bảng/cây):
- luôn LƯU bản màu sáng gốc (thuộc tính / data role riêng),
- đang ở giao diện tối thì HIỂN THỊ bản đã đổi màu theo bảng LIGHT_TO_DARK.
Đổi giao diện khi đang chạy → recolor_all() vẽ lại mọi thứ từ bản gốc, nên đổi qua lại bao nhiêu lần cũng đúng."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QApplication, QLabel, QTableWidget, QTableWidgetItem, QTextEdit, QTreeWidget,
                               QTreeWidgetItem, QTreeWidgetItemIterator, QWidget)

# màu sáng (viết trong code các tab) → màu dễ đọc trên nền tối. #FFFFFF không đổi (chữ trắng trên nền màu,
# khung trang giấy PDF).
LIGHT_TO_DARK = {
    # chữ nhấn
    "#15803D": "#4ADE80", "#047857": "#34D399", "#059669": "#3DDBA5", "#10B981": "#34D3A0", "#0F766E": "#2DD4BF",
    "#B91C1C": "#F87171", "#DC2626": "#FB7A7A", "#EF4444": "#FC8888", "#E11D48": "#FB7185", "#BE123C": "#FDA4AF",
    "#9F1239": "#FECDD3", "#B45309": "#FBBF24", "#92400E": "#FCD34D", "#D97706": "#FBBF2A",
    "#1E40AF": "#90C2FC", "#1D4ED8": "#7DB0FA", "#1E3A8A": "#A5C8FD", "#2563EB": "#60A5FA", "#155E75": "#67E8F9",
    "#7C3AED": "#C4B5FD", "#6D28D9": "#B9A4FB", "#5B21B6": "#DDD6FE", "#6366F1": "#A9B4FD", "#4F46E5": "#A5B4FC",
    "#4338CA": "#C7D2FE",
    # chữ thường / phụ
    "#0F172A": "#E6EBF2", "#1E293B": "#DCE3EC", "#334155": "#C3CDDB", "#475569": "#A6B4C8", "#64748B": "#9AA9BE",
    "#94A3B8": "#76859B", "#CBD5E1": "#3A475D", "#E2E8F0": "#243044",
    # nền nhạt (dòng bảng, thẻ, ô tô màu)
    "#DCFCE7": "#14432A", "#BBF7D0": "#1B5E3A", "#FEE2E2": "#4C1D1D", "#FEF2F2": "#3F1C1C", "#FEF9C3": "#4A3B0B",
    "#FEF3C7": "#4A3A10", "#FDE68A": "#5C4A12", "#FFF7ED": "#3D2A14", "#FFEDD5": "#4A2E12", "#FED7AA": "#5A3514",
    "#DBEAFE": "#1E3A66", "#BFDBFE": "#2B4C8C", "#EFF6FF": "#172B4D", "#F8FAFC": "#0F1729", "#F1F5F9": "#172033",
}
assert not set(LIGHT_TO_DARK.values()) & set(LIGHT_TO_DARK), "màu tối trùng màu sáng"

_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
_P_SS, _P_TEXT, _P_HTML = "_theme_light_ss", "_theme_light_text", "_theme_light_html"
_ROLE = int(Qt.UserRole) + 700           # lưu màu gốc: _ROLE + 2*cột (chữ), _ROLE + 2*cột + 1 (nền)
_dark = False
_orig: dict = {}


def is_dark() -> bool:
    return _dark


def set_dark(on: bool) -> None:
    global _dark
    _dark = bool(on)


def tc(color: str) -> str:
    """Màu theo giao diện đang dùng (code tự vẽ – QPainter – gọi hàm này)."""
    return LIGHT_TO_DARK.get(color.upper(), color) if _dark else color


def map_text(text: str) -> str:
    """Đổi mọi mã màu #RRGGBB trong chuỗi (stylesheet, HTML) theo giao diện đang dùng."""
    if not _dark or "#" not in text:
        return text
    return _HEX.sub(lambda m: LIGHT_TO_DARK.get(m.group(0).upper(), m.group(0)), text)


# ------------------------------------------------------------------ bọc hàm đặt màu
def _set_ss(self, ss):
    has = isinstance(ss, str) and "#" in ss
    if has or self.property(_P_SS) is not None:
        self.setProperty(_P_SS, ss if has else None)
    _orig["ss"](self, map_text(ss) if has else ss)


def _set_text(self, text):
    has = isinstance(text, str) and "#" in text
    if has or self.property(_P_TEXT) is not None:
        self.setProperty(_P_TEXT, text if has else None)
    _orig["text"](self, map_text(text) if has else text)


def _set_html(self, html):
    has = isinstance(html, str) and "#" in html
    if has or self.property(_P_HTML) is not None:
        self.setProperty(_P_HTML, html if has else None)
    _orig["html"](self, map_text(html) if has else html)


def _brush(arg) -> QBrush:
    return arg if isinstance(arg, QBrush) else QBrush(QColor(arg) if isinstance(arg, str) else arg)


def _mapped(b: QBrush) -> QBrush:
    if not _dark or b.style() == Qt.NoBrush:
        return b
    name = b.color().name().upper()
    return QBrush(QColor(LIGHT_TO_DARK[name])) if name in LIGHT_TO_DARK else b


def _tree_fg(self, col, arg):
    b = _brush(arg)
    self.setData(col, _ROLE + 2 * col, b)
    _orig["tree_fg"](self, col, _mapped(b))


def _tree_bg(self, col, arg):
    b = _brush(arg)
    self.setData(col, _ROLE + 2 * col + 1, b)
    _orig["tree_bg"](self, col, _mapped(b))


def _table_fg(self, arg):
    b = _brush(arg)
    self.setData(_ROLE, b)
    _orig["table_fg"](self, _mapped(b))


def _table_bg(self, arg):
    b = _brush(arg)
    self.setData(_ROLE + 1, b)
    _orig["table_bg"](self, _mapped(b))


def install() -> None:
    """Bọc các hàm đặt màu (gọi 1 lần lúc khởi động, trước khi dựng giao diện)."""
    if _orig:
        return
    _orig.update(ss=QWidget.setStyleSheet, text=QLabel.setText, html=QTextEdit.setHtml,
                 tree_fg=QTreeWidgetItem.setForeground, tree_bg=QTreeWidgetItem.setBackground,
                 table_fg=QTableWidgetItem.setForeground, table_bg=QTableWidgetItem.setBackground)
    QWidget.setStyleSheet = _set_ss
    QLabel.setText = _set_text
    QTextEdit.setHtml = _set_html
    QTreeWidgetItem.setForeground = _tree_fg
    QTreeWidgetItem.setBackground = _tree_bg
    QTableWidgetItem.setForeground = _table_fg
    QTableWidgetItem.setBackground = _table_bg


def recolor_all(app: QApplication) -> None:
    """Vẽ lại mọi màu viết thẳng theo giao diện vừa chọn (từ bản màu sáng đã lưu)."""
    if not _orig:
        return
    for w in app.allWidgets():
        try:
            ss = w.property(_P_SS)
            if ss is not None:
                _orig["ss"](w, map_text(ss))
            if isinstance(w, QLabel):
                t = w.property(_P_TEXT)
                if t is not None:
                    _orig["text"](w, map_text(t))
            if isinstance(w, QTextEdit):
                h = w.property(_P_HTML)
                if h is not None:
                    _orig["html"](w, map_text(h))
            if isinstance(w, QTreeWidget):
                it = QTreeWidgetItemIterator(w)
                cols = w.columnCount()
                while it.value():
                    item = it.value()
                    for c in range(cols):
                        fg, bg = item.data(c, _ROLE + 2 * c), item.data(c, _ROLE + 2 * c + 1)
                        if fg is not None:
                            _orig["tree_fg"](item, c, _mapped(fg))
                        if bg is not None:
                            _orig["tree_bg"](item, c, _mapped(bg))
                    it += 1
            elif isinstance(w, QTableWidget):
                for r in range(w.rowCount()):
                    for c in range(w.columnCount()):
                        item = w.item(r, c)
                        if item is None:
                            continue
                        fg, bg = item.data(_ROLE), item.data(_ROLE + 1)
                        if fg is not None:
                            _orig["table_fg"](item, _mapped(fg))
                        if bg is not None:
                            _orig["table_bg"](item, _mapped(bg))
        except RuntimeError:            # widget đã bị xoá phía C++
            continue
