"""TAB THÙNG RÁC của PDF-Read Pro: trang đã xoá + bản gốc trước khi sửa – xem, khôi phục, xoá vĩnh viễn, dọn sạch, tự dọn."""
from __future__ import annotations

from ..paths import make_settings

import os
from datetime import datetime
from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMessageBox, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import trash as T
from .common import fmt_size
from .filterbar import FILTER_ALL, FilterBar
from .preview import PreviewPane
from .styles import button
from .tablekit import install_column_chooser, install_row_menu

COLS = ["STT", "Thời gian xoá", "Loại", "Tên file", "Trang", "Đường dẫn ban đầu", "Dung lượng", "Lý do"]
KIND_ICON = {T.KIND_PAGES: "📄 ", T.KIND_BACKUP: "🗂 ", T.KIND_FILE: "📁 "}
GRAY, RED = "#64748B", "#DC2626"
SET_AUTO, SET_DAYS = "trash_auto", "trash_days"


def auto_purge() -> int:
    """Tự dọn mục cũ nếu người dùng đã bật (gọi lúc mở app và khi mở thùng rác). Trả về số mục đã xoá."""
    try:
        st = make_settings()
        if st.value(SET_AUTO, False) in (True, "true", "1", 1):
            return T.purge_older_than(max(1, int(st.value(SET_DAYS, 30))))
    except Exception:
        pass
    return 0


