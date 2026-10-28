"""Khung xem trước PDF (kiểu Hồ sơ 1361): mặc định VỪA KHÍT TRANG trong khung, render nét theo DPI màn hình,
luồng nền + cache, chuyển trang, phóng to/thu nhỏ (Ctrl + lăn chuột), vừa chiều rộng, xoay khi xem."""
from __future__ import annotations

from ..paths import make_settings

import os
import threading

from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, QThreadPool, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QDesktopServices, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QMessageBox, QScrollArea, QSizePolicy, QSplitter,
                               QSpinBox, QVBoxLayout, QWidget)

from .styles import button

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

_LOCK = threading.Lock()
_STATE = {"key": None, "doc": None}
_MAX_STREAM = 200 * 1024 * 1024
FIT_AUTO, FIT_PAGE, FIT_WIDTH, FIT_NONE = "auto", "page", "width", "none"
# Tự động: hiện trọn trang nếu chữ vẫn đủ lớn (≥ 78% so với vừa ngang), ngược lại vừa ngang để dễ đọc
_AUTO_RATIO = 0.78
_MARGIN = 12          # khoảng đệm quanh trang trong khung


def release_document() -> None:
    """Đóng tài liệu đang giữ để file có thể được đổi tên/nén/xoá."""
    with _LOCK:
        doc = _STATE["doc"]
        _STATE["doc"], _STATE["key"] = None, None
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass


class _Prefs(QObject):
    """Cài đặt dùng chung cho mọi khung xem trước: có hỏi xác nhận trước khi xoá / cắt không (lưu trong QSettings)."""
    confirmChanged = Signal(bool)

    def __init__(self):
        super().__init__()
        try:
            v = make_settings().value("confirm_delete", True)
        except Exception:
            v = True
        self._confirm = v in (True, "true", "1", 1)

    @property
    def confirm(self) -> bool:
        return self._confirm

    def set_confirm(self, on: bool) -> None:
        if on != self._confirm:
            self._confirm = bool(on)
            try:
                make_settings().setValue("confirm_delete", self._confirm)
            except Exception:
                pass
            self.confirmChanged.emit(self._confirm)


_PREFS: "_Prefs | None" = None


def prefs() -> _Prefs:
    global _PREFS
    if _PREFS is None:
        _PREFS = _Prefs()
    return _PREFS


