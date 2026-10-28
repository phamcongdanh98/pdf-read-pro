"""Công cụ hồ sơ: kiểm tra đủ 5 file, thư mục CCCD, copy nhóm file."""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QProgressDialog, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..core import activity, tools as T
from ..core.models import FILTER_ALL, FILTER_SIGNED, FILTER_UNSIGNED, ScanResult
from .common import fmt, fmt_size, open_path


def _table(cols, widths) -> QTableWidget:
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(28)
    t.setAlternatingRowColors(True)
    hh = t.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.Interactive)
    hh.setStretchLastSection(True)
    for i, w in enumerate(widths):
        t.setColumnWidth(i, w)
    return t


class Check5Dialog(QDialog):
    def __init__(self, parent, result: ScanResult, scope: Optional[str]):
        super().__init__(parent)
        self.setWindowTitle("Kiểm tra đủ 5 file hồ sơ")
        self.resize(940, 580)
        self.result, self.scope = result, scope
        self.rows = T.check_five(result, scope)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b style='font-size:12pt;color:#1E40AF'>📋 Kiểm tra đủ 5 file (01. – 05.)</b><br>"
                             "<span style='color:#475569'>Mỗi thư mục có PDF trực tiếp phải có đủ 5 file PDF bắt đầu bằng "
                             "<b>01.</b> <b>02.</b> <b>03.</b> <b>04.</b> <b>05.</b> (viết <b>1.</b> thiếu số 0 vẫn nhận; 10., 11. không tính).</span>"))
        top = QHBoxLayout()
        self.ck_all = QCheckBox("Hiện cả thư mục đã đủ")
        self.ck_all.toggled.connect(self.fill)
        self.lbl = QLabel("")
        self.lbl.setStyleSheet("font-weight:700;color:#1E40AF")
        top.addWidget(self.lbl, 1)
        top.addWidget(self.ck_all)
        lay.addLayout(top)
        self.table = _table(["Thư mục", "Số PDF", "Thiếu", "Ghi chú"], [380, 80, 160, 260])
        self.table.cellDoubleClicked.connect(self.open_row)
        lay.addWidget(self.table, 1)
        bot = QHBoxLayout()
        self.btn_copy = QPushButton()
        self.btn_copy.clicked.connect(self.copy_missing)
        bot.addWidget(self.btn_copy)
        bot.addStretch(1)
        close = QPushButton("Đóng")
        close.clicked.connect(self.accept)
        bot.addWidget(close)
        lay.addLayout(bot)
        self.fill()

    def fill(self, *_):
        miss = [r for r in self.rows if not r.complete]
        shown = self.rows if self.ck_all.isChecked() else miss
        self._shown = shown
        self.table.setRowCount(len(shown))
        for i, r in enumerate(shown):
            note = ", ".join(f"{n:02d}. có {r.found[n]} file" for n in r.duplicates)
            vals = [r.rel or "(thư mục gốc)", r.count_pdf,
                    ", ".join(f"{n:02d}" for n in r.missing) if r.missing else "✔ Đủ", note]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 2:
                    it.setForeground(QColor("#DC2626" if r.missing else "#15803D"))
                self.table.setItem(i, c, it)
        self.lbl.setText(f"{fmt(len(self.rows))} thư mục có PDF · thiếu file: {fmt(len(miss))}")
        self.btn_copy.setText(f"📦 Copy {len(miss)} thư mục thiếu ra thư mục mới")
        self.btn_copy.setEnabled(bool(miss))

    def open_row(self, row, col):
        if 0 <= row < len(self._shown):
            open_path(os.path.join(self.result.root, self._shown[row].rel))

    def copy_missing(self):
        miss = [r.rel for r in self.rows if not r.complete]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            dest, n = T.copy_dirs_flat(self.result, miss)
        except OSError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Lỗi copy", e.strerror or str(e))
            return
        QApplication.restoreOverrideCursor()
        activity.log("Copy thư mục thiếu file", f"{len(miss)} thư mục, {n} file → {dest}")
        if QMessageBox.question(self, "Hoàn tất", f"Đã chép {len(miss)} thư mục ({n} file) sang:\n{dest}\n\nMở thư mục?") == QMessageBox.Yes:
            open_path(dest)