class TrashPanel(QWidget):
    """Tab «Thùng rác»: danh sách mục + xem trước + khôi phục / xoá vĩnh viễn / dọn sạch / tự dọn."""
    changed = Signal(str)                      # đã khôi phục → file này vừa đổi (các tab cập nhật dòng)
    countChanged = Signal()                    # số mục trong thùng rác đổi

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: List[T.Entry] = []
        self.settings = make_settings()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 8)
        lay.setSpacing(8)
        title = QLabel("🗑 THÙNG RÁC VÀ LỊCH SỬ XOÁ")
        title.setStyleSheet("font-size:14pt;font-weight:800;color:#1E3A8A;")
        lay.addWidget(title)
        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("Hint")
        self.lbl_info.setWordWrap(True)
        lay.addWidget(self.lbl_info)

        self.fbar = FilterBar(
            [("Tất cả", FILTER_ALL), ("📄 Trang đã xoá", T.KIND_PAGES), ("🗂 Bản gốc trước khi sửa", T.KIND_BACKUP),
             ("📁 File", T.KIND_FILE), ("⚠ File đã mất", "missing")],
            [("Mới nhất trước", "orig", False), ("Cũ nhất trước", "old", False), ("Tên file A → Z", "name", False),
             ("Dung lượng lớn → nhỏ", "size", True)],
            "🔍 Tìm theo tên file / đường dẫn / lý do…")
        self.fbar.changed.connect(self._fill)
        lay.addWidget(self.fbar)

        split = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, w in enumerate((42, 124, 170, 190, 70, 170, 96)):
            self.table.setColumnWidth(i, w)
        install_column_chooser(self.table, "trash", (3,))
        self.fbar.attach_columns(self.table, "trash", (3,))
        install_row_menu(self.table, lambda rows: [self.entries[r].stored for r in rows if 0 <= r < len(self.entries)],
                         lambda rows: [("↩ Khôi phục mục này", self.restore_selected),
                                       ("✖ Xoá vĩnh viễn mục này", self.delete_selected)])
        self.table.itemSelectionChanged.connect(self._selection)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_selected())
        split.addWidget(self.table)
        pbox = QWidget()
        pl = QVBoxLayout(pbox)
        pl.setContentsMargins(0, 0, 0, 0)
        self.preview = PreviewPane(title="Xem trước")
        self.preview.set_readonly()
        pl.addWidget(self.preview)
        pbox.setMinimumWidth(300)
        split.addWidget(pbox)
        split.setStretchFactor(0, 70)
        split.setStretchFactor(1, 30)
        split.setSizes([1010, 380])
        lay.addWidget(split, 1)

        # tự dọn
        ar = QHBoxLayout()
        self.ck_auto = QCheckBox("Tự dọn mục cũ hơn")
        self.ck_auto.setToolTip("Mỗi lần mở app / mở thùng rác sẽ xoá vĩnh viễn các mục quá hạn. Mặc định TẮT.")
        self.sp_days = QSpinBox()
        self.sp_days.setRange(1, 3650)
        self.sp_days.setSuffix(" ngày")
        self.sp_days.setFixedWidth(100)
        self.ck_auto.setChecked(self.settings.value(SET_AUTO, False) in (True, "true", "1", 1))
        try:
            self.sp_days.setValue(int(self.settings.value(SET_DAYS, 30)))
        except (TypeError, ValueError):
            self.sp_days.setValue(30)
        self.ck_auto.toggled.connect(self._auto_changed)
        self.sp_days.valueChanged.connect(self._auto_changed)
        ar.addWidget(self.ck_auto)
        ar.addWidget(self.sp_days)
        self.btn_loc = button("📁 Nơi lưu bản sao lưu…", "light", self.pick_backup_root,
                              "Bản gốc trước khi sửa được lưu ở thư mục này (mặc định trong dữ liệu của app, KHÔNG nằm trong thư mục hồ sơ)", "sm")
        ar.addWidget(self.btn_loc)
        ar.addStretch(1)
        self.lbl_sel = QLabel("")
        self.lbl_sel.setObjectName("Hint")
        ar.addWidget(self.lbl_sel)
        lay.addLayout(ar)

        bt = QHBoxLayout()
        self.btn_open = button("👁 Xem / Mở file rác", "primary", self.open_selected, "Mở file đang giữ bằng phần mềm đọc PDF")
        self.btn_restore = button("↩ Khôi phục đã chọn", "success", self.restore_selected,
                                  "Trang → chèn lại đúng vị trí cũ · Bản gốc → trả file về như trước khi sửa")
        self.btn_del = button("✖ Xoá vĩnh viễn đã chọn", "danger", self.delete_selected, "Không khôi phục được nữa")
        self.btn_clear = button("🧹 Dọn sạch thùng rác", "warning", self.clear_all, "Xoá vĩnh viễn mọi mục")
        bt.addWidget(self.btn_open)
        bt.addWidget(self.btn_restore)
        bt.addStretch(1)
        bt.addWidget(self.btn_del)
        bt.addWidget(self.btn_clear)
        lay.addLayout(bt)
        auto_purge()
        self.reload()

    # ------------------------------------------------------------------ dữ liệu
    def reload(self) -> None:
        self.entries = T.list_entries()
        self.table.setRowCount(len(self.entries))
        for r, e in enumerate(self.entries):
            when = datetime.fromtimestamp(e.time).strftime("%d/%m/%Y %H:%M")
            kind = KIND_ICON.get(e.kind, "") + T.KIND_TEXT.get(e.kind, e.kind)
            vals = [str(r + 1), when, kind, e.name, e.page_text or "—", e.orig_path,
                    fmt_size(e.size) if e.exists else "đã mất", e.reason]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setToolTip(v)
                if c in (0, 4, 6):
                    it.setTextAlignment(Qt.AlignCenter)
                if not e.exists:
                    it.setForeground(QColor(RED))
                self.table.setItem(r, c, it)
        self._fill()
        total = T.total_size(self.entries)
        self.lbl_info.setText(
            f"Trang đã xoá và bản gốc trước khi sửa / nén / cắt được cất ở đây (khác Thùng rác của Windows). "
            f"Hiện có <b>{len(self.entries)}</b> mục · <b>{fmt_size(total)}</b> · bản sao lưu gốc lưu tại <b>{T.backup_root()}</b> "
            "(không nằm trong thư mục hồ sơ)")

    def _info(self, r: int):
        e = self.entries[r]
        tags = {e.kind}
        if not e.exists:
            tags.add("missing")
        return tags, f"{e.name} {e.orig_path} {e.reason}".lower(), {
            "old": e.time, "name": e.name.lower(), "size": e.size}

    def _fill(self, *_):
        if self.entries:
            self.fbar.apply(self.table, len(self.entries), self._info)
        self._selection()

    def _picked(self) -> List[T.Entry]:
        rows = sorted({ix.row() for ix in self.table.selectionModel().selectedRows()}) if self.table.selectionModel() else []
        return [self.entries[r] for r in rows if 0 <= r < len(self.entries)]

    def _selection(self) -> None:
        sel = self._picked()
        has = bool(sel)
        for b in (self.btn_open, self.btn_restore, self.btn_del):
            b.setEnabled(has)
        self.btn_clear.setEnabled(bool(self.entries))
        self.lbl_sel.setText(f"Đã chọn {len(sel)} mục · {fmt_size(sum(e.size for e in sel if e.exists))}" if sel else "")
        if len(sel) == 1 and sel[0].exists:
            self.preview.show_file(sel[0].stored)
        else:
            self.preview.clear("Chọn 1 mục để xem trước" if not sel else "Chọn đúng 1 mục để xem trước")

    # ------------------------------------------------------------------ thao tác
    def open_selected(self) -> None:
        sel = self._picked()
        if len(sel) == 1 and sel[0].exists:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(sel[0].stored))
        elif sel:
            QMessageBox.information(self, "Thùng rác", "Chọn đúng 1 mục còn file để mở.")

    def restore_selected(self) -> None:
        sel = self._picked()
        if not sel:
            return
        if QMessageBox.question(
                self, "Khôi phục", f"Khôi phục {len(sel)} mục đã chọn về vị trí ban đầu?\n\n"
                "• Trang đã xoá → chèn lại đúng vị trí cũ trong file.\n"
                "• Bản gốc trước khi sửa → file được trả về như trước khi sửa "
                "(bản hiện tại được cất vào thùng rác để vẫn quay lại được).",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        self.preview.release()
        ok_n, notes, dest, restored = 0, [], None, []
        for e in sel:
            ok, msg, out = T.restore(e, dest)
            if not ok and "chọn nơi lưu" in msg:
                if dest is None:
                    d = QFileDialog.getExistingDirectory(self, "Thư mục gốc không còn – chọn nơi lưu file khôi phục")
                    if d:
                        dest = os.path.normpath(d)
                if dest:
                    ok, msg, out = T.restore(e, dest)
            ok_n += ok
            if ok and out:
                restored.append(out)
            if not ok:
                notes.append(f"• {e.name}: {msg}")
        self.reload()
        text = f"Đã khôi phục {ok_n}/{len(sel)} mục."
        if notes:
            text += "\n\nKhông khôi phục được:\n" + "\n".join(notes[:8])
        (QMessageBox.information if ok_n else QMessageBox.warning)(self, "Khôi phục", text)
        for path in restored:
            self.changed.emit(path)                   # file / số trang đã đổi → các tab cập nhật
        self.countChanged.emit()

    def delete_selected(self) -> None:
        sel = self._picked()
        if not sel:
            return
        if QMessageBox.question(self, "Xoá vĩnh viễn",
                                f"Xoá VĨNH VIỄN {len(sel)} mục đã chọn?\nKhông thể khôi phục lại.",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.preview.release()
        for e in sel:
            T.delete(e)
        self.reload()
        self.countChanged.emit()

    def clear_all(self) -> None:
        if not self.entries:
            return
        if QMessageBox.question(self, "Dọn sạch thùng rác",
                                f"Xoá VĨNH VIỄN toàn bộ {len(self.entries)} mục ({fmt_size(T.total_size(self.entries))})?\n"
                                "Không thể khôi phục lại.", QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        self.preview.release()
        T.clear()
        self.reload()
        self.countChanged.emit()

    def pick_backup_root(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu bản sao lưu gốc", T.backup_root())
        if not d:
            return
        d = os.path.normpath(d)
        T.set_config(backup_root="" if os.path.normcase(d) == os.path.normcase(T.default_backup_root()) else d)
        QMessageBox.information(self, "Nơi lưu bản sao lưu",
                                f"Từ nay bản gốc trước khi sửa được lưu ở:\n{T.backup_root()}\n\n"
                                "Các bản sao lưu cũ vẫn nằm nguyên chỗ cũ (vẫn khôi phục được).")
        self.reload()

    def _auto_changed(self, *_):
        self.settings.setValue(SET_AUTO, self.ck_auto.isChecked())
        self.settings.setValue(SET_DAYS, self.sp_days.value())
        self.sp_days.setEnabled(self.ck_auto.isChecked())