class _CropOverlay(QWidget):
    """Khung cắt kéo được phủ lên trang: kéo 4 góc / 4 cạnh để đổi cỡ, kéo bên trong để dời, kéo ra ngoài để vẽ khung mới.
    Toạ độ lưu theo TỈ LỆ 0..1 của trang đang hiển thị."""
    changed = Signal()
    HANDLES = ("tl", "t", "tr", "l", "r", "bl", "b", "br")
    MIN = 0.03

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.rect_n = [0.04, 0.04, 0.96, 0.96]
        self._drag = None

    def reset(self) -> None:
        self.rect_n = [0.04, 0.04, 0.96, 0.96]
        self.update()
        self.changed.emit()

    def _px(self) -> QRectF:
        w, h = max(1, self.width()), max(1, self.height())
        x0, y0, x1, y1 = self.rect_n
        return QRectF(x0 * w, y0 * h, (x1 - x0) * w, (y1 - y0) * h)

    def _points(self) -> dict:
        r = self._px()
        cx, cy = r.center().x(), r.center().y()
        return {"tl": QPointF(r.left(), r.top()), "t": QPointF(cx, r.top()), "tr": QPointF(r.right(), r.top()),
                "l": QPointF(r.left(), cy), "r": QPointF(r.right(), cy), "bl": QPointF(r.left(), r.bottom()),
                "b": QPointF(cx, r.bottom()), "br": QPointF(r.right(), r.bottom())}

    def _hit(self, pos) -> str:
        for name, pt in self._points().items():
            if abs(pos.x() - pt.x()) <= 9 and abs(pos.y() - pt.y()) <= 9:
                return name
        return "move" if self._px().contains(QPointF(pos)) else "new"

    def paintEvent(self, _):
        p = QPainter(self)
        r, full = self._px(), QRectF(self.rect())
        dim = QColor(0, 0, 0, 120)
        p.fillRect(QRectF(0, 0, full.width(), r.top()), dim)
        p.fillRect(QRectF(0, r.bottom(), full.width(), full.height() - r.bottom()), dim)
        p.fillRect(QRectF(0, r.top(), r.left(), r.height()), dim)
        p.fillRect(QRectF(r.right(), r.top(), full.width() - r.right(), r.height()), dim)
        pen = QPen(QColor("#2563EB"), 2, Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        p.setPen(QPen(QColor("#2563EB"), 1.5))
        p.setBrush(QColor("#FFFFFF"))
        for pt in self._points().values():
            p.drawRect(QRectF(pt.x() - 5, pt.y() - 5, 10, 10))

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        hit = self._hit(pos)
        self._drag = (hit, pos, list(self.rect_n))
        if hit == "new":
            self._drag = ("new", pos, [self._nx(pos.x()), self._ny(pos.y())] * 2)

    def _nx(self, x: float) -> float:
        return min(1.0, max(0.0, x / max(1, self.width())))

    def _ny(self, y: float) -> float:
        return min(1.0, max(0.0, y / max(1, self.height())))

    def mouseMoveEvent(self, e):
        pos = e.position()
        if not self._drag:
            cur = {"tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
                   "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor, "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
                   "move": Qt.SizeAllCursor, "new": Qt.CrossCursor}[self._hit(pos)]
            self.setCursor(QCursor(cur))
            return
        mode, p0, r0 = self._drag
        dx = (pos.x() - p0.x()) / max(1, self.width())
        dy = (pos.y() - p0.y()) / max(1, self.height())
        x0, y0, x1, y1 = r0
        if mode == "move":
            w, h = x1 - x0, y1 - y0
            nx0 = min(1 - w, max(0.0, x0 + dx))
            ny0 = min(1 - h, max(0.0, y0 + dy))
            x0, y0, x1, y1 = nx0, ny0, nx0 + w, ny0 + h
        elif mode == "new":
            ax, ay = r0[0], r0[1]
            bx, by = self._nx(pos.x()), self._ny(pos.y())
            x0, x1, y0, y1 = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
        else:
            if "l" in mode:
                x0 = min(x1 - self.MIN, max(0.0, x0 + dx))
            if "r" in mode:
                x1 = max(x0 + self.MIN, min(1.0, x1 + dx))
            if mode in ("tl", "t", "tr"):
                y0 = min(y1 - self.MIN, max(0.0, y0 + dy))
            if mode in ("bl", "b", "br"):
                y1 = max(y0 + self.MIN, min(1.0, y1 + dy))
        self.rect_n = [x0, y0, x1, y1]
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, e):
        if self._drag and self._drag[0] == "new":
            x0, y0, x1, y1 = self.rect_n
            if x1 - x0 < self.MIN or y1 - y0 < self.MIN:          # chỉ bấm, không kéo → giữ khung cũ
                self.rect_n = [0.04, 0.04, 0.96, 0.96]
                self.update()
        self._drag = None
        self.changed.emit()


class _Signals(QObject):
    done = Signal(int, QImage, int, float, str)   # req, ảnh, tổng trang, zoom (theo điểm ảnh logic), lỗi


class _Job(QRunnable):
    def __init__(self, req, path, page, zoom, fit, box_w, box_h, rotation, dpr, sig):
        super().__init__()
        self.req, self.path, self.page, self.zoom, self.fit = req, path, page, zoom, fit
        self.box_w, self.box_h, self.rotation, self.dpr, self.sig = box_w, box_h, rotation, dpr, sig

    def run(self):
        img, total, zoom, err = QImage(), 0, self.zoom, ""
        with _LOCK:
            try:
                key = (self.path, os.path.getmtime(self.path))
                if _STATE["key"] != key:
                    if _STATE["doc"] is not None:
                        _STATE["doc"].close()
                        _STATE["doc"] = None
                    if os.path.getsize(self.path) <= _MAX_STREAM:
                        with open(self.path, "rb") as fh:   # đọc vào RAM: không khoá file trên đĩa
                            _STATE["doc"] = fitz.open(stream=fh.read(), filetype="pdf")
                    else:
                        _STATE["doc"] = fitz.open(self.path)
                    _STATE["key"] = key
                doc = _STATE["doc"]
                if doc.needs_pass:
                    raise RuntimeError("File có mật khẩu – không xem trước được")
                total = doc.page_count
                if total == 0:
                    raise RuntimeError("File không có trang nào")
                pg = doc[max(0, min(self.page, total - 1))]
                rect = pg.rect
                pw, ph = (rect.height, rect.width) if self.rotation % 180 else (rect.width, rect.height)
                z_page = min((self.box_w - _MARGIN) / max(1.0, pw), (self.box_h - _MARGIN) / max(1.0, ph))
                z_width = (self.box_w - _MARGIN - 12) / max(1.0, pw)   # chừa chỗ thanh cuộn
                if self.fit == FIT_PAGE:
                    zoom = z_page
                elif self.fit == FIT_WIDTH:
                    zoom = z_width
                elif self.fit == FIT_AUTO:
                    zoom = z_page if z_page >= _AUTO_RATIO * z_width else z_width
                zoom = max(0.05, min(8.0, zoom))
                scale = zoom * self.dpr                        # render đúng mật độ điểm ảnh màn hình → nét
                pix = pg.get_pixmap(matrix=fitz.Matrix(scale, scale).prerotate(self.rotation), alpha=False,
                                    annots=True)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
                img.setDevicePixelRatio(self.dpr)
            except Exception as e:
                err = str(e) or "Không xem trước được file này"
                _STATE["doc"], _STATE["key"] = None, None
        self.sig.done.emit(self.req, img, total, zoom, err)


