"""Vẽ icon giao diện (ô tích, nút chọn, mũi tên) bằng QPainter rồi lưu PNG để stylesheet dùng –
giống Hồ sơ 1361 dùng ảnh riêng cho ô tích; không phụ thuộc giao diện Windows sáng/tối."""
from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF

from .. import paths

_SCALE = 3          # vẽ lớn để sắc nét trên màn hình độ phân giải cao
_VERSION = "v2"


def _canvas(w: int, h: int) -> QImage:
    img = QImage(w * _SCALE, h * _SCALE, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    return img


def _painter(img: QImage) -> QPainter:
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(_SCALE, _SCALE)
    return p


def _checkbox(checked: bool, disabled: bool = False) -> QImage:
    img = _canvas(18, 18)
    p = _painter(img)
    r = QRectF(1, 1, 16, 16)
    if checked:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#CBD5E1" if disabled else "#2563EB"))
        p.drawRoundedRect(r, 4, 4)
        pen = QPen(QColor("#FFFFFF"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        path = QPainterPath(QPointF(4.8, 9.3))
        path.lineTo(7.8, 12.2)
        path.lineTo(13.4, 5.8)
        p.drawPath(path)
    else:
        p.setPen(QPen(QColor("#CBD5E1" if disabled else "#94A3B8"), 1.4))
        p.setBrush(QColor("#F1F5F9" if disabled else "#FFFFFF"))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
    p.end()
    return img


def _radio(checked: bool) -> QImage:
    img = _canvas(18, 18)
    p = _painter(img)
    p.setPen(QPen(QColor("#2563EB" if checked else "#94A3B8"), 1.5))
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(QRectF(1.5, 1.5, 15, 15))
    if checked:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2563EB"))
        p.drawEllipse(QRectF(5, 5, 8, 8))
    p.end()
    return img


def _arrow(direction: str, color: str = "#475569") -> QImage:
    img = _canvas(10, 6)
    p = _painter(img)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    pts = [QPointF(0.5, 0.5), QPointF(9.5, 0.5), QPointF(5, 5.5)] if direction == "down" else \
        [QPointF(0.5, 5.5), QPointF(9.5, 5.5), QPointF(5, 0.5)]
    p.drawPolygon(QPolygonF(pts))
    p.end()
    return img


def ensure_icons() -> dict:
    """Tạo (một lần) và trả về {tên: đường dẫn dạng / cho QSS}."""
    d = os.path.join(paths.data_dir(), "ui_icons", _VERSION)
    os.makedirs(d, exist_ok=True)
    makers = {
        "chk_off": lambda: _checkbox(False), "chk_on": lambda: _checkbox(True),
        "chk_off_dis": lambda: _checkbox(False, True), "chk_on_dis": lambda: _checkbox(True, True),
        "radio_off": lambda: _radio(False), "radio_on": lambda: _radio(True),
        "arrow_down": lambda: _arrow("down"), "arrow_up": lambda: _arrow("up"),
        "arrow_down_dis": lambda: _arrow("down", "#CBD5E1"),
    }
    out = {}
    for name, make in makers.items():
        path = os.path.join(d, name + ".png")
        if not os.path.exists(path):
            make().save(path)
        out[name] = path.replace("\\", "/")
    return out


def icon_style() -> str:
    i = ensure_icons()
    return f"""
QCheckBox::indicator, QTableWidget::indicator, QTreeWidget::indicator, QListWidget::indicator {{ width: 18px; height: 18px; }}
QCheckBox::indicator:unchecked, QTableWidget::indicator:unchecked, QListWidget::indicator:unchecked {{ image: url("{i['chk_off']}"); }}
QCheckBox::indicator:checked, QTableWidget::indicator:checked, QListWidget::indicator:checked {{ image: url("{i['chk_on']}"); }}
QCheckBox::indicator:unchecked:disabled {{ image: url("{i['chk_off_dis']}"); }}
QCheckBox::indicator:checked:disabled {{ image: url("{i['chk_on_dis']}"); }}
QRadioButton::indicator {{ width: 18px; height: 18px; }}
QRadioButton::indicator:unchecked {{ image: url("{i['radio_off']}"); }}
QRadioButton::indicator:checked {{ image: url("{i['radio_on']}"); }}
QComboBox::down-arrow {{ image: url("{i['arrow_down']}"); width: 10px; height: 6px; }}
QComboBox::down-arrow:disabled {{ image: url("{i['arrow_down_dis']}"); }}
QSpinBox::up-arrow {{ image: url("{i['arrow_up']}"); width: 8px; height: 5px; }}
QSpinBox::down-arrow {{ image: url("{i['arrow_down']}"); width: 8px; height: 5px; }}
"""