class CccdDialog(QDialog):
    def __init__(self, parent, result: ScanResult):
        super().__init__(parent)
        self.setWindowTitle("Thư mục tên là số CCCD")
        self.resize(940, 560)
        self.result = result
        self.changed = False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.rows = T.find_cccd_dirs(result)
        finally:
            QApplication.restoreOverrideCursor()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b style='font-size:12pt;color:#1E40AF'>🔍 Thư mục tên là số CCCD</b><br>"
                             "<span style='color:#475569'>Thư mục con có tên <b>đúng 12 chữ số</b>. Xoá đưa vào Thùng rác "
                             "(khôi phục được). Ổ mạng/USB không có Thùng rác → xoá vĩnh viễn, có xác nhận.</span>"))
        self.table = _table(["☑", "Thư mục", "Số file", "Số PDF", "Dung lượng"], [44, 380, 80, 80, 110])
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            self.table.setItem(i, 0, chk)
            for c, v in enumerate([r.rel, r.files, r.pdfs, fmt_size(r.size)], 1):
                it = QTableWidgetItem(str(v))
                if r.pdfs:
                    it.setForeground(QColor("#B45309"))
                    it.setBackground(QColor("#FFEDD5"))
                self.table.setItem(i, c, it)
        self.table.cellDoubleClicked.connect(lambda r, c: c and open_path(self.rows[r].path))
        lay.addWidget(self.table, 1)
        self.lbl = QLabel(f"Tìm thấy {len(self.rows)} thư mục. Ô cam = bên trong có PDF. Bấm đôi để mở xem.")
        lay.addWidget(self.lbl)
        bot = QHBoxLayout()
        b = QPushButton("Chọn tất cả")
        b.clicked.connect(lambda: self.set_all(True))
        b2 = QPushButton("Bỏ chọn")
        b2.clicked.connect(lambda: self.set_all(False))
        bot.addWidget(b)
        bot.addWidget(b2)
        bot.addStretch(1)
        self.btn_del = QPushButton("🗑 Xoá thư mục đã chọn")
        self.btn_del.setObjectName("danger")
        self.btn_del.clicked.connect(self.delete)
        close = QPushButton("Đóng")
        close.clicked.connect(self.accept)
        bot.addWidget(self.btn_del)
        bot.addWidget(close)
        lay.addLayout(bot)
        self.btn_del.setEnabled(bool(self.rows))

    def set_all(self, on: bool):
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def delete(self):
        sel = [self.rows[i] for i in range(self.table.rowCount()) if self.table.item(i, 0).checkState() == Qt.Checked]
        if not sel:
            QMessageBox.information(self, "Xoá", "Chưa chọn thư mục nào.")
            return
        perm = [r for r in sel if not T.drive_is_fixed(r.path)]
        has_pdf = sum(1 for r in sel if r.pdfs)
        msg = f"Xoá {len(sel)} thư mục đã chọn vào Thùng rác?"
        if has_pdf:
            msg += f"\n\n⚠ {has_pdf} thư mục có chứa file PDF."
        if QMessageBox.question(self, "Xác nhận xoá", msg) != QMessageBox.Yes:
            return
        if perm and QMessageBox.warning(
                self, "XOÁ VĨNH VIỄN",
                f"{len(perm)} thư mục nằm trên ổ mạng/USB nên KHÔNG có Thùng rác – sẽ bị xoá vĩnh viễn, không khôi phục được.\n\nXoá thật sự?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            sel = [r for r in sel if r not in perm]
        ok = fail = 0
        errs = []
        for r in sel:
            good, why = T.delete_dir(r.path, permanent=r in perm)
            if good:
                ok += 1
            else:
                fail += 1
                errs.append(f"{r.rel}: {why}")
        activity.log("Xoá thư mục CCCD", f"{ok} thành công, {fail} lỗi")
        if ok:
            self.changed = True
        QMessageBox.information(self, "Kết quả", f"Đã xoá {ok} thư mục." + (f"\nLỗi {fail}:\n" + "\n".join(errs[:8]) if fail else ""))
        if self.changed:
            self.accept()


class CopyGroupDialog(QDialog):
    def __init__(self, parent, result: ScanResult, mode: str):
        super().__init__(parent)
        self.setWindowTitle("Copy nhóm file ra thư mục mới")
        self.result = result
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b style='font-size:12pt;color:#1E40AF'>📦 Copy nhóm file ra thư mục mới</b><br>"
                             "<span style='color:#475569'>Chép đúng nhóm file đã chọn, giữ nguyên toàn bộ cây thư mục (kể cả thư mục rỗng). "
                             "Chỉ copy giống hệt từng byte nên chữ ký số còn nguyên; không ghi đè, không đụng file gốc.</span>"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Nhóm file:"))
        self.cb = QComboBox()
        self.cb.addItem("Tất cả file", FILTER_ALL)
        self.cb.addItem("Chỉ file .signed", FILTER_SIGNED)
        self.cb.addItem("Chỉ file không .signed", FILTER_UNSIGNED)
        self.cb.setCurrentIndex(max(0, self.cb.findData(mode)))
        row.addWidget(self.cb, 1)
        lay.addLayout(row)
        self.lbl = QLabel("")
        lay.addWidget(self.lbl)
        self.cb.currentIndexChanged.connect(self.upd)
        bot = QHBoxLayout()
        bot.addStretch(1)
        go = QPushButton("📦 Copy")
        go.setObjectName("primary")
        go.clicked.connect(self.go)
        close = QPushButton("Đóng")
        close.clicked.connect(self.reject)
        bot.addWidget(go)
        bot.addWidget(close)
        lay.addLayout(bot)
        self.setMinimumWidth(560)
        self.upd()

    def upd(self):
        from ..core.models import match_filter
        m = self.cb.currentData()
        n = sum(1 for f in self.result.files if match_filter(f, m))
        self.lbl.setText(f"Sẽ chép {fmt(n)} file → thư mục “{os.path.basename(self.result.root.rstrip(os.sep))} - {T.GROUP_SUFFIX[m]}” "
                         "(cùng cấp với thư mục nguồn).")

    def go(self):
        m = self.cb.currentData()
        pd = QProgressDialog("Đang copy…", "Dừng", 0, 100, self)
        pd.setWindowModality(Qt.WindowModal)
        pd.setMinimumDuration(300)
        cancelled = {"v": False}

        def prog(i, n):
            pd.setMaximum(max(1, n))
            pd.setValue(i)
            QApplication.processEvents()
            cancelled["v"] = pd.wasCanceled()

        try:
            dest, done, total = T.copy_group(self.result, m, progress=prog, cancel=lambda: cancelled["v"])
        except (OSError, ValueError) as e:
            pd.close()
            QMessageBox.warning(self, "Lỗi copy", getattr(e, "strerror", None) or str(e))
            return
        pd.close()
        activity.log("Copy nhóm file", f"{done}/{total} file → {dest}")
        if QMessageBox.question(self, "Hoàn tất", f"Đã chép {done}/{total} file sang:\n{dest}\n\nMở thư mục?") == QMessageBox.Yes:
            open_path(dest)
        self.accept()
