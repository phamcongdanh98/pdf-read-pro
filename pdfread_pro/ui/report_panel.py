"""Tab BÁO CÁO HỒ SƠ: kiểm tra Hồ sơ số hóa › Chi bộ › CCCD_HoVaTen › file 01–05.
Mỗi hồ sơ chỉ có 2 kết quả: ĐỦ (có đủ file bắt buộc) hoặc THIẾU (ghi rõ thiếu gì); vấn đề khác ghi ở Ghi chú.
Xem theo chi bộ, lọc Đủ / Thiếu / Thiếu từng mục, chuẩn hoá tên thư mục, xuất Excel."""
from __future__ import annotations

import html
import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QSplitter, QTextBrowser, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core import activity, report as R
from ..core.models import ScanResult
from .common import fmt, open_path, run_bg
from .styles import button
from .widgets import StatCard

GREEN, RED, AMBER = "#15803D", "#B91C1C", "#B45309"
BG_OK, BG_NO, BG_NOTE = "#DCFCE7", "#FEE2E2", "#FEF9C3"
ROLE = Qt.UserRole


class ReportPanel(QWidget):
    renamed = Signal()                       # đã đổi tên thư mục → cửa sổ chính quét lại

    def __init__(self, rules_provider, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.rules_provider = rules_provider     # hàm trả bộ quy tắc 1361 hiện hành
        self.result: Optional[ScanResult] = None
        self.rep: Optional[R.Report] = None
        self.last_renames: List[R.FolderRename] = []
        self.busy_check = lambda: False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(8)

        # ---- thiết lập + hành động
        g = QGroupBox("Báo cáo hồ sơ số hoá")
        gl = QVBoxLayout(g)
        r = QHBoxLayout()
        r.addWidget(QLabel("File bắt buộc (mã):"))
        self.ed_req = QLineEdit("01-05")
        self.ed_req.setFixedWidth(150)
        self.ed_req.setToolTip("Mã file bắt buộc trong mỗi hồ sơ, theo bộ quy tắc 1361. VD: 01-05 hoặc 01, 02, 05")
        self.ed_req.editingFinished.connect(self.refresh)
        r.addWidget(self.ed_req)
        r.addSpacing(16)
        r.addWidget(QLabel("Tính file:"))
        self.cb_sign = QComboBox()
        for k in (R.SIGN_ALL, R.SIGN_ONLY, R.SIGN_NONE):
            self.cb_sign.addItem({R.SIGN_ALL: "Cả 2 (đã ký và chưa ký)", R.SIGN_ONLY: "✍ Chỉ file đã ký (.signed)",
                                  R.SIGN_NONE: "Chỉ file chưa ký (không .signed)"}[k], k)
        self.cb_sign.setToolTip("Khi ký số thường có 2 bản: X.pdf (chưa ký) và X.signed.pdf (đã ký).\n"
                                "• Cả 2: có bản nào cũng tính là Có\n"
                                "• Chỉ file đã ký: mục chỉ có bản chưa ký vẫn tính Thiếu (ghi “mới có bản chưa ký”)\n"
                                "• Chỉ file chưa ký: chỉ tính các file không có .signed")
        self.cb_sign.currentIndexChanged.connect(self.refresh)
        r.addWidget(self.cb_sign)
        r.addStretch(1)
        self.btn_fix = button("✏ Chuẩn hoá tên thư mục", "warning", self.fix_folders, size="sm",
                              tip="Đổi tên các thư mục hồ sơ sai chuẩn theo tên gợi ý (VD 056123456789_TranVanThai)")
        self.btn_undo = button("↶ Hoàn tác đổi tên", "light", self.undo_folders, size="sm")
        self.btn_undo.setEnabled(False)
        self.ck_adv = QCheckBox("Kèm báo cáo nâng cao")
        self.ck_adv.setToolTip("Thêm các trang: Chi tiết từng file · Thống kê theo loại giấy tờ · Vấn đề cần xử lý")
        self.btn_excel = button("📥 XUẤT BÁO CÁO EXCEL", "success", self.export, size="lg",
                                tip="Tổng hợp chi bộ · Danh sách toàn bộ · Danh sách thiếu · Giải thích")
        for w in (self.btn_fix, self.btn_undo, self.ck_adv, self.btn_excel):
            r.addWidget(w)
        gl.addLayout(r)
        self.lbl_req = QLabel("")
        self.lbl_req.setObjectName("Hint")
        self.lbl_req.setWordWrap(True)
        gl.addWidget(self.lbl_req)
        self.lbl_struct = QLabel("Cấu trúc chuẩn: <b>Hồ sơ số hóa</b> › <b>Chi bộ</b> › <b>CCCD_HoVaTen</b> "
                                 "(VD 056123456789_TranVanThai) › các file PDF đặt tên theo bộ quy tắc 1361. "
                                 "<b>Đủ</b> = có đủ file bắt buộc · <b>Thiếu</b> = còn thiếu ít nhất 1 file.")
        self.lbl_struct.setObjectName("Hint")
        self.lbl_struct.setWordWrap(True)
        gl.addWidget(self.lbl_struct)
        outer.addWidget(g)

        # ---- thẻ thống kê (bấm để lọc)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.cards: Dict[str, StatCard] = {}
        for i, (k, t, a) in enumerate((("all", "TỔNG HỒ SƠ", "blue"), ("ok", "ĐỦ HỒ SƠ", "green"),
                                       ("miss", "THIẾU HỒ SƠ", "red"), ("note", "CÓ GHI CHÚ (CẦN XEM LẠI)", "amber"))):
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
        f.addWidget(QLabel("Hiển thị:"))
        self.cb_status = QComboBox()
        self.cb_status.setMinimumWidth(280)
        self.cb_status.currentIndexChanged.connect(self.apply_filter)
        f.addWidget(self.cb_status)
        f.addSpacing(12)
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("🔍 Tìm số CCCD / họ tên…")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.textChanged.connect(self.apply_filter)
        f.addWidget(self.ed_search, 1)
        outer.addLayout(f)

        # ---- danh sách + chi tiết
        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.itemSelectionChanged.connect(self.show_detail)
        self.tree.itemDoubleClicked.connect(self._open_item)
        tb = QGroupBox("Danh sách người theo chi bộ")
        tl = QVBoxLayout(tb)
        tl.setContentsMargins(6, 6, 6, 6)
        tl.addWidget(self.tree)
        split.addWidget(tb)
        db = QGroupBox("Chi tiết hồ sơ")
        dl = QVBoxLayout(db)
        dl.setContentsMargins(8, 8, 8, 8)
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        self.detail.anchorClicked.connect(lambda u: open_path(u.toLocalFile() or u.toString()))
        dl.addWidget(self.detail, 1)
        self.btn_open = button("📂 Mở Thư Mục Hồ Sơ", "primary", self._open_selected, size="sm")
        dl.addWidget(self.btn_open)
        split.addWidget(db)
        split.setStretchFactor(0, 68)
        split.setStretchFactor(1, 32)
        split.setSizes([920, 430])
        split.setChildrenCollapsible(False)
        db.setMinimumWidth(320)
        outer.addWidget(split, 1)
        self._fill_status(R.DEFAULT_REQUIRED)
        self._setup_columns(R.DEFAULT_REQUIRED)
        self._update_buttons()
        self.detail.setHtml(self._empty_html())

    # ------------------------------------------------------------------ dữ liệu
    def set_result(self, result: Optional[ScanResult]):
        self.result = result
        self.refresh()

    def _required(self):
        try:
            req = R.parse_required(self.ed_req.text())
            self.ed_req.setStyleSheet("")
            return req
        except ValueError as e:
            self.ed_req.setStyleSheet("border:1px solid #DC2626;")
            self.lbl_req.setText(f"<span style='color:#B91C1C'>⚠ {e}</span>")
            return None

    def refresh(self):
        req = self._required()
        if req is None:
            return
        rules = self.rules_provider()
        self.lbl_req.setText("File bắt buộc: " + " · ".join(
            f"<b>{c}</b> {html.escape(R.doc_title(c, rules))}" for c in req[:8]) + (" …" if len(req) > 8 else ""))
        self._fill_status(req)
        self._setup_columns(req)
        self.rep = R.build_report(self.result, rules, req, self.cb_sign.currentData()) if self.result else None
        self._fill_chibo()
        self._update_cards()
        self.apply_filter()
        self._update_buttons()

    def _fill_status(self, req):
        cur = self.cb_status.currentData()
        self.cb_status.blockSignals(True)
        self.cb_status.clear()
        self.cb_status.addItem("Tất cả", "")
        self.cb_status.addItem("✅ Đủ hồ sơ", "ok")
        self.cb_status.addItem("❌ Thiếu hồ sơ", "miss")
        rules = self.rules_provider()
        for c in req:
            self.cb_status.addItem(f"    Thiếu {c} – {R.doc_title(c, rules)}", "miss:" + c)
        self.cb_status.addItem("⚠ Có ghi chú (cần xem lại)", "note")
        i = self.cb_status.findData(cur)
        self.cb_status.setCurrentIndex(max(0, i))
        self.cb_status.blockSignals(False)

    def _setup_columns(self, req):
        rules = self.rules_provider()
        cols = ["Chi bộ / Họ và tên", "Số CCCD"] + list(req) + ["Kết quả", "Còn thiếu", "Ghi chú"]
        self.tree.setColumnCount(len(cols))
        self.tree.setHeaderLabels(cols)
        self.tree.header().setStretchLastSection(True)
        widths = [260, 115] + [52] * len(req) + [70, 230, 200]
        hi = self.tree.headerItem()
        for i, w in enumerate(widths):
            self.tree.setColumnWidth(i, w)
            if 2 <= i < 2 + len(req):
                hi.setTextAlignment(i, Qt.AlignCenter)
                hi.setToolTip(i, f"{req[i - 2]} – {R.doc_title(req[i - 2], rules)}")
        hi.setTextAlignment(2 + len(req), Qt.AlignCenter)

    def _fill_chibo(self):
        cur = self.cb_chibo.currentData()
        self.cb_chibo.blockSignals(True)
        self.cb_chibo.clear()
        self.cb_chibo.addItem("Tất cả chi bộ", "")
        if self.rep:
            for c in self.rep.chibos:
                ds = [d for d in self.rep.dossiers if d.chibo == c]
                ok = sum(1 for d in ds if d.complete)
                self.cb_chibo.addItem(f"{c}  (đủ {ok}/{len(ds)})", c)
        i = self.cb_chibo.findData(cur)
        self.cb_chibo.setCurrentIndex(max(0, i))
        self.cb_chibo.blockSignals(False)

    def _update_cards(self):
        rep = self.rep
        if not rep:
            for c in self.cards.values():
                c.set_data("0", "—")
            return
        total = len(rep.dossiers)
        ok = sum(1 for d in rep.dossiers if d.complete)
        miss = {c: sum(1 for d in rep.dossiers if c in d.missing) for c in rep.required}
        noted = sum(1 for d in rep.dossiers if d.notes)
        self.cards["all"].set_data(fmt(total), f"{len(rep.chibos)} chi bộ · {fmt(sum(d.pages for d in rep.dossiers))} trang")
        self.cards["ok"].set_data(fmt(ok), f"{round(ok * 100 / total) if total else 0}% có đủ file bắt buộc")
        detail = " · ".join(f"thiếu {c}: {n}" for c, n in miss.items() if n) or "không ai thiếu"
        self.cards["miss"].set_data(fmt(total - ok), detail, "Số người thiếu theo từng mục:\n" + "\n".join(
            f"{c} – {R.doc_title(c, rep.rules)}: {n}" for c, n in miss.items()))
        self.cards["note"].set_data(fmt(noted), "sai tên, trùng CCCD, file lỗi…"
                                    + (f" · {len(rep.stray)} file lạc chỗ" if rep.stray else ""))

    def _card_clicked(self, key: str):
        target = {"all": "", "ok": "ok", "miss": "miss", "note": "note"}[key]
        self.cb_status.setCurrentIndex(self.cb_status.findData(target))

    # ------------------------------------------------------------------ danh sách
    def _match(self, d: R.Dossier) -> bool:
        cb = self.cb_chibo.currentData()
        st = self.cb_status.currentData() or ""
        q = self.ed_search.text().strip().lower()
        if cb and d.chibo != cb:
            return False
        if st == "ok" and not d.complete:
            return False
        if st == "miss" and d.complete:
            return False
        if st.startswith("miss:") and st[5:] not in d.missing:
            return False
        if st == "note" and not d.notes:
            return False
        if q and q not in d.folder.lower() and q not in d.name.lower() and q not in d.cccd:
            return False
        return True

    def apply_filter(self, *_):
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        rep = self.rep
        if rep:
            req = list(rep.required)
            c_res = 2 + len(req)
            groups: Dict[str, QTreeWidgetItem] = {}
            bold = QFont()
            bold.setBold(True)
            for d in sorted(rep.dossiers, key=lambda x: (rep.chibos.index(x.chibo) if x.chibo in rep.chibos else 9999,
                                                          (x.name.split() or ["~"])[-1].lower(), x.name.lower())):
                if not self._match(d):
                    continue
                g = groups.get(d.chibo)
                if g is None:
                    ds = [x for x in rep.dossiers if x.chibo == d.chibo]
                    ok = sum(1 for x in ds if x.complete)
                    g = QTreeWidgetItem([f"🏛 {d.chibo}", f"{len(ds)} hồ sơ"])
                    g.setText(c_res, f"Đủ {ok}/{len(ds)}")
                    g.setText(c_res + 1, "" if ok == len(ds) else f"{len(ds) - ok} người còn thiếu")
                    for col in (0, c_res, c_res + 1):
                        g.setFont(col, bold)
                    g.setForeground(c_res, QBrush(QColor(GREEN if ok == len(ds) else AMBER)))
                    g.setForeground(c_res + 1, QBrush(QColor(RED)))
                    g.setData(0, ROLE, ("chibo", d.chibo))
                    self.tree.addTopLevelItem(g)
                    groups[d.chibo] = g
                marks = ["Có" if d.have.get(c) else "Thiếu" for c in req]
                missing = ", ".join(c + R.missing_hint(d, c, rep.sign_filter) for c in d.missing)
                it = QTreeWidgetItem([d.name or d.folder, d.cccd] + marks + [d.result, missing, "; ".join(d.notes)])
                it.setData(0, ROLE, ("dossier", d))
                it.setToolTip(0, f"{d.folder}\n{d.path}")
                it.setToolTip(c_res + 1, R.doc_title(d.missing[0], rep.rules) if len(d.missing) == 1 else
                              "\n".join(f"{c} – {R.doc_title(c, rep.rules)}" for c in d.missing))
                it.setToolTip(c_res + 2, "\n".join(d.notes))
                for j, m in enumerate(marks):
                    col = 2 + j
                    it.setTextAlignment(col, Qt.AlignCenter)
                    if m == "Thiếu":
                        it.setForeground(col, QBrush(QColor(RED)))
                        it.setBackground(col, QBrush(QColor(BG_NO)))
                        it.setFont(col, bold)
                    else:
                        it.setForeground(col, QBrush(QColor(GREEN)))
                it.setTextAlignment(c_res, Qt.AlignCenter)
                it.setFont(c_res, bold)
                it.setForeground(c_res, QBrush(QColor(GREEN if d.complete else RED)))
                it.setBackground(c_res, QBrush(QColor(BG_OK if d.complete else BG_NO)))
                it.setForeground(c_res + 1, QBrush(QColor(RED)))
                if d.notes:
                    it.setForeground(c_res + 2, QBrush(QColor(AMBER)))
                    it.setBackground(c_res + 2, QBrush(QColor(BG_NOTE)))
                g.addChild(it)
            st = self.cb_status.currentData() or ""
            if rep.stray and not self.cb_chibo.currentData() and st in ("", "note"):
                g = QTreeWidgetItem([f"📄 File nằm ngoài thư mục hồ sơ ({len(rep.stray)})"])
                g.setFont(0, bold)
                g.setForeground(0, QBrush(QColor(AMBER)))
                g.setData(0, ROLE, ("stray", None))
                for s in rep.stray:
                    c = QTreeWidgetItem([s.rel])
                    c.setToolTip(0, s.note)
                    c.setData(0, ROLE, ("file", s))
                    g.addChild(c)
                self.tree.addTopLevelItem(g)
        self.tree.expandAll()
        self.tree.setUpdatesEnabled(True)
        if not rep:
            self.detail.setHtml(self._empty_html())

    def _selected(self):
        it = self.tree.currentItem()
        return it.data(0, ROLE) if it else None

    # ------------------------------------------------------------------ chi tiết
    def _empty_html(self) -> str:
        return ("<div style='color:#64748B;padding:20px'>Chọn thư mục <b>Hồ sơ số hóa</b> (hoặc 1 chi bộ) ở ô "
                "<b>Thư mục chứa file</b> rồi bấm <b>Quét</b>.<br><br>Mỗi hồ sơ là 1 thư mục tên "
                "<b>056123456789_TranVanThai</b>, bên trong có đủ file "
                f"<b>{html.escape(self.ed_req.text())}</b> theo bộ quy tắc 1361.</div>")

    def show_detail(self):
        sel = self._selected()
        self.btn_open.setEnabled(bool(sel and sel[0] in ("dossier", "file")))
        if not sel or not self.rep:
            return
        kind, obj = sel
        if kind == "dossier":
            self.detail.setHtml(self._dossier_html(obj))
        elif kind == "file":
            self.detail.setHtml(f"<h3>📄 {html.escape(os.path.basename(obj.path))}</h3>"
                                f"<p style='color:{AMBER}'>⚠ {html.escape(obj.note)}</p><p>{html.escape(obj.path)}</p>")
        elif kind == "chibo":
            ds = [d for d in self.rep.dossiers if d.chibo == obj]
            ok = sum(1 for d in ds if d.complete)
            rows = "".join(f"<tr><td>Thiếu {c} – {html.escape(R.doc_title(c, self.rep.rules))}</td>"
                           f"<td align=right style='color:{RED if n else GREEN}'><b>{n}</b></td></tr>"
                           for c, n in ((c, sum(1 for d in ds if c in d.missing)) for c in self.rep.required))
            lack = "".join(f"<li>{html.escape(d.name)} ({d.cccd}) – thiếu {', '.join(d.missing)}</li>"
                           for d in ds if not d.complete)
            self.detail.setHtml(f"<h3 style='margin:0'>🏛 {html.escape(obj)}</h3>"
                                f"<p>Tổng: <b>{len(ds)}</b> hồ sơ · <span style='color:{GREEN}'><b>Đủ {ok}</b></span> · "
                                f"<span style='color:{RED}'><b>Thiếu {len(ds) - ok}</b></span></p>"
                                f"<table cellpadding=3>{rows}</table>"
                                + (f"<p style='margin:8px 0 2px'><b>Người còn thiếu</b></p><ul style='margin:0'>{lack}</ul>"
                                   if lack else f"<p style='color:{GREEN}'><b>🎉 Tất cả hồ sơ đều đủ.</b></p>"))

    def _dossier_html(self, d: R.Dossier) -> str:
        e = html.escape
        rules = self.rep.rules
        col, bg = (GREEN, BG_OK) if d.complete else (RED, BG_NO)
        h = [f"<h3 style='margin:0'>👤 {e(d.name or d.folder)}</h3>",
             f"<p style='margin:4px 0'>Số CCCD: <b>{e(d.cccd) or '(chưa rõ)'}</b> · Chi bộ: <b>{e(d.chibo)}</b></p>",
             f"<p style='margin:4px 0'>Kết quả: <span style='background:{bg};color:{col};font-weight:bold'>"
             f"&nbsp;{d.result.upper()}&nbsp;</span></p>"]
        if d.missing:
            h.append(f"<p style='margin:4px 0;color:{RED}'><b>Còn thiếu:</b> "
                     + "; ".join(f"{c} – {e(R.doc_title(c, rules))}{R.missing_hint(d, c, self.rep.sign_filter)}"
                                 for c in d.missing) + "</p>")
        h.append("<p style='margin:8px 0 2px'><b>File bắt buộc</b></p><table cellpadding=2>")
        for c in self.rep.required:
            fs = d.have.get(c, [])
            title = e(R.doc_title(c, rules))
            if not fs:
                h.append(f"<tr><td style='color:{RED}'><b>Thiếu</b></td><td>{c} – {title}</td></tr>")
            for f in fs:
                url = "file:///" + f.fi.path.replace("\\", "/")
                pages = f" · {f.fi.pages} trang" if f.fi.pages else ""
                warn = "" if f.name_ok else f"<br><span style='color:{AMBER}'>đặt sai tên → {e(rules.get(c, ''))}.pdf</span>"
                h.append(f"<tr><td style='color:{GREEN}'><b>Có</b></td><td>{c} – {title}: "
                         f"<a href='{url}'>{e(f.fi.name)}</a><span style='color:#64748B'>{pages}</span>{warn}</td></tr>")
        h.append("</table>")
        if d.excluded:
            h.append(f"<p style='margin:8px 0 2px;color:#64748B'><b>Không tính ({len(d.excluded)} file – "
                     f"{e(R.SIGN_LABELS[self.rep.sign_filter].lower())})</b>: "
                     + ", ".join(e(x.fi.name) for x in d.excluded[:8]) + (" …" if len(d.excluded) > 8 else "") + "</p>")
        extra = [f for f in d.files if not f.required]
        if extra:
            h.append(f"<p style='margin:8px 0 2px'><b>Giấy tờ khác ({len(extra)})</b></p><ul style='margin:0'>")
            for f in extra:
                url = "file:///" + f.fi.path.replace("\\", "/")
                h.append(f"<li><a href='{url}'>{e(f.fi.name)}</a></li>")
            h.append("</ul>")
        notes = [i for i in d.issues if i.text in d.notes]
        if notes:
            h.append("<p style='margin:8px 0 2px'><b>Ghi chú (cần xem lại)</b></p><ul style='margin:0'>")
            for i in notes:
                h.append(f"<li><span style='color:{AMBER}'>{e(i.text)}</span>"
                         + (f"<br><span style='color:#475569'>→ {e(i.fix)}</span>" if i.fix else "") + "</li>")
            h.append("</ul>")
        h.append(f"<p style='margin:8px 0 0;color:#64748B'>Thư mục: {e(d.folder)}</p>")
        return "".join(h)

    def _open_selected(self):
        sel = self._selected()
        if sel and sel[0] == "dossier":
            open_path(sel[1].path)
        elif sel and sel[0] == "file":
            open_path(os.path.dirname(sel[1].path))

    def _open_item(self, item, col):
        sel = item.data(0, ROLE)
        if sel and sel[0] in ("dossier", "file"):
            open_path(sel[1].path)

    # ------------------------------------------------------------------ hành động
    def _update_buttons(self):
        has = bool(self.rep and (self.rep.dossiers or self.rep.stray))
        self.btn_excel.setEnabled(has)
        n = sum(1 for d in self.rep.dossiers if d.suggestion) if self.rep else 0
        self.btn_fix.setEnabled(n > 0)
        self.btn_fix.setText(f"✏ Chuẩn hoá tên thư mục ({n})" if n else "✏ Chuẩn hoá tên thư mục")
        self.btn_open.setEnabled(False)

    def export(self):
        if not self.rep:
            return
        base = os.path.basename(self.rep.root.rstrip("\\/")) or "Ho_so"
        default = os.path.join(self.rep.root, f"Bao_cao_{base}_{self.rep.created:%Y%m%d_%H%M}.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "Lưu báo cáo Excel", default, "Excel (*.xlsx)")
        if not path:
            return
        from ..core.report_excel import export_excel
        rep, dst, adv = self.rep, os.path.normpath(path), self.ck_adv.isChecked()
        # ghi Excel hàng nghìn dòng ở luồng phụ → giao diện không đứng
        run_bg(self, self.btn_excel, "⏳ Đang xuất Excel…", lambda: export_excel(rep, dst, advanced=adv),
               lambda out, err: self._exported(rep, out, err))

    def _exported(self, rep, out, err):
        if isinstance(err, PermissionError):
            QMessageBox.warning(self, "Không lưu được", "File đang mở trong Excel – hãy đóng file rồi thử lại.")
            return
        if err is not None:
            QMessageBox.warning(self, "Không lưu được", f"❌ {err}")
            return
        ok = sum(1 for d in rep.dossiers if d.complete)
        activity.log("Báo cáo hồ sơ", f"{os.path.basename(out)} – {len(rep.dossiers)} hồ sơ, đủ {ok}, "
                                      f"thiếu {len(rep.dossiers) - ok}")
        if QMessageBox.question(self, "Đã xuất báo cáo", f"🎉 Đã lưu báo cáo:\n{out}\n\nMở file ngay?") == QMessageBox.Yes:
            open_path(out)

    def fix_folders(self):
        if not self.rep or self.busy_check():
            return
        todo = [d for d in self.rep.dossiers if d.suggestion]
        if not todo:
            return
        lines = "\n".join(f"• {d.folder}  →  {d.suggestion}" for d in todo[:25])
        more = f"\n… và {len(todo) - 25} thư mục khác" if len(todo) > 25 else ""
        if QMessageBox.question(self, "Chuẩn hoá tên thư mục hồ sơ",
                                f"Đổi tên {len(todo)} thư mục theo chuẩn CCCD_HoVaTen?\n\n{lines}{more}\n\n"
                                "Có thể hoàn tác bằng nút “Hoàn tác đổi tên”.") != QMessageBox.Yes:
            return
        from .preview import release_document
        release_document()
        res = R.rename_folders([(d.path, d.suggestion) for d in todo])
        self.last_renames = [r for r in res if r.ok]
        for r in res:
            activity.log("Đổi tên thư mục" if r.ok else "Đổi tên thư mục lỗi",
                         f"{os.path.basename(r.old)} → {os.path.basename(r.new)}" + ("" if r.ok else f" ({r.message})"))
        bad = [r for r in res if not r.ok]
        msg = f"✔ Đã đổi tên {len(self.last_renames)}/{len(res)} thư mục."
        if bad:
            msg += "\n\nKhông đổi được:\n" + "\n".join(f"• {os.path.basename(r.old)}: {r.message}" for r in bad[:10])
        QMessageBox.information(self, "Chuẩn hoá tên thư mục", msg)
        self.btn_undo.setEnabled(bool(self.last_renames))
        self.renamed.emit()

    def undo_folders(self):
        if not self.last_renames or self.busy_check():
            return
        from .preview import release_document
        release_document()
        res = R.undo_renames(self.last_renames)
        ok = sum(r.ok for r in res)
        activity.log("Hoàn tác đổi tên thư mục", f"{ok}/{len(res)} thư mục")
        QMessageBox.information(self, "Hoàn tác", f"↶ Đã khôi phục {ok}/{len(res)} tên thư mục.")
        self.last_renames = []
        self.btn_undo.setEnabled(False)
        self.renamed.emit()
