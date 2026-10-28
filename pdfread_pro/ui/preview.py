"""Khung xem trước PDF (kiểu Hồ sơ 1361): mặc định VỪA KHÍT TRANG trong khung, render nét theo DPI màn hình,
luồng nền + cache, chuyển trang, phóng to/thu nhỏ (Ctrl + lăn chuột), vừa chiều rộng, xoay khi xem."""
from __future__ import annotations

import os
import threading

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QSplitter,
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
                  self.btn_rl, self.btn_r180, self.btn_rr, self.btn_open):
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
