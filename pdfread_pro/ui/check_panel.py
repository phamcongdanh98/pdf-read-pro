"""Tab KIỂM TRA TRANG: phát hiện trang ngược / nằm ngang, số trang thiếu / trùng / sai thứ tự (Windows OCR),
sửa tự động (xoay, sắp xếp, bỏ trang trắng). Bên phải là khung xem trước cao hết tab như Tổng quan."""
from __future__ import annotations

import dataclasses
import os
import shutil
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QItemSelectionModel, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar, QPushButton,
                               QRadioButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..core import activity, compressor as C, pagecheck as K, pagenum
from ..core.trash import find_backup as _find_backup
from ..core.models import FileInfo
from .common import fmt
from .filterbar import FILTER_ALL, SORT_ORIG, FilterBar
from .preview import PreviewPane, make_collapsible
from .styles import button
from .tablekit import column_button, install_column_chooser, install_row_menu

ROTATE_TEXT = {90: "xoay 90° sang trái", 180: "xoay 180°", 270: "xoay 90° sang phải"}
GREEN, AMBER, RED, GRAY, TEXT = "#15803D", "#B45309", "#DC2626", "#64748B", "#1E293B"
DONE_BG = "#DCFCE7"
# màu cột «Trạng thái»: mỗi tình trạng một màu chữ + màu nền riêng cho dễ nhìn
STATUS_STYLE = {
    "ok": (GREEN, None),                       # ✔ Đạt: chữ xanh lá
    "fix": ("#B45309", "#FFEDD5"),             # 🛠 Cần sửa: cam
    "review": ("#92400E", "#FEF9C3"),          # ⚠ Cần xem lại: vàng
    "error": (RED, "#FEE2E2"),                 # lỗi: đỏ
    "done": ("#15803D", "#DCFCE7"),            # ✔ Đã xử lý / đã sửa: xanh lá đậm + nền xanh
    "stale": ("#6D28D9", "#EDE9FE"),           # ⏳ cần kiểm tra lại: tím
    "running": ("#1D4ED8", "#DBEAFE"),         # đang chạy: xanh dương
    "pending": (GRAY, None),                   # chưa kiểm tra: xám
}


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
    PCOLS = ["Trang", "Số in", "Hướng", "Nội dung", "Đề xuất sửa"]
    SHOW = ["Tất cả trang", "Chỉ trang có vấn đề", "Chỉ trang trắng / đen"]
    KIND_TEXT = {"blank": "⬜ Trắng", "near": "⬜ Gần trắng (nhiễu)", "sparse": "▫ Rất ít nội dung"}
    changed = Signal()
    busyChanged = Signal(bool)
    helpRequested = Signal(str)
    refreshRequested = Signal(str)                      # «Cập nhật dòng này»: đọc lại thông tin file (số trang, chữ ký) ở mọi tab

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.files: List[FileInfo] = []
        self.root = ""
        self.worker: Optional[Worker] = None
        self.results: Dict[str, K.CheckResult] = {}     # path → kết quả kiểm tra (giữ lại khi quét lại)
        self.fixed: Dict[str, str] = {}                  # path → file đã sửa
        self.handled: Dict[str, str] = {}                # path → ghi chú đã xử lý trực tiếp (xoá trang / cắt viền)
        self._keep: set = set()                          # file vừa sửa tại chỗ mà kết quả kiểm tra vẫn dùng được
        self.release_cb: Callable[[], None] = lambda: None
        self._view = "orig"
        self._shown_row = -1
        self._filling = False
        self._cache: Optional[dict] = None              # bộ nhớ đệm kết quả kiểm tra (nạp khi cần)

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
        # --- chọn các kiểm tra cần chạy (bỏ OCR = rất nhanh)
        row = QHBoxLayout()
        row.addWidget(QLabel("<b>Kiểm tra:</b>"))
        self.c_blank = QCheckBox("⬜ Trắng")
        self.c_blank.setToolTip("Trang trắng hẳn / gần trắng (nhiễu, vết bẩn, lề đen scan). Rất nhanh, không cần OCR.")
        self.c_black = QCheckBox("⬛ Đen")
        self.c_black.setToolTip("Trang đen gần hết, đen một phần, ảnh tối. Rất nhanh, không cần OCR.")
        self.sp_black = QSpinBox()
        self.sp_black.setRange(50, 99)
        self.sp_black.setValue(int(K.BLACK_THR * 100))
        self.sp_black.setPrefix("≥ ")
        self.sp_black.setSuffix("%")
        self.sp_black.setFixedWidth(96)
        self.sp_black.setToolTip("Trang có từ ngần này % diện tích là điểm tối trở lên thì coi là trang đen.")
        self.c_orient = QCheckBox("🔄 Ngược / ngang")
        self.c_orient.setToolTip("Trang bị ngược 180° hoặc nằm ngang 90° (đọc chữ bằng Windows OCR – chậm hơn).")
        self.c_num = QCheckBox("🔢 Số trang")
        self.c_num.setToolTip("Đọc số trang in: báo thiếu / trùng / sai thứ tự (Windows OCR – chậm hơn).")
        self.c_blur = QCheckBox("🌫 Mờ")
        self.c_blur.setToolTip("Trang có thể bị mờ / out nét so với các trang còn lại.")
        self.c_size = QCheckBox("📐 Khổ lệch")
        self.c_size.setToolTip("Trang có khổ giấy lệch hẳn so với khổ phổ biến của file. Rất nhanh.")
        self.c_dup = QCheckBox("⧉ Trùng")
        self.c_dup.setToolTip("Trang trùng nội dung với trang trước (cùng chữ + cùng ảnh). Rất nhanh.")
        self.CHECKS = {"blank": self.c_blank, "black": self.c_black, "orient": self.c_orient, "numbers": self.c_num,
                       "blur": self.c_blur, "size": self.c_size, "dup": self.c_dup}
        for key, ck in self.CHECKS.items():
            ck.setChecked(True)
            ck.toggled.connect(lambda _=False: self._refresh_all())
            row.addWidget(ck)
            if key == "black":
                row.addWidget(self.sp_black)
        self.sp_black.valueChanged.connect(lambda _=0: self._refresh_all())
        self.btn_quick = button("☑ Chọn nhanh ▾", "light", None, "Chọn nhanh các kiểm tra", "sm")
        qm = QMenu(self.btn_quick)
        for text, keys in (("Tất cả", K.CHECK_KEYS),
                           ("⚡ Chỉ trắng + đen (nhanh, không OCR)", ("blank", "black")),
                           ("⚡ Chỉ nội dung trang (trắng, đen, mờ, khổ lệch, trùng)", ("blank", "black", "blur", "size", "dup")),
                           ("🔢 Chỉ hướng + số trang (OCR)", ("orient", "numbers")),
                           ("Chỉ trang trắng", ("blank",)), ("Chỉ trang đen", ("black",)), ("Chỉ trang ngược / ngang", ("orient",))):
            qm.addAction(text).triggered.connect(lambda _=False, k=keys: self._quick(k))
        self.btn_quick.setMenu(qm)
        row.addWidget(self.btn_quick)
        row.addStretch(1)
        cl.addLayout(row)
        # --- tự sửa khi bấm SỬA TỰ ĐỘNG
        row = QHBoxLayout()
        row.addWidget(QLabel("<b>Tự sửa:</b>"))
        self.ck_rot = QCheckBox("🔄 Xoay trang sai hướng")
        self.ck_rot.setToolTip("Trang bị ngược (180°) hoặc nằm ngang (90°) được xoay cho đứng thuận chiều.")
        self.ck_sort = QCheckBox("↕ Sắp xếp theo số trang in")
        self.ck_sort.setToolTip("Sắp lại trang theo số trang in ở đầu / chân trang (OCR).\n"
                                "Chỉ tự sắp khi đọc được số ở ≥ 1/2 số trang và không có số trùng.\n"
                                "Trang không có số đi liền sau trang đứng trước nó.")
        self.ck_blank = QCheckBox("⬜ Bỏ trang trắng")
        self.ck_blank.setToolTip("Trắng hẳn hoặc gần trắng. Trang rất ít nội dung (dấu, chữ ký) KHÔNG bị bỏ – chỉ cảnh báo.")
        self.ck_black = QCheckBox("⬛ Bỏ trang đen")
        self.ck_black.setToolTip("Trang đen gần hết (scan lỗi). Ảnh tối có chi tiết (vd ảnh chụp) KHÔNG bị bỏ.")
        self.ck_signed = QCheckBox("Bỏ qua file đã ký số")
        self.ck_signed.setToolTip("Sửa file đã ký số làm mất hiệu lực chữ ký.")
        for ck, default in ((self.ck_rot, True), (self.ck_sort, True), (self.ck_blank, False), (self.ck_black, False),
                            (self.ck_signed, True)):
            ck.setChecked(default)
            ck.toggled.connect(lambda _=False: self._refresh_all())
            row.addWidget(ck)
        row.addStretch(1)
        cl.addLayout(row)
        row = QHBoxLayout()
        self.rb_new = QRadioButton("Lưu sang thư mục mới (giữ file gốc)")
        self.rb_over = QRadioButton("Ghi đè file gốc")
        self.rb_new.setChecked(True)
        self.ck_backup = QCheckBox("Sao lưu bản gốc (vào Thùng rác của app)")
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
        self.hint = QLabel("Đọc chữ & số trang bằng Windows OCR (không cần mạng); đo trang trắng / đen / mờ / khổ lệch / trùng. "
                           "Sửa chỉ xoay, đổi thứ tự, xoá trang – không nén lại ảnh. Sửa tay: bấm đôi ô <b>Số in</b>; "
                           "chuột phải hoặc phím <b>Delete</b> để đánh dấu xoá trang.")
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

        self.fbar = FilterBar(
            [("Tất cả", FILTER_ALL), ("⚠ File có vấn đề", "problem"), ("🛠 Cần sửa", "fix"), ("❓ Cần xem lại", "review"),
             ("✔ Đạt", "ok"), ("❌ File lỗi", "error"), ("⏳ Chưa kiểm tra", "pending"), ("✔ Đã sửa", "done"),
             ("⬜ Có trang trắng", "blank"), ("⬛ Có trang đen", "black"), ("🔄 Có trang sai hướng", "orient"),
             ("↕ Sai thứ tự / thiếu / trùng số", "order"), ("🌫 Có trang mờ", "blur"), ("📐 Có trang khổ lệch", "size"),
             ("⧉ Có trang trùng", "dup"), ("🗑 Có trang đánh dấu xoá", "marked")],
            [("Thứ tự gốc", SORT_ORIG, False), ("Tên file A → Z", "name", False), ("Thư mục A → Z", "dir", False),
             ("Số trang nhiều → ít", "pages", True), ("Dung lượng lớn → nhỏ", "size", True),
             ("Vấn đề lên trước", "problem", False), ("Số vấn đề nhiều → ít", "count", True)])
        self.fbar.changed.connect(self.apply_filter)
        lay.addWidget(self.fbar)
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
        install_column_chooser(self.table, "check_files", (1,))
        self.fbar.attach_columns(self.table, "check_files", (1,))
        install_row_menu(self.table, self._paths_of_rows, self._row_extras)

        pg = QGroupBox("Chi tiết từng trang")
        pgl = QVBoxLayout(pg)
        pgl.setContentsMargins(6, 6, 6, 6)
        self.lbl_detail = QLabel("Chọn 1 file đã kiểm tra để xem từng trang.")
        self.lbl_detail.setWordWrap(True)
        pgl.addWidget(self.lbl_detail)
        tb = QHBoxLayout()
        tb.setSpacing(4)
        self.cmb_show = QComboBox()
        self.cmb_show.addItems(self.SHOW)
        self.cmb_show.setToolTip("Lọc danh sách trang của file đang chọn")
        self.cmb_show.currentIndexChanged.connect(lambda _=0: self._fill_pages())
        tb.addWidget(self.cmb_show)
        self.btn_now = button("🗑 Xoá ngay", "danger", self._delete_now_selected,
                              "Xoá THẬT các trang đang chọn khỏi file ngay (cất vào Thùng rác, hoàn tác được). Chọn nhiều trang bằng Ctrl / Shift.",
                              "sm")
        self.btn_mark = button("🏷 Đánh dấu", "light", lambda: self._mark_selected(True),
                               "Chỉ ĐÁNH DẤU các trang đang chọn; xoá thật khi bấm SỬA TỰ ĐỘNG (có thể gom với xoay / sắp xếp).", "sm")
        self.btn_unmark = button("↩ Bỏ dấu", "light", lambda: self._mark_selected(False),
                                 "Bỏ đánh dấu xoá các trang đang chọn", "sm")
        self.btn_pick = button("☑ Chọn nhanh ▾", "light", None,
                               "Đánh dấu xoá cùng lúc: mọi trang trắng, đen, trùng nội dung hoặc mờ của file đang chọn", "sm")
        pm = QMenu(self.btn_pick)
        for text, kinds in (("⬜ Mọi trang trắng", ("blank",)), ("⬛ Mọi trang đen", ("black",)),
                            ("⬜⬛ Mọi trang trắng + đen", ("blank", "black")), ("⧉ Các trang trùng nội dung", ("dup",)),
                            ("🌫 Các trang có thể mờ", ("blurry",))):
            pm.addAction(text).triggered.connect(lambda _=False, k=kinds: self._mark_kinds(k))
        self.btn_pick.setMenu(pm)
        for w in (self.btn_now, self.btn_mark, self.btn_unmark, self.btn_pick):
            tb.addWidget(w)
        tb.addStretch(1)
        tb.addWidget(QLabel("Nút 🗑:"))
        self.cb_del = QComboBox()
        self.cb_del.addItem("🗑 Xoá ngay", "now")
        self.cb_del.addItem("🏷 Chỉ đánh dấu", "mark")
        self.cb_del.setToolTip("Nút 🗑 Xoá trang ở khung xem trước và phím Delete: xoá luôn khỏi file, hoặc chỉ đánh dấu "
                               "(xoá khi bấm SỬA TỰ ĐỘNG). Mặc định: xoá ngay.")
        tb.addWidget(self.cb_del)
        pgl.addLayout(tb)
        self.ptable = QTableWidget(0, len(self.PCOLS))
        self.ptable.setHorizontalHeaderLabels(self.PCOLS)
        self.ptable.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.ptable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ptable.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.ptable.verticalHeader().setVisible(False)
        self.ptable.verticalHeader().setDefaultSectionSize(26)
        self.ptable.horizontalHeader().setStretchLastSection(True)
        for i, w in enumerate((56, 64, 100, 170)):
            self.ptable.setColumnWidth(i, w)
        install_column_chooser(self.ptable, "check_pages", (0,))
        tb.addWidget(column_button(self.ptable))
        sc = QShortcut(QKeySequence(Qt.Key_Delete), self.ptable)
        sc.setContext(Qt.WidgetShortcut)
        sc.activated.connect(lambda: self._mark_selected(None))
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
        self.btn_check.setToolTip("Kiểm tra mọi file trong phạm vi. File không đổi từ lần kiểm tra trước dùng lại kết quả "
                                  "đã lưu (rất nhanh). Giữ Ctrl khi bấm: chỉ kiểm tra lại từ đầu file đang chọn.")
        self.btn_check.clicked.connect(lambda: self.check())
        self.btn_stop = QPushButton("■ Dừng")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.clicked.connect(self.stop)
        self.btn_fix = QPushButton("🛠 SỬA TỰ ĐỘNG")
        self.btn_fix.setObjectName("success")
        self.btn_fix.setProperty("size", "lg")
        self.btn_fix.setToolTip("Xoay / sắp xếp / bỏ trang trắng cho các file cần sửa (theo lựa chọn bên trên)")
        self.btn_fix.clicked.connect(lambda: self.fix())
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
        self.preview.delete_handler = self._preview_delete      # 🗑 ở khung xem trước: xoá ngay hoặc đánh dấu (theo cài đặt)
        self.preview.pageDeleted.connect(self.page_deleted)
        self.preview.fileEdited.connect(self.file_edited)
        self.preview.cropped.connect(self.page_cropped)
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
            self.handled.clear()
            base = root.rstrip(os.sep)
            self.out_edit.setText(os.path.join(os.path.dirname(base), os.path.basename(base) + " - Đã kiểm tra")
                                  if base else "")
        self.fbar.restore_order(self.table)
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
            self.lbl.setText("⚠ Máy không có Windows OCR (cần Windows 10/11) – chỉ kiểm tra được trắng / đen / mờ / khổ / trùng "
                             "(bỏ tích “Ngược / ngang” và “Số trang”).")
        else:
            self.lbl.setText(f"{fmt(len(files))} file trong phạm vi. Bấm “Kiểm tra” để tìm trang ngược / sai thứ tự."
                             if files else "Không có file nào trong phạm vi.")
        self._enable_actions()
        self.apply_filter()
        self.show_selected()

    # ------------------------------------------------------------------ chọn kiểm tra
    @property
    def checks(self) -> set:
        return {k for k, ck in self.CHECKS.items() if ck.isChecked()}

    def _quick(self, keys):
        for k, ck in self.CHECKS.items():
            ck.blockSignals(True)
            ck.setChecked(k in keys)
            ck.blockSignals(False)
        self._refresh_all()

    def _stale(self, r: Optional[K.CheckResult]) -> bool:
        """Kết quả cũ chưa đo mục người dùng vừa bật thêm (hướng / số trang / độ nét) → cần kiểm tra lại."""
        ck = self.checks
        return bool(r and r.pages and ((ck & K.OCR_CHECKS and not r.ocr) or ("blur" in ck and not r.blur)))

    # ------------------------------------------------------------------ phương án sửa
    def _plan(self, path: str) -> Optional[K.Plan]:
        r = self.results.get(path)
        if not r or r.error or not r.pages or self._stale(r):
            return None
        return K.make_plan(r.pages, remove_blank=self.ck_blank.isChecked(), rotate=self.ck_rot.isChecked(),
                           reorder=self.ck_sort.isChecked(), remove_black=self.ck_black.isChecked(),
                           black_thr=self.sp_black.value() / 100, checks=self.checks)

    def _is_done(self, f, plan) -> bool:
        """File đã xử lý xong? Sửa tại chỗ từng trang (xoá / cắt) mà file vẫn còn trang lỗi thì CHƯA xong."""
        if f.path not in self.fixed and f.path not in self.handled:
            return False
        if self.handled.get(f.path, "") != "đánh dấu bằng tay" and plan is not None \
                and (plan.needs_fix or plan.issues()) and os.path.normcase(self.fixed.get(f.path, "")) == os.path.normcase(f.path):
            return False
        return True

    def _info(self, row: int):
        f = self.files[row]
        r = self.results.get(f.path)
        plan = self._plan(f.path)
        tags, count = set(), 0
        if f.error or (r and r.error and not r.pages):
            tags.add("error")
        elif r is None or (r.pages and plan is None):
            tags.add("pending")
        elif plan is not None:
            done = self._is_done(f, plan)
            if done:
                tags.add("done")
            for key, lst in (("blank", plan.blanks), ("black", plan.blacks), ("orient", plan.rotate),
                             ("blur", plan.blurry), ("size", plan.odd_size), ("dup", plan.dup_pages),
                             ("marked", plan.marked)):
                if lst:
                    tags.add(key)
                    count += len(lst)
            if plan.reordered or plan.missing or plan.duplicates or plan.suspicious:
                tags.add("order")
                count += 1
            if plan.needs_fix and not done:
                tags.add("fix")
            elif (plan.issues() or plan.sort_note) and not done:
                tags.add("review")
            elif not done:
                tags.add("ok")
        if tags & {"error", "fix", "review"}:
            tags.add("problem")
        rank = 0 if "error" in tags else 1 if "fix" in tags else 2 if "review" in tags else 3 if "pending" in tags else 4
        return tags, f"{f.name} {f.dir_rel}".lower(), {
            "name": f.name.lower(), "dir": f.dir_rel.lower(), "pages": f.pages or 0, "size": f.size,
            "problem": rank, "count": count}

    def apply_filter(self, *_):
        if self.files:
            self.fbar.apply(self.table, len(self.files), self._info)

    # ------------------------------------------------------------------ menu chuột phải theo dòng
    def _paths_of_rows(self, rows):
        return [self.files[r].path for r in rows if 0 <= r < len(self.files)]

    def _row_extras(self, rows):
        if not rows or not 0 <= rows[0] < len(self.files):
            return []
        r0 = rows[0]
        f = self.files[r0]
        plan = self._plan(f.path)
        busy = self.running
        bb = bool(plan and (plan.blanks or plan.blacks))
        items = [
            ("🔄 Cập nhật dòng này (đọc lại file + kiểm tra lại)", lambda: self.refresh_rows(rows), not busy),
            ("🔍 Kiểm tra lại file này (bỏ qua kết quả đã lưu)", lambda: self.check(rows, True), not busy),
            ("🛠 Sửa tự động riêng file này", lambda: self.fix(rows), not busy and bool(plan and plan.needs_fix)),
            None,
            ("🗑 Xoá ngay các trang trắng + đen của file này", lambda: self._delete_blank_black(r0), not busy and bb),
            ("↩ Khôi phục bản gốc (từ bản sao lưu)", lambda: self._restore_original(r0), not busy and bool(_find_backup(f.path))),
        ]
        done = f.path in self.handled or f.path in self.fixed
        if done:
            items.append(("☐ Bỏ đánh dấu «đã xử lý»", lambda: self._set_done(rows, False)))
        else:
            items.append(("✔ Đánh dấu là đã xử lý (bằng tay)", lambda: self._set_done(rows, True)))
        if plan and plan.issues():
            issues = "\n".join(plan.issues())
            items.append(("📋 Sao chép danh sách vấn đề", lambda: QGuiApplication.clipboard().setText(issues)))
        return items

    def refresh_rows(self, rows):
        """Cập nhật bằng tay: đọc lại thông tin file (số trang, chữ ký) rồi kiểm tra lại từ đầu."""
        for r in rows:
            if 0 <= r < len(self.files):
                self.refreshRequested.emit(self.files[r].path)
        self.check(rows, True)

    def _set_done(self, rows, on: bool):
        for r in rows:
            f = self.files[r]
            if on:
                self.handled[f.path] = "đánh dấu bằng tay"
            else:
                self.handled.pop(f.path, None)
                self.fixed.pop(f.path, None)
            self._render(r)
        self.apply_filter()

    def _delete_blank_black(self, row: int):
        f = self.files[row]
        plan = self._plan(f.path)
        if plan:
            self.preview.delete_pages_direct(f.path, sorted(set(plan.blanks) | set(plan.blacks)))

    def _restore_original(self, row: int):
        from ..core import trash
        f = self.files[row]
        ent = next((e for e in trash.list_entries() if e.kind == trash.KIND_BACKUP
                    and os.path.normcase(e.orig_path) == os.path.normcase(os.path.abspath(f.path)) and e.exists), None)
        if ent is None:
            QMessageBox.information(self, "Khôi phục", "Không tìm thấy bản sao lưu gốc của file này trong Thùng rác.")
            return
        if QMessageBox.question(self, "Khôi phục bản gốc",
                                f"Trả “{f.name}” về bản gốc trước khi sửa?\n(Bản hiện tại được cất vào Thùng rác.)",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.preview.release()
        ok, msg, _ = trash.restore(ent)
        self.lbl.setText(("✔ " if ok else "⚠ ") + msg)
        self.file_edited(f.path)
        self.refreshRequested.emit(f.path)

    def run_for_path(self, path: str, force: bool = True) -> bool:
        """Chọn dòng của `path` và kiểm tra lại riêng file đó (dùng từ menu của tab khác)."""
        for i, f in enumerate(self.files):
            if os.path.normcase(f.path) == os.path.normcase(path):
                self.table.selectRow(i)
                self.check([i], force)
                return True
        return False

    def _skipped(self, f: FileInfo) -> bool:
        return self.ck_signed.isChecked() and (f.has_real_sig or f.name_signed)

    def _set(self, row: int, col: int, text, color: Optional[str] = None):
        it = self.table.item(row, col)
        it.setText(str(text))
        it.setForeground(QColor(color or TEXT))

    def _set_status(self, row: int, text: str, key: str, tip: str = ""):
        fg, bg = STATUS_STYLE[key]
        it = self.table.item(row, 6)
        it.setText(text)
        it.setForeground(QColor(fg))
        it.setToolTip(tip)
        f = it.font()
        f.setBold(key in ("fix", "error", "done"))
        it.setFont(f)
        self._tint_row(row, bg)                                  # tô CẢ HÀNG cùng màu với trạng thái

    def _tint_row(self, row: int, bg: Optional[str]):
        for c in range(len(self.COLS)):
            it = self.table.item(row, c)
            if it is not None:
                it.setBackground(QColor(bg) if bg else QBrush())

    def _render(self, row: int):
        f = self.files[row]
        r = self.results.get(f.path)
        self._tint_row(row, None)
        if f.error:
            self._set_status(row, f.error, "error")
            return
        if r is None:
            self._set(row, 3, f.pages if f.pages is not None else "")      # số trang MỚI của file (vừa sửa ở tab khác)
            self._set(row, 4, "")
            self._set(row, 5, "")
            self._set_status(row, "Chưa kiểm tra", "pending")
            return
        if r.error and not r.pages:
            self._set(row, 5, "")
            self._set_status(row, r.error, "error")
            return
        plan = self._plan(f.path)
        self._set(row, 3, len(r.pages))
        if plan is None:                       # bật thêm kiểm tra hướng / số trang / mờ sau khi đã kiểm tra
            self._set(row, 4, "")
            self._set(row, 5, "")
            self._set_status(row, "⏳ Cần kiểm tra lại (đã bật thêm mục kiểm tra)", "stale")
            return
        text_pages = plan.text_pages
        if "numbers" in self.checks:
            self._set(row, 4, f"{plan.read}/{text_pages}", GREEN if plan.read == text_pages else AMBER)
        else:
            self._set(row, 4, "—", GRAY)
        issues = plan.issues()
        self._set(row, 5, " · ".join(issues) if issues else "—", AMBER if issues else GREEN)
        self.table.item(row, 5).setToolTip("\n".join(issues + ([plan.sort_note] if plan.sort_note else [])))
        partial = (f.path in self.handled or f.path in self.fixed) and not self._is_done(f, plan)
        if partial:
            note = f" (đã {self.handled[f.path][3:]}, còn vấn đề)" if self.handled.get(f.path, "").startswith("đã ") else " (còn vấn đề)"
            self._set_status(row, ("🛠 Cần sửa" if plan.needs_fix else "⚠ Cần xem lại") + note,
                             "fix" if plan.needs_fix else "review", self.fixed.get(f.path, ""))
        elif f.path in self.handled:
            self._set_status(row, "✔ Đã xử lý – " + self.handled[f.path], "done", self.fixed.get(f.path, ""))
        elif f.path in self.fixed:
            self._set_status(row, "✔ Đã sửa", "done", self.fixed[f.path])
        elif r.error:
            self._set_status(row, r.error, "error")
        elif plan.needs_fix:
            self._set_status(row, "🛠 Cần sửa" + (" (đã ký số – bỏ qua)" if self._skipped(f) else ""), "fix")
        elif issues or plan.sort_note:
            self._set_status(row, "⚠ Cần xem lại", "review")
        else:
            self._set_status(row, "✔ Đạt", "ok")

    def _refresh_all(self):
        for r in range(len(self.files)):
            self._render(r)
        self._fill_pages(keep=True)
        self._enable_actions()
        self.apply_filter()

    # ------------------------------------------------------------------ chi tiết trang
    def _row(self) -> int:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return rows[0].row() if rows else -1

    def _page_of_row(self, row: int) -> int:
        it = self.ptable.item(row, 0)
        return it.data(Qt.UserRole) if it is not None else -1

    def _selected_pages(self) -> List[int]:
        rows = sorted({ix.row() for ix in self.ptable.selectionModel().selectedRows()}) \
            if self.ptable.selectionModel() else []
        return [self._page_of_row(r) for r in rows if self._page_of_row(r) >= 0]

    def _page_tags(self, i: int, p: K.PageInfo, plan: K.Plan) -> str:
        tags = []
        if p.kind == "black":
            tags.append(f"⬛ Đen {p.dark:.0%}")
        elif p.kind == "part_black":
            tags.append(f"◧ Đen một phần {p.dark:.0%}")
        elif p.kind == "dark_img":
            tags.append(f"◼ Tối {p.dark:.0%} (có chi tiết)")
        elif p.kind in self.KIND_TEXT:
            tags.append(self.KIND_TEXT[p.kind])
        if i in plan.blurry:
            tags.append("🌫 Có thể mờ")
        if i in plan.odd_size:
            tags.append("📐 Khổ lệch")
        if i in plan.dup_pages:
            tags.append(f"⧉ Trùng nội dung tr.{plan.dup_pages[i] + 1}")
        return " · ".join(tags)

    def _fill_pages(self, keep: bool = False):
        row = self._row()
        prev = self._page_of_row(self.ptable.currentRow()) if keep else -1
        prev_sel = self._selected_pages() if keep else []
        self._filling = True
        self.ptable.setRowCount(0)
        f = self.files[row] if 0 <= row < len(self.files) else None
        r = self.results.get(f.path) if f else None
        plan = self._plan(f.path) if f else None
        if not plan:
            self.lbl_detail.setText(r.error if r and r.error else "Chọn 1 file đã kiểm tra để xem từng trang.")
            self._filling = False
            self._enable_actions()
            return
        pos = {src: k for k, src in enumerate(plan.order)}
        base = {src: k for k, src in enumerate(sorted(plan.order))}
        mode = self.cmb_show.currentIndex()
        problem = (set(plan.rotate) | set(plan.blanks) | set(plan.blacks) | set(plan.dark_pages) | set(plan.sparse)
                   | set(plan.blurry) | set(plan.odd_size) | set(plan.dup_pages) | set(plan.marked)
                   | set(plan.suspicious) | set(plan.removed))
        shown = [i for i in range(len(r.pages))
                 if mode == 0 or (mode == 1 and (i in problem or (plan.reordered and i in pos and pos[i] != base[i])))
                 or (mode == 2 and (i in plan.blanks or i in plan.blacks))]
        self.ptable.setRowCount(len(shown))
        strike = self.ptable.font()
        strike.setStrikeOut(True)
        for rr, i in enumerate(shown):
            p = r.pages[i]
            empty = i in plan.blanks or i in plan.blacks
            sugg = []
            if i in plan.marked:
                sugg.append("🗑 xoá (đã đánh dấu)")
            elif i in plan.removed:
                sugg.append("bỏ (trang trắng)" if p.blank else "bỏ (trang đen)")
            elif empty:
                sugg.append("trang trắng" if p.blank else "trang đen")
            if i in plan.rotate:
                sugg.append(ROTATE_TEXT[plan.rotate[i]])
            if plan.reordered and i in pos and pos[i] != base[i]:
                sugg.append(f"chuyển tới vị trí {pos[i] + 1}")
            if i in plan.suspicious:
                sugg.append("số lạ – bỏ qua khi sắp")
            vals = [i + 1, "" if p.number is None else p.number,
                    "—" if empty else K.ANGLE_TEXT.get(p.angle, "?"), self._page_tags(i, p, plan) or "—",
                    " · ".join(sugg) or "—"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c != 1:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c < 3:
                    it.setTextAlignment(Qt.AlignCenter)
                if c == 0:
                    it.setData(Qt.UserRole, i)
                self.ptable.setItem(rr, c, it)
            warn = bool(sugg) and not (empty and sugg == ["trang trắng"] or sugg == ["trang đen"])
            color = AMBER if warn or self.ptable.item(rr, 3).text() != "—" else TEXT
            if empty and not warn:
                color = GRAY
            for c in (2, 3, 4):
                self.ptable.item(rr, c).setForeground(QColor(color))
            if i in plan.marked or i in plan.removed:
                for c in range(len(self.PCOLS)):
                    self.ptable.item(rr, c).setFont(strike)
                    self.ptable.item(rr, c).setForeground(QColor(RED))
                self.ptable.item(rr, 4).setFont(self.ptable.font())
            if p.edited:
                self.ptable.item(rr, 1).setForeground(QColor("#1D4ED8"))
                self.ptable.item(rr, 1).setToolTip("Đã sửa tay")
            if p.sharp:
                self.ptable.item(rr, 3).setToolTip(f"Tối {p.dark:.0%} · mực {0 if p.ink is None else p.ink:.2%} · "
                                                   f"chi tiết {p.detail:.1%} · độ nét {p.sharp:.0f}")
        notes = [f"<b>{os.path.basename(f.path)}</b> · {len(r.pages)} trang · đọc {r.seconds:.1f} giây"
                 + (f" · <span style='color:{RED}'>xoá {len(plan.removed)} trang</span>" if plan.removed else "")]
        if plan.sort_note:
            notes.append(f"<span style='color:{AMBER}'>{plan.sort_note}</span>")
        if plan.missing and plan.unread:
            notes.append(f"Số {', '.join(map(str, plan.missing[:8]))} có thể nằm ở {plan.unread} trang chưa đọc được "
                         "số – bấm đôi ô Số in để nhập tay.")
        self.lbl_detail.setText("<br>".join(notes))
        self._filling = False
        if prev >= 0 or prev_sel:
            sel = set(prev_sel) | {prev}
            self._filling = True                          # chọn lại đúng các trang đang chọn (đánh dấu nhiều trang liên tiếp)
            for rr in range(self.ptable.rowCount()):
                if self._page_of_row(rr) in sel:
                    self.ptable.selectionModel().select(self.ptable.model().index(rr, 0),
                                                        QItemSelectionModel.Select | QItemSelectionModel.Rows)
                if self._page_of_row(rr) == prev:
                    self.ptable.setCurrentCell(rr, 0, QItemSelectionModel.NoUpdate)
            self._filling = False
        self._enable_actions()

    def page_selected(self):
        if self._filling:
            return
        i = self._page_of_row(self.ptable.currentRow())
        f = self.files[self._row()] if 0 <= self._row() < len(self.files) else None
        if i < 0 or not f:
            return
        if self._view == "fixed":
            if f.path in self.fixed and os.path.normcase(self.fixed[f.path]) == os.path.normcase(f.path):
                if f.path in self.handled:               # xoá / cắt tại chỗ: bảng đã bỏ trang tương ứng → chỉ số khớp file hiện tại
                    self.preview.goto(i)
                return                                   # sửa tự động ghi đè: thứ tự đã đổi, giữ trang đang xem
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
        p = r.pages[self._page_of_row(item.row())]
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
        rr = self.ptable.rowAt(pos.y())
        row = self._row()
        if rr < 0 or row < 0:
            return
        i = self._page_of_row(rr)
        r = self.results.get(self.files[row].path)
        if not r or i < 0:
            return
        m = QMenu(self)
        if r.pages[i].marked:
            m.addAction("↩ Bỏ đánh dấu xoá").triggered.connect(lambda: self._mark_selected(False))
        else:
            m.addAction("🗑 Đánh dấu xoá trang này").triggered.connect(lambda: self._mark_selected(True))
        m.addSeparator()
        for text, ang in (("Trang đúng chiều (không xoay)", 0), ("Trang bị ngược – xoay 180°", 180),
                          ("Nằm ngang – xoay 90° sang phải", 270), ("Nằm ngang – xoay 90° sang trái", 90)):
            a = m.addAction(text)
            a.setCheckable(True)
            a.setChecked((r.pages[i].angle or 0) == ang)
            a.triggered.connect(lambda _=False, g=ang: self._set_angle(i, g))
        m.exec(self.ptable.viewport().mapToGlobal(pos))

    def _set_angle(self, i: int, ang: int):
        r = self.results.get(self.files[self._row()].path)
        p = r.pages[i]
        p.angle, p.edited = ang, True
        p.blank, p.kind, p.manual_kind = False, "", True        # người dùng khẳng định đây là trang có nội dung
        self._render(self._row())
        self._fill_pages(keep=True)
        self._enable_actions()

    # ------------------------------------------------------------------ đánh dấu xoá trang
    def _cur_result(self):
        row = self._row()
        return (self.files[row], self.results.get(self.files[row].path)) if 0 <= row < len(self.files) else (None, None)

    def _after_mark(self):
        self._render(self._row())
        self._fill_pages(keep=True)
        self._enable_actions()

    def _mark_selected(self, on: Optional[bool]):
        """on=True đánh dấu, False bỏ đánh dấu, None = phím Delete (xoá ngay hoặc đảo dấu, theo cài đặt «Nút 🗑 / Delete»)."""
        if on is None and self.cb_del.currentData() == "now":
            self._delete_now_selected()
            return
        f, r = self._cur_result()
        pages = self._selected_pages()
        if not r or not pages or self.running:
            return
        if on is None:
            on = not all(r.pages[i].marked for i in pages)
        for i in pages:
            r.pages[i].marked = on
        self._after_mark()
        if on:
            self.lbl.setText(f"🗑 Đã đánh dấu xoá {len(pages)} trang – sẽ xoá khi bấm “SỬA TỰ ĐỘNG” "
                             "(có sao lưu / lưu sang thư mục mới).")

    def _delete_now_selected(self):
        """Xoá THẬT các trang đang chọn trong bảng chi tiết (hỏi xác nhận nếu đang bật; cất Thùng rác; hoàn tác được)."""
        f, r = self._cur_result()
        pages = self._selected_pages()
        if not f or not pages or self.running:
            return
        self.preview.delete_pages_direct(f.path, pages)

    def page_deleted(self, path: str, page: int):
        """Khung xem trước / nút «Xoá ngay» vừa xoá trang `page` của `path` → bỏ đúng trang đó khỏi kết quả (không cần kiểm tra lại)."""
        f = next((x for x in self.files if os.path.normcase(x.path) == os.path.normcase(path)), None)
        if not f:
            return
        r = self.results.get(f.path)
        if r and r.pages and 0 <= page < len(r.pages):
            r.pages.pop(page)
        import re
        m = re.search(r"đã xoá (\d+) trang", self.handled.get(f.path, ""))
        n = (int(m.group(1)) if m else 0) + 1
        self.handled[f.path] = f"đã xoá {n} trang"
        self.fixed[f.path] = f.path                 # để chuyển được giữa «Bản gốc» (bản sao lưu) ↔ «Bản đã sửa»
        self._keep.add(f.path)
        self._view = "fixed"

    def page_cropped(self, path: str):
        f = next((x for x in self.files if os.path.normcase(x.path) == os.path.normcase(path)), None)
        if f:
            self.handled[f.path] = "đã cắt viền"
            self.fixed[f.path] = f.path
            self._keep.add(f.path)
            self._view = "fixed"

    def _mark_kinds(self, kinds):
        f, r = self._cur_result()
        plan = self._plan(f.path) if f else None
        if not r or not plan:
            return
        hit = set()
        if "blank" in kinds:
            hit |= set(plan.blanks)
        if "black" in kinds:
            hit |= set(plan.blacks)
        if "dup" in kinds:
            hit |= set(plan.dup_pages)
        if "blurry" in kinds:
            hit |= set(plan.blurry)
        if not hit:
            self.lbl.setText("Không có trang nào thuộc loại này trong file đang chọn.")
            return
        for i in hit:
            r.pages[i].marked = True
        self._after_mark()
        self.lbl.setText(f"🗑 Đã đánh dấu xoá {len(hit)} trang ({K._pages(sorted(hit))}) – "
                         "bấm “SỬA TỰ ĐỘNG” để xoá thật.")

    def _preview_delete(self, path: str, page: int) -> bool:
        """🗑 ở khung xem trước. Bản gốc đang xem → chỉ đánh dấu (xoá khi Sửa). Bản sao lưu → không cho xoá.
        Bản đã sửa → để khung xem trước xoá trực tiếp (có hỏi + sao lưu)."""
        f, r = self._cur_result()
        if not f or self._view != "orig":
            return False
        if os.path.normcase(path) != os.path.normcase(f.path):
            QMessageBox.information(self, "Xoá trang", "Đây là bản sao lưu của file gốc – không xoá ở đây.")
            return True
        if self.cb_del.currentData() == "now":
            return False                                   # xoá ngay: để khung xem trước xoá thật (hỏi nếu đang bật)
        if not r or not 0 <= page < len(r.pages):
            QMessageBox.information(self, "Xoá trang", "File này chưa được kiểm tra – hãy bấm “Kiểm tra” trước, "
                                    "hoặc dùng tab Tổng quan để xoá trực tiếp.")
            return True
        if self.running:
            return True
        p = r.pages[page]
        p.marked = not p.marked
        for rr in range(self.ptable.rowCount()):
            if self._page_of_row(rr) == page:
                self.ptable.selectRow(rr)
                break
        self._after_mark()
        self.lbl.setText((f"🗑 Đã đánh dấu xoá trang {page + 1}" if p.marked else f"↩ Đã bỏ đánh dấu trang {page + 1}")
                         + " – xoá thật khi bấm “SỬA TỰ ĐỘNG”.")
        return True

    def file_edited(self, path: str):
        """Khung xem trước vừa xoá trang trực tiếp trong `path` → kết quả kiểm tra cũ không còn đúng."""
        f = next((x for x in self.files if os.path.normcase(x.path) == os.path.normcase(path)), None)
        if f:
            if f.path in self._keep:                       # xoá trang / cắt viền: kết quả vẫn dùng được (đã bỏ trang tương ứng)
                self._keep.discard(f.path)
            else:                                          # hoàn tác / khôi phục: số trang đổi → phải kiểm tra lại
                self.results.pop(f.path, None)
                self.fixed.pop(f.path, None)
                self.handled.pop(f.path, None)
            row = self.files.index(f)
            self._render(row)
            self._fill_pages()
            self._enable_actions()
            self.apply_filter()
            if row == self._row():
                self.show_selected()                       # cập nhật nút «Bản gốc / Bản đã sửa»

    def sync_file(self, path: str):
        """File bị sửa ở NƠI KHÁC (khung xem trước của tab Tổng quan / Đổi tên / Nén, Thùng rác khôi phục…): nếu số trang không còn khớp
        kết quả kiểm tra đã lưu thì bỏ kết quả cũ (hiện «Chưa kiểm tra») thay vì giữ số trang / vấn đề cũ."""
        f = next((x for x in self.files if os.path.normcase(x.path) == os.path.normcase(path)), None)
        if not f:
            return
        r = self.results.get(f.path)
        if r and r.pages:
            try:
                import pymupdf as fitz
                with fitz.open(f.path) as d:
                    n = d.page_count
            except Exception:
                n = -1
            if n != len(r.pages):
                self.results.pop(f.path, None)
                self.fixed.pop(f.path, None)
                self.handled.pop(f.path, None)
        row = self.files.index(f)
        self._render(row)
        self._fill_pages(keep=True)
        self._enable_actions()
        self.apply_filter()

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
            orig = _find_backup(f.path)
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
        need_ocr = bool(self.checks & K.OCR_CHECKS)
        self.btn_check.setEnabled(not run and (ocr or not need_ocr) and bool(self.files) and bool(self.checks))
        self.btn_fix.setEnabled(not run and bool(self._need_fix()))
        for w in (self.ck_signed, self.rb_new, self.rb_over, self.btn_quick, *self.CHECKS.values()):
            w.setEnabled(not run)
        ck = self.checks
        self.sp_black.setEnabled(not run and "black" in ck)
        for w, key in ((self.ck_rot, "orient"), (self.ck_sort, "numbers"), (self.ck_blank, "blank"),
                       (self.ck_black, "black")):
            w.setEnabled(not run and key in ck)                # sửa theo mục nào thì mục đó phải đang được kiểm tra
        # bảng chi tiết trang vẫn cuộn / xem được khi đang kiểm tra (chỉ khoá sửa số in)
        self.ptable.setEditTriggers(QAbstractItemView.NoEditTriggers if run else
                                    QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        has_pages = self.ptable.rowCount() > 0 and not run
        for w in (self.btn_now, self.btn_mark, self.btn_unmark, self.btn_pick):
            w.setEnabled(has_pages)
        self.cmb_show.setEnabled(not run)
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
    def check(self, rows=None, force=None):
        """Kiểm tra các dòng `rows` (mặc định: tất cả; giữ Ctrl: chỉ dòng đang chọn, làm lại từ đầu). force: bỏ qua bộ nhớ đệm."""
        from PySide6.QtWidgets import QApplication
        if rows is None:
            ctrl = bool(QApplication.keyboardModifiers() & Qt.ControlModifier) and self._row() >= 0
            rows = [self._row()] if ctrl else list(range(len(self.files)))
            force = ctrl if force is None else force
        only_sel = bool(force)
        idx = rows
        ck = self.checks
        if not ck:
            self.lbl.setText("Hãy tích ít nhất 1 mục kiểm tra.")
            return
        jobs, hits = [], []
        need_ocr, need_blur = bool(ck & K.OCR_CHECKS), "blur" in ck
        if self._cache is None:
            self._cache = K.load_cache()
        for i in idx:
            f = self.files[i]
            if f.error:
                continue
            self.fixed.pop(f.path, None)
            self.handled.pop(f.path, None)
            cached = None if only_sel else K.cache_get(self._cache, f.path, need_ocr, need_blur)
            if cached is not None:
                self.results[f.path] = cached
                hits.append(i)
                continue
            self._set(i, 6, "⏳ Đang kiểm tra…")
            jobs.append((i, [f.path, self.sp_black.value() / 100, need_ocr, need_blur]))
        if not jobs and not hits:
            self.lbl.setText("Không có file nào để kiểm tra.")
            return
        # nhiều tiến trình (mỗi tiến trình 1–2 file) + mỗi tiến trình đọc song song vài trang bằng nhiều engine OCR
        cpu = os.cpu_count() or 4
        workers = max(1, min(C.safe_workers(), max(1, len(jobs)), max(2, cpu // 2)))
        conc = max(2, min(6, cpu // workers))
        jobs = [(i, tuple(args) + (conc,)) for i, args in jobs]
        self.stats = {"ok": 0, "fix": 0, "review": 0, "err": 0}
        for i in hits:
            self._count(self.files[i].path, self.results[self.files[i].path])
            self._render(i)
        self.cached_n = len(hits)
        saved = f" · ♻ {fmt(len(hits))} file dùng kết quả đã lưu" if hits else ""
        if not jobs:                                    # mọi file đều có kết quả đã lưu → xong ngay
            self.apply_filter()
            self.show_selected()
            self._enable_actions()
            self._check_summary("")
            return
        self.lbl.setText(f"Đang kiểm tra {fmt(len(jobs))} file bằng {workers} tiến trình"
                         + (" (đọc chữ từng trang)…" if ck & K.OCR_CHECKS else " (không cần OCR – nhanh)…") + saved)
        self._start("check", K.job_check, jobs, lambda a, m: K.CheckResult(a[0], error=m), workers)

    def fix(self, rows=None):
        """Sửa tự động các file cần sửa (mặc định: tất cả; `rows`: chỉ các dòng này)."""
        todo = [i for i in self._need_fix() if rows is None or i in rows]
        if not todo:
            if rows is not None:
                self.lbl.setText("File này không có gì cần sửa theo các mục đang chọn (hoặc đã ký số / đã sửa rồi).")
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
                + ("\nBản gốc được sao lưu vào Thùng rác của app (không để trong thư mục hồ sơ)." if self.ck_backup.isChecked()
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
            elif not overwrite and f.path in self.results and rows is None:
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
            self._count(f.path, res)
            if self._cache is not None:
                K.cache_put(self._cache, f.path, res)
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
                r.pages = [dataclasses.replace(r.pages[k], angle=0 if r.pages[k].angle is not None or k in rot
                                               else None, marked=False) for k in order]
        self._render(i)
        if i == self._row():
            if mode == "fix":
                self._view = "fixed"
            self.show_selected()

    def _count(self, path: str, res) -> None:
        plan = self._plan(path)
        key = "err" if res.error else "fix" if plan and plan.needs_fix else \
            "review" if plan and (plan.issues() or plan.sort_note) else "ok"
        self.stats[key] += 1

    def _check_summary(self, msg: str) -> None:
        s = self.stats
        extra = f" · ♻ {fmt(self.cached_n)} file dùng kết quả đã lưu" if getattr(self, "cached_n", 0) else ""
        self.lbl.setText(f"✔ Kiểm tra xong: {s['ok']} đạt · {s['fix']} cần sửa · {s['review']} cần xem lại · "
                         f"{s['err']} lỗi{extra}. {msg}")
        activity.log("Kiểm tra trang", f"{s['ok']} đạt, {s['fix']} cần sửa, {s['review']} cần xem lại, "
                                       f"{s['err']} lỗi")

    def on_finish(self, mode: str, msg: str):
        self.worker.wait()
        self._enable_actions()
        self.busyChanged.emit(False)
        self.apply_filter()
        s = self.stats
        if mode == "check":
            self._check_summary(msg)
            if self._cache is not None:
                K.save_cache(self._cache)
        else:
            extra = f" · chép nguyên {s['copied']} file" if s["copied"] else ""
            self.lbl.setText(f"✔ Đã sửa {s['ok']} file · {s['err']} lỗi{extra}. {msg}")
            activity.log("Sửa trang", f"{s['ok']} file đã xoay / sắp xếp, {s['err']} lỗi"
                                      + (" – ghi đè file gốc" if self._overwrite else f" – lưu {self.out_edit.text()}"))
            if s["ok"] and self._overwrite:
                self.changed.emit()
