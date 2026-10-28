"""Tab ĐỐI CHIẾU DANH SÁCH: so file Excel danh sách đảng viên (xuất từ hệ thống) với thư mục hồ sơ đang quản lý.
Khoá chính là số CCCD; người dùng tự chọn cột CCCD / Họ tên / Chi bộ. Có thao tác sửa (xác nhận + hoàn tác)."""
from __future__ import annotations

from ..paths import make_settings

import json
import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core import activity, compare as C
from .common import fmt, open_path, run_bg
from .styles import button
from .widgets import ElidedLabel, StatCard

GREEN, RED, AMBER = "#15803D", "#B91C1C", "#B45309"
KIND_COLOR = {C.K_MATCH: (GREEN, "#DCFCE7"), C.K_NAME: (AMBER, "#FEF9C3"), C.K_CHIBO: (AMBER, "#FEF9C3"),
              C.K_TYPO: (AMBER, "#FEF9C3"), C.K_NO_FOLDER: (RED, "#FEE2E2"), C.K_NOT_IN_LIST: (RED, "#FEE2E2")}
NONE = "— (không dùng) —"
ROLES = (("cccd", "🔑 Số CCCD (khoá so sánh)", "CCCD", "#FDE68A", "#FEF3C7"),
         ("name", "👤 Họ và tên", "HỌ TÊN", "#BFDBFE", "#DBEAFE"),
         ("chibo", "🏠 Chi bộ", "CHI BỘ", "#BBF7D0", "#DCFCE7"))


