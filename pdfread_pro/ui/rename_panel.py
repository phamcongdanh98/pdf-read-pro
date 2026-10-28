"""Tab XEM TRƯỚC & ĐỔI TÊN (bố cục Hồ sơ 1361): mặc định đổi tên theo BỘ QUY TẮC MÃ SỐ 1361;
có thể chọn mẫu đổi tên tuỳ chỉnh. Bảng kết quả trực tiếp + khung xem trước PDF bên phải."""
from __future__ import annotations

import os
from typing import Callable, List, Optional

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..core import activity, renamer as R
from ..core.models import FileInfo
from .common import ListDialog, fmt
from .preview import PreviewPane, make_collapsible
from .rules1361_panel import Rules1361Panel
from .rules_panel import RulesPanel
from .styles import button

MODE_1361 = "1361"
MODE_CUSTOM = "custom"

# (màu chữ, màu nền) cho cột Tên mới + Trạng thái
STATUS_STYLE = {
    R.ST_READY: ("#047857", None),
    R.ST_RENAMED_AUTO: ("#92400E", "#FEF3C7"),
    R.ST_SAME: ("#64748B", None),
    R.ST_CONFLICT: ("#B45309", "#FFEDD5"),
    R.ST_INVALID: ("#B91C1C", "#FEE2E2"),
    R.ST_NO_RULE: ("#B45309", "#FFF7ED"),
    R.ST_NO_CODE: ("#B91C1C", "#FEF2F2"),
}
STATUS_ICON = {R.ST_READY: "✔ ", R.ST_RENAMED_AUTO: "⚠ ", R.ST_SAME: "● ", R.ST_CONFLICT: "⚠ ",
               R.ST_INVALID: "✖ ", R.ST_NO_RULE: "❓ ", R.ST_NO_CODE: "✖ "}
COLS = ["", "STT", "Thư Mục", "Tên File Gốc", "Mã Số", "Quy Tắc Khớp Tương Ứng", "Tên File Mới Dự Kiến", "Trạng Thái"]
CAN_RENAME = (R.ST_READY, R.ST_RENAMED_AUTO)


