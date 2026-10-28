"""Tab TÁCH TRANG PDF (kiểu "Cắt & Ghép Sổ Lý Lịch" của Hồ sơ 1361): A3 → A4, A4 → 2 nửa phóng ra A4,
sổ gỡ ghim scan 2 mặt → đúng thứ tự trang. Trái: thiết lập · Giữa: trang scan gốc + đường cắt đỏ ·
Phải: xem trước kết quả (giống 100% file xuất) · Dưới: lưu."""
from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import QRectF, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QFrame, QLabel, QLineEdit, QMessageBox, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
                               QToolButton,
                               QVBoxLayout, QWidget)

from ..core import activity, pagenum, splitter as S
from ..core.models import FileInfo
from . import file_picker, illustrations
from .common import open_path
from .preview import release_document
from .styles import button
from .widgets import ElidedLabel

PRESET_TEXT = {"a3_to_a4": "A3 ngang → 2 trang A4\nScan khổ A3, mỗi bên là 1 trang",
               "a4_to_a4": "A4 → 2 nửa → 2 trang A4\nMỗi nửa trang phóng thành A4",
               "booklet": "Sổ lý lịch gỡ ghim\nScan 2 mặt → sắp đúng thứ tự"}

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz


class PageView(QLabel):
    """Hiển thị 1 trang vừa khít khung, nét theo DPI; vẽ đường cắt đỏ và nhãn trạng thái nếu có.
    draggable=True: kéo đường cắt đỏ bằng chuột (phát cutDragged(%) liên tục khi kéo)."""
    cutDragged = Signal(float)
    GRAB = 8                 # khoảng cách (điểm ảnh) quanh đường cắt để bắt chuột

    def __init__(self, empty_text: str, draggable: bool = False):
        super().__init__()
        self.draggable = draggable
        self._dragging = False
        self._base: Optional[QImage] = None     # ảnh trang chưa vẽ đường cắt (vẽ lại nhanh khi kéo)
        self._dpr = 1.0
        self.setMouseTracking(draggable)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setMinimumSize(180, 160)
        self.setStyleSheet("background:#FFFFFF;border:1px dashed #CBD5E1;border-radius:4px;color:#64748B;")
        self.empty_text = empty_text
        self.doc = None
        self.index = 0
        self.cut = None        # (mode, percent) hoặc None
        self.badge = ""        # nhãn góc trên, vd "GIỮ NGUYÊN"
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.setInterval(80)
        self._t.timeout.connect(self._render)
        self.setText(empty_text)

    def show_page(self, doc, index: int, cut=None, badge: str = ""):
        same = doc is self.doc and index == self.index and self._base is not None
        self.doc, self.index, self.cut, self.badge = doc, index, cut, badge
        if same and not self._dragging:
            self._compose()                     # chỉ đổi đường cắt / nhãn: không cần vẽ lại trang
        elif not same:
            self._base = None
            self._t.start()

    def clear(self, text: str = ""):
        self.doc = None
        self._base = None
        self.unsetCursor()
        self.setPixmap(QPixmap())
        self.setText(text or self.empty_text)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.doc is not None:
            self._base = None
            self._t.start()

    # ---- kéo đường cắt
    def _img_rect(self) -> QRectF:
        """Vị trí ảnh trang trong khung (toạ độ widget)."""
        if self._base is None:
            return QRectF()
        w, h = self._base.width() / self._dpr, self._base.height() / self._dpr
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _near_cut(self, pos) -> bool:
        if not (self.draggable and self.cut and self._base is not None):
            return False
        r = self._img_rect()
        mode, pct = self.cut
        if mode == "left_right":
            return abs(pos.x() - (r.left() + r.width() * pct / 100)) <= self.GRAB and r.top() <= pos.y() <= r.bottom()
        return abs(pos.y() - (r.top() + r.height() * pct / 100)) <= self.GRAB and r.left() <= pos.x() <= r.right()

    def _pct_at(self, pos) -> float:
        r = self._img_rect()
        if self.cut[0] == "left_right":
            v = (pos.x() - r.left()) / max(1.0, r.width()) * 100
        else:
            v = (pos.y() - r.top()) / max(1.0, r.height()) * 100
        return float(max(5, min(95, round(v))))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._near_cut(e.position()):
            self._dragging = True
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._dragging:
            pct = self._pct_at(pos)
            if pct != self.cut[1]:
                self.cut = (self.cut[0], pct)
                self._compose()
                self.cutDragged.emit(pct)
            return
        if self._near_cut(pos):
            self.setCursor(Qt.SplitHCursor if self.cut[0] == "left_right" else Qt.SplitVCursor)
            self.setToolTip("Kéo để dời đường cắt")
        else:
            self.unsetCursor()
            self.setToolTip("")
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self._dragging = False
            self._compose()
            return
        super().mouseReleaseEvent(e)

    def _render(self):
        if self.doc is None or not (0 <= self.index < self.doc.page_count):
            return
        pg = self.doc[self.index]
        dpr = max(1.0, self.devicePixelRatioF())
        bw, bh = max(50, self.width() - 16), max(50, self.height() - 16)
        z = min(bw / pg.rect.width, bh / pg.rect.height)
        pix = pg.get_pixmap(matrix=fitz.Matrix(z * dpr, z * dpr), alpha=False)
        self._base = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        self._dpr = dpr
        self._compose()

    def _compose(self):
        """Vẽ khung, đường cắt, nhãn lên bản sao của ảnh trang."""
        if self._base is None:
            return
        dpr = self._dpr
        img = self._base.copy()
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#CBD5E1"), 1 * dpr))
        p.drawRect(0, 0, img.width() - 1, img.height() - 1)
        if self.cut:
            mode, pct = self.cut
            pen = QPen(QColor("#DC2626"), (3.5 if self._dragging else 2.5) * dpr,
                       Qt.SolidLine if self._dragging else Qt.DashLine)
            p.setPen(pen)
            if mode == "left_right":
                x = img.width() * pct / 100
                p.drawLine(int(x), 0, int(x), img.height())
            else:
                y = img.height() * pct / 100
                p.drawLine(0, int(y), img.width(), int(y))
            if self.draggable:                   # tay nắm ở giữa đường cắt + % khi đang kéo
                cx, cy = (x, img.height() / 2) if mode == "left_right" else (img.width() / 2, y)
                p.setPen(QPen(QColor("#FFFFFF"), 1.5 * dpr))
                p.setBrush(QColor("#DC2626"))
                hw, hh = (7 * dpr, 22 * dpr) if mode == "left_right" else (22 * dpr, 7 * dpr)
                p.drawRoundedRect(QRectF(cx - hw, cy - hh, 2 * hw, 2 * hh), 4 * dpr, 4 * dpr)
                if self._dragging:
                    f = QFont("Segoe UI")
                    f.setBold(True)
                    f.setPixelSize(int(13 * dpr))
                    p.setFont(f)
                    txt = f"{pct:.0f} %"
                    tw = p.fontMetrics().horizontalAdvance(txt) + 12 * dpr
                    r = QRectF(cx + 12 * dpr, cy - 34 * dpr, tw, 22 * dpr) if mode == "left_right" else \
                        QRectF(cx - tw / 2, cy + 12 * dpr, tw, 22 * dpr)
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor("#DC2626"))
                    p.drawRoundedRect(r, 5 * dpr, 5 * dpr)
                    p.setPen(QColor("#FFFFFF"))
                    p.drawText(r, Qt.AlignCenter, txt)
        if self.badge:
            f = QFont("Segoe UI")
            f.setBold(True)
            f.setPixelSize(int(13 * dpr))
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(self.badge) + int(16 * dpr)
            r = QRectF(8 * dpr, 8 * dpr, tw, 24 * dpr)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(15, 23, 42, 200))
            p.drawRoundedRect(r, 5 * dpr, 5 * dpr)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(r, Qt.AlignCenter, self.badge)
        p.end()
        img.setDevicePixelRatio(dpr)
        self.setText("")
        self.setPixmap(QPixmap.fromImage(img))


