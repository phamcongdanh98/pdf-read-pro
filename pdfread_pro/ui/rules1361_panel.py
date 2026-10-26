"""Tab QUẢN LÝ BỘ QUY TẮC (mã số 1361) – bố cục theo Hồ sơ 1361: thêm/sửa/xoá, tìm kiếm, bảng 104+ quy tắc,
nhập/xuất .json/.txt, khôi phục mặc định. Bộ máy đổi tên đồng bộ ngay khi bộ quy tắc thay đổi."""
from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import activity, rules1361 as RS
from .common import fmt
from .styles import button


class Rules1361Panel(QWidget):
    rulesChanged = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.rules: Dict[str, str] = RS.load_rules()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        g = QGroupBox("Thêm hoặc chỉnh sửa Quy tắc Mã số")
        gl = QHBoxLayout(g)
        gl.addWidget(QLabel("Mã số / Mã phụ (Key):"))
        self.ed_key = QLineEdit()
        self.ed_key.setPlaceholderText("VD: 01, 07a, 86dh,...")
        self.ed_key.setFixedWidth(170)
        self.ed_key.textChanged.connect(self._key_typed)
        gl.addWidget(self.ed_key)
        gl.addSpacing(8)
        gl.addWidget(QLabel("Tên mẫu tiêu chuẩn:"))
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("VD: 86. Bang dai hoc  →  tự chuẩn hoá thành 86.Bang_dai_hoc")
        self.ed_name.returnPressed.connect(self.add_update)
        gl.addWidget(self.ed_name, 1)
        gl.addWidget(button("✚ Thêm / Cập Nhật", "success", self.add_update))
        gl.addWidget(button("🗑 Xóa Quy Tắc", "danger", self.delete))
        lay.addWidget(g)

        r = QHBoxLayout()
        r.addWidget(QLabel("<b>Tìm kiếm quy tắc:</b>"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Gõ mã số hoặc tên mẫu để lọc...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        r.addWidget(self.search, 1)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("StatusText")
        r.addWidget(self.lbl_count)
        lay.addLayout(r)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Mã Số Key", "Tên Mẫu Quy Tắc Tiêu Chuẩn"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 140)
        self.table.itemSelectionChanged.connect(self._row_selected)
        lay.addWidget(self.table, 1)

        bot = QHBoxLayout()
        bot.addWidget(button("📥 Nhập Tệp Quy Tắc (.json / .txt)...", "cyan", self.import_rules))
        bot.addWidget(button("📤 Xuất Tệp Quy Tắc (.json / .txt)...", "cyan", self.export_rules))
        bot.addStretch(1)
        bot.addWidget(button("♻ Reset bộ tiêu chí về mặc định", "warning", self.reset))
        lay.addLayout(bot)
        self.fill()

    # ------------------------------------------------------------------
    def fill(self, select: str = ""):
        items = RS.sorted_items(self.rules)
        self.table.setRowCount(len(items))
        sel_row = -1
        for r, (k, v) in enumerate(items):
            a = QTableWidgetItem(k)
            a.setTextAlignment(Qt.AlignCenter)
            f = a.font()
            f.setBold(True)
            a.setFont(f)
            a.setForeground(Qt.darkBlue)
            self.table.setItem(r, 0, a)
            b = QTableWidgetItem(v)
            b.setToolTip(v)
            self.table.setItem(r, 1, b)
            if k == select:
                sel_row = r
        self._filter(self.search.text())
        if sel_row >= 0:
            self.table.selectRow(sel_row)
            self.table.scrollToItem(self.table.item(sel_row, 0), QAbstractItemView.PositionAtCenter)

    def _filter(self, text: str):
        t = text.strip().lower()
        shown = 0
        for r in range(self.table.rowCount()):
            hit = not t or t in self.table.item(r, 0).text().lower() or t in self.table.item(r, 1).text().lower()
            self.table.setRowHidden(r, not hit)
            shown += hit
        self.lbl_count.setText(f"Tổng: {fmt(len(self.rules))} quy tắc" + (f" · đang lọc: {fmt(shown)}" if t else ""))

    def _row_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            r = rows[0].row()
            self.ed_key.blockSignals(True)
            self.ed_key.setText(self.table.item(r, 0).text())
            self.ed_key.blockSignals(False)
            self.ed_name.setText(self.table.item(r, 1).text())

    def _key_typed(self, text: str):
        k = RS.normalize_key(text)
        if k in self.rules:
            self.ed_name.setText(self.rules[k])

    def _commit(self, msg: str):
        RS.save_rules(self.rules)
        activity.log("Bộ quy tắc 1361", msg)
        self.rulesChanged.emit()

    # ------------------------------------------------------------------
    def add_update(self):
        key, name = RS.normalize_key(self.ed_key.text()), self.ed_name.text()
        err = RS.validate_rule(key, name)
        if err:
            QMessageBox.warning(self, "Quy tắc chưa hợp lệ", err)
            return
        name = RS.normalize_name(key, name)
        old = self.rules.get(key)
        if old == name:
            return
        if old is not None and QMessageBox.question(
                self, "Cập nhật quy tắc", f"Mã [{key}] đã có:\n{old}\n\nCập nhật thành:\n{name} ?") != QMessageBox.Yes:
            return
        self.rules[key] = name
        self.ed_name.setText(name)
        self._commit(f"{'Cập nhật' if old else 'Thêm'} [{key}] → {name}")
        self.fill(select=key)

    def delete(self):
        key = RS.normalize_key(self.ed_key.text())
        if key not in self.rules:
            QMessageBox.information(self, "Xóa quy tắc", "Hãy chọn một quy tắc trong bảng hoặc gõ đúng mã số cần xoá.")
            return
        if QMessageBox.question(self, "Xóa quy tắc", f"Xoá quy tắc [{key}] {self.rules[key]} ?") != QMessageBox.Yes:
            return
        del self.rules[key]
        self.ed_key.clear()
        self.ed_name.clear()
        self._commit(f"Xoá [{key}]")
        self.fill()

    def import_rules(self):
        p, _ = QFileDialog.getOpenFileName(self, "Nhập tệp bộ quy tắc", "", "JSON Files (*.json);;Text Files (*.txt)")
        if not p:
            return
        try:
            new = RS.parse_file(p)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Lỗi Nhập Quy Tắc", f"✖ Không thể nạp tệp quy tắc:\n{e}")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Nhập quy tắc")
        box.setText(f"Tệp có {len(new)} quy tắc.\n\nGộp vào bộ hiện tại (mã trùng sẽ được cập nhật) hay thay thế toàn bộ?")
        merge = box.addButton("Gộp vào", QMessageBox.AcceptRole)
        replace = box.addButton("Thay thế toàn bộ", QMessageBox.DestructiveRole)
        box.addButton("Huỷ", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is merge:
            self.rules.update(new)
        elif box.clickedButton() is replace:
            self.rules = dict(new)
        else:
            return
        self._commit(f"Nhập {len(new)} quy tắc từ {p}")
        self.fill()
        QMessageBox.information(self, "Nhập Quy Tắc Thành Công",
                                f"✔ Đã nạp từ tệp: {p}\n\nBộ máy đổi tên đã được đồng bộ thời gian thực!")

    def export_rules(self):
        p, _ = QFileDialog.getSaveFileName(self, "Xuất tệp bộ quy tắc", "QuyTacHoso1361.json",
                                           "JSON Files (*.json);;Text Files (*.txt)")
        if not p:
            return
        try:
            RS.export_file(self.rules, p)
        except OSError as e:
            QMessageBox.warning(self, "Lỗi Xuất Quy Tắc", f"✖ Không thể xuất tệp quy tắc:\n{e}")
            return
        QMessageBox.information(self, "Xuất Quy Tắc Thành Công", f"✔ Tệp đã lưu tại:\n{p}")

    def reset(self):
        n = len(RS.default_rules())
        if QMessageBox.question(self, "Xác nhận khôi phục",
                                f"Bạn có chắc chắn muốn khôi phục toàn bộ danh mục quy tắc về {n} tiêu chí mặc định ban đầu?"
                                ) != QMessageBox.Yes:
            return
        self.rules = RS.reset_defaults()
        activity.log("Bộ quy tắc 1361", "Khôi phục mặc định")
        self.rulesChanged.emit()
        self.fill()
        QMessageBox.information(self, "Khôi Phục Mặc Định", "Đã khôi phục bộ quy tắc chuẩn về mặc định thành công!")