class _Area(QScrollArea):
    """Vùng hiển thị: Ctrl + lăn chuột để phóng to/thu nhỏ; báo khi đổi kích thước."""
    zoomWheel = Signal(int)
    pageWheel = Signal(int)
    resized = Signal()

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        if e.modifiers() & Qt.ControlModifier:
            self.zoomWheel.emit(1 if dy > 0 else -1)
            e.accept()
            return
        bar = self.verticalScrollBar()
        if dy < 0 and bar.value() >= bar.maximum():
            self.pageWheel.emit(1)            # đã ở cuối trang → sang trang sau
            e.accept()
            return
        if dy > 0 and bar.value() <= bar.minimum():
            self.pageWheel.emit(-1)           # đã ở đầu trang → về trang trước
            e.accept()
            return
        super().wheelEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.resized.emit()


class PreviewPane(QWidget):
    shown = Signal()                     # vừa chọn xem 1 file (khung gập tự mở ra)
    fileEdited = Signal(str)             # file vừa bị sửa trực tiếp (xoá trang / cắt viền / hoàn tác): các tab cập nhật dòng
    pageDeleted = Signal(str, int)       # (file, chỉ số trang gốc từ 0) – phát cho TỪNG trang đã xoá, từ cuối về đầu
    cropped = Signal(str)                # đã cắt viền file

    def __init__(self, parent: QWidget | None = None, title: str = "Xem trước file PDF"):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.sig = _Signals()
        self.sig.done.connect(self._on_done)
        self.path = ""
        self.page = 0
        self.total = 0
        self.zoom = 1.0
        self.fit = FIT_PAGE
        self.rotation = 0
        self._req = 0
        self._to_bottom = False
        # tab có cách xoá riêng (vd Kiểm tra trang: đánh dấu rồi xoá khi "Sửa") gán hàm nhận (đường dẫn, trang) → True nếu đã xử lý
        self.delete_handler = None
        self.setFocusPolicy(Qt.StrongFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        if title:
            cap = QLabel(title)
            cap.setStyleSheet("font-weight:bold;color:#1E3A8A;")
            lay.addWidget(cap)

        # vùng hiển thị (giống Hồ sơ 1361: nền trắng, viền nét đứt, trang vừa khít khung)
        self.area = _Area()
        self.area.setObjectName("PreviewArea")
        self.area.setWidgetResizable(True)
        self.area.zoomWheel.connect(lambda d: self.set_zoom(self.zoom * (1.15 if d > 0 else 1 / 1.15)))
        self.area.pageWheel.connect(self._wheel_page)
        self.area.resized.connect(lambda: self._resize_t.start())
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(4, 4, 4, 4)
        hl.setAlignment(Qt.AlignCenter)
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.canvas.setStyleSheet("border:1px solid #E2E8F0;background:#FFFFFF;")
        self.overlay = _CropOverlay(self.canvas)
        self.overlay.hide()
        self.msg = QLabel()
        self.msg.setAlignment(Qt.AlignCenter)
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet("color:#64748B;font-size:9pt;background:transparent;border:none;")
        hl.addWidget(self.canvas, 0, Qt.AlignCenter)
        hl.addWidget(self.msg, 0, Qt.AlignCenter)
        self.area.setWidget(holder)
        lay.addWidget(self.area, 1)

        # tên file (như 1361) + điều hướng trang gọn 1 hàng
        self.lbl_file = QLabel("Chưa chọn file")
        self.lbl_file.setAlignment(Qt.AlignCenter)
        self.lbl_file.setStyleSheet("font-size:8.5pt;color:#334155;font-weight:600;")
        self.lbl_file.setWordWrap(True)
        lay.addWidget(self.lbl_file)
        bar = QHBoxLayout()
        bar.setSpacing(3)
        self.btn_prev = button("◀", "light", lambda: self.goto(self.page - 1), "Trang trước (PageUp / lăn chuột)", "sm")
        self.spin = QSpinBox()
        self.spin.setMinimum(1)
        self.spin.setFixedWidth(48)
        self.spin.setAlignment(Qt.AlignCenter)
        self.spin.setButtonSymbols(QSpinBox.NoButtons)
        self.spin.editingFinished.connect(lambda: self.goto(self.spin.value() - 1))
        self.lbl_total = QLabel("/ 0")
        self.lbl_total.setStyleSheet("font-weight:600;color:#334155")
        self.btn_next = button("▶", "light", lambda: self.goto(self.page + 1), "Trang sau (PageDown / lăn chuột)", "sm")
        for w in (self.btn_prev, self.spin, self.lbl_total, self.btn_next):
            bar.addWidget(w)
        bar.addStretch(1)
        self.lbl_zoom = QLabel("")
        self.lbl_zoom.setObjectName("Hint")
        bar.addWidget(self.lbl_zoom)
        self.btn_out = button("−", "light", lambda: self.set_zoom(self.zoom / 1.2), "Thu nhỏ (Ctrl + lăn chuột)", "sm")
        self.btn_in = button("+", "light", lambda: self.set_zoom(self.zoom * 1.2), "Phóng to (Ctrl + lăn chuột)", "sm")
        self.btn_page = button("⛶", "light", lambda: self.set_fit(FIT_PAGE), "Vừa trọn trang trong khung", "sm")
        self.btn_width = button("⇔", "light", lambda: self.set_fit(FIT_WIDTH), "Vừa chiều ngang khung", "sm")
        for w in (self.btn_out, self.btn_in, self.btn_page, self.btn_width):
            bar.addWidget(w)
        lay.addLayout(bar)
        self.btn_first = self.btn_last = self.btn_auto = None

        rot = QHBoxLayout()
        rot.setSpacing(4)
        self.btn_rl = button("↶ Xoay trái", "primary", lambda: self.rotate(-90), "Chỉ xoay khi xem, không sửa file", "sm")
        self.btn_r180 = button("🔄 Xoay 180°", "primary", lambda: self.rotate(180), "Chỉ xoay khi xem, không sửa file", "sm")
        self.btn_rr = button("↷ Xoay phải", "primary", lambda: self.rotate(90), "Chỉ xoay khi xem, không sửa file", "sm")
        for b in (self.btn_rl, self.btn_r180, self.btn_rr):
            rot.addWidget(b, 1)
        lay.addLayout(rot)
        er = QHBoxLayout()
        er.setSpacing(4)
        self.btn_del = button("🗑 Xoá trang này", "danger", self.delete_current,
                              "Xoá trang đang xem khỏi file. Trang xoá + bản gốc được cất vào Thùng rác (khôi phục được). "
                              "Phím tắt: Delete", "sm")
        self.btn_crop = button("✂ Cắt viền", "violet", None,
                               "Kéo khung để cắt bỏ phần thừa của trang (vd viền đen khi scan). Không nén lại ảnh.", "sm")
        self.btn_crop.setCheckable(True)
        self.btn_crop.toggled.connect(self.toggle_crop)
        er.addWidget(self.btn_del, 1)
        er.addWidget(self.btn_crop, 1)
        lay.addLayout(er)
        self.ck_confirm = QCheckBox("Hỏi xác nhận trước khi xoá / cắt")
        self.ck_confirm.setToolTip("Tắt = xoá / cắt ngay khi bấm nút, không hỏi lại (vẫn cất vào Thùng rác để hoàn tác; "
                                   "file đã ký số luôn được hỏi).")
        self.ck_confirm.setChecked(prefs().confirm)
        self.ck_confirm.toggled.connect(prefs().set_confirm)
        prefs().confirmChanged.connect(self._sync_confirm)
        lay.addWidget(self.ck_confirm)
        # thanh hoàn tác (hiện sau khi xoá / cắt)
        self.undo_bar = QWidget()
        ub = QHBoxLayout(self.undo_bar)
        ub.setContentsMargins(0, 0, 0, 0)
        self.lbl_undo = QLabel("")
        self.lbl_undo.setWordWrap(True)
        self.lbl_undo.setStyleSheet("color:#15803D;font-weight:700;")
        ub.addWidget(self.lbl_undo, 1)
        self.btn_undo = button("↩ Hoàn tác", "warning", self._do_undo, "Trả lại như trước khi xoá / cắt", "sm")
        ub.addWidget(self.btn_undo)
        self.undo_bar.hide()
        lay.addWidget(self.undo_bar)
        self._undo_stack: list = []                 # [(nhãn, hàm hoàn tác, đường dẫn)] – hoàn tác được nhiều bước, KHÔNG tự ẩn
        # thanh cắt viền (hiện khi bật chế độ cắt)
        self.crop_bar = QWidget()
        cb = QVBoxLayout(self.crop_bar)
        cb.setContentsMargins(0, 0, 0, 0)
        cb.setSpacing(3)
        self.lbl_crop = QLabel("✂ Kéo 4 góc / 4 cạnh của khung để chọn phần GIỮ LẠI (ngoài khung sẽ bị cắt). "
                               "Kéo bên trong để dời khung.")
        self.lbl_crop.setWordWrap(True)
        self.lbl_crop.setObjectName("Hint")
        cb.addWidget(self.lbl_crop)
        self.btn_crop_one = button("✔ Cắt trang này", "success", self.apply_crop,
                                   "Cắt trang đang xem theo khung (có sao lưu, hoàn tác được)")
        self.btn_crop_undo = button("↩ Hoàn tác", "warning", self._do_undo, "Hoàn tác lần cắt / xoá gần nhất", "sm")
        self.btn_crop_undo.setEnabled(False)
        self.btn_crop_reset = button("↺ Đặt lại khung", "light", lambda: self.overlay.reset(), "Đặt lại khung", "sm")
        self.btn_crop_cancel = button("✖ Huỷ cắt", "light", lambda: self.btn_crop.setChecked(False),
                                      "Thoát chế độ cắt", "sm")
        cr = QHBoxLayout()
        cr.setSpacing(4)
        cr.addWidget(self.btn_crop_one, 2)
        cr.addWidget(self.btn_crop_undo, 1)
        cb.addLayout(cr)
        cr2 = QHBoxLayout()
        cr2.setSpacing(4)
        cr2.addWidget(self.btn_crop_reset, 1)
        cr2.addWidget(self.btn_crop_cancel, 1)
        cb.addLayout(cr2)
        self.crop_bar.hide()
        lay.addWidget(self.crop_bar)
        self.btn_open = button("📂 Mở file PDF này", "primary", self.open_external, "Mở bằng phần mềm đọc PDF mặc định")
        lay.addWidget(self.btn_open)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(90)
        self._debounce.timeout.connect(self._render)
        self._resize_t = QTimer(self)
        self._resize_t.setSingleShot(True)
        self._resize_t.setInterval(150)
        self._resize_t.timeout.connect(lambda: self.path and self.fit != FIT_NONE and self._render())
        self.clear()
        self._mark_fit()

    # ------------------------------------------------------------------ điều khiển
    def _enable(self, on: bool) -> None:
        for w in (self.btn_prev, self.btn_next, self.spin, self.btn_out, self.btn_in, self.btn_page, self.btn_width,
                  self.btn_rl, self.btn_r180, self.btn_rr, self.btn_open, self.btn_del, self.btn_crop):
            w.setEnabled(on)

    def show_file(self, path: str, keep_view: bool = False) -> None:
        """keep_view: giữ trang / thu phóng / xoay hiện tại (so 2 bản của cùng 1 tài liệu, vd gốc ↔ đã nén);
        cùng đường dẫn thì vẽ lại (file có thể vừa bị ghi đè)."""
        if path == self.path:
            if keep_view:
                self._debounce.start()
            return
        if keep_view and self.path:
            self.path = path
        else:
            self.path, self.page, self.rotation = path, 0, 0
            self.fit = FIT_PAGE
            self._mark_fit()
        self.lbl_file.setText(os.path.basename(path))
        self.lbl_file.setToolTip(path)
        self.btn_crop.setChecked(False)
        self._undo_stack.clear()
        self._refresh_undo()
        self._enable(True)
        self._debounce.start()
        self.shown.emit()

    def clear(self, message: str = "Vui lòng chọn 1 file .pdf\ntrong danh sách để xem trước") -> None:
        self.path = ""
        self._req += 1
        self.total = 0
        self.lbl_total.setText("/ 0")
        self.lbl_zoom.setText("")
        self.lbl_file.setText("Chưa chọn file")
        self.lbl_file.setToolTip("")
        self.btn_crop.setChecked(False)
        self._show_message(message)
        self._enable(False)

    def release(self) -> None:
        """Giải phóng file đang xem (gọi trước khi đổi tên, nén, xoá)."""
        self._req += 1
        release_document()

    def refresh(self) -> None:
        if self.path:
            self._render()

    def goto(self, page: int) -> None:
        if 0 <= page and (not self.total or page < self.total) and page != self.page:   # file vừa mở: chưa biết tổng
            self.page = page
            self._debounce.start()
        self.spin.setValue(self.page + 1)

    def set_zoom(self, z: float) -> None:
        if not self.path:
            return
        self.fit = FIT_NONE
        self._mark_fit()
        self.zoom = max(0.1, min(8.0, z))
        self._debounce.start()

    def set_fit(self, mode: str) -> None:
        self.fit = mode
        self._mark_fit()
        self._debounce.start()

    def _mark_fit(self) -> None:
        for b, m in ((self.btn_page, FIT_PAGE), (self.btn_width, FIT_WIDTH)):
            b.setObjectName("primary" if self.fit == m else "light")
            b.style().unpolish(b)
            b.style().polish(b)

    def _wheel_page(self, d: int) -> None:
        if not self.total:
            return
        nxt = self.page + d
        if 0 <= nxt < self.total:
            self._to_bottom = d < 0          # về trang trước thì hiện phần cuối trang đó
            self.goto(nxt)

    def rotate(self, deg: int) -> None:
        self.rotation = (self.rotation + deg) % 360
        self._debounce.start()

    def set_readonly(self) -> None:
        """Chỉ xem (vd trong Thùng rác): ẩn nút xoá / cắt / xoay."""
        for w in (self.btn_del, self.btn_crop, self.ck_confirm, self.btn_rl, self.btn_r180, self.btn_rr):
            w.hide()
        self.btn_del.setEnabled(False)
        self.btn_crop.setEnabled(False)

    # ------------------------------------------------------------------ cài đặt / hoàn tác
    def _sync_confirm(self, on: bool) -> None:
        if self.ck_confirm.isChecked() != on:
            self.ck_confirm.blockSignals(True)
            self.ck_confirm.setChecked(on)
            self.ck_confirm.blockSignals(False)

    def _show_undo(self, text: str, fn, path: str = "") -> None:
        self._undo_stack.append((text, fn, path or self.path))
        self._refresh_undo()

    def _refresh_undo(self) -> None:
        if not self._undo_stack:
            self.undo_bar.hide()
            self.btn_crop_undo.setEnabled(False)
            return
        text = self._undo_stack[-1][0]
        more = len(self._undo_stack) - 1
        self.lbl_undo.setText(text + (f"  (còn {more} bước trước đó)" if more else ""))
        self.undo_bar.show()
        self.btn_crop_undo.setEnabled(True)

    def _do_undo(self) -> None:
        if not self._undo_stack:
            return
        _, fn, path = self._undo_stack.pop()
        self._refresh_undo()
        path = path or self.path
        self.release()
        ok, msg = fn()
        if self.path:
            self.refresh()
        elif path and ok:
            self.show_file(path)
        if ok:
            self.fileEdited.emit(path)
        else:
            QMessageBox.warning(self, "Hoàn tác", msg)

    def _confirm(self, title: str, text: str, signed: bool) -> bool:
        """Hỏi xác nhận nếu đang bật; file đã ký số luôn hỏi (mất hiệu lực chữ ký)."""
        if not prefs().confirm and not signed:
            return True
        return QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes

    def _is_signed(self, path: str) -> bool:
        from ..core.signature import inspect_signatures
        try:
            with open(path, "rb") as fh:
                return bool(inspect_signatures(fh.read()))
        except Exception:
            return False

    # ------------------------------------------------------------------ cắt viền
    def toggle_crop(self, on: bool) -> None:
        if on and (not self.path or not self.total):
            self.btn_crop.setChecked(False)
            return
        if on and self.rotation % 360:
            self.rotation = 0                       # cắt theo trang gốc: đưa xem trước về hướng gốc
            self._debounce.start()
        self.crop_bar.setVisible(on)
        self.btn_crop.setVisible(not on)            # đang cắt viền thì ẩn nút «Cắt viền» (thoát bằng «Huỷ cắt» / «Cắt trang này»)
        self.overlay.setVisible(on)
        if on:
            self.overlay.reset()
            self._place_overlay()
        for b in (self.btn_rl, self.btn_r180, self.btn_rr):
            b.setEnabled(not on)

    def _place_overlay(self) -> None:
        self.overlay.setGeometry(0, 0, self.canvas.width(), self.canvas.height())
        self.overlay.raise_()

    def apply_crop(self) -> None:
        if not self.path or not self.total:
            return
        r = tuple(round(v, 4) for v in self.overlay.rect_n)
        if r[0] <= 0.002 and r[1] <= 0.002 and r[2] >= 0.998 and r[3] >= 0.998:
            QMessageBox.information(self, "Cắt viền", "Khung đang bao trọn cả trang – hãy kéo các cạnh vào trong.")
            return
        from ..core import pagecheck
        path, name = self.path, os.path.basename(self.path)
        pages = [self.page]
        what = f"trang {self.page + 1}"
        text = (f"Cắt viền {what} của “{name}” theo khung đã chọn?\n\nPhần ngoài khung bị ẩn (không nén lại ảnh). "
                "Bản gốc được sao lưu vào Thùng rác của app.")
        signed = self._is_signed(path)
        if signed:
            text += "\n\n⚠ File ĐÃ KÝ SỐ – cắt sẽ làm mất hiệu lực chữ ký."
        if not self._confirm("Cắt viền", text, signed):
            return
        self.release()
        try:
            prev = pagecheck.get_cropboxes(path, pages)
            pagecheck.crop_pages(path, {i: r for i in pages})
        except Exception as e:
            QMessageBox.warning(self, "Cắt viền", f"Không cắt được: {e}")
            self.refresh()
            return
        self.btn_crop.setChecked(False)
        self.refresh()
        self.cropped.emit(path)
        self.fileEdited.emit(path)
        self._show_undo(f"✂ Đã cắt viền {what}.", lambda: self._undo_crop(path, prev), path)

    @staticmethod
    def _undo_crop(path: str, prev: dict):
        from ..core import pagecheck
        try:
            pagecheck.set_cropboxes(path, prev)
            return True, ""
        except Exception as e:
            return False, f"Không hoàn tác được: {e}"

    def delete_current(self) -> None:
        """Xoá trang đang xem. Tab nào có `delete_handler` thì để tab đó xử lý; mặc định: hỏi → sao lưu → xoá thật."""
        if not self.path or not self.total:
            return
        if self.delete_handler and self.delete_handler(self.path, self.page):
            return
        self.delete_pages_direct(self.path, [self.page])

    def delete_pages_direct(self, path: str, pages: list) -> bool:
        """Xoá THẬT các trang (chỉ số từ 0) của `path`: hỏi (nếu đang bật) → cất vào Thùng rác + sao lưu → ghi file → báo các tab.
        Dùng chung cho nút 🗑 ở khung xem trước và nút «Xoá ngay» của tab Kiểm tra trang."""
        from ..core import pagecheck, trash
        pages = sorted(set(pages))
        try:
            with fitz.open(path) as d:
                total = d.page_count
        except Exception as e:
            QMessageBox.warning(self, "Xoá trang", f"Không mở được file: {e}")
            return False
        if not pages or any(not 0 <= i < total for i in pages):
            return False
        if len(pages) >= total:
            QMessageBox.warning(self, "Xoá trang", "Không thể xoá hết mọi trang của file.")
            return False
        name = os.path.basename(path)
        label = f"trang {pages[0] + 1}" if len(pages) == 1 else f"{len(pages)} trang ({', '.join(str(i + 1) for i in pages[:8])}" \
            + ("…)" if len(pages) > 8 else ")")
        signed = self._is_signed(path)
        text = (f"Xoá {label} của “{name}” (hiện {total} trang)?\n\nTrang xoá và bản gốc được cất vào Thùng rác "
                "(khôi phục được từ tab Thùng rác)."
                + ("\n\n⚠ File ĐÃ KÝ SỐ – xoá trang sẽ làm mất hiệu lực chữ ký." if signed else ""))
        if not self._confirm("Xoá trang", text, signed):
            return False
        mine = os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(self.path or ""))
        self.release()
        try:
            pagecheck.delete_pages(path, pages, backup=True)
        except Exception as e:
            QMessageBox.warning(self, "Xoá trang", f"Không xoá được: {e}")
            if mine:
                self.refresh()
            return False
        for i in reversed(pages):                       # từ cuối về đầu để chỉ số các trang còn lại không lệch
            self.pageDeleted.emit(path, i)
        if mine:
            self.refresh()
        self.fileEdited.emit(path)
        ent = next((e for e in trash.list_entries() if e.kind == trash.KIND_PAGES and e.orig_path == os.path.abspath(path)),
                   None)
        if ent is not None:
            self._show_undo(f"🗑 Đã xoá {label}.", lambda: self._undo_delete(ent), path)
        return True

    @staticmethod
    def _undo_delete(ent):
        from ..core import trash
        ok, msg, _ = trash.restore(ent)
        return ok, msg

    def open_external(self) -> None:
        if self.path and os.path.exists(self.path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_PageDown, Qt.Key_Right):
            self.goto(self.page + 1)
        elif k in (Qt.Key_PageUp, Qt.Key_Left):
            self.goto(self.page - 1)
        elif k == Qt.Key_Home:
            self.goto(0)
        elif k == Qt.Key_End:
            self.goto(self.total - 1)
        elif k == Qt.Key_Delete:
            self.delete_current()
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------------ render
    def _render(self) -> None:
        if not self.path:
            return
        self._req += 1
        vp = self.area.viewport()
        dpr = max(1.0, self.devicePixelRatioF())
        self.pool.start(_Job(self._req, self.path, self.page, self.zoom, self.fit,
                             vp.width() - 8, vp.height() - 8, self.rotation, dpr, self.sig))

    def _show_message(self, text: str) -> None:
        self.canvas.hide()
        self.msg.setText(text)
        self.msg.setFixedWidth(max(220, min(420, self.area.viewport().width() - 40)))
        self.msg.show()

    def _on_done(self, req: int, img: QImage, total: int, zoom: float, err: str) -> None:
        if req != self._req:
            return
        if err:
            self._show_message("⚠ " + err)
            return
        self.total, self.zoom = total, zoom
        self.page = max(0, min(self.page, total - 1))
        self.spin.setMaximum(max(1, total))
        self.spin.setValue(self.page + 1)
        self.lbl_total.setText(f"/ {total}")
        self.lbl_zoom.setText(f"{zoom * 100 / (96 / 72):.0f}%")
        self.btn_prev.setEnabled(self.page > 0)
        self.btn_next.setEnabled(self.page < total - 1)
        self.msg.hide()
        pm = QPixmap.fromImage(img)
        self.canvas.setPixmap(pm)
        self.canvas.setFixedSize(pm.deviceIndependentSize().toSize())
        self.canvas.show()
        self._place_overlay()
        bar = self.area.verticalScrollBar()
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum() if self._to_bottom else 0))
        self._to_bottom = False


