"""Tab GIẢM DUNG LƯỢNG PDF: nén theo giới hạn dung lượng mỗi trang (đa tiến trình)."""
from __future__ import annotations

import os
import shutil
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QRadioButton, QSpinBox,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import activity, compressor as C
from ..core.models import FileInfo
from .common import fmt, fmt_size
from .preview import PreviewPane

DEFAULT_LIMIT_KB = 250     # mặc định 250 KB/trang (chữ scan 300 dpi vẫn rõ – xem README)

STATUS_COLOR = {C.ST_COMPRESSED: "#15803D", C.ST_OK_ALREADY: "#15803D", C.ST_PARTIAL: "#B45309",
                C.ST_NO_IMAGE: "#B45309", C.ST_NO_GAIN: "#B45309", C.ST_ERROR: "#DC2626",
                C.ST_ENCRYPTED: "#DC2626", C.ST_SKIP_SIGNED: "#64748B"}


class Worker(QThread):
    one = Signal(int, object)        # chỉ mục, Result
    finished_all = Signal(str)

    def __init__(self, mode: str, jobs: list, workers: int):
        super().__init__()
        self.mode, self.jobs, self.workers = mode, jobs, workers   # jobs: [(index, args)]
        self.cancel_ev = threading.Event()

    def run(self):
        fn = C.job_measure if self.mode == "measure" else C.job_compress
        msg = ""
        try:
            with ProcessPoolExecutor(max_workers=self.workers) as ex:
                futs = {ex.submit(fn, args): (idx, args) for idx, args in self.jobs}
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
                        self.one.emit(idx, C.Result(path=args[0], status=C.ST_ERROR, message=f"Lỗi: {e}"))
        except Exception as e:
            msg = f"Lỗi: {e}"
        self.finished_all.emit(msg)


