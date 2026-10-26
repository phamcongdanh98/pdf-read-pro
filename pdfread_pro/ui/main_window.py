"""Cửa sổ chính (bố cục kiểu Hồ sơ 1361): khung Cấu hình & thư mục nguồn + hàng nút công cụ,
các tab chức năng, thanh tiến trình và nhật ký thao tác ở dưới."""
from __future__ import annotations

import os
import threading
import time
from typing import Dict, List, Optional

from PySide6.QtCore import QSettings, Qt, QThread, Signal
from PySide6.QtGui import QColor, QGuiApplication, QTextCursor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QSplitter, QTabWidget, QTextBrowser,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import paths
from ..core import activity, renamer, scanner, stats as st
from ..core.models import FILTER_ALL, FILTER_SIGNED, FILTER_UNSIGNED, FileInfo, ScanResult, match_filter
from .common import REVIEW_TEXT, ListDialog, fmt, fmt_size, open_path, reveal, sig_label, who_when
from .compress_panel import CompressPanel
from .guide import GUIDE_HTML
from .preview import PreviewPane, release_document
from .rename_panel import RenamePanel
from .report_panel import ReportPanel
from .compare_panel import ComparePanel
from .rules1361_panel import Rules1361Panel
from .split_panel import SplitPanel
from .rules_panel import RulesPanel
from .styles import button
from .widgets import ElidedLabel, StatCard

ROLE = Qt.UserRole
FILTER_TITLES = {FILTER_ALL: "", FILTER_SIGNED: " · CHỈ .SIGNED", FILTER_UNSIGNED: " · KHÔNG .SIGNED"}
FILTER_SHORT = {FILTER_ALL: "", FILTER_SIGNED: " (chỉ .signed)", FILTER_UNSIGNED: " (không .signed)"}


class ScanThread(QThread):
    progress = Signal(int, int, int)
    finished_scan = Signal(object)

    def __init__(self, root: str, recursive: bool):
        super().__init__()
        self.root, self.recursive = root, recursive
        self.cancel_ev = threading.Event()
        self._last = 0.0

    def _cb(self, done: int, total: int, pages: int) -> None:
        now = time.monotonic()
        if done == total or now - self._last > 0.05:
            self._last = now
            self.progress.emit(done, total, pages)

    def run(self):
        self.finished_scan.emit(scanner.scan(self.root, self.recursive, self._cb, self.cancel_ev))


