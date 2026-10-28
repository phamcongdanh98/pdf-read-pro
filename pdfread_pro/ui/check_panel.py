"""Tab KIỂM TRA TRANG: phát hiện trang ngược / nằm ngang, số trang thiếu / trùng / sai thứ tự (Windows OCR),
sửa tự động (xoay, sắp xếp, bỏ trang trắng). Bên phải là khung xem trước cao hết tab như Tổng quan."""
from __future__ import annotations

import os
import shutil
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar, QPushButton, QRadioButton,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import activity, compressor as C, pagecheck as K, pagenum
from ..core.models import FileInfo
from .common import fmt
from .preview import PreviewPane, make_collapsible

ROTATE_TEXT = {90: "xoay 90° sang trái", 180: "xoay 180°", 270: "xoay 90° sang phải"}
GREEN, AMBER, RED, GRAY, TEXT = "#15803D", "#B45309", "#DC2626", "#64748B", "#1E293B"


class Worker(QThread):
    """Chạy `fn(args)` cho từng file ở các tiến trình con (OCR / PyMuPDF không chặn giao diện)."""
    one = Signal(int, object)
    finished_all = Signal(str)

    def __init__(self, fn: Callable, jobs: list, workers: int, on_error: Callable):
        super().__init__()
        self.fn, self.jobs, self.workers, self.on_error = fn, jobs, workers, on_error
        self.cancel_ev = threading.Event()

    def run(self):
        msg = ""
        try:
            with ProcessPoolExecutor(max_workers=self.workers) as ex:
                futs = {ex.submit(self.fn, args): (idx, args) for idx, args in self.jobs}
                for fut in as_completed(futs):
                    idx, args = futs[fut]
                    if self.cancel_ev.is_set():
                        for f in futs:
                            f.cancel()
                        msg = "Đã dừng theo yêu cầu."
                        break
                    try:
                        self.one.emit(idx, fut.result())
                    except BrokenProcessPool:
                        msg = "Một tiến trình bị dừng đột ngột (có thể thiếu bộ nhớ)."
                        break
                    except Exception as e:
                        self.one.emit(idx, self.on_error(args, f"Lỗi: {e}"))
        except Exception as e:
            msg = f"Lỗi: {e}"
        self.finished_all.emit(msg)