class ComparePanel(QWidget):
    changed = Signal()                     # đã đổi tên / chuyển / tạo thư mục → cửa sổ chính quét lại

    def __init__(self, report_provider, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.report_provider = report_provider    # hàm trả R.Report hiện hành (theo thiết lập tab Báo cáo)
        self.settings = make_settings()
        self.table: Optional[C.Table] = None
        self.cmp: Optional[C.Comparison] = None
        self.last_ops: List[C.Op] = []
        self.busy_check = lambda: False
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(8)

        # ---- file Excel + ghép cột
        g = QGroupBox("Danh sách hệ thống (file Excel .xlsx)")
        gl = QVBoxLayout(g)
        r1 = QHBoxLayout()
        r1.addWidget(button("📂 Chọn file Excel…", "primary", self.pick_file, size="sm"))
        self.lbl_file = ElidedLabel("Chưa chọn file – chọn file Excel danh sách đảng viên đã số hoá xuất từ hệ thống")
        self.lbl_file.setStyleSheet("color:#475569;")
        r1.addWidget(self.lbl_file, 1)
        r1.addWidget(QLabel("Sheet:"))
        self.cb_sheet = QComboBox()
        self.cb_sheet.setMinimumWidth(160)
        self.cb_sheet.currentIndexChanged.connect(lambda: self._reload(auto_header=True))
        r1.addWidget(self.cb_sheet)
        r1.addWidget(QLabel("Dòng tiêu đề:"))
        self.sp_head = QSpinBox()
        self.sp_head.setRange(1, 100)
        self.sp_head.setToolTip("Dòng chứa tên cột (app tự dò; sửa nếu sai)")
        self.sp_head.valueChanged.connect(lambda: self._reload(auto_header=False))
        r1.addWidget(self.sp_head)
        gl.addLayout(r1)
        r2 = QHBoxLayout()
        self.cb_cols: Dict[str, QComboBox] = {}
        for key, label in (("cccd", "🔑 Cột Số CCCD:"), ("name", "👤 Cột Họ và tên:"), ("chibo", "🏠 Cột Chi bộ:")):
            lb = QLabel(f"<b>{label}</b>" if key == "cccd" else label)
            if key == "cccd":
                lb.setToolTip("Số CCCD là khoá để so danh sách với thư mục – bắt buộc chọn đúng")
            r2.addWidget(lb)
            cb = QComboBox()
            cb.setMinimumWidth(190)
            cb.setMaxVisibleItems(20)
            cb.currentIndexChanged.connect(self._cols_changed)
            self.cb_cols[key] = cb
            r2.addWidget(cb, 1)
            r2.addSpacing(8)
        self.btn_run = button("🔗 ĐỐI CHIẾU", "success", self.run, size="lg",
                              tip="So danh sách Excel với thư mục hồ sơ đang quét (theo số CCCD)")
        r2.addWidget(self.btn_run)
        gl.addLayout(r2)
        hint = QLabel("💡 Bấm vào <b>tiêu đề cột</b> trong bảng dưới để gán: <span style='background:#FEF3C7'>"
                      "&nbsp;🔑 CCCD&nbsp;</span> · <span style='background:#DBEAFE'>&nbsp;👤 Họ tên&nbsp;</span> · "
                      "<span style='background:#DCFCE7'>&nbsp;🏠 Chi bộ&nbsp;</span>. So sánh dựa trên số CCCD; "
                      "họ tên và chi bộ chỉ để kiểm tra thêm.")
        hint.setObjectName("Hint")
        gl.addWidget(hint)
        self.preview = QTableWidget(0, 0)
        self.preview.setFixedHeight(190)
        self.preview.horizontalHeader().setStretchLastSection(True)
        self.preview.setWordWrap(False)
        self.preview.verticalHeader().setVisible(False)
        self.preview.horizontalHeader().setSectionsClickable(True)
        self.preview.horizontalHeader().sectionClicked.connect(self._header_menu)
        self.preview.horizontalHeader().setToolTip("Bấm vào tiêu đề để gán cột CCCD / Họ tên / Chi bộ")
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview.verticalHeader().setDefaultSectionSize(20)
        self.preview.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        gl.addWidget(self.preview)
        self.lbl_info = QLabel("Cần quét thư mục hồ sơ ở trên trước, sau đó chọn file Excel và bấm Đối chiếu.")
        self.lbl_info.setObjectName("Hint")
        self.lbl_info.setWordWrap(True)
        gl.addWidget(self.lbl_info)
        outer.addWidget(g)

        # ---- thẻ
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.cards: Dict[str, StatCard] = {}
        for i, (k, t, a) in enumerate((("all", "TRONG DANH SÁCH", "blue"), ("match", "KHỚP", "green"),
                                       ("fix", "CẦN SỬA", "amber"), ("nofolder", "CHƯA CÓ THƯ MỤC", "red"),
                                       ("notin", "NGOÀI DANH SÁCH", "violet"))):
            c = StatCard(k, t, a)
            c.clicked.connect(self._card_clicked)
            self.cards[k] = c
            grid.addWidget(c, 0, i)
            grid.setColumnStretch(i, 1)
        outer.addLayout(grid)

        # ---- lọc
        f = QHBoxLayout()
        f.addWidget(QLabel("Chi bộ:"))
        self.cb_chibo = QComboBox()
        self.cb_chibo.setMinimumWidth(260)
        self.cb_chibo.currentIndexChanged.connect(self.apply_filter)
        f.addWidget(self.cb_chibo)
        f.addSpacing(12)
        f.addWidget(QLabel("Kết quả:"))
        self.cb_kind = QComboBox()
        self.cb_kind.addItem("Tất cả", "")
        self.cb_kind.addItem("⚠ Cần sửa (lệch tên · khác chi bộ · nghi gõ nhầm)", "fix")
        for k in (C.K_MATCH, C.K_NAME, C.K_CHIBO, C.K_TYPO, C.K_NO_FOLDER, C.K_NOT_IN_LIST):
            self.cb_kind.addItem(k, k)
        self.cb_kind.addItem("Có ghi chú", "note")
        self.cb_kind.setMinimumWidth(260)
        self.cb_kind.currentIndexChanged.connect(self.apply_filter)
        f.addWidget(self.cb_kind)
        f.addSpacing(12)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("🔍 Tìm số CCCD / họ tên / thư mục…")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.textChanged.connect(self.apply_filter)
        f.addWidget(self.ed_search, 1)
        outer.addLayout(f)

        # ---- bảng kết quả
        self.tree = QTreeWidget()
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        cols = ["Kết quả", "Số CCCD", "Họ và tên (danh sách)", "Chi bộ (danh sách)", "Thư mục hồ sơ",
                "Chi bộ (thư mục)", "Hồ sơ 01–05", "Gợi ý xử lý", "Ghi chú"]
        self.tree.setHeaderLabels(cols)
        for i, w in enumerate((120, 110, 170, 190, 220, 180, 110, 260, 260)):
            self.tree.setColumnWidth(i, w)
        self.tree.itemDoubleClicked.connect(self._open_item)
        outer.addWidget(self.tree, 1)

        # ---- thao tác
        a = QHBoxLayout()
        self.btn_rename = button("✏ Đổi Tên Thư Mục Theo Danh Sách", "warning", self.do_rename, size="sm",
                                 tip="Đổi tên thư mục thành CCCD_HoVaTen theo danh sách (sửa cả số CCCD gõ nhầm)")
        self.btn_move = button("📦 Chuyển Về Đúng Chi Bộ", "warning", self.do_move, size="sm",
                               tip="Chuyển thư mục hồ sơ sang thư mục chi bộ ghi trong danh sách")
        self.btn_create = button("➕ Tạo thư mục còn thiếu", "primary", self.do_create, size="sm",
                                 tip="Tạo thư mục rỗng CCCD_HoVaTen cho người có trong danh sách nhưng chưa có thư mục")
        self.btn_undo = button("↶ Hoàn tác", "light", self.undo, size="sm")
        self.btn_export = button("📥 XUẤT EXCEL ĐỐI CHIẾU", "success", self.export, size="lg")
        for w in (self.btn_rename, self.btn_move, self.btn_create, self.btn_undo):
            a.addWidget(w)
        a.addStretch(1)
        a.addWidget(self.btn_export)
        outer.addLayout(a)
        self._update()
        self._pending_file = self.settings.value("compare_file", "") or ""   # đọc khi mở tab lần đầu (mở app nhanh)

    def showEvent(self, e):
        super().showEvent(e)
        p, self._pending_file = self._pending_file, ""
        if p and self.table is None and os.path.isfile(p):
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self.load_file(p, quiet=True)
            finally:
                QApplication.restoreOverrideCursor()

    # ------------------------------------------------------------------ đọc file Excel
    def pick_file(self):
        start = os.path.dirname(self.table.path) if self.table else ""
        p, _ = QFileDialog.getOpenFileName(self, "Chọn file Excel danh sách hệ thống", start, "Excel (*.xlsx *.xlsm)")
        if p:
            self.load_file(os.path.normpath(p))

    def load_file(self, path: str, quiet: bool = False):
        try:
            t = C.read_table(path)
        except C.CompareError as e:
            if not quiet:
                QMessageBox.warning(self, "Không đọc được file", str(e))
            return
        self._loading = True
        self.cb_sheet.clear()
        self.cb_sheet.addItems(t.sheets)
        self.cb_sheet.setCurrentText(t.sheet)
        self.sp_head.setValue(t.header_row)
        self._loading = False
        self.settings.setValue("compare_file", path)
        self._set_table(t)

    def _reload(self, auto_header: bool):
        if self._loading or not self.table:
            return
        try:
            t = C.read_table(self.table.path, self.cb_sheet.currentText(), None if auto_header else self.sp_head.value())
        except C.CompareError as e:
            QMessageBox.warning(self, "Không đọc được file", str(e))
            return
        if auto_header:
            self._loading = True
            self.sp_head.setValue(t.header_row)
            self._loading = False
        self._set_table(t)

    def _set_table(self, t: C.Table):
        self.table = t
        self.cmp = None
        self.lbl_file.set_full_text(f"📄 {os.path.basename(t.path)}  ·  {len(t.rows)} dòng dữ liệu  ·  {t.path}", t.path)
        guess = C.guess_columns(t.headers, t.rows)
        saved = {}
        try:
            saved = json.loads(self.settings.value("compare_cols", "{}") or "{}")
        except ValueError:
            pass
        self._loading = True
        for key, cb in self.cb_cols.items():
            cb.clear()
            if key == "chibo":
                cb.addItem(NONE, None)
            for i, h in enumerate(t.headers):
                ex = C.sample_value(t.rows, i)
                cb.addItem(f"{C._col_letter(i)} · {h}" + (f"   (vd: {ex})" if ex else ""), i)
            idx = t.headers.index(saved[key]) if saved.get(key) in t.headers else guess.get(key)
            cb.setCurrentIndex(cb.findData(idx) if idx is not None else 0)
        self._loading = False
        self._fill_preview()
        self._cols_changed()

    def _columns(self) -> Dict[str, Optional[int]]:
        return {k: cb.currentData() for k, cb in self.cb_cols.items()}

    def _cols_changed(self, *_):
        if self._loading or not self.table:
            return
        cols = self._columns()
        self.settings.setValue("compare_cols", json.dumps(
            {k: self.table.headers[v] for k, v in cols.items() if v is not None}, ensure_ascii=False))
        self._fill_preview()
        try:
            people, skipped = C.extract_people(self.table, cols)
            fixed = sum(1 for p in people if "thêm số 0" in p.note)
            bad = sum(1 for p in people if not p.cccd)
            ratio = C.cccd_ratio(self.table.rows, cols["cccd"])
            if ratio < 0.5:
                self.lbl_info.setText(f"<span style='color:{RED}'>⚠ Cột “{self.table.headers[cols['cccd']]}” chỉ có "
                                      f"{round(ratio * 100)}% ô là số CCCD – có thể chọn nhầm cột. Bấm vào tiêu đề "
                                      f"cột chứa số CCCD trong bảng dưới để gán lại.</span>")
                self._update()
                return
            self.lbl_info.setText(f"✔ Cột CCCD hợp lệ {round(ratio * 100)}% · đọc được <b>{len(people)}</b> người"
                                  + (f" · tự thêm số 0 đầu cho {fixed} CCCD" if fixed else "")
                                  + (f" · <span style='color:{RED}'>{bad} dòng CCCD không hợp lệ</span>" if bad else "")
                                  + (f" · bỏ qua {len(skipped)} dòng trống/lỗi" if skipped else "")
                                  + " – bấm <b>ĐỐI CHIẾU</b>.")
        except C.CompareError as e:
            self.lbl_info.setText(f"<span style='color:{RED}'>⚠ {e}</span>")
        self._update()

    def _fill_preview(self):
        t = self.table
        cols = self._columns()
        picked = {v: k for k, v in cols.items() if v is not None}
        role = {r[0]: r for r in ROLES}
        self.preview.clear()
        self.preview.setColumnCount(len(t.headers))
        self.preview.setRowCount(min(10, len(t.rows)))
        for i, h in enumerate(t.headers):
            hi = QTableWidgetItem(f"{C._col_letter(i)}\n{h}" if i not in picked
                                  else f"{role[picked[i]][2]} ✔\n{h}")
            if i in picked:
                hi.setBackground(QBrush(QColor(role[picked[i]][3])))
                f = hi.font()
                f.setBold(True)
                hi.setFont(f)
            self.preview.setHorizontalHeaderItem(i, hi)
        self.preview.setVerticalHeaderLabels([str(n) for n, _ in t.rows[:10]])
        for r, (_, vals) in enumerate(t.rows[:10]):
            for c, v in enumerate(vals):
                it = QTableWidgetItem("" if v is None else str(v))
                if c in picked:
                    it.setBackground(QBrush(QColor(role[picked[c]][4])))
                self.preview.setItem(r, c, it)
        for c in range(len(t.headers)):
            self.preview.setColumnWidth(c, 160 if c in picked else 100)

    def _header_menu(self, col: int):
        """Bấm tiêu đề cột trong bảng xem trước → chọn vai trò cho cột đó."""
        if not self.table:
            return
        m = QMenu(self)
        m.addSection(f"Cột {C._col_letter(col)}: {self.table.headers[col]}")
        cur = self._columns()
        for key, text, *_ in ROLES:
            a = m.addAction(("✔ " if cur.get(key) == col else "") + "Dùng làm cột " + text)
            a.setData(key)
        m.addSeparator()
        clear = m.addAction("✖ Không dùng cột Chi bộ")
        clear.setData("")
        clear.setVisible(cur.get("chibo") == col)
        act = m.exec(QCursor.pos())
        if act is None or act.data() is None:
            return
        self.assign_column(act.data(), col)

    def assign_column(self, key: str, col: int):
        """Gán cột col cho vai trò key ('' = bỏ gán chi bộ). Vai trò khác đang dùng cột này đổi sang cột cũ của key."""
        self._loading = True
        old = self.cb_cols[key].currentData() if key else None
        for k, cb in self.cb_cols.items():
            if cb.currentData() == col and k != key:
                target = old if old is not None else None
                if target is None and k != "chibo":
                    continue                         # CCCD / Họ tên không để trống
                cb.setCurrentIndex(cb.findData(target))
        if key:
            self.cb_cols[key].setCurrentIndex(self.cb_cols[key].findData(col))
        self._loading = False
        self._cols_changed()

    # ------------------------------------------------------------------ đối chiếu
    def refresh(self):
        """Gọi lại sau mỗi lần quét: nếu đã đối chiếu thì làm lại với dữ liệu mới."""
        if self.report_provider() is None:
            self.cmp = None
            self._fill_chibo()
            self.apply_filter()
            self._update()
        elif self.cmp is not None and self.table is not None:
            self.run(quiet=True)
        else:
            self._update()

    def run(self, quiet: bool = False):
        rep = self.report_provider()
        if not rep:
            if not quiet:
                QMessageBox.information(self, "Chưa có dữ liệu", "Hãy chọn thư mục Hồ sơ số hóa ở trên và bấm Quét trước.")
            return
        if not self.table:
            if not quiet:
                QMessageBox.information(self, "Chưa chọn file", "Hãy chọn file Excel danh sách hệ thống.")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.cmp = C.compare(self.table, self._columns(), rep)
        except C.CompareError as e:
            self.cmp = None
            if not quiet:
                QMessageBox.warning(self, "Không đối chiếu được", str(e))
        finally:
            QApplication.restoreOverrideCursor()
        self._fill_chibo()
        self.apply_filter()
        self._update()
        if self.cmp and not quiet:
            activity.log("Đối chiếu danh sách", f"{os.path.basename(self.table.path)}: {len(self.cmp.people)} người · "
                                               f"khớp {self.cmp.count(C.K_MATCH)} · chưa có thư mục "
                                               f"{self.cmp.count(C.K_NO_FOLDER)} · ngoài danh sách "
                                               f"{self.cmp.count(C.K_NOT_IN_LIST)}")

    def _fill_chibo(self):
        cur = self.cb_chibo.currentData()
        self.cb_chibo.blockSignals(True)
        self.cb_chibo.clear()
        self.cb_chibo.addItem("Tất cả chi bộ", "")
        if self.cmp:
            for g in C.summary_by_chibo(self.cmp):
                self.cb_chibo.addItem(f"{g['chibo']}  ({g['excel']} người · khớp {g['match']})", g["chibo"])
        self.cb_chibo.setCurrentIndex(max(0, self.cb_chibo.findData(cur)))
        self.cb_chibo.blockSignals(False)

    def _group_of(self, r: C.MatchRow) -> str:
        if r.person:
            return r.person.chibo or "(không ghi chi bộ)"
        return f"(chỉ có thư mục) {r.dossier.chibo}"

    def _match(self, r: C.MatchRow) -> bool:
        cb = self.cb_chibo.currentData()
        k = self.cb_kind.currentData() or ""
        q = self.ed_search.text().strip().lower()
        if cb and self._group_of(r) != cb:
            return False
        if k == "fix" and r.kind not in C.NEED_FIX:
            return False
        if k == "note" and not r.notes:
            return False
        if k and k not in ("fix", "note") and r.kind != k:
            return False
        if q:
            hay = " ".join(x for x in ((r.person.cccd, r.person.name.lower(), C.name_key(r.person.name)) if r.person else ())
                           + ((r.dossier.folder.lower(),) if r.dossier else ()))
            if q not in hay and C.name_key(q) not in hay:
                return False
        return True

    def apply_filter(self, *_):
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        bold = QFont()
        bold.setBold(True)
        if self.cmp:
            for r in self.cmp.rows:
                if not self._match(r):
                    continue
                p, d = r.person, r.dossier
                hs = ""
                if d:
                    hs = "Đủ" if d.complete else "Thiếu " + ", ".join(d.missing)
                it = QTreeWidgetItem([r.kind, (p.cccd or p.cccd_raw) if p else C._folder_cccd(d),
                                      p.name if p else "", p.chibo if p else "", d.folder if d else "",
                                      d.chibo if d else "", hs, r.suggestion, "; ".join(r.notes)])
                fg, bg = KIND_COLOR[r.kind]
                it.setForeground(0, QBrush(QColor(fg)))
                it.setBackground(0, QBrush(QColor(bg)))
                it.setFont(0, bold)
                if d:
                    it.setForeground(6, QBrush(QColor(GREEN if d.complete else RED)))
                    it.setToolTip(4, d.path)
                if r.notes:
                    it.setForeground(8, QBrush(QColor(AMBER)))
                    it.setToolTip(8, "\n".join(r.notes))
                it.setToolTip(7, r.suggestion)
                it.setData(0, Qt.UserRole, r)
                self.tree.addTopLevelItem(it)
        self.tree.setUpdatesEnabled(True)

    def _open_item(self, item, col):
        r = item.data(0, Qt.UserRole)
        if r and r.dossier:
            open_path(r.dossier.path)

    def _card_clicked(self, key: str):
        target = {"all": "", "match": C.K_MATCH, "fix": "fix", "nofolder": C.K_NO_FOLDER,
                  "notin": C.K_NOT_IN_LIST}[key]
        self.cb_kind.setCurrentIndex(self.cb_kind.findData(target))

    def _update(self):
        cmp = self.cmp
        if cmp:
            n_folder = sum(1 for r in cmp.rows if r.person and r.dossier)
            self.cards["all"].set_data(fmt(len(cmp.people)), f"có thư mục: {n_folder} · thư mục quét: "
                                                            f"{len(cmp.report.dossiers)}")
            self.cards["match"].set_data(fmt(cmp.count(C.K_MATCH)),
                                         f"{round(cmp.count(C.K_MATCH) * 100 / max(1, len(cmp.people)))}% danh sách")
            self.cards["fix"].set_data(fmt(sum(cmp.count(k) for k in C.NEED_FIX)),
                                       f"lệch tên {cmp.count(C.K_NAME)} · khác chi bộ {cmp.count(C.K_CHIBO)} · "
                                       f"gõ nhầm {cmp.count(C.K_TYPO)}")
            self.cards["nofolder"].set_data(fmt(cmp.count(C.K_NO_FOLDER)), "có trong danh sách, chưa có thư mục")
            self.cards["notin"].set_data(fmt(cmp.count(C.K_NOT_IN_LIST)), "có thư mục, không có trong danh sách")
            nr, nm, nc = len(C.plan_renames(cmp)), len(C.plan_moves(cmp)), len(C.plan_creates(cmp))
        else:
            for c in self.cards.values():
                c.set_data("0", "—")
            nr = nm = nc = 0
        self.btn_run.setEnabled(self.table is not None)
        self.btn_rename.setEnabled(nr > 0)
        self.btn_rename.setText(f"✏ Đổi Tên Thư Mục Theo Danh Sách ({nr})" if nr else "✏ Đổi Tên Thư Mục Theo Danh Sách")
        self.btn_move.setEnabled(nm > 0)
        self.btn_move.setText(f"📦 Chuyển Về Đúng Chi Bộ ({nm})" if nm else "📦 Chuyển Về Đúng Chi Bộ")
        self.btn_create.setEnabled(nc > 0)
        self.btn_create.setText(f"➕ Tạo thư mục còn thiếu ({nc})" if nc else "➕ Tạo thư mục còn thiếu")
        self.btn_undo.setEnabled(bool(self.last_ops))
        self.btn_export.setEnabled(cmp is not None)

    # ------------------------------------------------------------------ thao tác
    def _confirm(self, title: str, lines: List[str], tail: str) -> bool:
        body = "\n".join(lines[:25]) + (f"\n… và {len(lines) - 25} mục khác" if len(lines) > 25 else "")
        return QMessageBox.question(self, title, f"{body}\n\n{tail}\nCó thể hoàn tác bằng nút “Hoàn tác”.") == \
            QMessageBox.Yes

    def _apply(self, title: str, ops_fn):
        from .preview import release_document
        release_document()
        ops = ops_fn()
        self.last_ops += [o for o in ops if o.ok]
        for o in ops:
            activity.log(title if o.ok else title + " lỗi",
                         f"{os.path.basename(o.src) or ''} → {o.dst}" + ("" if o.ok else f" ({o.message})"))
        bad = [o for o in ops if not o.ok]
        msg = f"✔ Xong {len(ops) - len(bad)}/{len(ops)} mục."
        if bad:
            msg += "\n\nKhông làm được:\n" + "\n".join(f"• {os.path.basename(o.src or o.dst)}: {o.message}"
                                                     for o in bad[:10])
        QMessageBox.information(self, title, msg)
        self._update()
        self.changed.emit()

    def do_rename(self):
        if not self.cmp or self.busy_check():
            return
        plan = C.plan_renames(self.cmp)
        if plan and self._confirm("Đổi tên thư mục theo danh sách",
                                  [f"• {os.path.basename(s)}  →  {n}" for s, n in plan],
                                  f"Đổi tên {len(plan)} thư mục?"):
            self._apply("Đổi tên thư mục theo danh sách", lambda: C.apply_ops(renames=plan))

    def do_move(self):
        if not self.cmp or self.busy_check():
            return
        plan = C.plan_moves(self.cmp)
        if plan and self._confirm("Chuyển về đúng chi bộ",
                                  [f"• {os.path.basename(s)}: {os.path.basename(os.path.dirname(s))}  →  "
                                   f"{os.path.basename(os.path.dirname(d))}" for s, d in plan],
                                  f"Chuyển {len(plan)} thư mục?"):
            self._apply("Chuyển chi bộ", lambda: C.apply_ops(moves=plan))

    def do_create(self):
        if not self.cmp or self.busy_check():
            return
        plan = C.plan_creates(self.cmp)
        if plan and self._confirm("Tạo thư mục còn thiếu",
                                  [f"• {os.path.basename(os.path.dirname(p))}\\{os.path.basename(p)}" for p in plan],
                                  f"Tạo {len(plan)} thư mục rỗng?"):
            self._apply("Tạo thư mục hồ sơ", lambda: C.apply_ops(creates=plan))

    def undo(self):
        if not self.last_ops or self.busy_check():
            return
        from .preview import release_document
        release_document()
        res = C.undo_ops(self.last_ops)
        ok = sum(o.ok for o in res)
        activity.log("Hoàn tác đối chiếu", f"{ok}/{len(res)} thao tác")
        kept = [o for o in res if not o.ok]
        QMessageBox.information(self, "Hoàn tác", f"↶ Đã hoàn tác {ok}/{len(res)} thao tác."
                                + (f"\n{len(kept)} mục giữ lại (thư mục đã có file hoặc bị đổi)." if kept else ""))
        self.last_ops = []
        self._update()
        self.changed.emit()

    def export(self):
        if not self.cmp:
            return
        rep = self.cmp.report
        default = os.path.join(rep.root, f"Doi_chieu_danh_sach_{rep.created:%Y%m%d_%H%M}.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "Lưu báo cáo đối chiếu", default, "Excel (*.xlsx)")
        if not path:
            return
        from ..core.compare_excel import export_compare
        cmp, dst = self.cmp, os.path.normpath(path)
        run_bg(self, self.btn_export, "⏳ Đang xuất Excel…", lambda: export_compare(cmp, dst), self._exported)

    def _exported(self, out, err):
        if isinstance(err, PermissionError):
            QMessageBox.warning(self, "Không lưu được", "File đang mở trong Excel – hãy đóng file rồi thử lại.")
            return
        if err is not None:
            QMessageBox.warning(self, "Không lưu được", f"❌ {err}")
            return
        activity.log("Xuất đối chiếu", os.path.basename(out))
        if QMessageBox.question(self, "Đã xuất", f"🎉 Đã lưu:\n{out}\n\nMở file ngay?") == QMessageBox.Yes:
            open_path(out)