def make_collapsible(split: QSplitter, preview: PreviewPane, opened: int = 400):
    """Khung xem trước bên phải GẬP được: mặc định gập để bảng chiếm hết bề ngang (thấy đủ cột Trạng thái / Vấn đề);
    chọn 1 file thì tự mở, bấm nút để gập lại (người dùng đã gập thì không tự mở nữa). Trả về nút bật / tắt để đặt vào hàng nút."""
    split.setChildrenCollapsible(True)
    split.setCollapsible(0, False)
    split.setCollapsible(1, True)
    btn = button("👁 Xem trước", "light", None, "Hiện / ẩn khung xem trước PDF (tự mở khi chọn 1 file)", "sm")
    btn.setCheckable(True)
    state = {"manual_closed": False}

    def is_open() -> bool:
        return split.sizes()[1] > 0

    def sync(*_):
        btn.blockSignals(True)
        btn.setChecked(is_open())
        btn.blockSignals(False)

    def set_open(on: bool):
        total = max(sum(split.sizes()), opened + 400)
        split.setSizes([total - opened, opened] if on else [total, 0])
        sync()

    def toggled(on: bool):
        state["manual_closed"] = not on
        set_open(on)

    def auto_open():
        if not is_open() and not state["manual_closed"]:
            set_open(True)

    btn.toggled.connect(toggled)
    split.splitterMoved.connect(sync)
    preview.shown.connect(auto_open)
    split.setSizes([10000, 0])
    sync()
    btn.set_open = set_open
    return btn