class CompressPanel(QWidget):
    COLS = ["STT", "Tên file", "Thư mục", "Trang", "Trang nặng nhất", "Trang vượt", "Dung lượng", "Trạng thái"]
    changed = Signal()
    busyChanged = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.files: List[FileInfo] = []
        self.root = ""
        self.worker: Optional[Worker] = None
        self.memory: Dict[str, Tuple[str, C.Result]] = {}   # path → (mode, kết quả) giữ lại sau khi quét lại
        self.release_cb: Callable[[], None] = lambda: None

        # bố cục như Tổng quan: bên trái thiết lập + bảng, bên phải khung xem trước cao hết tab
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 8)
        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split)
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        cfg = QGroupBox("Thiết lập nén")
        cl = QVBoxLayout(cfg)
        row = QHBoxLayout()
        row.addWidget(QLabel("Dung lượng tối đa mỗi trang:"))
        self.sp = QSpinBox()
        self.sp.setRange(20, 20000)
        self.sp.setValue(DEFAULT_LIMIT_KB)          # lần sau mở app: giá trị đã chọn được nạp lại (ui/persist.py)
        self.sp.setSuffix(" KB")
        self.sp.setMinimumWidth(110)
        row.addWidget(self.sp)
        row.addSpacing(16)
        self.ck_clean = QCheckBox("✨ Rõ chữ (khuyến nghị)")
        self.ck_clean.setToolTip("Làm trắng nền giấy, chữ đậm và sắc hơn; trang không có màu (không dấu đỏ, chữ ký màu)\n"
                                 "lưu ảnh xám – nhẹ hơn, nén nhanh hơn. Trang có dấu đỏ / ảnh màu vẫn giữ màu.\n"
                                 "Bỏ chọn nếu cần giữ nguyên màu giấy như bản scan.")
        self.ck_clean.setChecked(True)
        row.addWidget(self.ck_clean)
        row.addSpacing(16)
        self.ck_signed = QCheckBox("Bỏ qua file đã ký số")
        self.ck_signed.setToolTip("Khuyến nghị – nén làm mất hiệu lực chữ ký số.")
        self.ck_signed.setChecked(True)
        row.addWidget(self.ck_signed)
        row.addStretch(1)
        cl.addLayout(row)
        row = QHBoxLayout()
        self.rb_new = QRadioButton("Lưu sang thư mục mới (giữ file gốc)")
        self.rb_over = QRadioButton("Ghi đè file gốc")
        self.rb_new.setChecked(True)
        row.addWidget(self.rb_new)
        row.addWidget(self.rb_over)
        self.ck_backup = QCheckBox("Sao lưu bản gốc vào _backup_goc")
        self.ck_backup.setChecked(True)
        row.addWidget(self.ck_backup)
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
        hint = QLabel("Chỉ nén ảnh trên các trang vượt giới hạn; mặc định 250 KB/trang. Ảnh trên 300 dpi được hạ về 300 dpi. "
                      "File chỉ có chữ/vector (không có ảnh) không nén được.")
        hint.setStyleSheet("color:#64748B;font-size:9pt")
        hint.setWordWrap(True)
        cl.addWidget(hint)
        lay.addWidget(cfg)
        self.rb_new.toggled.connect(self.mode_changed)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, w in enumerate((44, 300, 150, 52, 130, 80, 160, 220)):
            self.table.setColumnWidth(i, w)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self.show_selected)
        self.table.cellDoubleClicked.connect(lambda r, c: self.preview.open_external())
        lay.addWidget(self.table, 1)

        # ---- xem trước: bản gốc ↔ bản đã nén (so độ rõ của chữ trước / sau khi nén)
        pbox = QGroupBox("Xem Trước File PDF")
        pl = QVBoxLayout(pbox)
        pl.setContentsMargins(8, 8, 8, 8)
        sw = QHBoxLayout()
        self.btn_orig = QPushButton("📄 Bản gốc")
        self.btn_comp = QPushButton("🗜 Bản đã nén")
        for b, tip in ((self.btn_orig, "Xem file gốc (trước khi nén)"),
                       (self.btn_comp, "Xem file sau khi nén – so độ rõ của chữ với bản gốc")):
            b.setCheckable(True)
            b.setObjectName("flat")
            b.setProperty("size", "sm")
            b.setToolTip(tip)
            b.clicked.connect(self._switch_view)
            sw.addWidget(b)
        sw.addStretch(1)
        pl.addLayout(sw)
        self.lbl_view = QLabel("")
        self.lbl_view.setObjectName("Hint")
        self.lbl_view.setWordWrap(True)
        pl.addWidget(self.lbl_view)
        self.preview = PreviewPane(title="")
        pl.addWidget(self.preview, 1)
        pbox.setMinimumWidth(300)
        self._view = "orig"

        bot = QHBoxLayout()
        self.lbl = QLabel("Chưa có dữ liệu – hãy chọn thư mục và bấm Quét.")
        self.lbl.setStyleSheet("font-weight:700;color:#1E40AF")
        self.lbl.setWordWrap(True)
        bot.addWidget(self.lbl, 1)
        self.prog = QProgressBar()
        self.prog.setFixedWidth(180)
        self.prog.hide()
        bot.addWidget(self.prog)
        self.btn_an = QPushButton("🔍 Phân tích")
        self.btn_an.setToolTip("Phân tích dung lượng từng trang, đếm trang vượt giới hạn")
        self.btn_an.setObjectName("cyan")
        self.btn_an.clicked.connect(self.analyze)
        self.btn_stop = QPushButton("■ Dừng")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.clicked.connect(self.stop)
        self.btn_stop.setEnabled(False)
        self.btn_go = QPushButton("⚡ BẮT ĐẦU NÉN")
        self.btn_go.setObjectName("success")
        self.btn_go.setProperty("size", "lg")
        self.btn_go.clicked.connect(self.compress)
        for w in (self.btn_an, self.btn_stop, self.btn_go):
            bot.addWidget(w)
        lay.addLayout(bot)
        split.addWidget(left)
        split.addWidget(pbox)
        split.setStretchFactor(0, 66)
        split.setStretchFactor(1, 34)
        split.setSizes([900, 480])
        split.setChildrenCollapsible(False)
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
            self.memory.clear()
            base = root.rstrip(os.sep)
            self.out_edit.setText(os.path.join(os.path.dirname(base), os.path.basename(base) + " - Đã nén"))
        self.files, self.root = files, root
        self.lbl_scope.setText(f"Phạm vi: <b>{scope_label}</b> · {fmt(len(files))} file")
        self.table.setRowCount(len(files))
        for r, f in enumerate(files):
            vals = [r + 1, f.name, f.dir_rel or "(gốc)", f.pages if f.pages is not None else "—", "", "",
                    fmt_size(f.size), "Chưa phân tích"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c in (0, 3, 5):
                    it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(r, c, it)
            if f.error:
                self._set(r, 7, f.error, "#DC2626")
            elif f.path in self.memory:
                mode, res = self.memory[f.path]
                self._render(mode, r, res, from_memory=True)
        self.lbl.setText(f"{fmt(len(files))} file trong phạm vi. Bấm “Phân tích” để xem trang vượt giới hạn, "
                         "hoặc bắt đầu nén luôn." if files else "Không có file nào trong phạm vi.")
        self._enable_actions()
        self.show_selected()

    # ------------------------------------------------------------------ xem trước
    def _paths_of(self, row: int) -> Tuple[str, str]:
        """(file gốc, file đã nén) của dòng `row`; '' nếu chưa có. Ghi đè có sao lưu → gốc nằm ở _backup_goc."""
        if not 0 <= row < len(self.files):
            return "", ""
        f = self.files[row]
        orig, comp = f.path, ""
        mode, r = self.memory.get(f.path, ("", None))
        if mode == "compress" and r and r.status in (C.ST_COMPRESSED, C.ST_PARTIAL) and r.out_path \
                and os.path.isfile(r.out_path):
            comp = r.out_path
            if os.path.normcase(os.path.abspath(r.out_path)) == os.path.normcase(os.path.abspath(f.path)):
                bak = os.path.join(os.path.dirname(f.path), "_backup_goc", os.path.basename(f.path))
                orig = bak if os.path.isfile(bak) else ""
        return orig, comp

    def show_selected(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        row = rows[0].row() if rows else -1
        orig, comp = self._paths_of(row)
        same_doc = row >= 0 and row == getattr(self, "_shown_row", -1)    # cùng file: giữ trang khi đổi gốc ↔ nén
        self._shown_row = row
        if row < 0:
            self.preview.clear()
            self.lbl_view.setText("")
            self.btn_orig.setEnabled(False)
            self.btn_comp.setEnabled(False)
            return
        if self._view == "comp" and not comp:
            self._view = "orig"
        if self._view == "orig" and not orig:
            self._view = "comp"
        self.btn_orig.setEnabled(bool(orig))
        self.btn_comp.setEnabled(bool(comp))
        self.btn_orig.setChecked(self._view == "orig")
        self.btn_comp.setChecked(self._view == "comp")
        path = orig if self._view == "orig" else comp
        mode, r = self.memory.get(self.files[row].path, ("", None))
        if comp and r:
            self.lbl_view.setText(f"Đang xem: <b>{'bản gốc' if self._view == 'orig' else 'bản đã nén'}</b> · "
                                  f"{fmt_size(r.before)} → {fmt_size(r.after)} · trang nặng nhất "
                                  f"{r.max_before_kb:,.0f} → {r.max_after_kb:,.0f} KB".replace(",", "."))
        else:
            self.lbl_view.setText("Nén xong sẽ bấm được <b>Bản đã nén</b> để so độ rõ của chữ.")
        if path:
            self.preview.show_file(path, keep_view=same_doc)
        else:
            self.preview.clear("Không còn bản gốc (đã ghi đè, không sao lưu)")

    def _switch_view(self):
        self._view = "comp" if self.sender() is self.btn_comp else "orig"
        self.show_selected()

    # ------------------------------------------------------------------ tiện ích
    def mode_changed(self):
        new = self.rb_new.isChecked()
        self.out_edit.setEnabled(new)
        self.ck_backup.setEnabled(not new)

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu file đã nén", self.out_edit.text())
        if d:
            self.out_edit.setText(os.path.normpath(d))

    def _skipped(self, f: FileInfo) -> bool:
        return self.ck_signed.isChecked() and (f.has_real_sig or f.name_signed)

    def _set(self, row: int, col: int, text, color: Optional[str] = None):
        it = self.table.item(row, col)
        it.setText(str(text))
        it.setForeground(QColor(color or "#1E293B"))

    def _enable_actions(self):
        run = self.running
        for w in (self.btn_an, self.btn_go):
            w.setEnabled(not run and bool(self.files))
        for w in (self.sp, self.ck_clean, self.ck_signed, self.rb_new, self.rb_over, self.out_edit, self.ck_backup):
            w.setEnabled(not run)
        if not run:
            self.mode_changed()
        self.btn_stop.setEnabled(run)
        self.prog.setVisible(run)

    def _start(self, mode: str, jobs: list):
        self.done_n = 0
        self.prog.setRange(0, max(1, len(jobs)))
        self.prog.setValue(0)
        self.worker = Worker(mode, jobs, C.safe_workers())
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
    def analyze(self):
        limit = self.sp.value()
        jobs = []
        for i, f in enumerate(self.files):
            if f.error:
                continue
            if self._skipped(f):
                self._set(i, 7, C.STATUS_TEXT[C.ST_SKIP_SIGNED], "#64748B")
            else:
                self._set(i, 7, "⏳ Đang phân tích…")
                jobs.append((i, (f.path, limit)))
        if not jobs:
            self.lbl.setText("Không có file nào cần phân tích.")
            return
        self.lbl.setText(f"Đang phân tích {fmt(len(jobs))} file…")
        self._start("measure", jobs)

    def compress(self):
        limit = self.sp.value()
        overwrite = self.rb_over.isChecked()
        out = self.out_edit.text().strip()
        if not overwrite:
            if not out:
                QMessageBox.warning(self, "Thiếu thư mục đích", "Hãy chọn thư mục lưu file đã nén.")
                return
            root = os.path.normcase(os.path.abspath(self.root))
            o = os.path.normcase(os.path.abspath(out))
            if o == root or o.startswith(root + os.sep):
                QMessageBox.warning(self, "Thư mục đích", "Thư mục đích không được nằm trong thư mục nguồn.")
                return
        elif QMessageBox.question(
                self, "Ghi đè file gốc",
                "Các file sẽ được nén và GHI ĐÈ lên file gốc."
                + ("\nBản gốc được sao lưu vào thư mục _backup_goc cạnh mỗi file." if self.ck_backup.isChecked()
                   else "\nKhông sao lưu – KHÔNG thể hoàn tác.") + "\n\nTiếp tục?") != QMessageBox.Yes:
            return
        self.release_cb()
        jobs = []
        for i, f in enumerate(self.files):
            if f.error:
                continue
            dst = f.path if overwrite else os.path.join(out, f.rel)
            if self._skipped(f):
                msg = C.STATUS_TEXT[C.ST_SKIP_SIGNED]
                if not overwrite:
                    try:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(f.path, dst)
                        msg += " (đã chép nguyên)"
                    except OSError as e:
                        msg = f"Lỗi chép: {e.strerror}"
                self._set(i, 7, msg, "#64748B")
                continue
            self._set(i, 7, "⏳ Đang nén…")
            jobs.append((i, (f.path, dst, limit, overwrite and self.ck_backup.isChecked())))
        if not jobs:
            self.lbl.setText("Không có file nào để nén.")
            return
        # chia nhân CPU: ít file thì mỗi file dùng nhiều luồng xử lý ảnh, nhiều file thì mỗi file 1–2 luồng
        procs = min(C.safe_workers(), len(jobs))
        threads = max(1, min(8, ((os.cpu_count() or 2) - 1) // procs))
        jobs = [(i, args + (threads, self.ck_clean.isChecked())) for i, args in jobs]
        self.stats = {"before": 0, "after": 0, "ok": 0, "partial": 0, "fail": 0}
        self.lbl.setText(f"Đang nén {fmt(len(jobs))} file bằng {C.safe_workers()} tiến trình…")
        self._start("compress", jobs)

    def _render(self, mode: str, i: int, r: C.Result, from_memory: bool = False):
        color = STATUS_COLOR.get(r.status, "#1E293B")
        changed = mode == "compress" and r.after != r.before
        if r.status not in (C.ST_ERROR, C.ST_ENCRYPTED):
            if r.pages:
                self._set(i, 3, r.pages)
            self._set(i, 4, f"{r.max_before_kb:,.0f} KB".replace(",", ".")
                      + (f" → {r.max_after_kb:,.0f} KB".replace(",", ".") if changed else ""))
            self._set(i, 5, f"{r.over_before}" + (f" → {r.over_after}" if changed else ""),
                      "#B45309" if (r.over_after if changed else r.over_before) else "#15803D")
        if mode == "compress":
            self._set(i, 6, f"{fmt_size(r.before)} → {fmt_size(r.after)}" if changed else fmt_size(r.before),
                      "#15803D" if changed else None)
        text = r.message if (r.status == C.ST_ERROR and r.message) else C.STATUS_TEXT.get(r.status, r.status)
        if mode == "measure" and r.status == C.ST_OK_ALREADY:
            text, color = ("⚠ Cần nén" if r.over_before else "✔ Đã đạt chuẩn"), ("#B45309" if r.over_before else "#15803D")
        elif r.status in (C.ST_COMPRESSED, C.ST_OK_ALREADY):
            text = "✔ " + text
        self._set(i, 7, text, color)

    def on_one(self, mode: str, i: int, r: C.Result):
        self.done_n += 1
        self.prog.setValue(self.done_n)
        if 0 <= i < len(self.files):
            self.memory[self.files[i].path] = (mode, r)
        self._render(mode, i, r)
        rows = self.table.selectionModel().selectedRows()
        if mode == "compress" and rows and rows[0].row() == i:
            self._view = "comp"
            self.show_selected()
        if mode == "compress":
            self.stats["before"] += r.before
            self.stats["after"] += r.after
            if r.status in (C.ST_COMPRESSED, C.ST_OK_ALREADY):
                self.stats["ok"] += 1
            elif r.status in (C.ST_PARTIAL, C.ST_NO_IMAGE, C.ST_NO_GAIN):
                self.stats["partial"] += 1
            else:
                self.stats["fail"] += 1

    def on_finish(self, mode: str, msg: str):
        self.worker.wait()
        self._enable_actions()
        self.busyChanged.emit(False)
        if mode == "compress":
            s = self.stats
            saved = max(0, s["before"] - s["after"])
            self.lbl.setText(f"✔ Xong: {s['ok']} đạt · {s['partial']} chưa đạt/không nén được · {s['fail']} lỗi · "
                             f"giảm {fmt_size(saved)}. {msg}")
            activity.log("Nén PDF", f"{s['ok']} đạt, {s['partial']} chưa đạt, {s['fail']} lỗi, giảm {fmt_size(saved)} "
                                    f"– giới hạn {self.sp.value()} KB/trang")
            if saved and self.rb_over.isChecked():
                self.changed.emit()
        else:
            need = sum(1 for m, r in self.memory.values() if m == "measure" and r.over_before)
            self.lbl.setText(f"Phân tích xong: {need} file có trang vượt {self.sp.value()} KB. {msg}")