def _btn(text: str, obj: str = "primary", slot=None, tip: str = "", size: str = "") -> QPushButton:
    return button(text, obj or "primary", slot, tip, size)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{paths.APP_NAME} v{paths.APP_VERSION} – Đọc, kiểm tra và xử lý PDF")
        self.resize(1440, 900)
        self.setAcceptDrops(True)
        self.settings = QSettings("PDFReadPro", "PDFReadPro")
        self.result: Optional[ScanResult] = None
        self.mode = FILTER_ALL
        self.scope: Optional[str] = None
        self.thread: Optional[ScanThread] = None
        self.scanning = False
        self.dir_items: Dict[str, QTreeWidgetItem] = {}
        self.file_items: List[tuple] = []
        activity.add_listener(self._on_activity)
        self._build_ui()
        last = self.settings.value("last_folder", "")
        if last and os.path.isdir(last):
            self.path_edit.setText(last)
        self._update_cards()
        self._push_files()
        self._check_journal()
        self._log_line("Sẵn sàng", f"{paths.APP_NAME} v{paths.APP_VERSION}")

    # ================================================================= dựng giao diện
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 8)
        root.setSpacing(8)

        # ---- banner tiêu đề (kiểu Hồ sơ 1361)
        head = QFrame()
        head.setObjectName("HeaderFrame")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 5, 14, 5)
        icon = QLabel("📑")
        icon.setStyleSheet("font-size:16pt;")
        hl.addWidget(icon)
        t = QLabel("PDF-READ PRO")
        t.setObjectName("AppTitle")
        hl.addWidget(t)
        hl.addSpacing(12)
        sub = QLabel("Kiểm tra chữ ký số · Đổi tên chuẩn 1361 · Tách trang · Giảm dung lượng · Báo cáo hồ sơ số hoá")
        sub.setObjectName("AppSubtitle")
        hl.addWidget(sub, 0, Qt.AlignVCenter)
        hl.addStretch(1)
        ver = QLabel(f"v{paths.APP_VERSION}")
        ver.setObjectName("VersionPill")
        hl.addWidget(ver, 0, Qt.AlignVCenter)
        root.addWidget(head)

        # ---- khung cấu hình & thư mục nguồn
        cfg = QGroupBox("Cấu hình && Thư mục nguồn")
        cl = QVBoxLayout(cfg)
        cl.setSpacing(8)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Thư mục chứa file:"))
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Chọn hoặc dán đường dẫn thư mục chứa các file .pdf… (có thể kéo thả thư mục vào cửa sổ)")
        self.path_edit.returnPressed.connect(self.start_scan)
        r1.addWidget(self.path_edit, 1)
        r1.addWidget(_btn("📁 Chọn Thư Mục...", "primary", self.choose_folder, size="sm"))
        self.btn_scan = _btn("🔍 Quét / Làm Mới", "success", self.start_scan, "Quét lại thư mục (F5)", "sm")
        self.btn_scan.setShortcut("F5")
        r1.addWidget(self.btn_scan)
        r1.addWidget(_btn("✖ Clear", "danger", self.clear_all, "Xóa đường dẫn thư mục đã chọn", "sm"))
        cl.addLayout(r1)

        r2 = QHBoxLayout()
        self.chk_rec = QCheckBox("Quét tất cả thư mục con bên trong (Recursive Scan)")
        self.chk_rec.setChecked(self.settings.value("recursive", "true") != "false")
        r2.addWidget(self.chk_rec)
        r2.addSpacing(24)
        r2.addWidget(QLabel("Tính số trang:"))
        self.combo = QComboBox()
        self.combo.addItem("Tất cả file", FILTER_ALL)
        self.combo.addItem("Chỉ file .signed", FILTER_SIGNED)
        self.combo.addItem("Không tính file .signed", FILTER_UNSIGNED)
        self.combo.setMinimumWidth(200)
        self.combo.currentIndexChanged.connect(self.filter_changed)
        r2.addWidget(self.combo)
        r2.addStretch(1)
        self.lbl_root = QLabel("", self)        # giữ để tương thích – đường dẫn đã hiện ở ô thư mục
        self.lbl_root.hide()
        r2.addWidget(QLabel("Công cụ:"))
        for text, slot, tip in (
                ("📋 Kiểm tra đủ 5 file", self.open_check5, "Mỗi thư mục có PDF phải có đủ file 01. – 05."),
                ("🪪 Thư mục CCCD", self.open_cccd, "Thư mục tên đúng 12 chữ số; xoá vào Thùng rác"),
                ("📦 Copy nhóm file", self.open_copy, "Copy file .signed / không .signed ra thư mục mới, giữ cây thư mục")):
            r2.addWidget(_btn(text, "light", slot, tip, "sm"))
        more = _btn("☰ Thêm", "light", None, "Mở thư mục nguồn, nhật ký, dữ liệu ứng dụng", "sm")
        m = QMenu(more)
        m.addAction("📂 Mở thư mục nguồn", self.open_root)
        m.addAction("📜 Nhật ký thao tác", self.show_log)
        m.addAction("🗂 Dữ liệu ứng dụng (bộ quy tắc, lịch sử)", lambda: open_path(paths.data_dir()))
        more.setMenu(m)
        r2.addWidget(more)
        cl.addLayout(r2)
        root.addWidget(cfg)

        # ---- các tab
        self.tabs = QTabWidget()
        self.overview = self._build_overview()
        self.tabs.addTab(self.overview, "📊 Tổng quan")
        self.rules1361 = Rules1361Panel()
        self.rules = RulesPanel()
        self.rules_tabs = QTabWidget()
        self.rules_tabs.setObjectName("SubTabs")
        self.rules_tabs.addTab(self.rules1361, "📋 Bộ quy tắc mã số 1361 (mặc định)")
        self.rules_tabs.addTab(self.rules, "🧩 Mẫu đổi tên tuỳ chỉnh (nâng cao)")
        self.rules_wrap = QWidget()
        rwl = QVBoxLayout(self.rules_wrap)
        rwl.setContentsMargins(8, 8, 8, 8)
        rwl.addWidget(self.rules_tabs)
        self.rename = RenamePanel(self.rules1361, self.rules)
        self.rename.busy_check = self._busy_guard
        self.rename.renamed.connect(self.rescan)
        self.rename.editRulesRequested.connect(
            lambda i: (self.tabs.setCurrentWidget(self.rules_wrap), self.rules_tabs.setCurrentIndex(i)))
        self.compress = CompressPanel()
        self.compress.release_cb = release_document
        self.compress.busyChanged.connect(lambda b: self._update_busy())
        self.compress.changed.connect(self.rescan)
        self.split = SplitPanel()
        self.split.saved.connect(self._split_saved)
        self.report = ReportPanel(lambda: self.rules1361.rules)
        self.report.busy_check = self._busy_guard
        self.report.renamed.connect(self.rescan)
        self.rules1361.rulesChanged.connect(self.report.refresh)
        self.compare = ComparePanel(lambda: self.report.rep)
        self.compare.busy_check = self._busy_guard
        self.compare.changed.connect(self.rescan)
        self.tabs.addTab(self.rename, "🏷 Đổi tên")
        self.tabs.addTab(self.split, "✂ Tách trang")
        self.tabs.addTab(self.compress, "⚡ Giảm dung lượng")
        self.tabs.addTab(self.report, "📑 Báo cáo hồ sơ")
        self.tabs.addTab(self.compare, "🔗 Đối chiếu danh sách")
        self.tabs.addTab(self.rules_wrap, "⚙ Bộ quy tắc")
        guide = QTextBrowser()
        guide.setOpenExternalLinks(True)
        guide.setHtml(GUIDE_HTML)
        gw = QWidget()
        gl = QVBoxLayout(gw)
        gl.setContentsMargins(16, 10, 16, 10)
        gl.addWidget(guide)
        self.tabs.addTab(gw, "📖 Hướng dẫn")
        root.addWidget(self.tabs, 1)

        # ---- tiến trình + nhật ký
        bar = QHBoxLayout()
        self.status = QLabel("Sẵn sàng. Chọn thư mục rồi bấm Quét.")
        self.status.setObjectName("StatusText")
        bar.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(320)
        self.progress.hide()
        bar.addWidget(self.progress)
        self.btn_stop = _btn("■ Dừng", "danger", self.stop_scan)
        self.btn_stop.hide()
        bar.addWidget(self.btn_stop)
        self.btn_log = _btn("📜 Nhật ký", "flat", None, "Hiện / ẩn nhật ký thao tác", "sm")
        self.btn_log.setCheckable(True)
        bar.addWidget(self.btn_log)
        root.addLayout(bar)
        self.log_box = QPlainTextEdit()
        self.log_box.setObjectName("log")
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(500)
        self.log_box.setFixedHeight(58)
        self.log_box.setPlaceholderText("Nhật ký thao tác sẽ hiển thị ở đây…")
        root.addWidget(self.log_box)
        show_log = self.settings.value("show_log", "false") == "true"
        self.log_box.setVisible(show_log)
        self.btn_log.setChecked(show_log)
        self.btn_log.toggled.connect(self._toggle_log)

    def _build_overview(self) -> QWidget:
        # Bố cục kiểu Hồ sơ 1361: bên trái (thẻ + cây), bên phải cột xem trước hẹp, cao hết chiều dọc tab
        w = QWidget()
        ol = QHBoxLayout(w)
        ol.setContentsMargins(10, 10, 10, 8)
        split = QSplitter(Qt.Horizontal)
        ol.addWidget(split)
        left = QWidget()
        lay = QVBoxLayout(left)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.cards: Dict[str, StatCard] = {}
        for i, (k, t, a) in enumerate((("dirs", "THƯ MỤC CÓ PDF", "blue"), ("files", "SỐ FILE PDF", "green"),
                                       ("pages", "TỔNG SỐ TRANG", "violet"), ("sigs", "CHỮ KÝ SỐ", "teal"),
                                       ("review", "CẦN XEM LẠI", "amber"))):
            c = StatCard(k, t, a)
            c.clicked.connect(self.card_clicked)
            self.cards[k] = c
            grid.addWidget(c, 0, i)
            grid.setColumnStretch(i, 1)
        lay.addLayout(grid)

        self.scope_bar = QFrame()
        self.scope_bar.setObjectName("scopeBar")
        sb = QHBoxLayout(self.scope_bar)
        sb.setContentsMargins(12, 4, 8, 4)
        self.scope_lbl = ElidedLabel("")
        self.scope_lbl.setStyleSheet("font-weight:700; color:#1E40AF;")
        sb.addWidget(self.scope_lbl, 1)
        sb.addWidget(_btn("✖ Xem toàn bộ", "flat", self.clear_scope, size="sm"))
        self.scope_bar.hide()
        lay.addWidget(self.scope_bar)

        r = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Tìm tên file / thư mục…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(300)
        self.search.textChanged.connect(self.apply_view)
        r.addWidget(self.search)
        r.addWidget(_btn("⊞ Mở hết", "light", lambda: self.tree.expandAll(), size="sm"))
        r.addWidget(_btn("⊟ Thu gọn", "light", lambda: self.tree.collapseAll(), size="sm"))
        r.addStretch(1)
        hint = QLabel("Bấm thư mục để thống kê riêng · bấm file để xem trước · bấm đôi để mở · chuột phải để thêm lựa chọn")
        hint.setObjectName("Hint")
        r.addWidget(hint)
        lay.addLayout(r)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Thư mục / Tên file", "Số trang", "Dung lượng", "Chữ ký số", "Ngày ký · Người ký"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.tree_menu)
        self.tree.itemSelectionChanged.connect(self.selection_changed)
        self.tree.itemDoubleClicked.connect(self.tree_double)
        self.tree.header().setStretchLastSection(True)
        for i, wd in enumerate((320, 85, 95, 145, 300)):
            self.tree.setColumnWidth(i, wd)
        treebox = QGroupBox("Cây thư mục && danh sách file PDF")
        tl = QVBoxLayout(treebox)
        tl.setContentsMargins(6, 6, 6, 6)
        tl.addWidget(self.tree)
        lay.addWidget(treebox, 1)
        box = QGroupBox("Xem Trước File PDF")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(8, 8, 8, 8)
        self.preview = PreviewPane(title="")
        bl.addWidget(self.preview, 1)
        split.addWidget(left)
        split.addWidget(box)
        split.setStretchFactor(0, 72)
        split.setStretchFactor(1, 28)
        split.setSizes([1040, 400])
        split.setChildrenCollapsible(False)
        box.setMinimumWidth(300)
        return w

    # ================================================================= tiện ích chung
    @property
    def busy(self) -> bool:
        return self.scanning or self.compress.running

    def _update_busy(self):
        self.btn_scan.setEnabled(not self.busy)

    def _busy_guard(self) -> bool:
        if self.busy:
            QMessageBox.information(self, "Đang xử lý", "Đang quét hoặc đang nén – hãy chờ xong rồi thao tác.")
            return True
        return False

    def _toggle_log(self, on: bool):
        self.log_box.setVisible(on)
        self.settings.setValue("show_log", "true" if on else "false")

    def info(self, text: str, title: str = "Thông báo"):
        QMessageBox.information(self, title, text)

    def warn(self, text: str, title: str = "Cảnh báo"):
        QMessageBox.warning(self, title, text)

    def _log_line(self, action: str, detail: str = "", when=None):
        from datetime import datetime
        when = when or datetime.now()
        self.log_box.appendPlainText(f"[{when:%H:%M:%S}] {action}" + (f" – {detail}" if detail else ""))
        self.log_box.moveCursor(QTextCursor.End)

    def _on_activity(self, when, action, detail):
        self._log_line(action, detail, when)

    def _check_journal(self):
        if renamer.pending_journal():
            n = renamer.recover_journal()
            self.warn(f"Lần đổi tên trước bị ngắt giữa chừng. Đã khôi phục {n} file về tên cũ.", "Khôi phục")
            activity.log("Khôi phục đổi tên", f"{n} file")

    # ================================================================= quét
    def choose_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa PDF", self.path_edit.text() or "")
        if d:
            self.path_edit.setText(os.path.normpath(d))
            self.start_scan()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.isdir(p):
                self.path_edit.setText(os.path.normpath(p))
                self.start_scan()
                return

    def open_root(self):
        p = self.result.root if self.result else self.path_edit.text().strip()
        if p and os.path.isdir(p):
            open_path(p)

    def clear_all(self):
        if self.busy:
            return
        self.result = None
        self.scope = None
        self.tree.clear()
        self.dir_items, self.file_items = {}, []
        self.preview.clear()
        self.path_edit.clear()
        self.lbl_root.setText("")
        self._update_scope_bar()
        self._update_cards()
        self._push_files()
        self.report.set_result(None)
        self.compare.refresh()
        self.status.setText("🧹 Đã làm sạch danh sách làm việc.")

    def start_scan(self):
        if self.busy:
            return
        folder = self.path_edit.text().strip().strip('"')
        if not folder or not os.path.isdir(folder):
            self.warn("Đường dẫn thư mục không hợp lệ.")
            return
        self.settings.setValue("last_folder", folder)
        self.settings.setValue("recursive", "true" if self.chk_rec.isChecked() else "false")
        release_document()
        self.preview.clear()
        self.scanning = True
        self._update_busy()
        same_root = self.result is not None and \
            os.path.normcase(self.result.root) == os.path.normcase(os.path.abspath(folder))
        if not same_root:
            self.scope = None
        self.progress.setRange(0, 0)
        self.progress.show()
        self.btn_stop.show()
        self.status.setText("⏳ Đang đọc cấu trúc thư mục…")
        self.thread = ScanThread(folder, self.chk_rec.isChecked())
        self.thread.progress.connect(self.on_progress)
        self.thread.finished_scan.connect(self.on_scan_done)
        self.thread.start()

    def rescan(self):
        if self.result:
            self.path_edit.setText(self.result.root)
        self.start_scan()

    def stop_scan(self):
        if self.thread:
            self.thread.cancel_ev.set()
            self.status.setText("Đang dừng…")

    def on_progress(self, done: int, total: int, pages: int):
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.status.setText(f"⏳ Đang quét: {fmt(done)}/{fmt(total)} file · {fmt(pages)} trang")

    def on_scan_done(self, res: ScanResult):
        self.thread.wait()
        self.progress.hide()
        self.btn_stop.hide()
        self.scanning = False
        self.result = res
        if self.scope and self.scope not in res.dirs:
            self.scope = None
        self._update_busy()
        self.build_tree()
        self.apply_view()
        self._update_scope_bar()
        self._update_cards()
        self._push_files()
        self.report.set_result(res)
        self.compare.refresh()
        self.lbl_root.setText(f"📁 {res.root}")
        tag = " (đã dừng giữa chừng)" if res.cancelled else ""
        s = st.compute(res, None, FILTER_ALL)
        self.status.setText(f"✔ Quét xong{tag}: {fmt(len(res.files))} file PDF · {fmt(s.dirs_with_pdf)} thư mục có PDF · "
                            f"{fmt(s.pages)} trang · {res.seconds:.1f} giây")
        activity.log("Quét", f"{res.root} → {len(res.files)} file, {s.pages} trang")

    def _push_files(self):
        """Đưa danh sách file (theo phạm vi + bộ lọc) sang các tab Đổi tên / Giảm dung lượng / Quy tắc."""
        files = self._scoped_files() if self.result else []
        label = self._scope_label() + FILTER_SHORT[self.mode]
        self.rename.set_files(files, label)
        self.compress.set_files(files, self.result.root if self.result else "", label)
        self.rules.set_sample_files(files)
        self.split.set_files(files)

    # ================================================================= cây thư mục
    def build_tree(self):
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        self.dir_items, self.file_items = {}, []
        res = self.result
        for d in res.dirs:
            if not d:
                continue
            parent = self.dir_items.get(os.path.dirname(d), self.tree.invisibleRootItem())
            it = QTreeWidgetItem(parent, ["📁 " + os.path.basename(d)])
            it.setData(0, ROLE, ("dir", d))
            f = it.font(0)
            f.setBold(True)
            it.setFont(0, f)
            it.setToolTip(0, os.path.join(res.root, d))
            self.dir_items[d] = it
        for f in res.files:
            parent = self.dir_items.get(f.dir_rel, self.tree.invisibleRootItem())
            it = QTreeWidgetItem(parent, ["📄 " + f.name])
            it.setData(0, ROLE, ("file", f))
            it.setToolTip(0, f.path)
            self.file_items.append((it, f))
            label, color = sig_label(f)
            it.setText(1, "—" if f.pages is None else fmt(f.pages))
            it.setText(2, fmt_size(f.size))
            it.setText(3, label)
            it.setForeground(3, QColor(color))
            it.setText(4, who_when(f))
            it.setToolTip(4, who_when(f))
            for c in (1, 2):
                it.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            if f.error:
                it.setForeground(0, QColor("#DC2626"))
                it.setToolTip(0, f"{f.path}\n{f.error}")
        for k, it in self.dir_items.items():
            if not os.path.dirname(k):
                it.setExpanded(True)
        self.tree.setUpdatesEnabled(True)

    def apply_view(self, *_):
        if not self.result:
            return
        q = self.search.text().strip().lower()
        self.tree.setUpdatesEnabled(False)
        visible_dirs = set()
        for it, f in self.file_items:
            show = match_filter(f, self.mode) and (not q or q in f.name.lower() or q in f.dir_rel.lower())
            it.setHidden(not show)
            if show:
                d = f.dir_rel
                while d:
                    visible_dirs.add(d)
                    d = os.path.dirname(d)
        narrow = bool(q) or self.mode != FILTER_ALL
        totals = st.folder_totals(self.result, self.mode)
        for d, it in self.dir_items.items():
            it.setHidden(narrow and d not in visible_dirs)
            dp, tp, dn, tn, ts = totals.get(d, (0, 0, 0, 0, 0))
            it.setText(1, f"Σ {fmt(tp)}" if tn else "—")
            tip = f"{fmt(tp)} trang trong {fmt(tn)} file"
            if tp != dp or tn != dn:
                tip = (f"Trực tiếp trong thư mục: {fmt(dp)} trang / {fmt(dn)} file\n"
                       f"Cả thư mục con: {fmt(tp)} trang / {fmt(tn)} file")
            it.setToolTip(1, tip if tn else "")
            it.setText(3, f"{ts}/{tn} file có ký số" if tn else "")
            it.setForeground(1, QColor("#1E40AF"))
            it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            it.setForeground(3, QColor("#475569"))
        if q:
            for d in visible_dirs:
                self.dir_items[d].setExpanded(True)
        self.tree.setUpdatesEnabled(True)

    def filter_changed(self):
        self.mode = self.combo.currentData()
        self.apply_view()
        self._update_cards()
        self._push_files()

    def selection_changed(self):
        items = self.tree.selectedItems()
        if not items:
            return
        kind, val = items[0].data(0, ROLE)
        if kind == "file":
            f: FileInfo = val
            if f.error:
                self.preview.clear("⚠ " + f.error)
            else:
                self.preview.show_file(f.path)
        elif val != self.scope:
            self._set_scope(val)

    def tree_double(self, item, col):
        kind, val = item.data(0, ROLE)
        if kind == "file" and os.path.exists(val.path):
            open_path(val.path)

    def tree_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        kind, val = item.data(0, ROLE)
        m = QMenu(self)
        if kind == "file":
            m.addAction("📄 Mở file", lambda: open_path(val.path))
            m.addAction("📂 Mở thư mục chứa", lambda: reveal(val.path))
            m.addAction("✂ Tách trang file này", lambda: (self.split.load_file(val.path),
                                                         self.tabs.setCurrentWidget(self.split)))
            m.addAction("📋 Sao chép đường dẫn", lambda: QGuiApplication.clipboard().setText(val.path))
        else:
            full = os.path.join(self.result.root, val)
            m.addAction("📊 Thống kê riêng thư mục này", lambda: self._set_scope(val))
            m.addAction("🏷 Đổi tên file trong thư mục này",
                        lambda: (self._set_scope(val), self.tabs.setCurrentWidget(self.rename)))
            m.addAction("📂 Mở thư mục", lambda: open_path(full))
            m.addAction("📋 Sao chép đường dẫn", lambda: QGuiApplication.clipboard().setText(full))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # ================================================================= phạm vi + thẻ
    def _set_scope(self, rel):
        self.scope = rel
        self._update_scope_bar()
        self._update_cards()
        self._push_files()

    def clear_scope(self):
        self.scope = None
        self.tree.clearSelection()
        self._update_scope_bar()
        self._update_cards()
        self._push_files()

    def _scope_label(self) -> str:
        return " › ".join(self.scope.split(os.sep)) if self.scope else "Toàn bộ"

    def _update_scope_bar(self):
        if self.scope:
            self.scope_lbl.set_full_text(f"📊 Đang xem riêng thư mục: {self._scope_label()}  "
                                         "(áp dụng cho cả tab Đổi tên và Giảm dung lượng)")
            self.scope_bar.show()
        else:
            self.scope_bar.hide()

    def _update_cards(self):
        c = self.cards
        suffix = FILTER_TITLES[self.mode]
        for k, t in (("dirs", "THƯ MỤC CÓ PDF"), ("files", "SỐ FILE PDF"), ("pages", "TỔNG SỐ TRANG"),
                     ("sigs", "CHỮ KÝ SỐ"), ("review", "CẦN XEM LẠI")):
            c[k].title.set_full_text(t + suffix)
        if not self.result:
            for k in c:
                c[k].set_data("0", "Chưa quét thư mục")
            c["review"].set_accent("amber")
            return
        s = st.compute(self.result, self.scope, self.mode)
        c["dirs"].set_data(fmt(s.dirs_with_pdf),
                           f"+{fmt(s.dirs_container_only)} chỉ chứa thư mục con · {fmt(s.dirs_total)} thư mục con",
                           f"Số thư mục có file PDF nằm TRỰC TIẾP trong nó: {s.dirs_with_pdf}.\n"
                           f"Thư mục chỉ chứa thư mục con (không có PDF trực tiếp) không được đếm: {s.dirs_container_only}.\n"
                           f"Tổng số thư mục con trong phạm vi: {s.dirs_total}.")
        c["files"].set_data(fmt(s.files),
                            f".signed: {fmt(s.files_signed_name)} · không .signed: {fmt(s.files_unsigned_name)}",
                            "Số file PDF theo lựa chọn 'Tính số trang'.\n"
                            f"File có .signed trong tên: {s.files_signed_name}\nFile không có .signed: {s.files_unsigned_name}")
        c["pages"].set_data(fmt(s.pages),
                            f".signed: {fmt(s.pages_signed_name)} · không .signed: {fmt(s.pages_unsigned_name)}",
                            "Tổng số trang theo lựa chọn 'Tính số trang'.")
        c["sigs"].set_data(fmt(s.sig_files), f"✔ {s.sig_ok} nguyên · ⚠ {s.sig_modified} sửa · ✖ {s.sig_broken} hỏng",
                           "Số file có chữ ký số thật (đọc từ nội dung file, không dựa vào tên).\n"
                           "✔ nguyên vẹn · ⚠ sửa sau khi ký · ✖ chữ ký hỏng.\n"
                           "Không kiểm tra độ tin cậy của chứng thư (CA).")
        parts = []
        if s.review_sig_no_name:
            parts.append(f"{s.review_sig_no_name} đã ký nhưng tên chưa .signed")
        if s.review_name_no_sig:
            parts.append(f"{s.review_name_no_sig} tên .signed nhưng không có chữ ký")
        if s.review_unreadable:
            parts.append(f"{s.review_unreadable} không đọc được chữ ký")
        if s.review_error:
            parts.append(f"{s.review_error} file lỗi")
        c["review"].set_accent("amber" if s.review else "green")
        c["review"].set_data(fmt(s.review), " · ".join(parts) if parts else "✔ Tên và chữ ký khớp nhau",
                             "\n".join(parts) if parts else "Mọi file có chữ ký số đều đã đặt tên .signed và ngược lại.")

    def _scoped_files(self) -> List[FileInfo]:
        return st.files_in(self.result, self.scope, self.mode)

    def card_clicked(self, key: str):
        if not self.result:
            return
        files = self._scoped_files()
        sub = f"Phạm vi: {self._scope_label()}{FILTER_SHORT[self.mode]}"
        if key == "dirs":
            by: Dict[str, List[FileInfo]] = {}
            for f in files:
                by.setdefault(f.dir_rel, []).append(f)
            rows = [(d or "(thư mục gốc)", len(v), sum(x.pages or 0 for x in v)) for d, v in sorted(by.items())]
            dlg = ListDialog(self, "Thư mục có file PDF", sub, ["Thư mục", "Số file", "Số trang"], rows,
                             [os.path.join(self.result.root, d) for d in sorted(by)], [520, 100, 100])
        elif key in ("files", "pages"):
            fs = sorted(files, key=(lambda f: -(f.pages or 0)) if key == "pages"
                        else (lambda f: (f.dir_rel.lower(), f.name.lower())))
            rows = [(f.name, f.dir_rel or "(gốc)", f.pages if f.pages is not None else "—", fmt_size(f.size)) for f in fs]
            dlg = ListDialog(self, "Danh sách file PDF" if key == "files" else "File theo số trang (nhiều → ít)",
                             sub, ["Tên file", "Thư mục", "Trang", "Dung lượng"], rows, [f.path for f in fs],
                             [430, 260, 70, 90])
        elif key == "sigs":
            fs = [f for f in files if f.has_real_sig]
            rows = [(f.name, sig_label(f)[0], who_when(f)) for f in fs]
            dlg = ListDialog(self, "File có chữ ký số", sub, ["Tên file", "Trạng thái", "Ngày ký · Người ký"], rows,
                             [f.path for f in fs], [380, 160, 380])
        else:
            fs = [f for f in files if f.needs_review]
            rows = [(f.name, f.dir_rel or "(gốc)", REVIEW_TEXT[f.needs_review]) for f in fs]
            dlg = ListDialog(self, "File cần xem lại", sub, ["Tên file", "Thư mục", "Lý do"], rows,
                             [f.path for f in fs], [380, 200, 340])
        dlg.exec()

    def _split_saved(self, path: str):
        """Lưu file tách trang trong thư mục đang quét → quét lại để thấy file mới."""
        if self.result and not self.busy:
            root = os.path.normcase(os.path.abspath(self.result.root))
            if os.path.normcase(os.path.abspath(path)).startswith(root + os.sep):
                self.rescan()

    # ================================================================= công cụ
    def _require_data(self) -> bool:
        if not self.result:
            self.info("Hãy chọn thư mục và bấm Quét trước.")
            return False
        return not self._busy_guard()

    def open_check5(self):
        if self._require_data():
            from .tools_dialogs import Check5Dialog
            Check5Dialog(self, self.result, self.scope).exec()

    def open_cccd(self):
        if not self._require_data():
            return
        from .tools_dialogs import CccdDialog
        release_document()
        dlg = CccdDialog(self, self.result)
        dlg.exec()
        if dlg.changed:
            self.rescan()

    def open_copy(self):
        if self._require_data():
            from .tools_dialogs import CopyGroupDialog
            CopyGroupDialog(self, self.result, self.mode).exec()

    def show_log(self):
        rows = []
        for ln in reversed(activity.read_lines()):
            parts = ln.rstrip("\n").split(" | ", 2)
            if len(parts) == 3:
                rows.append(tuple(parts))
        ListDialog(self, "Nhật ký thao tác", f"Lưu tại {paths.data_file('activity.log')}",
                   ["Thời gian", "Thao tác", "Chi tiết"], rows, widths=[160, 200, 560]).exec()

    def closeEvent(self, e):
        if self.compress.running:
            QMessageBox.information(self, "Đang nén", "Đang nén PDF – hãy bấm Dừng và chờ xong trước khi thoát.")
            e.ignore()
            return
        if self.thread and self.thread.isRunning():
            self.thread.cancel_ev.set()
            self.thread.wait(3000)
        release_document()
        super().closeEvent(e)
