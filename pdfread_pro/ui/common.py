"""Hàm định dạng và hộp thoại danh sách dùng chung."""
from __future__ import annotations

import os
import subprocess
from typing import Callable, List, Optional, Sequence

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..core.models import FileInfo


def fmt(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def fmt_size(n: int) -> str:
    x = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if x < 1024 or u == "GB":
            return f"{x:.0f} {u}" if u == "B" else f"{x:.1f} {u}".replace(".", ",")
        x /= 1024
    return str(n)


SIG_TEXT = {
    "ok": ("✔ Còn nguyên", "#15803D"),
    "modified": ("⚠ Sửa sau khi ký", "#B45309"),
    "broken": ("✖ Đã hỏng", "#DC2626"),
    "unreadable": ("? Không đọc được", "#DC2626"),
    "none": ("— Chưa ký", "#64748B"),
}

REVIEW_TEXT = {
    "sig_no_name": "Có chữ ký số thật nhưng tên chưa có .signed",
    "name_no_sig": "Tên có .signed nhưng file không có chữ ký số",
    "unreadable": "Không đọc được chữ ký số",
    "error": "File lỗi / có mật khẩu",
}


def sig_label(f: FileInfo):
    if f.error:
        return "✖ " + f.error, "#DC2626"
    if f.sig_status == "none" and f.name_signed:
        return "✖ Không có (tên .signed)", "#DC2626"
    return SIG_TEXT.get(f.sig_status, SIG_TEXT["none"])


def who_when(f: FileInfo) -> str:
    parts = []
    if f.sign_time:
        parts.append(f.sign_time.strftime("%d/%m/%Y %H:%M"))
    if f.signers:
        parts.append(" → ".join(f.signers))
    return " · ".join(parts)


def open_path(path: str) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def reveal(path: str) -> None:
    try:
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            open_path(path)
    except OSError:
        open_path(os.path.dirname(path))


class ListDialog(QDialog):
    """Bảng danh sách đơn giản có ô tìm kiếm; bấm đôi mở file/thư mục."""

    def __init__(self, parent, title: str, subtitle: str, columns: Sequence[str],
                 rows: List[Sequence], paths: Optional[List[str]] = None,
                 widths: Optional[Sequence[int]] = None, colors: Optional[List[Optional[str]]] = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(980, 560)
        self._paths = paths or []
        lay = QVBoxLayout(self)
        head = QLabel(f"<b style='font-size:12pt;color:#1E40AF'>{title}</b><br>"
                      f"<span style='color:#475569'>{subtitle}</span>")
        head.setWordWrap(True)
        lay.addWidget(head)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Tìm trong danh sách…")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.table = QTableWidget(len(rows), len(columns))
        self.table.setHorizontalHeaderLabels(list(columns))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                it = QTableWidgetItem(str(val))
                if isinstance(val, (int, float)):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if colors and colors[r] and c == len(row) - 1:
                    it.setForeground(QColor(colors[r]))
                self.table.setItem(r, c, it)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, w in enumerate(widths or []):
            self.table.setColumnWidth(i, w)
        self.table.cellDoubleClicked.connect(self._open)
        lay.addWidget(self.table, 1)
        bot = QHBoxLayout()
        self.count = QLabel(f"{fmt(len(rows))} mục")
        bot.addWidget(self.count)
        bot.addStretch(1)
        if self._paths:
            b = QPushButton("📂 Mở thư mục chứa")
            b.clicked.connect(self._reveal)
            bot.addWidget(b)
        close = QPushButton("Đóng")
        close.clicked.connect(self.accept)
        bot.addWidget(close)
        lay.addLayout(bot)

    def _cur_path(self) -> str:
        r = self.table.currentRow()
        return self._paths[r] if 0 <= r < len(self._paths) else ""

    def _open(self, row, col):
        p = self._cur_path()
        if p and os.path.exists(p):
            open_path(p)

    def _reveal(self):
        p = self._cur_path()
        if p:
            reveal(p)

    def _filter(self, text: str):
        t = text.strip().lower()
        shown = 0
        for r in range(self.table.rowCount()):
            hit = not t or any(t in (self.table.item(r, c).text().lower())
                               for c in range(self.table.columnCount()))
            self.table.setRowHidden(r, not hit)
            shown += hit
        self.count.setText(f"{fmt(shown)} mục")
