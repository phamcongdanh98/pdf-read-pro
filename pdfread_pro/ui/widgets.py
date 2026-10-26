"""Widget dùng chung: thẻ thống kê tự co giãn (không bao giờ cắt chữ), nhãn rút gọn."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget


class ElidedLabel(QLabel):
    """Một dòng; quá dài thì rút gọn bằng … và hiện đủ nội dung trong tooltip."""

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(10)
        self.set_full_text(text)

    def set_full_text(self, text: str, tooltip: str | None = None) -> None:
        self._full = text
        self.setToolTip(tooltip if tooltip is not None else text)
        self._apply()

    def _apply(self) -> None:
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, Qt.ElideRight, max(10, self.width())))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply()


class StatCard(QFrame):
    """Thẻ: tiêu đề nhỏ · một số lớn · một dòng phụ. Các thẻ cao bằng nhau."""
    clicked = Signal(str)

    ACCENTS = {"blue": "#2563EB", "green": "#15803D", "violet": "#7C3AED",
               "teal": "#0F766E", "amber": "#B45309", "red": "#DC2626"}

    def __init__(self, key: str, title: str, accent: str = "blue", parent: QWidget | None = None):
        super().__init__(parent)
        self.key = key
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(92)
        self.setMaximumHeight(92)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(2)
        self.title = ElidedLabel(title)
        self.title.setStyleSheet("color:#64748B; font-size:8pt; font-weight:700; letter-spacing:0.5px;")
        self.value = QLabel("0")
        self.value.setStyleSheet(f"color:{self.ACCENTS[accent]}; font-size:24pt; font-weight:800;")
        self.sub = ElidedLabel("")
        self.sub.setStyleSheet("color:#475569; font-size:9pt;")
        lay.addWidget(self.title)
        lay.addWidget(self.value)
        lay.addWidget(self.sub)
        self.accent = accent

    def set_accent(self, accent: str) -> None:
        self.accent = accent
        self.value.setStyleSheet(f"color:{self.ACCENTS[accent]}; font-size:24pt; font-weight:800;")

    def set_data(self, value: str, sub: str, tooltip: str = "") -> None:
        self.value.setText(value)
        self.sub.set_full_text(sub, tooltip or sub)
        self.setToolTip(tooltip or sub)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.key)
        super().mouseReleaseEvent(e)