class RenamePanel(QWidget):
    renamed = Signal()                 # đã đổi tên / hoàn tác → cửa sổ chính quét lại
    editRulesRequested = Signal(int)   # 0 = bộ quy tắc 1361, 1 = mẫu tuỳ chỉnh

    def __init__(self, rules1361: Rules1361Panel, custom: RulesPanel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.r1361, self.custom = rules1361, custom
        self.files: List[FileInfo] = []
        self.items: List[R.PreviewItem] = []
        self._rows: List[R.PreviewItem] = []
        self.unchecked = set()
        self.busy_check: Callable[[], bool] = lambda: False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(8)
        split = QSplitter(Qt.Horizontal)          # trái: cấu hình + bảng · phải: xem trước hẹp, cao hết tab
        outer.addWidget(split, 1)
        leftw = QWidget()
        root = QVBoxLayout(leftw)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        g = QGroupBox("Cách đổi tên")
        gl = QHBoxLayout(g)
        gl.addWidget(QLabel("Bộ quy tắc:"))
        self.cb_mode = QComboBox()
        self.cb_mode.setMinimumWidth(330)
        self.cb_mode.activated.connect(self._mode_chosen)
        gl.addWidget(self.cb_mode)
        self.btn_edit = button("⚙ Quản lý bộ quy tắc", "violet", lambda: self.editRulesRequested.emit(
            0 if self.mode == MODE_1361 else 1), size="sm")
        gl.addWidget(self.btn_edit)
        gl.addSpacing(10)
        self.ck_suffix = QCheckBox("Luôn thêm hậu tố .1 (khi chỉ có 1 file)")
        self.ck_suffix.toggled.connect(lambda: self._timer.start())
        gl.addWidget(self.ck_suffix)
        gl.addStretch(1)
        gl.addWidget(button("🔄 Làm mới xem trước", "primary", self.refresh, "Tính lại tên mới", "sm"))
        root.addWidget(g)

        r = QHBoxLayout()
        self.lbl_rule = QLabel("")
        self.lbl_rule.setWordWrap(True)
        r.addWidget(self.lbl_rule, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Lọc theo tên file…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self.fill_table)
        r.addWidget(self.search)
        self.ck_only = QCheckBox("Chỉ hiện file sẽ đổi")
        self.ck_only.toggled.connect(self.fill_table)
        r.addWidget(self.ck_only)
        self.lbl_scope = QLabel("")
        self.lbl_scope.setObjectName("Hint")
        r.addWidget(self.lbl_scope)
        root.addLayout(r)

        left = QGroupBox("Xem trước kết quả đổi tên")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(6, 6, 6, 6)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, w in enumerate((30, 44, 120, 250, 58, 260, 300, 150)):
            self.table.setColumnWidth(i, w)
        self.table.itemChanged.connect(self._item_changed)
        self.table.currentCellChanged.connect(lambda row, *_: self._show_row(row))
        ll.addWidget(self.table)
        root.addWidget(left, 1)
        split.addWidget(leftw)
        rightg = QGroupBox("Xem trước file PDF")
        rl = QVBoxLayout(rightg)
        rl.setContentsMargins(8, 8, 8, 8)
        self.preview = PreviewPane(title="")
        rl.addWidget(self.preview)
        split.addWidget(rightg)
        split.setStretchFactor(0, 72)
        split.setStretchFactor(1, 28)
        rightg.setMinimumWidth(300)
        btn_prev = make_collapsible(split, self.preview)

        bot = QHBoxLayout()
        self.lbl_sum = QLabel("Tổng số: 0 file | Đã khớp: 0 | Chưa có quy tắc: 0")
        self.lbl_sum.setObjectName("StatusText")
        bot.addWidget(self.lbl_sum, 1)
        bot.addWidget(btn_prev)
        bot.addWidget(button("☑ Chọn tất cả", "light", lambda: self.set_all(True), size="sm"))
        bot.addWidget(button("☐ Bỏ chọn", "light", lambda: self.set_all(False), size="sm"))
        bot.addSpacing(10)
        self.btn_apply = button("🚀 BẮT ĐẦU ĐỔI TÊN HÀNG LOẠT", "success", self.apply, size="lg")
        self.btn_undo = button("↩️ HOÀN TÁC", "warning", self.undo, size="lg")
        bot.addWidget(self.btn_apply)
        bot.addWidget(self.btn_undo)
        outer.addLayout(bot)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.refresh)
        self.mode = MODE_1361
        rules1361.rulesChanged.connect(lambda: self.mode == MODE_1361 and self._timer.start())
        custom.rulesChanged.connect(self._custom_changed)
        custom.presetsChanged.connect(self._reload_combo)
        self._reload_combo()
        self._update_rule_label()
        self.refresh_undo_btn()

    # ------------------------------------------------------------- chế độ / bộ quy tắc
    def _reload_combo(self):
        self.cb_mode.blockSignals(True)
        self.cb_mode.clear()
        self.cb_mode.addItem("📋 Bộ quy tắc mã số 1361 (mặc định)", MODE_1361)
        self.cb_mode.insertSeparator(1)
        for p in self.custom.presets:
            self.cb_mode.addItem("🧩 Mẫu: " + p["name"], "preset:" + p["name"])
        self.cb_mode.addItem("🧩 Mẫu đang soạn ở tab Quản lý bộ quy tắc", MODE_CUSTOM)
        self._sync_combo()
        self.cb_mode.blockSignals(False)

    def _sync_combo(self):
        if self.mode == MODE_1361:
            self.cb_mode.setCurrentIndex(0)
            return
        idx = self.cb_mode.findData("preset:" + self.custom.ruleset.get("name", ""))
        self.cb_mode.setCurrentIndex(idx if idx >= 0 and not self.custom.dirty else self.cb_mode.findData(MODE_CUSTOM))

    def _mode_chosen(self, idx: int):
        data = self.cb_mode.itemData(idx)
        if data == MODE_1361:
            self.set_mode(MODE_1361)
            return
        if data and data.startswith("preset:"):
            self.custom.select_preset(data[7:])
        self.set_mode(MODE_CUSTOM)

    def set_mode(self, mode: str):
        self.mode = mode
        self.ck_suffix.setEnabled(mode == MODE_1361)
        self._sync_combo()
        self._update_rule_label()
        self._timer.start()

    def _custom_changed(self):
        if self.mode == MODE_CUSTOM:
            self.cb_mode.blockSignals(True)
            self._sync_combo()
            self.cb_mode.blockSignals(False)
            self._update_rule_label()
            self._timer.start()

    def _update_rule_label(self, error: str = ""):
        if error:
            text, style = "⚠ " + error, "color:#B91C1C;font-weight:bold"
        elif self.mode == MODE_1361:
            text = (f"📐 Đổi theo <b>{fmt(len(self.r1361.rules))} quy tắc mã số 1361</b>: mã ở đầu tên file "
                    "(01, 07a, 86dh…) → tên mẫu tiêu chuẩn; nhiều file cùng mã trong 1 thư mục → thêm .1, .2…; "
                    "giữ phần <b>.signed</b> ở cuối.")
            style = "color:#1E3A8A"
        else:
            text, style = "📐 " + self.custom.summary(), "color:#1E3A8A"
        self.lbl_rule.setText(text)
        self.lbl_rule.setStyleSheet(style + ";font-size:9pt")

    # ------------------------------------------------------------- dữ liệu vào
    def set_files(self, files: List[FileInfo], scope_label: str):
        self.files = files
        self.unchecked &= {f.path for f in files}
        self.lbl_scope.setText(f"Phạm vi: <b>{scope_label}</b>")
        self.preview.clear()
        self._timer.start()

    # ------------------------------------------------------------- xem trước
    def refresh(self):
        if not self.files:
            self.items = []
            self.fill_table()
            return
        if self.mode == MODE_1361:
            self.items = R.build_preview_1361(self.files, self.r1361.rules, self.ck_suffix.isChecked())
            self._update_rule_label()
        else:
            self.items = R.build_preview(self.files, self.custom.current_ruleset(), self.custom.policy())
            notes = {it.note for it in self.items if it.status == R.ST_INVALID}
            if len(notes) == 1 and all(it.status == R.ST_INVALID for it in self.items):
                self._update_rule_label(notes.pop() + " – hãy sửa ở tab Quản lý bộ quy tắc.")
            else:
                self._update_rule_label()
            name = self.custom.ruleset.get("name", "")
            for it in self.items:
                it.code = it.code or R.extract_code(os.path.splitext(it.fi.name)[0])
                it.rule = f"Mẫu: {name}"
        for it in self.items:
            it.checked = it.fi.path not in self.unchecked
        self.fill_table()

    def fill_table(self, *_):
        q = self.search.text().strip().lower()
        only = self.ck_only.isChecked()
        rows = [it for it in self.items
                if (not only or it.status in CAN_RENAME)
                and (not q or q in it.fi.name.lower() or q in it.new_name.lower() or q in it.fi.dir_rel.lower())]
        self._rows = rows
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(rows))
        for r, it in enumerate(rows):
            fg, bg = STATUS_STYLE[it.status]
            status = STATUS_ICON[it.status] + (it.note if it.status in (R.ST_NO_RULE, R.ST_NO_CODE, R.ST_INVALID,
                                                                       R.ST_CONFLICT, R.ST_SAME) and it.note
                                               else R.STATUS_TEXT[it.status])
            new = it.new_name if it.status in CAN_RENAME else ("(giữ nguyên)" if it.status == R.ST_SAME else "—")
            vals = [None, str(r + 1), it.fi.dir_rel or "(gốc)", it.fi.name, it.code, it.rule or "—", new, status]
            for c, text in enumerate(vals):
                cell = QTableWidgetItem(text or "")
                if c == 0:
                    can = it.status in CAN_RENAME
                    cell.setFlags((Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable) if can
                                  else Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    if can:
                        cell.setCheckState(Qt.Checked if it.checked else Qt.Unchecked)
                else:
                    cell.setToolTip(text or "")
                    if c in (1, 4):
                        cell.setTextAlignment(Qt.AlignCenter)
                    if c == 4 and it.code:
                        cell.setForeground(QColor("#1E3A8A"))
                        f = cell.font()
                        f.setBold(True)
                        cell.setFont(f)
                    if c == 5:
                        cell.setForeground(QColor("#475569"))
                    if c in (6, 7):
                        cell.setForeground(QColor(fg))
                        if bg:
                            cell.setBackground(QColor(bg))
                    if c == 6 and it.status in CAN_RENAME:
                        f = cell.font()
                        f.setBold(True)
                        cell.setFont(f)
                self.table.setItem(r, c, cell)
        self.table.setUpdatesEnabled(True)
        self.table.blockSignals(False)
        self.update_summary()

    def _show_row(self, row: int):
        if 0 <= row < len(self._rows):
            f = self._rows[row].fi
            if f.error:
                self.preview.clear("⚠ " + f.error)
            else:
                self.preview.show_file(f.path)

    def _item_changed(self, cell: QTableWidgetItem):
        if cell.column() != 0 or cell.row() >= len(self._rows):
            return
        it = self._rows[cell.row()]
        it.checked = cell.checkState() == Qt.Checked
        (self.unchecked.discard if it.checked else self.unchecked.add)(it.fi.path)
        self.update_summary()

    def set_all(self, on: bool):
        for it in self.items:
            if it.status in CAN_RENAME:
                it.checked = on
                (self.unchecked.discard if on else self.unchecked.add)(it.fi.path)
        self.fill_table()

    def update_summary(self):
        n = len(self.items)
        matched = sum(1 for it in self.items if it.status in CAN_RENAME + (R.ST_SAME,))
        no_rule = sum(1 for it in self.items if it.status in (R.ST_NO_RULE, R.ST_NO_CODE))
        will = sum(1 for it in self.items if it.will_rename)
        bits = [f"Tổng số: {fmt(n)} file", f"Đã khớp: {fmt(matched)}", f"Chưa có quy tắc: {fmt(no_rule)}",
                f"Sẽ đổi: {fmt(will)}"]
        bad = sum(1 for it in self.items if it.status in (R.ST_INVALID, R.ST_CONFLICT))
        if bad:
            bits.append(f"Lỗi/trùng: {fmt(bad)}")
        self.lbl_sum.setText(" | ".join(bits))
        self.btn_apply.setEnabled(will > 0)
        self.btn_apply.setText(f"🚀 BẮT ĐẦU ĐỔI TÊN HÀNG LOẠT ({fmt(will)})" if will else "🚀 BẮT ĐẦU ĐỔI TÊN HÀNG LOẠT")

    # ------------------------------------------------------------- áp dụng / hoàn tác
    def refresh_undo_btn(self):
        b = R.last_undoable()
        self.btn_undo.setEnabled(bool(b))
        self.btn_undo.setToolTip(f"Hoàn tác lần đổi lúc {b['time']} ({len(b['ops'])} file)" if b
                                 else "Chưa có lần đổi tên nào để hoàn tác")

    def _show_failed(self, rep):
        ListDialog(self, "Một số file không xử lý được", rep.summary, ["File", "Lý do"],
                   [(os.path.basename(p), why) for p, why in rep.failed], [p for p, _ in rep.failed],
                   [420, 360]).exec()

    def _rule_name(self) -> str:
        return "bộ quy tắc mã số 1361" if self.mode == MODE_1361 else f"mẫu “{self.custom.ruleset.get('name')}”"

    def pipeline_config(self) -> dict:
        """Quy tắc đổi tên đang chọn ở tab này – dùng cho tab Quy trình 1 click (luôn lấy giá trị hiện tại)."""
        import copy
        if self.mode == MODE_1361:
            return {"mode": "1361", "rules": dict(self.r1361.rules), "always_suffix": self.ck_suffix.isChecked(),
                    "ruleset": {}, "policy": "auto",
                    "label": "Bộ quy tắc mã số 1361" + (" (luôn thêm hậu tố .1)" if self.ck_suffix.isChecked() else "")}
        return {"mode": "custom", "rules": {}, "always_suffix": False,
                "ruleset": copy.deepcopy(self.custom.current_ruleset()), "policy": self.custom.policy(),
                "label": f"Mẫu “{self.custom.ruleset.get('name', '')}”"}

    def apply(self):
        if self.busy_check():
            return
        todo = [it for it in self.items if it.will_rename]
        if not todo:
            return
        if QMessageBox.question(
                self, "Xác nhận đổi tên",
                f"Đổi tên {fmt(len(todo))} file theo {self._rule_name()}?\n\n"
                "Chỉ đổi tên, không sửa nội dung (chữ ký số còn nguyên); không ghi đè file nào.\n"
                "Có thể hoàn tác bằng nút HOÀN TÁC.") != QMessageBox.Yes:
            return
        self.preview.release()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            def prog(done, total):
                self.lbl_sum.setText(f"⏳ Đang đổi tên… {done}/{total}")
                QApplication.processEvents()
            rep = R.apply_renames(todo, prog)
        finally:
            QApplication.restoreOverrideCursor()
        activity.log("Đổi tên", f"{rep.summary} – theo {self._rule_name()}")
        if rep.failed:
            self._show_failed(rep)
        self.refresh_undo_btn()
        if rep.ok:
            self.renamed.emit()

    def undo(self):
        if self.busy_check():
            return
        b = R.last_undoable()
        if not b:
            return
        if QMessageBox.question(self, "Hoàn tác",
                                f"Hoàn tác lần đổi tên lúc {b['time']} ({len(b['ops'])} file)?") != QMessageBox.Yes:
            return
        self.preview.release()
        rep = R.undo_last()
        activity.log("Hoàn tác đổi tên", rep.summary)
        if rep.failed:
            self._show_failed(rep)
        self.refresh_undo_btn()
        if rep.ok:
            self.renamed.emit()
