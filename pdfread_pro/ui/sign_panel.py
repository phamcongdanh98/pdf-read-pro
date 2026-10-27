"""Tab GOM KÝ SỐ: ① gom (chép) file chưa ký của các hồ sơ CCCD_HoVaTen vào 1 thư mục, tên thêm đuôi _CCCD_HoVaTen
→ ký số hàng loạt bằng phần mềm ký → ② trả bản .signed về đúng hồ sơ / chép ra thư mục mới, bỏ đuôi.
Bản ký được kiểm tra chữ ký số thật + số trang; thư mục gom được theo dõi khi đang ký; hoàn tác nhớ cả sau khi tắt app."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Callable, List, Optional

from PySide6.QtCore import (QAbstractTableModel, QFileSystemWatcher, QModelIndex, QSortFilterProxyModel, QThread,
                            QTimer, Qt, Signal)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar, QRadioButton, QSpinBox,
                               QTableView, QVBoxLayout, QWidget)

from .. import paths
from ..core import activity, signgather as G, signgather_excel as GX
from ..core.models import FileInfo
from .common import fmt, open_path, run_bg
from .file_picker import fold
from .styles import button
from .theme import tc

GREEN, AMBER, RED, GRAY, BLUE, TEXT = "#15803D", "#B45309", "#DC2626", "#64748B", "#1D4ED8", "#1E293B"
COLOR = {G.G_NEW: GREEN, G.G_EXISTS: GRAY, G.G_SIGNED: GRAY, G.G_NOT_DOSSIER: AMBER, G.G_DUPNAME: RED,
         G.R_SIGNED: GREEN, G.R_BACK: GREEN, G.R_DUP: GRAY, G.R_CONFLICT: RED, G.R_WAIT: AMBER, G.R_UNKNOWN: AMBER,
         G.R_COPY: GREEN, G.R_EXTRA: BLUE, G.R_HAVE: GRAY, G.R_NOSIG: RED, G.R_BADSIG: RED, G.R_BAD: RED,
         G.R_PAGES: RED, G.R_BUSY: AMBER, G.R_CHANGED: RED, G.R_SPARE: GRAY}
SKIPPED = {G.G_EXISTS, G.G_SIGNED, G.G_NOT_DOSSIER, G.R_DUP, G.R_WAIT, G.R_HAVE}
SHORT = {G.R_NOSIG: "không có chữ ký thật", G.R_BADSIG: "chữ ký hỏng", G.R_BAD: "file lỗi", G.R_PAGES: "lệch số trang",
         G.R_BUSY: "đang ký", G.R_CHANGED: "bản gốc đã đổi", G.R_CONFLICT: "xung đột", G.R_UNKNOWN: "không rõ hồ sơ",
         G.R_SPARE: "bản ký dư", G.G_DUPNAME: "trùng tên hồ sơ"}
JOURNAL = "gom_ky_so_hoan_tac.json"
KIND_TEXT = {"gather": "lần gom (xoá các file đã chép vào thư mục gom)",
             "copy": "lần chép ra thư mục mới (xoá các file vừa chép)",
             "return": "lần trả về (đưa file về lại thư mục gom)",
             "regroup": "lần tách file cần ký lại (đưa file về chỗ cũ)"}


def _journal_path() -> str:
    return os.path.join(paths.data_dir(), JOURNAL)


class FileOpThread(QThread):
    """Chép / chuyển / kiểm tra file ở luồng phụ (không đụng widget) – có tiến độ."""
    progress = Signal(int, int)
    done = Signal(object, object)            # kết quả, lỗi

    def __init__(self, fn: Callable):
        super().__init__()
        self.fn = fn
        self.cancelled = False

    def run(self):
        try:
            self.done.emit(self.fn(lambda i, n: self.progress.emit(i, n), lambda: self.cancelled), None)
        except Exception as e:
            self.done.emit(None, e)


class _Model(QAbstractTableModel):
    """Bảng ảo: hàng nghìn dòng không tạo hàng chục nghìn ô → đổ dữ liệu / lọc / tìm tức thì."""
    COLS = ["STT", "Hồ sơ (CCCD_HoVaTen)", "Tên file", "→ Thư mục gom / đích", "Trạng thái", "Ghi chú"]

    def __init__(self):
        super().__init__()
        self.rows: List[tuple] = []          # (hồ sơ, tên, đích gọn, đích đủ, mã, nguồn, ghi chú, chữ trạng thái)

    def set_rows(self, rows: List[tuple]):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            return self.COLS[s]
        return None

    def data(self, idx, role=Qt.DisplayRole):
        r = self.rows[idx.row()]
        c = idx.column()
        if role == Qt.DisplayRole:
            return (idx.row() + 1, r[0], r[1], r[2], r[7], r[6])[c]
        if role == Qt.ToolTipRole:
            return {2: r[5], 3: r[3], 5: r[6]}.get(c) or None
        if role == Qt.ForegroundRole and c == 4:
            return QColor(tc(COLOR.get(r[4], TEXT)))
        if role == Qt.TextAlignmentRole and c == 0:
            return int(Qt.AlignCenter)
        return None


class _Filter(QSortFilterProxyModel):
    def __init__(self, panel: "SignPanel"):
        super().__init__()
        self.p = panel
        self.text = ""

    def filterAcceptsRow(self, row, parent):
        r = self.sourceModel().rows[row]
        if self.p.ck_hide.isChecked() and r[4] in SKIPPED:
            return False
        if self.p.ck_issue.isChecked() and r[4] not in G.ISSUES:
            return False
        return not self.text or self.text in fold(f"{r[0]} {r[1]} {r[2]} {r[6]}")


class SignPanel(QWidget):
    changed = Signal()
    busyChanged = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.files: List[FileInfo] = []
        self.root = ""
        self.mode = "gather"                   # gather | return
        self.gplan: List[G.GatherItem] = []
        self.rplan: List[G.ReturnItem] = []
        self.journal: Optional[G.Journal] = G.load_journal(_journal_path())    # hoàn tác được cả sau khi tắt app
        self.journal_kind = self.journal.kind if self.journal else ""
        self.thread: Optional[FileOpThread] = None
        self.busy_check: Callable[[], bool] = lambda: False
        self._note = ""                        # thông báo kết quả vừa làm (giữ lại khi app tự quét lại)
        self._planning = False                 # luồng phụ đang chỉ ĐỌC thư mục gom (kiểm tra trả về)
        self._recheck = False                  # có thay đổi trong lúc đang kiểm tra → kiểm tra lại khi xong
        self._out_auto = True                  # ô thư mục mới do app tự điền (được tự đổi theo thư mục gom)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 8)
        g = QGroupBox("Gom file để ký số hàng loạt")
        gl = QVBoxLayout(g)
        steps = QLabel("<b>①</b> <b>Gom để ký</b>: chép file <b>chưa ký</b> của các hồ sơ <code>CCCD_HoVaTen</code> vào 1 "
                       "thư mục, tên thêm đuôi hồ sơ (vd <code>01.Ly_lich…_056123456789_TranVanThai.pdf</code>) "
                       "&nbsp;➜&nbsp; ✍ <b>Ký số hàng loạt</b> bằng phần mềm ký &nbsp;➜&nbsp; <b>②</b> <b>Trả về</b>: bản "
                       "<code>.signed</code> (đã kiểm tra chữ ký thật) về đúng hồ sơ, bỏ đuôi. "
                       "File gốc luôn giữ nguyên, không ghi đè.")
        steps.setObjectName("Steps")
        steps.setWordWrap(True)
        gl.addWidget(steps)
        r = QHBoxLayout()
        r.addWidget(QLabel("Thư mục gom:"))
        self.ed_dir = QLineEdit()
        self.ed_dir.setPlaceholderText("Thư mục chứa các file gom để ký")
        self.ed_dir.editingFinished.connect(self.refresh)
        self.ed_dir.textEdited.connect(lambda _: setattr(self, "_dir_auto", False))
        self._dir_auto = True                  # ô thư mục gom do app tự điền theo thư mục quét
        r.addWidget(self.ed_dir, 1)
        r.addWidget(button("📁 Chọn…", "light", self.pick_dir, size="sm"))
        r.addWidget(button("📂 Mở thư mục gom", "light", self.open_dir, size="sm"))
        gl.addLayout(r)
        r = QHBoxLayout()
        self.lbl_scope = QLabel("")
        self.lbl_scope.setStyleSheet("color:#475569")
        r.addWidget(self.lbl_scope, 1)
        r.addWidget(QLabel("Chia lô:"))
        self.cb_batch = QComboBox()
        for text, data in (("Không chia", G.BATCH_NONE), ("Theo chi bộ", G.BATCH_CHIBO), ("Mỗi lô N file", G.BATCH_SIZE)):
            self.cb_batch.addItem(text, data)
        self.cb_batch.setToolTip("Gom vào thư mục con theo chi bộ hoặc mỗi lô N file – phần mềm ký giới hạn số file "
                                 "mỗi lần / lỗi lô nào chỉ ký lại lô đó")
        r.addWidget(self.cb_batch)
        self.sp_batch = QSpinBox()
        self.sp_batch.setRange(10, 5000)
        self.sp_batch.setSingleStep(50)
        self.sp_batch.setValue(300)
        self.sp_batch.setSuffix(" file/lô")
        r.addWidget(self.sp_batch)
        self.cb_batch.currentIndexChanged.connect(self._batch_changed)
        self.sp_batch.valueChanged.connect(lambda _: self._batch_changed())
        gl.addLayout(r)
        # ② trả về: vào hồ sơ gốc HOẶC chép ra thư mục mới (cùng cây Chi bộ\CCCD_HoVaTen, hồ sơ gốc không đổi)
        r = QHBoxLayout()
        r.addWidget(QLabel("<b>② Sau ký:</b>"))
        self.rb_back = QRadioButton("Trả về thư mục hồ sơ gốc")
        self.rb_back.setToolTip("Chuyển bản .signed vào đúng thư mục CCCD_HoVaTen, bỏ đuôi; xoá bản sao chưa ký thừa")
        self.rb_copy = QRadioButton("Chép ra thư mục mới (giữ nguyên hồ sơ gốc)")
        self.rb_copy.setToolTip("Thư mục mới có cùng cây Chi bộ\\CCCD_HoVaTen, chứa bản đã ký + chưa ký (bỏ đuôi);\n"
                                "hồ sơ gốc và thư mục gom không bị thay đổi")
        self.rb_copy.setChecked(True)
        r.addWidget(self.rb_back)
        r.addWidget(self.rb_copy)
        self.ck_full = QCheckBox("Chép kèm đủ bộ hồ sơ")
        self.ck_full.setToolTip("Chép thêm các file khác trong hồ sơ (giấy tờ đã ký trước, file không cần ký…) →\n"
                                "thư mục mới là bộ hồ sơ đầy đủ")
        self.ck_full.setChecked(True)
        r.addWidget(self.ck_full)
        r.addStretch(1)
        gl.addLayout(r)
        r = QHBoxLayout()
        self.lbl_out = QLabel("Thư mục mới:")
        r.addWidget(self.lbl_out)
        self.ed_out = QLineEdit()
        self.ed_out.setPlaceholderText("Thư mục nhận bộ hồ sơ đã ký")
        self.ed_out.editingFinished.connect(self._out_changed)
        self.ed_out.textEdited.connect(lambda _: setattr(self, "_out_auto", False))      # người dùng tự gõ
        r.addWidget(self.ed_out, 1)
        self.btn_out = button("📁 Chọn…", "light", self.pick_out, size="sm")
        self.btn_open_out = button("📂 Mở", "light", lambda: open_path(self.out_dir()) if os.path.isdir(self.out_dir())
                                   else None, size="sm")
        r.addWidget(self.btn_out)
        r.addWidget(self.btn_open_out)
        gl.addLayout(r)
        r = QHBoxLayout()
        self.ck_verify = QCheckBox("🛡 Kiểm tra chữ ký số thật + số trang (khuyên dùng)")
        self.ck_verify.setToolTip("Chỉ nhận bản ký có chữ ký số thật (không chỉ đổi tên .signed), chữ ký không hỏng,\n"
                                  "mở được và cùng số trang bản gốc. Tắt chỉ khi test với file giả.")
        self.ck_verify.setChecked(True)
        self.ck_watch = QCheckBox("👁 Tự cập nhật khi đang ký")
        self.ck_watch.setToolTip("Theo dõi thư mục gom: phần mềm ký tạo file mới → bảng tự kiểm tra lại")
        self.ck_watch.setChecked(True)
        r.addWidget(self.ck_verify)
        r.addWidget(self.ck_watch)
        r.addStretch(1)
        gl.addLayout(r)
        for w in (self.rb_back, self.rb_copy, self.ck_full, self.ck_verify):
            w.toggled.connect(self._out_changed)
        lay.addWidget(g)

        self.lbl_mode = QLabel("")
        self.lbl_mode.setStyleSheet("font-weight:700;color:#1E40AF")
        lay.addWidget(self.lbl_mode)
        r = QHBoxLayout()
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("🔎 Tìm hồ sơ / tên file / ghi chú (không cần dấu)…")
        self.ed_search.setClearButtonEnabled(True)
        r.addWidget(self.ed_search, 1)
        self.ck_issue = QCheckBox("⚠ Chỉ dòng cần xử lý")
        self.ck_hide = QCheckBox("Ẩn dòng bỏ qua / giữ lại")
        r.addWidget(self.ck_issue)
        r.addWidget(self.ck_hide)
        self.btn_regroup = button("📦 Tách file cần ký lại", "light", self.do_regroup, size="sm",
                                  tip="File chưa ký → thư mục con “Ký lại …” để ký riêng phần còn thiếu;\n"
                                      "bản ký lỗi / dư → “_Bản ký lỗi” (không bị kiểm tra lại). Có hoàn tác.")
        self.btn_excel = button("📊 Xuất Excel", "light", self.export_excel, size="sm",
                                tip="Xuất bảng đang xem: tổng hợp theo hồ sơ + chi tiết từng file")
        r.addWidget(self.btn_regroup)
        r.addWidget(self.btn_excel)
        lay.addLayout(r)

        self.model = _Model()
        self.proxy = _Filter(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, w in enumerate((50, 230, 290, 400, 260)):
            self.table.setColumnWidth(i, w)
        self.table.doubleClicked.connect(self._open_row)
        lay.addWidget(self.table, 1)
        self._search_timer = QTimer(self, singleShot=True, interval=200)
        self._search_timer.timeout.connect(self._apply_filter)
        self.ed_search.textChanged.connect(lambda _: self._search_timer.start())
        for w in (self.ck_issue, self.ck_hide):
            w.toggled.connect(self._apply_filter)

        bot = QHBoxLayout()
        self.lbl = QLabel("Chưa có dữ liệu – hãy chọn thư mục chi bộ / Hồ sơ số hóa và bấm Quét, "
                          "hoặc chọn thư mục gom rồi bấm “🔍 Kiểm tra trả về”.")
        self.lbl.setWordWrap(True)
        self.lbl.setStyleSheet("font-weight:700;color:#1E40AF")
        bot.addWidget(self.lbl, 1)
        self.prog = QProgressBar()
        self.prog.setFixedWidth(180)
        self.prog.hide()
        bot.addWidget(self.prog)
        self.btn_gather = button("① GOM ĐỂ KÝ", "success", self.gather, size="lg",
                                 tip="Chép file chưa ký vào thư mục gom (đổi tên thêm đuôi _CCCD_HoVaTen)")
        self.btn_check = button("🔍 Kiểm tra trả về", "cyan", self.check_return,
                                tip="Kiểm tra các bản ký trong thư mục gom (chữ ký thật, số trang) và nơi trả về")
        self.btn_return = button("② TRẢ VỀ SAU KÝ", "indigo", self.do_return, size="lg",
                                 tip="Chuyển bản .signed về đúng hồ sơ, bỏ đuôi _CCCD_HoVaTen")
        self.btn_undo = button("↶ Hoàn tác", "light", self.undo, tip="Hoàn tác lần gom / trả về / chép vừa làm")
        for b in (self.btn_gather, self.btn_check, self.btn_return, self.btn_undo):
            bot.addWidget(b)
        lay.addLayout(bot)

        # theo dõi thư mục gom khi đang ký (gộp nhiều thay đổi liên tiếp → kiểm tra lại 1 lần)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda _: self._watch_timer.start())
        self._watch_timer = QTimer(self, singleShot=True, interval=1500)
        self._watch_timer.timeout.connect(self._auto_recheck)
        self._busy_timer = QTimer(self, singleShot=True, interval=(G.BUSY_SECONDS + 1) * 1000)
        self._busy_timer.timeout.connect(self._auto_recheck)
        self._enable()
        self._out_changed()

    # ------------------------------------------------------------------ dữ liệu vào
    @property
    def running(self) -> bool:
        return self.thread is not None        # tới khi _finish nhận kết quả (luồng có thể đã dừng mà tín hiệu chưa tới)

    def set_files(self, files: List[FileInfo], root: str, scope_label: str):
        if self.running and not self._planning:
            return
        if root and root != self.root:                     # thư mục người dùng đã tự chọn thì giữ nguyên
            base = root.rstrip("\\/")
            if self._dir_auto:
                self.ed_dir.setText(os.path.join(os.path.dirname(base), os.path.basename(base) + " - Gom ký số"))
            if self._out_auto:
                self.ed_out.setText(os.path.join(os.path.dirname(base), os.path.basename(base) + " - Đã ký"))
        if root != self.root:
            self.mode = "gather"
        self.files, self.root = files, root
        self.lbl_scope.setText(f"Phạm vi: <b>{scope_label}</b> · {fmt(len(files))} file")
        self.refresh()

    def gather_dir(self) -> str:
        return os.path.normpath(self.ed_dir.text().strip().strip('"')) if self.ed_dir.text().strip() else ""

    def refresh(self):
        if self.mode == "return":
            self.check_return()
            return
        self.gplan = G.plan_gather(self.files, self.gather_dir(), self.cb_batch.currentData(), self.sp_batch.value())
        n = sum(1 for it in self.gplan if it.status == G.G_NEW)
        lots = len({it.sub for it in self.gplan if it.status == G.G_NEW and it.sub})
        self.lbl_mode.setText(f"Xem trước ① Gom để ký – {fmt(n)} file sẽ được chép vào thư mục gom"
                              + (f", chia {lots} lô" if lots else ""))
        self.fill()
        if self.files:
            c = {k: sum(1 for it in self.gplan if it.status == k) for k in (G.G_SIGNED, G.G_EXISTS, G.G_DUPNAME)}
            longs = sum(1 for it in self.gplan if "đường dẫn dài" in it.note)
            self.lbl.setText(f"{fmt(n)} file chưa ký sẽ gom · {fmt(c[G.G_SIGNED])} file đã có bản ký · "
                             f"{fmt(c[G.G_EXISTS])} file đã có trong thư mục gom"
                             + (f" · ⚠ {fmt(c[G.G_DUPNAME])} file trùng tên hồ sơ (không gom)" if c[G.G_DUPNAME] else "")
                             + (f" · ⚠ {fmt(longs)} đường dẫn dài" if longs else "") + ".")
        self._enable()

    def _batch_changed(self, *_):
        self.sp_batch.setEnabled(self.cb_batch.currentData() == G.BATCH_SIZE and not self.running)
        if self.mode == "gather" and not self.running:
            self.refresh()

    def fill(self, *_):
        copy = self.mode == "return" and self.copy_mode()
        if self.mode == "gather":
            gd = self.gather_dir()
            rows = [(it.folder, os.path.basename(it.src), it.rel if it.new_name else "—",
                     os.path.join(gd, it.rel) if it.new_name else "", it.status, it.src, it.note, G.TEXT[it.status])
                    for it in self.gplan]
        else:
            # đích hiện gọn "hồ sơ\tên file" (đường dẫn đầy đủ ở tooltip)
            rows = [(it.folder or "?", os.path.basename(it.path),
                     os.path.join(os.path.basename(os.path.dirname(it.dest)), os.path.basename(it.dest))
                     if it.dest else "—", it.dest, it.status, it.path, it.note,
                     "Chép bản đã ký" if copy and it.status == G.R_SIGNED else G.TEXT[it.status])
                    for it in self.rplan]
        self.model.set_rows(rows)

    def _apply_filter(self, *_):
        self.proxy.text = fold(self.ed_search.text().strip())
        self.proxy.invalidateFilter()

    def view_rows(self) -> int:
        return self.proxy.rowCount()

    def _open_row(self, idx):
        r = self.model.rows[self.proxy.mapToSource(idx).row()]
        for p in (r[3], r[5]):
            if p and os.path.exists(G._lp(p)):
                open_path(os.path.dirname(p))
                return

    # ------------------------------------------------------------------ tiện ích
    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục gom để ký", self.gather_dir())
        if d:
            self.ed_dir.setText(os.path.normpath(d))
            self._dir_auto = False
            self.refresh()

    def open_dir(self):
        d = self.gather_dir()
        if d and os.path.isdir(d):
            open_path(d)
        else:
            QMessageBox.information(self, "Thư mục gom", "Thư mục gom chưa có – hãy bấm “① Gom để ký” trước.")

    def _valid_dir(self) -> bool:
        d = self.gather_dir()
        if not d:
            QMessageBox.warning(self, "Thiếu thư mục gom", "Hãy chọn thư mục gom.")
            return False
        if self.root:
            r = os.path.normcase(os.path.abspath(self.root))
            g = os.path.normcase(os.path.abspath(d))
            if g == r or g.startswith(r + os.sep):
                QMessageBox.warning(self, "Thư mục gom", "Thư mục gom không được nằm trong thư mục hồ sơ đang quét.")
                return False
        return True

    def copy_mode(self) -> bool:
        return self.rb_copy.isChecked()

    def out_dir(self) -> str:
        t = self.ed_out.text().strip().strip('"')
        return os.path.normpath(t) if t else ""

    def pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục nhận bộ hồ sơ đã ký", self.out_dir())
        if d:
            self.ed_out.setText(os.path.normpath(d))
            self._out_auto = False
            self._out_changed()

    def _out_changed(self, *_):
        copy = self.copy_mode()
        for w in (self.lbl_out, self.ed_out, self.btn_out, self.btn_open_out, self.ck_full):
            w.setEnabled(copy and not self.running)
        self.btn_return.setText("② CHÉP RA THƯ MỤC MỚI" if copy else "② TRẢ VỀ SAU KÝ")
        if self.mode == "return":
            self.check_return()

    def _valid_out(self) -> bool:
        o = self.out_dir()
        if not o:
            QMessageBox.warning(self, "Thiếu thư mục mới", "Hãy chọn thư mục nhận bộ hồ sơ đã ký.")
            return False
        on = os.path.normcase(os.path.abspath(o))
        for other, what in ((self.root, "thư mục hồ sơ đang quét"), (self.gather_dir(), "thư mục gom")):
            if other:
                x = os.path.normcase(os.path.abspath(other))
                if on == x or on.startswith(x + os.sep) or x.startswith(on + os.sep):
                    QMessageBox.warning(self, "Thư mục mới", f"Thư mục mới không được trùng / lồng với {what}.")
                    return False
        return True

    def _enable(self):
        run = self.running
        self.btn_gather.setEnabled(not run and any(it.status == G.G_NEW for it in self.gplan))
        self.btn_check.setEnabled(not run and bool(self.gather_dir()))
        acts = G.COPY_ACTIONS if self.copy_mode() else G.BACK_ACTIONS
        self.btn_return.setEnabled(not run and self.mode == "return" and any(it.status in acts for it in self.rplan))
        self.btn_regroup.setEnabled(not run and self.mode == "return" and
                                    any(it.status in G.REJECTS or it.status == G.R_WAIT for it in self.rplan))
        self.btn_excel.setEnabled(not run and self.model.rowCount() > 0)
        for w in (self.rb_back, self.rb_copy, self.ck_verify, self.cb_batch):
            w.setEnabled(not run)
        self.sp_batch.setEnabled(not run and self.cb_batch.currentData() == G.BATCH_SIZE)
        for w in (self.lbl_out, self.ed_out, self.btn_out, self.btn_open_out, self.ck_full):
            w.setEnabled(not run and self.copy_mode())
        self.btn_undo.setEnabled(not run and self.journal is not None)
        if self.journal is not None:
            when = self.journal.time.replace("T", " ")[:16]
            self.btn_undo.setToolTip(f"Hoàn tác {KIND_TEXT.get(self.journal_kind, 'thao tác vừa rồi')}\n"
                                     f"lúc {when} – {len(self.journal)} file (nhớ cả sau khi tắt app)")
        self.ed_dir.setEnabled(not run)
        self.prog.setVisible(run)

    def _run(self, fn, on_done, total: int):
        self.prog.setRange(0, max(1, total) if total else 0)          # total = 0 → thanh chạy qua lại
        self.prog.setValue(0)
        t = FileOpThread(fn)
        t.progress.connect(self._progress)
        t.done.connect(on_done)
        self.thread = t
        t.start()
        self._enable()
        self.busyChanged.emit(True)

    def _progress(self, i: int, n: int):
        if self.prog.maximum() != n:
            self.prog.setRange(0, max(1, n))
        self.prog.setValue(i)

    def _finish(self):
        if self.thread:
            self.thread.wait()
        self.thread = None
        self._enable()
        self.busyChanged.emit(False)

    # ------------------------------------------------------------------ nhật ký hoàn tác (lưu ra file)
    def _keep_journal(self, j: Optional[G.Journal], kind: str):
        """Giữ nhật ký để hoàn tác (kể cả lần làm dở vì lỗi) và lưu ra file – tắt app vẫn hoàn tác được."""
        if j is None or not len(j):
            return
        j.kind = kind
        self.journal, self.journal_kind = j, kind
        try:
            G.save_journal(_journal_path(), j)
        except OSError:
            pass

    def _checkpoint(self, kind: str):
        def save(j: G.Journal):                 # gọi từ luồng phụ mỗi 100 file: mất điện vẫn còn nhật ký
            j.kind = kind
            try:
                G.save_journal(_journal_path(), j)
            except OSError:
                pass
        return save

    def _partial(self, err) -> Optional[G.Journal]:
        return getattr(err, "partial_journal", None)

    # ------------------------------------------------------------------ ① gom
    def gather(self):
        if self.busy_check() or not self._valid_dir():
            return
        todo = [it for it in self.gplan if it.status == G.G_NEW]
        if not todo:
            return
        d = self.gather_dir()
        lots = sorted({it.sub for it in todo if it.sub})
        if QMessageBox.question(self, "Gom để ký",
                                f"Chép {len(todo)} file chưa ký vào:\n{d}\n"
                                + (f"chia {len(lots)} lô ({lots[0]} … {lots[-1]})\n" if lots else "")
                                + "\n(tên thêm đuôi _CCCD_HoVaTen; file gốc giữ nguyên)\n\nTiếp tục?") != QMessageBox.Yes:
            return
        plan = list(self.gplan)
        self.lbl.setText(f"Đang chép {len(todo)} file…")
        cp = self._checkpoint("gather")
        self._run(lambda prog, cancel: G.gather(plan, d, prog, cancel, cp), self._gathered, len(todo))

    def _gathered(self, j, err):
        self._finish()
        self._keep_journal(j if j is not None else self._partial(err), "gather")
        self.refresh()
        if err is not None:
            QMessageBox.warning(self, "Lỗi gom file", f"❌ {err}")
            return
        activity.log("Gom ký số", f"{len(j.copied)} file → {self.gather_dir()}")
        self.lbl.setText(f"✔ Đã gom {len(j.copied)} file vào thư mục gom. Hãy ký số các file trong thư mục này, "
                         "xong bấm “🔍 Kiểm tra trả về”.")
        self._enable()
        if QMessageBox.question(self, "Đã gom", f"Đã chép {len(j.copied)} file.\n\nMở thư mục gom để ký số?") \
                == QMessageBox.Yes:
            open_path(self.gather_dir())

    # ------------------------------------------------------------------ ② trả về
    def check_return(self):
        """Đọc thư mục gom ở LUỒNG PHỤ (hàng nghìn file / ổ mạng không làm đứng giao diện), xong mới hiện bảng."""
        d = self.gather_dir()
        self.mode = "return"
        if self.running:
            self._recheck = self._planning                 # đang kiểm tra → kiểm tra lại khi xong
            return
        copy = self.copy_mode()
        if not (d and os.path.isdir(d)):
            self.rplan = []
            self._show_return()
            return
        # thư mục hồ sơ gốc theo sổ ghi → chạy được cả khi CHƯA quét / quét nhầm chính thư mục gom
        base = G.guess_root(d)
        roots = [r for r in (base, self.root) if r]
        if self._out_auto and (base or self.root):          # thư mục mới chưa tự chọn → đặt cạnh thư mục hồ sơ gốc
            src = (base or self.root).rstrip("\\/")
            self.ed_out.setText(os.path.join(os.path.dirname(src), os.path.basename(src) + " - Đã ký"))
        out, full, verify = (self.out_dir() if copy else ""), self.ck_full.isChecked(), self.ck_verify.isChecked()
        if copy and not out:
            self.rplan = []
            self._show_return()
            return
        self._planning = True
        if not self.rplan:
            self.lbl.setText("⏳ Đang kiểm tra thư mục gom" + (" (đọc chữ ký số + số trang)…" if verify else "…"))
        self._run(lambda prog, cancel: G.plan_return(d, roots, out, full, verify, prog), self._planned, 0)

    def _planned(self, plan, err):
        self._planning = False
        self._finish()
        if self.mode != "return":                          # đã chuyển sang xem gom (vd quét thư mục khác) → bỏ kết quả
            self._recheck = False
            return
        if self._recheck:                                  # tuỳ chọn / thư mục đã đổi trong lúc kiểm tra
            self._recheck = False
            self.check_return()
            return
        self.rplan = plan or []
        if err is not None:
            QMessageBox.warning(self, "Lỗi kiểm tra", f"❌ {err}")
        self._show_return()
        self._watch()
        if any(it.status == G.R_BUSY for it in self.rplan):
            self._busy_timer.start()                       # phần mềm ký còn đang ghi → tự kiểm tra lại sau vài giây

    def _show_return(self):
        copy = self.copy_mode()
        c = {k: sum(1 for it in self.rplan if it.status == k) for k in G.TEXT}
        # bản ký hợp lệ (kể cả đích đã có / xung đột ở đích – chữ ký vẫn đúng)
        done = sum(1 for it in self.rplan if it.signed and it.status in (G.R_SIGNED, G.R_HAVE, G.R_CONFLICT))
        wait = sum(1 for it in self.rplan if not it.signed and it.status in (G.R_WAIT, G.R_BUSY, G.R_CHANGED))
        prog = f"✍ Đã ký hợp lệ {fmt(done)} / {fmt(done + wait)} văn bản" if done + wait else ""
        if copy:
            head = (f"Xem trước ② Chép ra thư mục mới – {fmt(c[G.R_SIGNED])} bản đã ký + {fmt(c[G.R_COPY])} bản chưa ký "
                    f"+ {fmt(c[G.R_EXTRA])} file kèm")
        else:
            head = f"Xem trước ② Trả về – {fmt(c[G.R_SIGNED] + c[G.R_BACK])} file về hồ sơ"
        self.lbl_mode.setText(head + (f"   ·   {prog}" if prog else ""))
        self.fill()
        note, self._note = self._note, ""
        issues = " · ".join(f"{fmt(c[k])} {t}" for k, t in SHORT.items() if c.get(k))
        if not self.rplan:
            d = self.gather_dir()
            if not d:
                why = "⚠ Chưa chọn thư mục gom – bấm “📁 Chọn…” ở dòng Thư mục gom."
            elif not os.path.isdir(d):
                why = f"⚠ Không thấy thư mục gom: {d} – bấm “📁 Chọn…” để chọn lại."
            elif copy and not self.out_dir():
                why = "⚠ Chưa có thư mục mới để chép ra – bấm “📁 Chọn…” ở dòng Thư mục mới."
            else:
                why = "Thư mục gom không có file PDF nào (đã trả về hết, hoặc chọn nhầm thư mục)."
            self.lbl.setText(note + why)
        elif copy:
            self.lbl.setText(note + f"Sẽ chép {fmt(sum(c[k] for k in G.COPY_ACTIONS))} file · {fmt(c[G.R_HAVE])} đã có "
                             f"· {fmt(c[G.R_WAIT])} chưa ký (bỏ qua)"
                             + (f" · ⚠ {issues} (tích “⚠ Chỉ dòng cần xử lý” để xem)" if issues else "")
                             + ". Hồ sơ gốc và thư mục gom không đổi.")
        else:
            self.lbl.setText(note + f"{fmt(c[G.R_SIGNED])} bản đã ký sẽ trả về · {fmt(c[G.R_DUP])} bản sao chưa ký "
                             f"sẽ xoá · {fmt(c[G.R_WAIT])} file chưa ký (giữ lại)"
                             + (f" · ⚠ {issues} (tích “⚠ Chỉ dòng cần xử lý” để xem)" if issues else "") + ".")
        self._enable()

    def _watch(self):
        """Theo dõi thư mục gom + thư mục con (lô, Signed/…) khi bật “Tự cập nhật”."""
        old = self.watcher.directories()
        if old:
            self.watcher.removePaths(old)
        d = self.gather_dir()
        if not (self.ck_watch.isChecked() and d and os.path.isdir(d)):
            return
        dirs = [d]
        for dp, dns, _ in os.walk(d):
            dns[:] = [x for x in dns if not x.startswith("_")]
            dirs += [os.path.join(dp, x) for x in dns]
        self.watcher.addPaths(dirs[:200])

    def _auto_recheck(self):
        if not (self.ck_watch.isChecked() and self.mode == "return"):
            return
        if self.running or not self.isVisible():
            self._dirty = True                             # kiểm tra khi xong việc / khi mở lại tab
            if self.running:
                self._watch_timer.start()
            return
        self.check_return()

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_dirty", False) and self.mode == "return" and not self.running:
            self._dirty = False
            self.check_return()

    def do_return(self):
        if self.busy_check():
            return
        if self.copy_mode():
            self._copy_out()
            return
        todo = [it for it in self.rplan if it.status in G.BACK_ACTIONS]
        if not todo:
            return
        n = sum(1 for it in todo if it.status != G.R_DUP)
        if QMessageBox.question(self, "Trả về sau ký",
                                f"Chuyển {n} file về đúng hồ sơ (bỏ đuôi _CCCD_HoVaTen) và xoá "
                                f"{len(todo) - n} bản sao chưa ký giống hệt bản gốc.\n\nKhông ghi đè file nào. "
                                "Tiếp tục?") != QMessageBox.Yes:
            return
        plan = list(self.rplan)
        self.lbl.setText(f"Đang trả về {n} file…")
        cp = self._checkpoint("return")
        self._run(lambda prog, cancel: G.do_return(plan, prog, False, cancel, cp), self._returned, len(todo))

    def _copy_out(self):
        if not self._valid_out():
            return
        todo = [it for it in self.rplan if it.status in G.COPY_ACTIONS]
        if not todo:
            return
        out = self.out_dir()
        if QMessageBox.question(self, "Chép ra thư mục mới",
                                f"Chép {len(todo)} file (bản đã ký, bản chưa ký"
                                + (", file kèm của hồ sơ" if self.ck_full.isChecked() else "")
                                + f") sang:\n{out}\n\ngiữ cây Chi bộ\\CCCD_HoVaTen, bỏ đuôi _CCCD_HoVaTen. Hồ sơ gốc và "
                                "thư mục gom không đổi, không ghi đè.\n\nTiếp tục?") != QMessageBox.Yes:
            return
        plan = list(self.rplan)
        self.lbl.setText(f"Đang chép {len(todo)} file…")
        cp = self._checkpoint("copy")
        self._run(lambda prog, cancel: G.do_return(plan, prog, True, cancel, cp), self._copied, len(todo))

    def _copied(self, j, err):
        self._finish()
        self._keep_journal(j if j is not None else self._partial(err), "copy")
        if j is not None:
            activity.log("Chép bộ hồ sơ đã ký", f"{len(j.copied)} file → {self.out_dir()}")
            self._note = f"✔ Đã chép {len(j.copied)} file sang thư mục mới. "
        if err is not None:
            QMessageBox.warning(self, "Lỗi chép", f"❌ {err}")
        self.check_return()
        if j is not None and j.copied and QMessageBox.question(
                self, "Đã chép", f"Đã chép {len(j.copied)} file.\n\nMở thư mục mới?") == QMessageBox.Yes:
            open_path(self.out_dir())

    def _returned(self, j, err):
        self._finish()
        self._keep_journal(j if j is not None else self._partial(err), "return")
        if j is not None:
            activity.log("Trả về sau ký", f"{len(j.moved)} file về hồ sơ, xoá {len(j.removed)} bản sao")
            self._note = f"✔ Đã trả {len(j.moved)} file về hồ sơ, xoá {len(j.removed)} bản sao. "
        if err is not None:
            QMessageBox.warning(self, "Lỗi trả về", f"❌ {err}")
        done = j if j is not None else self._partial(err)
        if done is not None and done.moved:
            self.changed.emit()       # quét lại (cây thư mục / báo cáo thấy bản .signed mới) → tự kiểm tra lại
        else:
            self.check_return()

    # ------------------------------------------------------------------ tách file cần ký lại
    def do_regroup(self):
        if self.busy_check():
            return
        pairs = G.plan_regroup(self.rplan, self.gather_dir())
        if not pairs:
            QMessageBox.information(self, "Tách file cần ký lại", "Không có file chưa ký / bản ký lỗi nào để tách.")
            return
        rej = sum(1 for _, d in pairs if os.path.basename(os.path.dirname(d)) == G.REJECT_DIR)
        redo = len(pairs) - rej
        redo_dir = next((os.path.dirname(d) for _, d in pairs if os.path.basename(os.path.dirname(d)) != G.REJECT_DIR),
                        "")
        if QMessageBox.question(self, "Tách file cần ký lại",
                                (f"Chuyển {redo} file chưa ký vào:\n{redo_dir}\n(ký riêng phần còn thiếu)\n\n" if redo
                                 else "") +
                                (f"Chuyển {rej} bản ký lỗi / dư vào thư mục “{G.REJECT_DIR}” "
                                 "(không bị kiểm tra lại, không xoá).\n\n" if rej else "") +
                                "Chỉ chuyển trong thư mục gom, có hoàn tác. Tiếp tục?") != QMessageBox.Yes:
            return
        self.lbl.setText(f"Đang tách {len(pairs)} file…")
        self._regroup_dir = redo_dir
        self._run(lambda prog, cancel: G.regroup(pairs, prog), self._regrouped, len(pairs))

    def _regrouped(self, j, err):
        self._finish()
        self._keep_journal(j if j is not None else self._partial(err), "regroup")
        if err is not None:
            QMessageBox.warning(self, "Lỗi tách file", f"❌ {err}")
        if j is not None:
            activity.log("Tách file cần ký lại", f"{len(j.moved)} file")
            self._note = f"✔ Đã tách {len(j.moved)} file. "
        self.check_return()
        d = getattr(self, "_regroup_dir", "")
        if j is not None and d and os.path.isdir(d) and QMessageBox.question(
                self, "Đã tách", f"Mở thư mục cần ký lại?\n{d}") == QMessageBox.Yes:
            open_path(d)

    # ------------------------------------------------------------------ Excel
    def export_excel(self):
        if not self.model.rows:
            return
        base = os.path.dirname(self.gather_dir()) if self.gather_dir() else os.path.expanduser("~")
        name = f"Ket_qua_gom_ky_so_{datetime.now():%Y%m%d_%H%M}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Xuất Excel kết quả", os.path.join(base, name), "Excel (*.xlsx)")
        if not path:
            return
        src = [self.model.rows[self.proxy.mapToSource(self.proxy.index(i, 0)).row()]
               for i in range(self.proxy.rowCount())]                      # đúng các dòng đang xem (sau lọc / tìm)
        signed = {it.path for it in self.rplan if it.signed} if self.mode == "return" else set()
        rows = [(r[0], r[1], r[3], r[4], r[7], r[6], r[5] in signed) for r in src]
        title = "Kết quả gom ký số – " + ("xem trước gom" if self.mode == "gather" else
                                           ("chép ra thư mục mới" if self.copy_mode() else "trả về hồ sơ"))
        sub = f"Thư mục gom: {self.gather_dir()}"

        def done(res, err):
            if err is not None:
                QMessageBox.warning(self, "Lỗi xuất Excel", f"❌ {err}")
            elif QMessageBox.question(self, "Đã xuất", f"Đã lưu:\n{res}\n\nMở file?") == QMessageBox.Yes:
                open_path(res)
        run_bg(self, self.btn_excel, "⏳ Đang xuất…", lambda: GX.export(path, rows, title, sub), done)

    # ------------------------------------------------------------------ hoàn tác
    def undo(self):
        if not self.journal or self.busy_check():
            return
        when = self.journal.time.replace("T", " ")[:16]
        what = KIND_TEXT.get(self.journal_kind, "thao tác vừa rồi")
        if QMessageBox.question(self, "Hoàn tác", f"Hoàn tác {what}?\n({len(self.journal)} file, lúc {when})") \
                != QMessageBox.Yes:
            return
        j = self.journal
        self.lbl.setText("⏳ Đang hoàn tác…")
        self._run(lambda prog, cancel: G.undo(j, prog), self._undone, 0)        # chuyển / xoá hàng nghìn file ở luồng phụ

    def _undone(self, n, err):
        self._finish()
        if err is not None:
            QMessageBox.warning(self, "Lỗi hoàn tác", f"❌ {err}")
            return
        kind, self.journal = self.journal_kind, None
        try:
            os.remove(_journal_path())
        except OSError:
            pass
        self._note = f"↶ Đã hoàn tác {n} file. "
        activity.log("Hoàn tác gom ký số", f"{n} file")
        if kind == "return":
            self.changed.emit()        # quét lại hồ sơ → set_files → tự kiểm tra lại (quét bỏ qua nếu app đang bận)
        elif kind in ("copy", "regroup") or self.mode == "return":
            self.check_return()
        else:
            self.refresh()
            note, self._note = self._note, ""
            self.lbl.setText(note + self.lbl.text())
        self._enable()
