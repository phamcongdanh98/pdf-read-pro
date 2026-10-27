"""Hộp chọn 1 file PDF trong thư mục đã quét: ô tìm kiếm (không cần gõ dấu) + cây theo thư mục, thay cho danh sách
thả xuống dài hàng nghìn dòng."""
from __future__ import annotations

import unicodedata
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from ..core.models import FileInfo
from .common import fmt, fmt_size

ROLE = Qt.UserRole


def fold(text: str) -> str:
    """Bỏ dấu + chữ thường để tìm kiếm ("hoa" khớp "Hòa", "đ" khớp "d")."""
    t = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").casefold()


class FilePickerDialog(QDialog):
    def __init__(self, parent, files: List[FileInfo], current: str = "", title: str = "Chọn file PDF"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 600)
        self.files = files
        self.current = current
        self.selected: Optional[str] = None
        self._keys = [(fold(f.name), fold(f.dir_rel)) for f in files]

        lay = QVBoxLayout(self)
        r = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Gõ tên file, CCCD, tên người hoặc thư mục… (không cần dấu)")
        self.search.setClearButtonEnabled(True)
        r.addWidget(self.search, 1)
        self.ck_multi = QCheckBox("Ẩn file 1 trang")
        self.ck_multi.setToolTip("File cần tách thường có nhiều trang")
        r.addWidget(self.ck_multi)
        lay.addLayout(r)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Thư mục / Tên file", "Số trang", "Dung lượng"])
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 560)
        self.tree.setColumnWidth(1, 80)
        self.tree.itemDoubleClicked.connect(lambda it, c: self._accept_item(it))
        self.tree.itemSelectionChanged.connect(self._sel_changed)
        lay.addWidget(self.tree, 1)
        self.lbl = QLabel("")
        self.lbl.setObjectName("Hint")
        lay.addWidget(self.lbl)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Chọn file này")
        bb.button(QDialogButtonBox.Cancel).setText("Huỷ")
        bb.accepted.connect(lambda: self._accept_item(self.tree.currentItem()))
        bb.rejected.connect(self.reject)
        self.ok_btn = bb.button(QDialogButtonBox.Ok)
        lay.addWidget(bb)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.fill)
        self.search.textChanged.connect(lambda: self._timer.start())
        self.ck_multi.toggled.connect(self.fill)
        self.fill()
        self.search.setFocus()

    def fill(self):
        q = fold(self.search.text().strip())
        words = q.split()
        hide1 = self.ck_multi.isChecked()
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        groups = {}
        shown = 0
        cur_item = None
        for f, (kn, kd) in zip(self.files, self._keys):
            if hide1 and f.pages == 1:
                continue
            if words and not all(w in kn or w in kd for w in words):
                continue
            g = groups.get(f.dir_rel)
            if g is None:
                g = QTreeWidgetItem([f"📁 {f.dir_rel or '(thư mục gốc)'}", "", ""])
                g.setFlags(g.flags() & ~Qt.ItemIsSelectable)
                groups[f.dir_rel] = g
                self.tree.addTopLevelItem(g)
            it = QTreeWidgetItem([f.name, "?" if f.pages is None else str(f.pages), fmt_size(f.size)])
            it.setData(0, ROLE, f.path)
            it.setTextAlignment(1, Qt.AlignCenter)
            it.setToolTip(0, f.path)
            g.addChild(it)
            shown += 1
            if f.path == self.current:
                cur_item = it
        for g in groups.values():
            g.setText(1, str(g.childCount()))
        # tìm kiếm / ít nhóm → mở hết; nhiều nhóm → chỉ mở nhóm chứa file đang chọn
        if words or len(groups) <= 12:
            self.tree.expandAll()
        if cur_item is not None:
            cur_item.parent().setExpanded(True)
            self.tree.setCurrentItem(cur_item)
            self.tree.scrollToItem(cur_item, QAbstractItemView.PositionAtCenter)
        elif words and shown:
            first = self.tree.topLevelItem(0).child(0)
            self.tree.setCurrentItem(first)
        self.tree.setUpdatesEnabled(True)
        self.lbl.setText(f"{fmt(shown)} / {fmt(len(self.files))} file · {fmt(len(groups))} thư mục · "
                         "bấm đôi (hoặc Enter) để chọn")
        self._sel_changed()

    def _sel_changed(self):
        it = self.tree.currentItem()
        self.ok_btn.setEnabled(bool(it and it.data(0, ROLE)))

    def _accept_item(self, it):
        if it and it.data(0, ROLE):
            self.selected = it.data(0, ROLE)
            self.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._accept_item(self.tree.currentItem())
            return
        if e.key() in (Qt.Key_Down, Qt.Key_Up) and self.search.hasFocus():
            self.tree.setFocus()
            self.tree.keyPressEvent(e)
            return
        super().keyPressEvent(e)


def pick(parent, files: List[FileInfo], current: str = "", title: str = "Chọn file PDF") -> Optional[str]:
    if not files:
        return None
    d = FilePickerDialog(parent, files, current, title)
    return d.selected if d.exec() == QDialog.Accepted else None


def neighbor(files: List[FileInfo], current: str, step: int) -> Optional[str]:
    """File liền trước / sau `current` trong danh sách (để duyệt nhanh từng file)."""
    paths = [f.path for f in files]
    if not paths:
        return None
    if current not in paths:
        return paths[0] if step > 0 else paths[-1]
    i = paths.index(current) + step
    return paths[i] if 0 <= i < len(paths) else None