class CheckPanel(QWidget):
    COLS = ["STT", "Tên file", "Thư mục", "Trang", "Đọc được số", "Vấn đề", "Trạng thái"]
    PCOLS = ["Trang", "Số in", "Hướng", "Đề xuất sửa"]
    changed = Signal()
    busyChanged = Signal(bool)
    helpRequested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.files: List[FileInfo] = []
        self.root = ""
        self.worker: Optional[Worker] = None
        self.results: Dict[str, K.CheckResult] = {}     # path → kết quả kiểm tra (giữ lại khi quét lại)
        self.fixed: Dict[str, str] = {}                  # path → file đã sửa
        self.release_cb: Callable[[], None] = lambda: None
        self._view = "orig"
        self._shown_row = -1
        self._filling = False

        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 8)
        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split)
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        cfg = QGroupBox("Kiểm tra && sửa tự động")
        cl = QVBoxLayout(cfg)
        row = QHBoxLayout()
        self.ck_rot = QCheckBox("🔄 Xoay trang sai hướng")
        self.ck_rot.setToolTip("Trang bị ngược (180°) hoặc nằm ngang (90°) được xoay cho đứng thuận chiều.")
        self.ck_sort = QCheckBox("↕ Sắp xếp theo số trang in")
        self.ck_sort.setToolTip("Sắp lại trang theo số trang in ở đầu / chân trang (OCR).\n"
                                "Chỉ tự sắp khi đọc được số ở ≥ 1/2 số trang và không có số trùng.\n"
                                "Trang không có số đi liền sau trang đứng trước nó.")
        self.ck_blank = QCheckBox("⬜ Bỏ trang trắng")
        self.ck_signed = QCheckBox("Bỏ qua file đã ký số")
        self.ck_signed.setToolTip("Sửa file đã ký số làm mất hiệu lực chữ ký.")
        for ck, default in ((self.ck_rot, True), (self.ck_sort, True), (self.ck_blank, False), (self.ck_signed, True)):
            ck.setChecked(default)
            ck.toggled.connect(lambda _=False: self._refresh_all())
            row.addWidget(ck)
        row.addStretch(1)
        cl.addLayout(row)
        row = QHBoxLayout()
        self.rb_new = QRadioButton("Lưu sang thư mục mới (giữ file gốc)")
        self.rb_over = QRadioButton("Ghi đè file gốc")
        self.rb_new.setChecked(True)
        self.ck_backup = QCheckBox("Sao lưu bản gốc vào _backup_goc")
        self.ck_backup.setChecked(True)
        for w in (self.rb_new, self.rb_over, self.ck_backup):
            row.addWidget(w)
        row.addStretch(1)
        self.lbl_scope = QLabel("")
        self.lbl_scope.setStyleSheet("color:#475569")
        row.addWidget(self.lbl_scope)
        cl.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Thư mục đích:"))
        self.out_edit = QLineEdit()
        row.addWidget(self.out_edit, 1)
        b = QPushButton("📁 Chọn…")
        b.setProperty("size", "sm")
        b.clicked.connect(self.pick_out)
        row.addWidget(b)
        cl.addLayout(row)
        self.hint = QLabel("Đọc chữ & số trang bằng Windows OCR (không cần mạng). Sửa chỉ xoay / đổi thứ tự trang, "
                           "không nén lại ảnh. Sửa tay: bấm đôi ô <b>Số in</b>; chuột phải để đổi hướng trang.")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        hr = QHBoxLayout()
        hr.addWidget(self.hint, 1)
        hb = QPushButton("❓ Hướng dẫn có hình")
        hb.setObjectName("flat")
        hb.setProperty("size", "sm")
        hb.clicked.connect(lambda: self.helpRequested.emit("check"))
        hr.addWidget(hb)
        cl.addLayout(hr)
        lay.addWidget(cfg)
        self.rb_new.toggled.connect(self.mode_changed)

        vs = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, w in enumerate((44, 260, 130, 56, 115, 300, 150)):
            self.table.setColumnWidth(i, w)
        self.table.itemSelectionChanged.connect(self.show_selected)
        self.table.cellDoubleClicked.connect(lambda r, c: self.preview.open_external())
        vs.addWidget(self.table)

        pg = QGroupBox("Chi tiết từng trang")
        pgl = QVBoxLayout(pg)
        pgl.setContentsMargins(6, 6, 6, 6)
        self.lbl_detail = QLabel("Chọn 1 file đã kiểm tra để xem từng trang.")
        self.lbl_detail.setWordWrap(True)
        pgl.addWidget(self.lbl_detail)
        self.ptable = QTableWidget(0, len(self.PCOLS))
        self.ptable.setHorizontalHeaderLabels(self.PCOLS)
        self.ptable.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.ptable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ptable.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ptable.verticalHeader().setVisible(False)
        self.ptable.verticalHeader().setDefaultSectionSize(26)
        self.ptable.horizontalHeader().setStretchLastSection(True)
        for i, w in enumerate((60, 70, 120)):
            self.ptable.setColumnWidth(i, w)
        self.ptable.itemSelectionChanged.connect(self.page_selected)
        self.ptable.itemChanged.connect(self.page_edited)
        self.ptable.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ptable.customContextMenuRequested.connect(self.page_menu)
        pgl.addWidget(self.ptable, 1)
        vs.addWidget(pg)
        vs.setStretchFactor(0, 55)
        vs.setStretchFactor(1, 45)
        vs.setChildrenCollapsible(False)
        lay.addWidget(vs, 1)

        bot = QHBoxLayout()
        self.lbl = QLabel("Chưa có dữ liệu – hãy chọn thư mục và bấm Quét.")
        self.lbl.setStyleSheet("font-weight:700;color:#1E40AF")
        self.lbl.setWordWrap(True)
        bot.addWidget(self.lbl, 1)
        self.prog = QProgressBar()
        self.prog.setFixedWidth(200)
        self.prog.hide()
        bot.addWidget(self.prog)
        self.btn_check = QPushButton("🔍 Kiểm tra")
        self.btn_check.setObjectName("cyan")
        self.btn_check.setToolTip("Kiểm tra mọi file trong phạm vi (giữ Ctrl khi bấm: chỉ file đang chọn)")
        self.btn_check.clicked.connect(self.check)
        self.btn_stop = QPushButton("■ Dừng")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.clicked.connect(self.stop)
        self.btn_fix = QPushButton("🛠 SỬA TỰ ĐỘNG")
        self.btn_fix.setObjectName("success")
        self.btn_fix.setProperty("size", "lg")
        self.btn_fix.setToolTip("Xoay / sắp xếp / bỏ trang trắng cho các file cần sửa (theo lựa chọn bên trên)")
        self.btn_fix.clicked.connect(self.fix)
        for w in (self.btn_check, self.btn_stop, self.btn_fix):
            bot.addWidget(w)
        lay.addLayout(bot)

        # ---- xem trước cao hết tab (như Tổng quan): bản gốc ↔ bản đã sửa
        pbox = QGroupBox("Xem trước file PDF")
        pl = QVBoxLayout(pbox)
        pl.setContentsMargins(8, 8, 8, 8)
        sw = QHBoxLayout()
        self.btn_orig = QPushButton("📄 Bản gốc")
        self.btn_fixed = QPushButton("🛠 Bản đã sửa")
        for b in (self.btn_orig, self.btn_fixed):
            b.setCheckable(True)
            b.setObjectName("flat")
            b.setProperty("size", "sm")
            b.clicked.connect(self._switch_view)
            sw.addWidget(b)
        sw.addStretch(1)
        pl.addLayout(sw)
        self.preview = PreviewPane(title="")
        pl.addWidget(self.preview, 1)
        pbox.setMinimumWidth(300)
        split.addWidget(left)
        split.addWidget(pbox)
        split.setStretchFactor(0, 66)
        split.setStretchFactor(1, 34)
        btn_prev = make_collapsible(split, self.preview)
        bot.insertWidget(2, btn_prev)           # cạnh thanh tiến trình, trước các nút chính

        self.mode_changed()
        self._enable_actions()

    # ------------------------------------------------------------------ dữ liệu vào
    @property
    def running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def set_files(self, files: List[FileInfo], root: str, scope_label: str):
        if self.running:
            return
        if root != self.root:
            self.results.clear()
            self.fixed.clear()
            base = root.rstrip(os.sep)
            self.out_edit.setText(os.path.join(os.path.dirname(base), os.path.basename(base) + " - Đã kiểm tra")
                                  if base else "")
        self.files, self.root = files, root
        self.lbl_scope.setText(f"Phạm vi: <b>{scope_label}</b> · {fmt(len(files))} file")
        self.table.setRowCount(len(files))
        for r, f in enumerate(files):
            for c, v in enumerate([r + 1, f.name, f.dir_rel or "(gốc)", f.pages if f.pages is not None else "—",
                                   "", "", ""]):
                it = QTableWidgetItem(str(v))
                if c in (0, 3, 4):
                    it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, it)
            self._render(r)
        if not pagenum.available():
            self.lbl.setText("⚠ Máy không có Windows OCR (cần Windows 10/11) – không kiểm tra được.")
        else:
            self.lbl.setText(f"{fmt(len(files))} file trong phạm vi. Bấm “Kiểm tra” để tìm trang ngược / sai thứ tự."
                             if files else "Không có file nào trong phạm vi.")
        self._enable_actions()
        self.show_selected()

    # ------------------------------------------------------------------ phương án sửa
    def _plan(self, path: str) -> Optional[K.Plan]:
        r = self.results.get(path)
        if not r or r.error or not r.pages:
            return None
        return K.make_plan(r.pages, remove_blank=self.ck_blank.isChecked(), rotate=self.ck_rot.isChecked(),
                           reorder=self.ck_sort.isChecked())

    def _skipped(self, f: FileInfo) -> bool:
        return self.ck_signed.isChecked() and (f.has_real_sig or f.name_signed)

    def _set(self, row: int, col: int, text, color: Optional[str] = None):
        it = self.table.item(row, col)
        it.setText(str(text))
        it.setForeground(QColor(color or TEXT))

    def _render(self, row: int):
        f = self.files[row]
        r = self.results.get(f.path)
        if f.error:
            self._set(row, 6, f.error, RED)
            return
        if r is None:
            self._set(row, 4, "")
            self._set(row, 5, "")
            self._set(row, 6, "Chưa kiểm tra", GRAY)
            return
        if r.error and not r.pages:
            self._set(row, 5, "")
            self._set(row, 6, r.error, RED)
            return
        plan = self._plan(f.path)
        self._set(row, 3, len(r.pages))
        text_pages = plan.total - len(plan.blanks)
        self._set(row, 4, f"{plan.read}/{text_pages}", GREEN if plan.read == text_pages else AMBER)
        issues = plan.issues()
        self._set(row, 5, " · ".join(issues) if issues else "—", AMBER if issues else GREEN)
        self.table.item(row, 5).setToolTip("\n".join(issues + ([plan.sort_note] if plan.sort_note else [])))
        if f.path in self.fixed:
            self._set(row, 6, "✔ Đã sửa", GREEN)
            self.table.item(row, 6).setToolTip(self.fixed[f.path])
        elif r.error:
            self._set(row, 6, r.error, RED)
        elif plan.needs_fix:
            self._set(row, 6, "🛠 Cần sửa" + (" (đã ký số – bỏ qua)" if self._skipped(f) else ""), AMBER)
        elif issues or plan.sort_note:
            self._set(row, 6, "⚠ Cần xem lại", AMBER)
        else:
            self._set(row, 6, "✔ Đạt", GREEN)

    def _refresh_all(self):
        for r in range(len(self.files)):
            self._render(r)
        self._fill_pages(keep=True)
        self._enable_actions()

    # ------------------------------------------------------------------ chi tiết trang
    def _row(self) -> int:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return rows[0].row() if rows else -1

    def _fill_pages(self, keep: bool = False):
        row = self._row()
        prev = self.ptable.currentRow() if keep else -1
        self._filling = True
        self.ptable.setRowCount(0)
        f = self.files[row] if 0 <= row < len(self.files) else None
        r = self.results.get(f.path) if f else None
        plan = self._plan(f.path) if f else None
        if not plan:
            self.lbl_detail.setText(r.error if r and r.error else "Chọn 1 file đã kiểm tra để xem từng trang.")
            self._filling = False
            return
        pos = {src: k for k, src in enumerate(plan.order)}
        base = {src: k for k, src in enumerate(sorted(plan.order))}
        self.ptable.setRowCount(len(r.pages))
        for i, p in enumerate(r.pages):
            sugg = []
            if p.blank:
                sugg.append("bỏ (trang trắng)" if i not in pos else "trang trắng")
            if i in plan.rotate:
                sugg.append(ROTATE_TEXT[plan.rotate[i]])
            if plan.reordered and i in pos and pos[i] != base[i]:
                sugg.append(f"chuyển tới vị trí {pos[i] + 1}")
            if i in plan.suspicious:
                sugg.append("số lạ – bỏ qua khi sắp")
            vals = [i + 1, "" if p.number is None else p.number,
                    "Trắng" if p.blank else K.ANGLE_TEXT.get(p.angle, "?"), " · ".join(sugg) or "—"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c != 1:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c < 3:
                    it.setTextAlignment(Qt.AlignCenter)
                self.ptable.setItem(i, c, it)
            color = AMBER if sugg and sugg != ["trang trắng"] else (GRAY if p.blank else TEXT)
            for c in (2, 3):
                self.ptable.item(i, c).setForeground(QColor(color))
            if p.edited:
                self.ptable.item(i, 1).setForeground(QColor("#1D4ED8"))
                self.ptable.item(i, 1).setToolTip("Đã sửa tay")
        notes = [f"<b>{os.path.basename(f.path)}</b> · {len(r.pages)} trang · đọc {r.seconds:.1f} giây"]
        if plan.sort_note:
            notes.append(f"<span style='color:{AMBER}'>{plan.sort_note}</span>")
        if plan.missing and plan.unread:
            notes.append(f"Số {', '.join(map(str, plan.missing[:8]))} có thể nằm ở {plan.unread} trang chưa đọc được "
                         "số – bấm đôi ô Số in để nhập tay.")
        self.lbl_detail.setText("<br>".join(notes))
        self._filling = False
        if 0 <= prev < self.ptable.rowCount():
            self.ptable.selectRow(prev)

    def page_selected(self):
        if self._filling:
            return
        i = self.ptable.currentRow()
        f = self.files[self._row()] if 0 <= self._row() < len(self.files) else None
        if i < 0 or not f:
            return
        if self._view == "fixed":
            if f.path in self.fixed and os.path.normcase(self.fixed[f.path]) == os.path.normcase(f.path):
                return                                   # đã ghi đè: thứ tự đã đổi, giữ trang đang xem
            plan = self._plan(f.path)
            if plan and i in plan.order:
                self.preview.goto(plan.order.index(i))
        else:
            self.preview.goto(i)

    def page_edited(self, item: QTableWidgetItem):
        if self._filling or item.column() != 1:
            return
        f = self.files[self._row()]
        r = self.results.get(f.path)
        if not r:
            return
        t = item.text().strip()
        p = r.pages[item.row()]
        if t == "":
            p.number = None
        elif t.isdigit() and 1 <= int(t) <= 9999:
            p.number = int(t)
        else:
            QMessageBox.warning(self, "Số trang", "Hãy nhập số nguyên dương (để trống = không có số).")
            self._fill_pages(keep=True)
            return
        p.edited = True
        self._render(self._row())
        self._fill_pages(keep=True)
        self._enable_actions()

    def page_menu(self, pos):
        i = self.ptable.rowAt(pos.y())
        row = self._row()
        if i < 0 or row < 0:
            return
        r = self.results.get(self.files[row].path)
        if not r:
            return
        m = QMenu(self)
        for text, ang in (("Trang đúng chiều (không xoay)", 0), ("Trang bị ngược – xoay 180°", 180),
                          ("Nằm ngang – xoay 90° sang phải", 270), ("Nằm ngang – xoay 90° sang trái", 90)):
            a = m.addAction(text)
            a.setCheckable(True)
            a.setChecked((r.pages[i].angle or 0) == ang)
            a.triggered.connect(lambda _=False, g=ang: self._set_angle(i, g))
        m.exec(self.ptable.viewport().mapToGlobal(pos))

    def _set_angle(self, i: int, ang: int):
        r = self.results.get(self.files[self._row()].path)
        r.pages[i].angle, r.pages[i].edited = ang, True
        r.pages[i].blank = False
        self._render(self._row())
        self._fill_pages(keep=True)
        self._enable_actions()

    # ------------------------------------------------------------------ xem trước
    def show_selected(self):
        row = self._row()
        same = row >= 0 and row == self._shown_row
        self._shown_row = row
        self._fill_pages()
        if row < 0:
            self.preview.clear()
            self.btn_orig.setEnabled(False)
            self.btn_fixed.setEnabled(False)
            return
        f = self.files[row]
        orig, fixed = f.path, self.fixed.get(f.path, "")
        if fixed and not os.path.isfile(fixed):
            fixed = ""
        if fixed and os.path.normcase(fixed) == os.path.normcase(f.path):
            bak = os.path.join(os.path.dirname(f.path), "_backup_goc", os.path.basename(f.path))
            orig = bak if os.path.isfile(bak) else ""
        if self._view == "fixed" and not fixed:
            self._view = "orig"
        if self._view == "orig" and not orig:
            self._view = "fixed"
        self.btn_orig.setEnabled(bool(orig))
        self.btn_fixed.setEnabled(bool(fixed))
        self.btn_orig.setChecked(self._view == "orig")
        self.btn_fixed.setChecked(self._view == "fixed")
        path = orig if self._view == "orig" else fixed
        if path:
            self.preview.show_file(path, keep_view=same)
        else:
            self.preview.clear("Không còn bản gốc (đã ghi đè, không sao lưu)")

    def _switch_view(self):
        self._view = "fixed" if self.sender() is self.btn_fixed else "orig"
        self.show_selected()

    # ------------------------------------------------------------------ tiện ích
    def mode_changed(self):
        new = self.rb_new.isChecked()
        self.out_edit.setEnabled(new and not self.running)
        self.ck_backup.setEnabled(not new and not self.running)

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu file đã sửa", self.out_edit.text())
        if d:
            self.out_edit.setText(os.path.normpath(d))

    def _need_fix(self) -> List[int]:
        out = []
        for i, f in enumerate(self.files):
            plan = self._plan(f.path)
            if plan and plan.needs_fix and f.path not in self.fixed and not self._skipped(f):
                out.append(i)
        return out

    def _enable_actions(self):
        run = self.running
        ocr = pagenum.available()
        self.btn_check.setEnabled(not run and ocr and bool(self.files))
        self.btn_fix.setEnabled(not run and bool(self._need_fix()))
        for w in (self.ck_rot, self.ck_sort, self.ck_blank, self.ck_signed, self.rb_new, self.rb_over):
            w.setEnabled(not run)
        self.ptable.setEnabled(not run)
        self.mode_changed()
        self.btn_stop.setEnabled(run)
        self.prog.setVisible(run)

    def _start(self, mode: str, fn, jobs: list, on_error, workers: int):
        self.done_n = 0
        self.prog.setRange(0, max(1, len(jobs)))
        self.prog.setValue(0)
        self.worker = Worker(fn, jobs, workers, on_error)
        self.worker.one.connect(lambda i, r, m=mode: self.on_one(m, i, r))
        self.worker.finished_all.connect(lambda msg, m=mode: self.on_finish(m, msg))
        self.worker.start()
        self._enable_actions()
        self.busyChanged.emit(True)

    def stop(self):
        if self.worker:
            self.worker.cancel_ev.set()
            self.lbl.setText("Đang dừng… (chờ các file đang xử lý xong)")

    # ------------------------------------------------------------------ hành động
    def check(self):
        from PySide6.QtWidgets import QApplication
        only_sel = bool(QApplication.keyboardModifiers() & Qt.ControlModifier) and self._row() >= 0
        idx = [self._row()] if only_sel else range(len(self.files))
        jobs = []
        for i in idx:
            f = self.files[i]
            if f.error:
                continue
            self.fixed.pop(f.path, None)
            self._set(i, 6, "⏳ Đang kiểm tra…")
            jobs.append((i, (f.path,)))
        if not jobs:
            self.lbl.setText("Không có file nào để kiểm tra.")
            return
        workers = max(1, min(C.safe_workers(), 4, len(jobs)))
        self.stats = {"ok": 0, "fix": 0, "review": 0, "err": 0}
        self.lbl.setText(f"Đang kiểm tra {fmt(len(jobs))} file bằng {workers} tiến trình (đọc chữ từng trang)…")
        self._start("check", K.job_check, jobs, lambda a, m: K.CheckResult(a[0], error=m), workers)

    def fix(self):
        todo = self._need_fix()
        if not todo:
            return
        overwrite = self.rb_over.isChecked()
        out = self.out_edit.text().strip()
        if not overwrite:
            if not out:
                QMessageBox.warning(self, "Thiếu thư mục đích", "Hãy chọn thư mục lưu file đã sửa.")
                return
            root = os.path.normcase(os.path.abspath(self.root))
            o = os.path.normcase(os.path.abspath(out))
            if o == root or o.startswith(root + os.sep):
                QMessageBox.warning(self, "Thư mục đích", "Thư mục đích không được nằm trong thư mục nguồn.")
                return
        elif QMessageBox.question(
                self, "Ghi đè file gốc",
                f"Sẽ xoay / sắp xếp lại và GHI ĐÈ {len(todo)} file gốc."
                + ("\nBản gốc được sao lưu vào thư mục _backup_goc cạnh mỗi file." if self.ck_backup.isChecked()
                   else "\nKhông sao lưu – KHÔNG thể hoàn tác.") + "\n\nTiếp tục?") != QMessageBox.Yes:
            return
        self.release_cb()
        self.preview.release()
        jobs, copied = [], 0
        todo_set = set(todo)
        for i, f in enumerate(self.files):
            if f.error:
                continue
            dst = f.path if overwrite else os.path.join(out, f.rel)
            if i in todo_set:
                plan = self._plan(f.path)
                self._set(i, 6, "⏳ Đang sửa…")
                jobs.append((i, (f.path, dst, plan.order, plan.rotate, overwrite and self.ck_backup.isChecked())))
            elif not overwrite and f.path in self.results:
                # thư mục mới đủ bộ: file không cần sửa (hoặc đã ký số) chép nguyên
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(f.path, dst)
                    copied += 1
                except OSError as e:
                    self._set(i, 6, f"Lỗi chép: {e.strerror}", RED)
        self.stats = {"ok": 0, "err": 0, "copied": copied}
        self._overwrite = overwrite
        self.lbl.setText(f"Đang sửa {fmt(len(jobs))} file…")
        self._start("fix", K.job_fix, jobs, lambda a, m: m, max(1, min(C.safe_workers(), len(jobs))))

    def on_one(self, mode: str, i: int, res):
        self.done_n += 1
        self.prog.setValue(self.done_n)
        if not 0 <= i < len(self.files):
            return
        f = self.files[i]
        if mode == "check":
            self.results[f.path] = res
            plan = self._plan(f.path)
            key = "err" if res.error else "fix" if plan and plan.needs_fix else \
                "review" if plan and (plan.issues() or plan.sort_note) else "ok"
            self.stats[key] += 1
        else:
            job = next(a for k, a in self.worker.jobs if k == i)
            if res:
                self.stats["err"] += 1
                self._set(i, 6, f"Lỗi: {res}", RED)
                return
            self.stats["ok"] += 1
            self.fixed[f.path] = job[1]
            if self._overwrite:            # file gốc đã đổi: cập nhật kết quả theo thứ tự / hướng mới
                r = self.results[f.path]
                order, rot = job[2], job[3]
                r.pages = [K.PageInfo(angle=0 if r.pages[k].angle is not None or k in rot else None,
                                      number=r.pages[k].number, blank=r.pages[k].blank) for k in order]
        self._render(i)
        if i == self._row():
            if mode == "fix":
                self._view = "fixed"
            self.show_selected()

    def on_finish(self, mode: str, msg: str):
        self.worker.wait()
        self._enable_actions()
        self.busyChanged.emit(False)
        s = self.stats
        if mode == "check":
            self.lbl.setText(f"✔ Kiểm tra xong: {s['ok']} đạt · {s['fix']} cần sửa · {s['review']} cần xem lại · "
                             f"{s['err']} lỗi. {msg}")
            activity.log("Kiểm tra trang", f"{s['ok']} đạt, {s['fix']} cần sửa, {s['review']} cần xem lại, "
                                           f"{s['err']} lỗi")
        else:
            extra = f" · chép nguyên {s['copied']} file" if s["copied"] else ""
            self.lbl.setText(f"✔ Đã sửa {s['ok']} file · {s['err']} lỗi{extra}. {msg}")
            activity.log("Sửa trang", f"{s['ok']} file đã xoay / sắp xếp, {s['err']} lỗi"
                                      + (" – ghi đè file gốc" if self._overwrite else f" – lưu {self.out_edit.text()}"))
            if s["ok"] and self._overwrite:
                self.changed.emit()
