"""Hình minh hoạ vẽ bằng QPainter (không cần file ảnh): các kiểu tách trang, kiểm tra trang.
Dùng cho thẻ chọn kiểu tách (tab Tách trang) và tab Hướng dẫn. Nền trong suốt, trang giấy trắng → hợp cả
giao diện sáng lẫn tối."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen

INK, PAPER, EDGE, CUT, ARROW, OK = "#1E293B", "#FFFFFF", "#64748B", "#DC2626", "#2563EB", "#15803D"


def _page(p: QPainter, r: QRectF, text: str = "", upside: bool = False, color: str = INK, lines: bool = True,
          rot90: bool = False):
    p.setPen(QPen(QColor(EDGE), 1.4))
    p.setBrush(QColor(PAPER))
    p.drawRoundedRect(r, 2, 2)
    p.save()
    p.translate(r.center())
    if upside:
        p.rotate(180)
    if rot90:
        p.rotate(90)
    w, h = (r.height(), r.width()) if rot90 else (r.width(), r.height())
    if lines:
        p.setPen(QPen(QColor("#CBD5E1"), 1.6))
        y = -h / 2 + h * 0.16
        while y < h / 2 - h * 0.30:
            p.drawLine(QPointF(-w / 2 + w * 0.16, y), QPointF(w / 2 - w * 0.16, y))
            y += max(4.0, h * 0.09)
    if text:
        f = QFont("Segoe UI", 1)
        f.setPixelSize(int(max(9, min(w, h) * 0.36)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(QRectF(-w / 2, h / 2 - h * 0.34, w, h * 0.3), Qt.AlignCenter, text)
    p.restore()


def _arrow(p: QPainter, x0: float, x1: float, y: float, color: str = ARROW):
    p.setPen(QPen(QColor(color), 3, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(x0, y), QPointF(x1 - 6, y))
    path = QPainterPath(QPointF(x1, y))
    path.lineTo(x1 - 10, y - 7)
    path.lineTo(x1 - 10, y + 7)
    path.closeSubpath()
    p.fillPath(path, QColor(color))


def _cut(p: QPainter, a: QPointF, b: QPointF):
    p.setPen(QPen(QColor(CUT), 2, Qt.DashLine))
    p.drawLine(a, b)


def _label(p: QPainter, r: QRectF, text: str, color: str = EDGE, px: int = 11):
    f = QFont("Segoe UI", 1)
    f.setPixelSize(px)
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(r, Qt.AlignCenter, text)


def _draw(kind: str, p: QPainter, W: float, H: float, captions: bool):
    cy = H / 2 - (8 if captions else 0)
    if kind == "a3_to_a4":                       # A3 ngang có 2 trang → cắt đôi → 2 trang A4
        src = QRectF(W * 0.03, cy - H * 0.27, W * 0.38, H * 0.54)
        _page(p, QRectF(src.x(), src.y(), src.width() / 2, src.height()), "1")
        _page(p, QRectF(src.center().x(), src.y(), src.width() / 2, src.height()), "2")
        _cut(p, QPointF(src.center().x(), src.y() - 5), QPointF(src.center().x(), src.bottom() + 5))
        _arrow(p, W * 0.45, W * 0.57, cy)
        ph = min(H * 0.58, (W * 0.37 - 8) / 2 * 1.414)
        pw = ph / 1.414
        _page(p, QRectF(W * 0.61, cy - ph / 2, pw, ph), "1")
        _page(p, QRectF(W * 0.61 + pw + 8, cy - ph / 2, pw, ph), "2")
        if captions:
            _label(p, QRectF(0, H - 18, W * 0.44, 16), "A3 ngang (scan)")
            _label(p, QRectF(W * 0.56, H - 18, W * 0.44, 16), "2 trang A4")
    elif kind == "a4_to_a4":                     # A4 dọc in 2 nửa → cắt ngang → phóng mỗi nửa thành A4
        ph = min(H * 0.62, (W * 0.39 - 8) / 2 * 1.414)
        pw = ph / 1.414
        src = QRectF(W * 0.10, cy - ph / 2, pw, ph)
        _page(p, src, lines=False)
        _page(p, QRectF(src.x() + 3, src.y() + 3, pw - 6, ph / 2 - 6), "1")
        _page(p, QRectF(src.x() + 3, src.center().y() + 3, pw - 6, ph / 2 - 6), "2")
        _cut(p, QPointF(src.x() - 5, src.center().y()), QPointF(src.right() + 5, src.center().y()))
        _arrow(p, W * 0.40, W * 0.54, cy)
        _page(p, QRectF(W * 0.59, cy - ph / 2, pw, ph), "1")
        _page(p, QRectF(W * 0.59 + pw + 8, cy - ph / 2, pw, ph), "2")
        if captions:
            _label(p, QRectF(0, H - 18, W * 0.42, 16), "A4 có 2 nửa")
            _label(p, QRectF(W * 0.54, H - 18, W * 0.46, 16), "mỗi nửa thành 1 trang A4")
    elif kind == "booklet":                      # sổ gỡ ghim scan 2 mặt → đúng thứ tự 1, 2, 3, 4
        sw, sh = W * 0.30, H * 0.30
        for k, (a, b, up) in enumerate((("4", "1", False), ("2", "3", True))):
            r = QRectF(W * 0.03, cy - sh - 5 + k * (sh + 10), sw, sh)
            _page(p, QRectF(r.x(), r.y(), sw / 2, sh), a, upside=up, lines=False)
            _page(p, QRectF(r.center().x(), r.y(), sw / 2, sh), b, upside=up, lines=False)
            _cut(p, QPointF(r.center().x(), r.y() - 2), QPointF(r.center().x(), r.bottom() + 2))
        _arrow(p, W * 0.36, W * 0.47, cy)
        ph = min(H * 0.46, (W * 0.50 - 15) / 4 * 1.414)
        pw = ph / 1.414
        for k, t in enumerate("1234"):
            _page(p, QRectF(W * 0.49 + k * (pw + 5), cy - ph / 2, pw, ph), t, color=OK, lines=False)
        if captions:
            _label(p, QRectF(0, H - 18, W * 0.37, 16), "mặt trước / mặt sau")
            _label(p, QRectF(W * 0.50, H - 18, W * 0.50, 16), "đúng thứ tự trang")
    elif kind == "check":                        # trang ngược, xáo thứ tự → xoay + sắp xếp
        ph = min(H * 0.50, (W * 0.40 - 10) / 3 * 1.414)
        pw = ph / 1.414
        for k, (t, up) in enumerate((("2", False), ("1", True), ("3", False))):
            _page(p, QRectF(W * 0.02 + k * (pw + 5), cy - ph / 2, pw, ph), t, upside=up,
                  color=CUT if up else INK)
        _arrow(p, W * 0.45, W * 0.55, cy)
        for k, t in enumerate("123"):
            _page(p, QRectF(W * 0.58 + k * (pw + 5), cy - ph / 2, pw, ph), t, color=OK)
        if captions:
            _label(p, QRectF(0, H - 18, W * 0.42, 16), "ngược, sai thứ tự")
            _label(p, QRectF(W * 0.55, H - 18, W * 0.45, 16), "đã xoay & sắp xếp")


def image(kind: str, w: int = 300, h: int = 120, captions: bool = True, dpr: float = 2.0) -> QImage:
    img = QImage(int(w * dpr), int(h * dpr), QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    img.setDevicePixelRatio(dpr)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    _draw(kind, p, w, h, captions)
    p.end()
    return img


KINDS = ("a3_to_a4", "a4_to_a4", "booklet", "check")