class OcrThread(QThread):
    """Đọc số trang (Windows OCR) ở luồng phụ – chỉ xử lý ảnh PIL, không đụng tới PyMuPDF."""
    progress = Signal(int, int)
    done = Signal(int, object, str)          # mã lượt, kết quả, lỗi

    def __init__(self, token: int, images):
        super().__init__()
        self.token, self.images = token, images

    def run(self):
        try:
            res = pagenum.read_pages(self.images, max_page=len(self.images) + 8,
                                     progress=lambda i, n: self.progress.emit(i, n))
            self.done.emit(self.token, res, "")
        except Exception as e:
            self.done.emit(self.token, None, str(e))


class SplitPanel(QWidget):
    saved = Signal(str)
    helpRequested = Signal(str)          # mở tab Hướng dẫn tại mục (anchor)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.files: List[FileInfo] = []
        self.src_path = ""
        self.src_doc = None
        self.info: Optional[S.PdfInfo] = None
        self.result: Optional[S.SplitResult] = None
        self.si = 0          # trang scan đang xem
        self.ri = 0          # trang kết quả đang xem
        self._loading = False
        self._sheet, self._face = "outer", "front"     # kiểu xếp tờ sổ (do tự đọc số trang xác định)
        self._reads: Optional[S.PageReads] = None
        self._guess: Optional[S.OrderGuess] = None
        self._ocr_token = 0
        self._ocr_keys = None
        self._ocr_opts: Optional[S.SplitOptions] = None
        self._ocr_thread: Optional[OcrThread] = None
        self._prep = None                    # đang chuẩn bị ảnh nửa trang cho OCR (từng phần)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(8)

        # ---- file nguồn (hộp chọn có tìm kiếm thay cho danh sách thả xuống hàng nghìn dòng)
        self.setAcceptDrops(True)
        g = QGroupBox("File PDF cần tách trang")
        gl = QVBoxLayout(g)
        steps = QLabel("<b>①</b> Chọn file (hoặc kéo thả file PDF vào đây) &nbsp;➜&nbsp; <b>②</b> Bấm hình kiểu tách "
                       "bên trái &nbsp;➜&nbsp; <b>③</b> Xem khung <b>Kết quả</b> (giống 100% file xuất) &nbsp;➜&nbsp; "
                       "<b>④</b> Bấm <b>LƯU</b>")
        steps.setObjectName("Steps")
        sr = QHBoxLayout()
        sr.addWidget(steps, 1)
        sr.addWidget(button("❓ Hướng dẫn có hình", "flat", lambda: self.helpRequested.emit("split"), size="sm"))
        gl.addLayout(sr)
        r = QHBoxLayout()
        self.lbl_file = ElidedLabel("Chưa chọn file – bấm “Chọn file” hoặc kéo thả file PDF vào đây")
        self.lbl_file.setObjectName("FileBox")
        r.addWidget(self.lbl_file, 1)
        self.btn_prev = button("◀", "light", lambda: self._step_file(-1), "File trước trong thư mục đã quét", "sm")
        self.btn_next = button("▶", "light", lambda: self._step_file(1), "File sau trong thư mục đã quét", "sm")
        self.btn_pick = button("🔎 Chọn file…", "primary", self.pick_scanned,
                               "Chọn trong thư mục đã quét – tìm theo tên, CCCD, thư mục (không cần dấu)", "sm")
        for b in (self.btn_prev, self.btn_next, self.btn_pick):
            r.addWidget(b)
        r.addWidget(button("📂 File khác…", "light", self.pick_file, "Chọn file PDF bất kỳ trên máy", "sm"))
        gl.addLayout(r)
        self.lbl_warn = QLabel("")
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setStyleSheet("color:#B45309;background:#FFF7ED;border:1px solid #FED7AA;border-radius:5px;"
                                    "padding:4px 8px;font-weight:600;")
        self.lbl_warn.hide()
        gl.addWidget(self.lbl_warn)
        outer.addWidget(g)

        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split, 1)

        # ---- thiết lập
        cfg = QGroupBox("Thiết lập tách trang")
        cfg.setMinimumWidth(360)
        form = QFormLayout(cfg)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setVerticalSpacing(7)

        def combo(items):
            c = QComboBox()
            for text, val in items:
                c.addItem(text, val)
            c.currentIndexChanged.connect(self._changed)
            return c

        self.cb_preset = QComboBox(self)          # giữ giá trị mẫu (ẩn) – người dùng bấm thẻ có hình bên dưới
        self.cb_preset.hide()
        self.cb_preset.addItem("⚙ Tuỳ chỉnh", "")
        for key, (name, _) in S.PRESETS.items():
            self.cb_preset.addItem(("📖 " if key == "booklet" else "📄 ") + name, key)
        self.cb_preset.currentIndexChanged.connect(self._preset_chosen)
        self.cb_preset.currentIndexChanged.connect(self._sync_cards)
        cards = QWidget()
        cvl = QVBoxLayout(cards)
        cvl.setContentsMargins(0, 0, 0, 0)
        cvl.setSpacing(6)
        self.cards = {}
        for key in S.PRESETS:
            b = QToolButton()
            b.setObjectName("PresetCard")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setIcon(QIcon(QPixmap.fromImage(illustrations.image(key, 128, 54, captions=False))))
            b.setIconSize(QSize(128, 54))
            b.setText(PRESET_TEXT[key])
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, k=key: self._card_clicked(k))
            cvl.addWidget(b)
            self.cards[key] = b
        self.lbl_custom = QLabel("⚙ Đang dùng thiết lập tuỳ chỉnh – xem “Tuỳ chọn nâng cao”.")
        self.lbl_custom.setObjectName("Hint")
        self.lbl_custom.hide()
        cvl.addWidget(self.lbl_custom)
        form.addRow(QLabel("<b>Chọn kiểu tách</b> (bấm vào hình):"))
        form.addRow(cards)
        self.cb_mode = combo([("⚡ Tự động theo khổ", "auto"),
                              ("✂ Cắt Trái / Phải", "left_right"), ("✂ Cắt Trên / Dưới", "top_bottom"),
                              ("Không cắt", "none")])
        self.cb_mode.setToolTip("Tự động: trang ngang → cắt trái/phải; trang dọc → cắt trên/dưới.\n"
                                "Không cắt: chỉ xoay / chuẩn hoá khổ giấy.")
        form.addRow("Kiểu cắt:", self.cb_mode)
        self.sp_cut = QSpinBox()
        self.sp_cut.setRange(5, 95)
        self.sp_cut.setValue(50)
        self.sp_cut.setSuffix(" %")
        self.sp_cut.valueChanged.connect(self._changed)
        form.addRow("Vị trí đường cắt:", self.sp_cut)
        self.cb_order = combo([("🟢 Trái/Trên ➔ Phải/Dưới", "first"), ("🔄 Phải/Dưới ➔ Trái/Trên", "second")])
        form.addRow("Thứ tự nửa trang:", self.cb_order)
        self.cb_arrange = combo([("Tách lần lượt", "sequential"), ("📖 Thứ tự sổ gỡ ghim", "booklet")])
        self.cb_arrange.setToolTip("Thứ tự sổ gỡ ghim: sổ tháo ghim, scan 2 mặt từng tờ → sắp lại đúng trang 1, 2, 3…")
        form.addRow("Sắp xếp:", self.cb_arrange)
        self.btn_auto = button("🔢 Tự đọc số trang && sắp xếp", "indigo", self.auto_order, size="sm")
        if pagenum.available():
            self.btn_auto.setToolTip("Đọc số trang in ở đầu/chân mỗi trang (OCR có sẵn của Windows) rồi tự chọn đúng\n"
                                     "cách xếp sổ: tờ nào scan trước, mặt nào trước, mặt sau có lộn ngược không…")
        else:
            self.btn_auto.setEnabled(False)
            self.btn_auto.setToolTip("Máy này không có Windows OCR (cần Windows 10/11 có gói ngôn ngữ).")
        form.addRow("", self.btn_auto)
        self.lbl_auto = QLabel("")
        self.lbl_auto.setWordWrap(True)
        self.lbl_auto.setStyleSheet("font-size:8.5pt;")
        self.lbl_auto.hide()
        form.addRow(self.lbl_auto)
        self.ck_first = QCheckBox("📌 Giữ nguyên trang đầu (bìa)")
        self.ck_last = QCheckBox("Giữ nguyên trang cuối")
        for c in (self.ck_first, self.ck_last):
            c.toggled.connect(self._changed)
        form.addRow("", self.ck_first)
        form.addRow("", self.ck_last)
        self.cb_flip = combo([("Tự động", "auto"), ("Có (mặt 2, 4, 6…)", "yes"), ("Không", "no")])
        self.cb_flip.setToolTip("Máy scan ADF 2 mặt có thể lật ngược mặt sau. Chọn 'Có' nếu khung giữa thấy mặt 2, 4… "
                                "bị lộn ngược.\nTự động: chỉ xoay khi sắp thứ tự sổ và cắt trên/dưới.")
        form.addRow("Xoay mặt sau (ADF):", self.cb_flip)
        self.cb_rot = combo([("Tự động", "auto"), ("Không xoay", "none"), ("🔃 Xoay phải 90°", "cw"),
                             ("🔄 Xoay trái 90°", "ccw"), ("🔁 Xoay 180°", "r180")])
        form.addRow("Xoay sau khi cắt:", self.cb_rot)
        self.cb_size = combo([("Giữ kích thước nửa trang", "original"), ("Chuẩn hoá khổ A4", "a4")])
        self.cb_size.setToolTip("Giữ kích thước: A3 cắt đôi ra đúng 2 trang A4.\n"
                                "Chuẩn hoá A4: nửa trang A4 (khổ A5) được phóng vừa trang A4, giữ nguyên tỉ lệ.")
        form.addRow("Khổ giấy kết quả:", self.cb_size)
        rr = QHBoxLayout()
        self.sp_from, self.sp_to = QSpinBox(), QSpinBox()
        for sp in (self.sp_from, self.sp_to):
            sp.setRange(0, 9999)
            sp.setSpecialValueText("–")
            sp.setMinimumWidth(70)
            sp.valueChanged.connect(self._changed)
        rr.addWidget(QLabel("từ"))
        rr.addWidget(self.sp_from)
        rr.addWidget(QLabel("đến"))
        rr.addWidget(self.sp_to)
        rr.addStretch(1)
        form.addRow("Trang scan:", rr)
        self.ck_blank = QCheckBox("Bỏ trang trắng sau khi tách")
        self.ck_blank.toggled.connect(self._changed)
        form.addRow("", self.ck_blank)
        # tuỳ chọn ít dùng → gom vào mục "Nâng cao" (thu gọn mặc định) cho đỡ rối mắt
        self._adv = []
        for w in (self.sp_cut, self.cb_order, self.ck_last, self.cb_flip, self.cb_rot, rr):
            res = form.takeRow(w)
            lab = res.labelItem.widget() if res.labelItem else None
            fld = res.fieldItem.widget() or res.fieldItem.layout()
            self._adv.append((lab, fld))
        self.btn_adv = button("⚙ Tuỳ chọn nâng cao ▸", "flat", None, size="sm",
                              tip="Vị trí đường cắt, thứ tự nửa trang, xoay mặt sau, xoay sau khi cắt, phạm vi trang")
        self.btn_adv.setCheckable(True)
        self.btn_adv.toggled.connect(self._toggle_adv)
        form.addRow(self.btn_adv)
        for lab, fld in self._adv:
            if lab is not None:
                form.addRow(lab, fld)
            else:
                form.addRow(fld)
        self._form = form
        self._toggle_adv(False)
        self.lbl_sum = QLabel("")
        self.lbl_sum.setWordWrap(True)
        self.lbl_sum.setObjectName("StatusText")
        form.addRow(self.lbl_sum)
        tip = QLabel("Mẹo: xem khung giữa để chỉnh đường cắt, khung phải giống 100% file sẽ xuất. "
                     "File gốc luôn được giữ nguyên.")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        form.addRow(tip)
        # cột thiết lập tự cuộn riêng → thanh "Lưu kết quả" bên dưới luôn hiện, kể cả màn hình thấp
        cfg_scroll = QScrollArea()
        cfg_scroll.setWidgetResizable(True)
        cfg_scroll.setFrameShape(QFrame.NoFrame)
        cfg_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cfg_scroll.setWidget(cfg)
        cfg_scroll.setMinimumWidth(380)
        cfg_scroll.setMaximumWidth(480)
        cfg_scroll.setMinimumHeight(220)
        split.addWidget(cfg_scroll)

        # ---- trang scan gốc
        gs = QGroupBox("1. Trang scan gốc (kéo đường cắt màu đỏ để chỉnh)")
        gsl = QVBoxLayout(gs)
        self.view_src = PageView("Chưa chọn file", draggable=True)
        self.view_src.cutDragged.connect(self._cut_dragged)
        gsl.addWidget(self.view_src, 1)
        self.lbl_src = QLabel("")
        self.lbl_src.setAlignment(Qt.AlignCenter)
        self.lbl_src.setStyleSheet("font-size:8.5pt;color:#334155;font-weight:600;")
        gsl.addWidget(self.lbl_src)
        nav = QHBoxLayout()
        self.btn_sp = button("◄ Trang trước", "light", lambda: self._go_src(-1), size="sm")
        self.btn_sn = button("Trang sau ►", "light", lambda: self._go_src(1), size="sm")
        nav.addWidget(self.btn_sp)
        nav.addStretch(1)
        nav.addWidget(self.btn_sn)
        gsl.addLayout(nav)
        split.addWidget(gs)

        # ---- kết quả
        gr = QGroupBox("2. Xem trước kết quả (giống 100% file xuất)")
        grl = QVBoxLayout(gr)
        self.view_res = PageView("Kết quả sẽ hiện ở đây")
        grl.addWidget(self.view_res, 1)
        self.lbl_res = QLabel("")
        self.lbl_res.setAlignment(Qt.AlignCenter)
        self.lbl_res.setWordWrap(True)
        self.lbl_res.setStyleSheet("font-size:8.5pt;color:#334155;font-weight:600;")
        grl.addWidget(self.lbl_res)
        nav2 = QHBoxLayout()
        self.btn_rp = button("◄ Trang kết quả trước", "light", lambda: self._go_res(-1), size="sm")
        self.btn_rn = button("Trang kết quả sau ►", "light", lambda: self._go_res(1), size="sm")
        nav2.addWidget(self.btn_rp)
        nav2.addStretch(1)
        nav2.addWidget(self.btn_rn)
        grl.addLayout(nav2)
        split.addWidget(gr)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setStretchFactor(2, 1)
        split.setSizes([360, 560, 560])
        split.setChildrenCollapsible(False)

        # ---- lưu
        gsave = QGroupBox("Lưu kết quả")
        sl = QHBoxLayout(gsave)
        sl.addWidget(QLabel("Lưu file kết quả tại:"))
        self.ed_out = QLineEdit()
        sl.addWidget(self.ed_out, 1)
        sl.addWidget(button("📁 Chọn vị trí…", "light", self.pick_out, size="sm"))
        sl.addSpacing(8)
        sl.addWidget(QLabel("Trang xuất:"))
        self.ed_pages = QLineEdit()
        self.ed_pages.setPlaceholderText("Tất cả  (VD: 1-4, 7)")
        self.ed_pages.setFixedWidth(150)
        self.ed_pages.setToolTip("Để trống = xuất tất cả trang kết quả. Ví dụ: 1-4, 7, 9-")
        sl.addWidget(self.ed_pages)
        self.ck_over = QCheckBox("💾 Lưu đè file gốc")
        self.ck_over.setToolTip("Thay file gốc bằng file đã tách; bản gốc được sao lưu vào thư mục _backup_goc")
        self.ck_over.toggled.connect(lambda on: self.ed_out.setEnabled(not on))
        sl.addWidget(self.ck_over)
        self.ck_open = QCheckBox("📂 Tự mở file khi xuất")
        self.ck_open.setChecked(True)
        sl.addWidget(self.ck_open)
        self.btn_save = button("🚀 LƯU TOÀN BỘ", "success", self.save, size="lg")
        sl.addWidget(self.btn_save)
        outer.addWidget(gsave)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self.rebuild)
        self._apply_preset("a3_to_a4")
        self._update_file_nav()
        self._update_enabled()

    def _cut_dragged(self, pct: float):
        """Kéo đường cắt trên trang scan → cập nhật ô Vị trí đường cắt (mở Tuỳ chọn nâng cao) và kết quả."""
        if not self.btn_adv.isChecked():
            self.btn_adv.setChecked(True)
        self.sp_cut.setValue(int(pct))

    def _toggle_adv(self, on: bool):
        for _, fld in self._adv:
            self._form.setRowVisible(fld, on)
        self.btn_adv.setText("⚙ Tuỳ chọn nâng cao ▾" if on else "⚙ Tuỳ chọn nâng cao ▸")

    # ------------------------------------------------------------------ dữ liệu vào
    def set_files(self, files: List[FileInfo]):
        self.files = files
        self._update_file_nav()

    def _update_file_nav(self):
        paths = [f.path for f in self.files]
        has = bool(paths)
        self.btn_pick.setEnabled(has)
        self.btn_pick.setText(f"🔎 Chọn file… ({len(paths):,})".replace(",", ".") if has else "🔎 Chọn file…")
        i = paths.index(self.src_path) if self.src_path in paths else -1
        self.btn_prev.setEnabled(has and i != 0)
        self.btn_next.setEnabled(has and (i < 0 or i < len(paths) - 1))

    def pick_scanned(self):
        p = file_picker.pick(self, self.files, self.src_path, "Chọn file PDF cần tách trang")
        if p:
            self.load_file(p)

    def _step_file(self, step: int):
        p = file_picker.neighbor(self.files, self.src_path, step)
        if p:
            self.load_file(p)

    def _card_clicked(self, key: str):
        i = self.cb_preset.findData(key)
        if i == self.cb_preset.currentIndex():
            self._sync_cards()
        else:
            self.cb_preset.setCurrentIndex(i)

    def _sync_cards(self, *_):
        key = self.cb_preset.currentData() or ""
        for k, b in self.cards.items():
            b.setChecked(k == key)
        self.lbl_custom.setVisible(not key)

    def dragEnterEvent(self, e):
        if any(u.toLocalFile().lower().endswith(".pdf") for u in e.mimeData().urls()):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith(".pdf") and os.path.isfile(p):
                self.load_file(os.path.normpath(p))
                break

    def pick_file(self):
        start = os.path.dirname(self.src_path) if self.src_path else ""
        p, _ = QFileDialog.getOpenFileName(self, "Chọn file PDF scan cần tách", start, "File PDF (*.pdf)")
        if p:
            self.load_file(os.path.normpath(p))

    def load_file(self, path: Optional[str]):
        if not path:
            return
        try:
            doc = S.open_source(path)
        except S.SplitError as e:
            QMessageBox.warning(self, "Lỗi đọc PDF", f"Không thể đọc file PDF:\n{e}")
            return
        self.src_path, self.src_doc = path, doc
        self.info = S.read_info(doc)
        rel = next((f.dir_rel or "(thư mục gốc)" for f in self.files if f.path == path), os.path.dirname(path))
        self.lbl_file.set_full_text(f"📄 {os.path.basename(path)}   ·   {self.info.pages} trang scan   ·   khổ "
                                    f"{self.info.label}   ·   {rel}", path)
        self._update_file_nav()
        if self.info.has_signature:
            self.lbl_warn.setText("⚠ File này có chữ ký số. File sau khi tách là file MỚI nên KHÔNG còn chữ ký hợp lệ; "
                                  "file gốc vẫn giữ nguyên (không nên chọn “Lưu đè file gốc”).")
            self.lbl_warn.show()
        else:
            self.lbl_warn.hide()
        self.ed_out.setText(S.default_output(path))
        self.ck_over.setChecked(False)
        # gợi ý mẫu theo khổ giấy (không đè nếu đang chọn sổ gỡ ghim)
        if self.cb_preset.currentData() != "booklet":
            self._apply_preset("a4_to_a4" if self.info.label.startswith("A4") or self.info.label.startswith("A5")
                               else "a3_to_a4")
        self.si = self.ri = 0
        self.sp_from.setMaximum(self.info.pages)
        self.sp_to.setMaximum(self.info.pages)
        self._clear_auto()
        self._update_enabled()
        self.rebuild()
        if self.cb_arrange.currentData() == "booklet":
            QTimer.singleShot(0, self.auto_order)          # sổ gỡ ghim: tự đọc số trang ngay

    # ------------------------------------------------------------------ tuỳ chọn
    def _set(self, combo: QComboBox, value):
        i = combo.findData(value)
        if i >= 0:
            combo.setCurrentIndex(i)

    def _apply_preset(self, key: str):
        _, o = S.PRESETS[key]
        self._loading = True
        self._set(self.cb_preset, key)
        self._set(self.cb_mode, o.split_mode)
        self.sp_cut.setValue(int(o.cut_percent))
        self._set(self.cb_order, o.half_order)
        self._set(self.cb_arrange, o.arrange)
        self.ck_first.setChecked(o.keep_first)
        self.ck_last.setChecked(o.keep_last)
        self._set(self.cb_flip, o.flip_back)
        self._set(self.cb_rot, o.post_rotation)
        self._set(self.cb_size, o.page_size)
        self.ck_blank.setChecked(o.remove_blank)
        self._sheet, self._face = o.sheet_order, o.face_first
        self._loading = False

    def _preset_chosen(self, idx: int):
        if self._loading:
            return
        key = self.cb_preset.itemData(idx)
        if key:
            self._apply_preset(key)
            self._clear_auto()
            self._timer.start()
            if key == "booklet" and self.src_doc is not None:
                QTimer.singleShot(300, self.auto_order)

    def _changed(self, *_):
        if self._loading:
            return
        self._loading = True
        self.cb_preset.setCurrentIndex(0)      # người dùng tự chỉnh → "Tuỳ chỉnh"
        self._loading = False
        self._timer.start()

    def options(self) -> S.SplitOptions:
        return S.SplitOptions(
            split_mode=self.cb_mode.currentData(), cut_percent=float(self.sp_cut.value()),
            half_order=self.cb_order.currentData(), arrange=self.cb_arrange.currentData(),
            keep_first=self.ck_first.isChecked(), keep_last=self.ck_last.isChecked(),
            flip_back=self.cb_flip.currentData(), post_rotation=self.cb_rot.currentData(),
            page_size=self.cb_size.currentData(), remove_blank=self.ck_blank.isChecked(),
            page_from=self.sp_from.value() or None, page_to=self.sp_to.value() or None,
            sheet_order=self._sheet, face_first=self._face)

    # ------------------------------------------------------------------ tự đọc số trang
    def _clear_auto(self):
        self._ocr_token += 1                         # bỏ qua kết quả của lượt đọc cũ (nếu đang chạy)
        self._prep = None
        self._reads = self._guess = None
        self.lbl_auto.hide()
        if self._ocr_thread is None:
            self.btn_auto.setText("🔢 Tự đọc số trang && sắp xếp")
            self.btn_auto.setEnabled(pagenum.available())

    def _auto_msg(self, html: str, color: str = "#334155"):
        self.lbl_auto.setText(f"<span style='color:{color}'>{html}</span>")
        self.lbl_auto.show()

    def auto_order(self):
        if self.src_doc is None or not pagenum.available() or self._ocr_thread is not None or self._prep:
            return
        self._clear_auto()
        opts = self.options()
        # ảnh nửa trang vẽ bằng PyMuPDF ở luồng chính → vẽ từng ít một (≈ 40 ms/lượt) xen kẽ sự kiện giao diện
        self._prep = (self._ocr_token, S.iter_half_images(self.src_doc, opts), [], [], opts)
        self.btn_auto.setEnabled(False)
        self.btn_auto.setText("⏳ Đang chuẩn bị ảnh…")
        QTimer.singleShot(0, self._prep_step)

    def _prep_step(self):
        import time
        if not self._prep or self._prep[0] != self._ocr_token:
            return                                    # đã huỷ (đổi file / đổi thiết lập)
        token, gen, keys, images, opts = self._prep
        t0 = time.perf_counter()
        try:
            for k, im in gen:
                keys.append(k)
                images.append(im)
                if time.perf_counter() - t0 > 0.04:
                    self.btn_auto.setText(f"⏳ Đang chuẩn bị ảnh… {len(images)}")
                    QTimer.singleShot(0, self._prep_step)
                    return
        except S.SplitError as e:
            self._prep = None
            self._clear_auto()
            self._auto_msg(f"⚠ {e}", "#B91C1C")
            return
        self._prep = None
        if len(images) < 2:
            self._clear_auto()
            self._auto_msg("⚠ Cần ít nhất 2 nửa trang để đọc số trang.", "#B45309")
            return
        self._ocr_keys, self._ocr_opts = keys, opts
        self.btn_auto.setEnabled(False)
        self.btn_auto.setText(f"⏳ Đang đọc số trang… 0/{len(images)}")
        t = OcrThread(self._ocr_token, images)
        t.progress.connect(lambda i, n: self.btn_auto.setText(f"⏳ Đang đọc số trang… {i}/{n}"))
        t.done.connect(self._ocr_done)
        t.finished.connect(t.deleteLater)
        self._ocr_thread = t
        t.start()

    def _ocr_done(self, token: int, results, err: str):
        self._ocr_thread = None
        self.btn_auto.setText("🔢 Tự đọc số trang && sắp xếp")
        self.btn_auto.setEnabled(True)
        if token != self._ocr_token or self.src_doc is None:
            return                                      # đã đổi file / mẫu trong lúc đọc
        if err:
            self._auto_msg(f"⚠ Không đọc được số trang: {err}", "#B91C1C")
            return
        pr = S.make_reads(self._ocr_keys, results)
        g = S.guess_order(self.src_doc, self._ocr_opts, pr)
        self._reads, self._guess = pr, g
        if g.options is None:
            self._auto_msg(f"⚠ Đọc được {pr.count}/{pr.halves} số trang. {g.description}<br>"
                           "Hãy tự chỉnh thiết lập và kiểm tra khung kết quả.", "#B45309")
            self._show_res()
            return
        o = g.options
        self._loading = True
        self._set(self.cb_arrange, o.arrange)
        self._set(self.cb_order, o.half_order)
        self._set(self.cb_flip, o.flip_back)
        self._set(self.cb_rot, o.post_rotation)
        self._sheet, self._face = o.sheet_order, o.face_first
        self._loading = False
        self._timer.stop()
        self.rebuild()
        self._auto_msg(f"✔ Đọc được <b>{pr.count}/{pr.halves}</b> số trang, khớp <b>{g.matched}</b> → "
                       f"đã tự sắp xếp: <b>{g.description}</b>", "#15803D")
        activity.log("Tách trang", f"Tự đọc số trang {os.path.basename(self.src_path)}: {pr.count}/{pr.halves}, "
                                   f"khớp {g.matched} – {g.description}")

    def _printed_number(self, k: int):
        """(số in đọc được, có khớp vị trí không) của trang kết quả k, hoặc None."""
        if not self._reads or not self.result or self._guess is None:
            return None
        u = self.result.units[k]
        if u.clip is None:
            return None
        up, down, ang = self._reads.reads.get(S.unit_key(u), (None, None, 0))
        d = (u.rotate - ang) % 360
        n = up if d == 0 else down if d == 180 else None
        if n is None:
            return None
        pos = sum(1 for x in self.result.units[:k + 1] if x.clip is not None) + self._guess.offset
        return n, n == pos

    # ------------------------------------------------------------------ dựng + xem trước
    def rebuild(self):
        if self.src_doc is None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.result = S.build(self.src_doc, self.options())
            err = ""
        except S.SplitError as e:
            self.result, err = None, str(e)
        except Exception as e:  # lỗi bất ngờ không làm sập app
            self.result, err = None, f"Lỗi xử lý: {e}"
        finally:
            QApplication.restoreOverrideCursor()
        if err:
            self.lbl_sum.setText(f"<span style='color:#B91C1C'>⚠ {err}</span>")
        else:
            res = self.result
            sizes = {}
            for pg in res.doc:
                n = S.paper_name(pg.rect.width, pg.rect.height)
                sizes[n] = sizes.get(n, 0) + 1
            txt = (f"✔ {self.info.pages} trang scan → <b>{res.doc.page_count} trang kết quả</b> "
                   f"({', '.join(f'{k} ×{v}' for k, v in sizes.items())})")
            if res.removed_blank:
                txt += f"<br>🗑 Đã bỏ {len(res.removed_blank)} trang trắng (vị trí: {', '.join(map(str, res.removed_blank[:12]))})"
            for w in res.warnings:
                txt += f"<br>⚠ {w}"
            self.lbl_sum.setText(txt)
        self.ri = min(self.ri, (self.result.doc.page_count - 1) if self.result else 0)
        self._show_src()
        self._show_res()
        self._update_enabled()

    def _src_status(self, i: int):
        """(đường cắt, nhãn) cho trang scan i theo tuỳ chọn hiện tại."""
        o = self.options()
        n = self.src_doc.page_count
        a, b = max(1, o.page_from or 1) - 1, min(n, o.page_to or n) - 1
        if not a <= i <= b:
            return None, "NGOÀI PHẠM VI"
        if o.keep_first and i == a:
            return None, "GIỮ NGUYÊN (BÌA)"
        if o.keep_last and i == b and b > a:
            return None, "GIỮ NGUYÊN"
        rect = self.src_doc[i].rect
        mode = S.resolve_mode(o, rect)
        if mode == "none":
            return None, ""
        j = i - a - (1 if o.keep_first else 0)
        badge = "MẶT SAU · XOAY 180°" if S._flip(o, mode, j) else ""
        return (mode, o.cut_percent), badge

    def _show_src(self):
        if self.src_doc is None:
            self.view_src.clear()
            return
        self.si = max(0, min(self.si, self.src_doc.page_count - 1))
        cut, badge = self._src_status(self.si)
        self.view_src.show_page(self.src_doc, self.si, cut, badge)
        r = self.src_doc[self.si].rect
        self.lbl_src.setText(f"Trang scan {self.si + 1} / {self.src_doc.page_count} · {S.paper_name(r.width, r.height)}")

    def _show_res(self):
        if not self.result or self.result.doc.page_count == 0:
            self.view_res.clear("Chưa có kết quả – xem thông báo ở khung thiết lập")
            self.lbl_res.setText("")
            return
        d = self.result.doc
        self.ri = max(0, min(self.ri, d.page_count - 1))
        self.view_res.show_page(d, self.ri)
        u = self.result.units[self.ri]
        r = d[self.ri].rect
        num = self._printed_number(self.ri)
        extra = ""
        if num:
            extra = (f" · <span style='color:#15803D'>số in: {num[0]}</span>" if num[1]
                     else f" · <span style='color:#B45309'>⚠ số in đọc được: {num[0]}</span>")
        self.lbl_res.setText(f"✅ Trang kết quả {self.ri + 1} / {d.page_count} · {S.paper_name(r.width, r.height)}{extra}"
                             f"<br><span style='color:#64748B;font-weight:normal'>{u.label}</span>")

    def _go_src(self, d: int):
        if self.src_doc is not None:
            self.si = max(0, min(self.si + d, self.src_doc.page_count - 1))
            self._show_src()
            # nhảy khung kết quả tới trang đầu tiên lấy từ trang scan này
            if self.result:
                for k, u in enumerate(self.result.units):
                    if u.src == self.si:
                        self.ri = k
                        self._show_res()
                        break
            self._update_enabled()

    def _go_res(self, d: int):
        if self.result:
            self.ri = max(0, min(self.ri + d, self.result.doc.page_count - 1))
            self._show_res()
            self._update_enabled()

    def _update_enabled(self):
        has = self.src_doc is not None
        n = self.src_doc.page_count if has else 0
        self.btn_sp.setEnabled(has and self.si > 0)
        self.btn_sn.setEnabled(has and self.si < n - 1)
        m = self.result.doc.page_count if self.result else 0
        self.btn_rp.setEnabled(m > 0 and self.ri > 0)
        self.btn_rn.setEnabled(m > 0 and self.ri < m - 1)
        self.btn_save.setEnabled(m > 0)

    # ------------------------------------------------------------------ lưu
    def pick_out(self):
        start = self.ed_out.text() or (S.default_output(self.src_path) if self.src_path else "")
        p, _ = QFileDialog.getSaveFileName(self, "Chọn vị trí lưu file PDF kết quả", start, "File PDF (*.pdf)")
        if p:
            self.ed_out.setText(os.path.normpath(p))

    def save(self):
        if not self.result:
            return
        try:
            pages = S.parse_pages(self.ed_pages.text(), self.result.doc.page_count)
        except S.SplitError as e:
            QMessageBox.warning(self, "Trang xuất", str(e))
            return
        over = self.ck_over.isChecked()
        out = self.ed_out.text().strip()
        if not over and not out:
            QMessageBox.information(self, "Thông báo", "Vui lòng chọn đường dẫn file kết quả.")
            return
        if over:
            msg = "Thay file gốc bằng file đã tách?\nBản gốc được sao lưu vào thư mục _backup_goc bên cạnh."
            if self.info and self.info.has_signature:
                msg += "\n\n⚠ File gốc có chữ ký số – file mới sẽ KHÔNG còn chữ ký hợp lệ."
            if QMessageBox.question(self, "Lưu đè file gốc", msg) != QMessageBox.Yes:
                return
        elif os.path.exists(out) and QMessageBox.question(self, "File đã tồn tại",
                                                          f"{out}\nđã tồn tại. Ghi đè file này?") != QMessageBox.Yes:
            return
        release_document()
        try:
            path = S.save(self.result, self.src_path, out, pages if len(pages) != self.result.doc.page_count else None,
                          overwrite_source=over)
        except (S.SplitError, OSError) as e:
            QMessageBox.warning(self, "Lỗi lưu file", f"❌ Không lưu được:\n{e}")
            return
        activity.log("Tách trang", f"{os.path.basename(self.src_path)} → {os.path.basename(path)} ({len(pages)} trang)")
        if over:
            self.load_file(path)
        else:
            self.ed_out.setText(S.default_output(self.src_path))
        if self.ck_open.isChecked():
            open_path(path)
        else:
            QMessageBox.information(self, "Hoàn tất", f"🎉 Đã tách trang thành công!\n{len(pages)} trang → {path}")
        self.saved.emit(path)
