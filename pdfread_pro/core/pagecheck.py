"""KIỂM TRA TRANG: phát hiện trang bị ngược / nằm ngang, đọc số trang in (Windows OCR) để báo thiếu / trùng /
sai thứ tự, và tự sửa: xoay đúng chiều, sắp lại theo số trang, (tuỳ chọn) bỏ trang trắng.

Sửa KHÔNG nén lại ảnh: chỉ đổi thuộc tính xoay (/Rotate) và thứ tự trang → giữ nguyên chất lượng.
Chỉ tự sắp xếp khi đủ chắc chắn: đọc được số ở ≥ 1/2 số trang và không có số trùng (file ghép nhiều văn bản,
mỗi văn bản đánh số lại từ 1 → không sắp, chỉ báo để người dùng xem)."""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

DPI = 150                  # độ phân giải ảnh đọc OCR (như tab Tách trang)
CLUSTER_GAP = 5            # số lệch hẳn khỏi dãy (cách số gần nhất > 5) → coi là đọc nhầm
MIN_READ_RATIO = 0.5       # cần đọc được số ở ≥ 50% trang có chữ mới tự sắp xếp

ST_OK, ST_ISSUE, ST_ERROR, ST_FIXED = "ok", "issue", "error", "fixed"
ANGLE_TEXT = {0: "Thuận", 90: "Nằm ngang", 180: "Ngược 180°", 270: "Nằm ngang", None: "?"}


@dataclass
class PageInfo:
    angle: Optional[int] = None       # độ cần xoay (ngược chiều kim đồng hồ) để đứng thuận; None = không rõ
    number: Optional[int] = None      # số trang in đọc được
    blank: bool = False
    edited: bool = False              # người dùng đã sửa tay số / hướng


@dataclass
class CheckResult:
    path: str
    pages: List[PageInfo] = field(default_factory=list)
    error: str = ""
    seconds: float = 0.0


@dataclass
class Plan:
    order: List[int]                                   # chỉ số trang gốc theo thứ tự mới
    rotate: Dict[int, int]                             # trang gốc → độ xoay cần (ngược chiều kim đồng hồ)
    blanks: List[int] = field(default_factory=list)
    suspicious: List[int] = field(default_factory=list)   # trang có số lệch hẳn dãy (bỏ qua khi sắp)
    missing: List[int] = field(default_factory=list)      # số trang không thấy trong dãy
    duplicates: List[int] = field(default_factory=list)
    unread: int = 0                                     # trang có chữ nhưng không đọc được số
    read: int = 0
    reordered: bool = False
    sort_note: str = ""                                 # lý do không tự sắp xếp (nếu có)
    total: int = 0

    @property
    def removed(self) -> List[int]:
        return [i for i in range(self.total) if i not in set(self.order)]

    @property
    def needs_fix(self) -> bool:
        return bool(self.rotate) or self.reordered or bool(self.removed)

    def issues(self) -> List[str]:
        out = []
        if self.rotate:
            out.append(f"🔄 {len(self.rotate)} trang sai hướng ({_pages(self.rotate)})")
        if self.reordered:
            out.append("↕ Sai thứ tự trang")
        if self.missing:
            out.append(f"⚠ Không thấy số {_nums(self.missing)}")
        if self.duplicates:
            out.append(f"⚠ Trùng số {_nums(self.duplicates)}")
        if self.suspicious:
            out.append(f"❓ Số lạ ở trang {_pages(self.suspicious)}")
        if self.blanks:
            out.append(f"⬜ {len(self.blanks)} trang trắng ({_pages(self.blanks)})")
        return out


def _nums(ns) -> str:
    ns = sorted(ns)
    return ", ".join(map(str, ns[:8])) + ("…" if len(ns) > 8 else "")


def _pages(idx) -> str:
    return "tr. " + _nums(i + 1 for i in idx)


# ------------------------------------------------------------------ lập phương án sửa (không cần OCR)

def make_plan(pages: List[PageInfo], remove_blank: bool = False, rotate: bool = True, reorder: bool = True) -> Plan:
    n = len(pages)
    plan = Plan(order=list(range(n)), rotate={}, total=n)
    plan.blanks = [i for i, p in enumerate(pages) if p.blank]
    if rotate:
        plan.rotate = {i: p.angle for i, p in enumerate(pages) if p.angle and not p.blank}

    nums = {i: p.number for i, p in enumerate(pages) if p.number is not None and not p.blank}
    # bỏ số lệch hẳn khỏi dãy chính (OCR đọc nhầm, số hiệu văn bản…): gom các số gần nhau, giữ cụm nhiều trang nhất
    vals = sorted(set(nums.values()))
    groups: List[List[int]] = []
    for v in vals:
        if groups and v - groups[-1][-1] <= CLUSTER_GAP:
            groups[-1].append(v)
        else:
            groups.append([v])
    if groups:
        main = max(groups, key=lambda g: (sum(1 for x in nums.values() if x in g), -g[0]))
        keep = set(main)
        plan.suspicious = sorted(i for i, v in nums.items() if v not in keep)
        nums = {i: v for i, v in nums.items() if v in keep}
        seen: Dict[int, int] = {}
        for v in nums.values():
            seen[v] = seen.get(v, 0) + 1
        plan.duplicates = sorted(v for v, c in seen.items() if c > 1)
        plan.missing = [v for v in range(main[0], main[-1] + 1) if v not in seen]
    text_pages = n - len(plan.blanks)
    plan.read = len(nums)
    plan.unread = text_pages - plan.read

    order = [i for i in range(n) if not (remove_blank and pages[i].blank)]
    if remove_blank and not order:
        order = list(range(n))                       # mọi trang đều trắng → không bỏ
    if reorder and plan.read >= 2:
        if plan.duplicates:
            plan.sort_note = "Có số trang trùng (file ghép nhiều văn bản?) – không tự sắp xếp, hãy xem lại."
        elif plan.read < MIN_READ_RATIO * max(1, text_pages):
            plan.sort_note = f"Chỉ đọc được số ở {plan.read}/{text_pages} trang – không tự sắp xếp."
        else:
            # trang không có số đi liền sau trang đứng trước nó (bìa đầu file giữ ở đầu)
            keys, last = {}, -1
            for i in range(n):
                if i in nums:
                    last = nums[i]
                    keys[i] = (last, 0, i)
                else:
                    keys[i] = (last, 1, i)
            order = sorted(order, key=keys.__getitem__)
    plan.order = order
    plan.reordered = [i for i in order] != sorted(order)
    return plan


# ------------------------------------------------------------------ kiểm tra 1 file (chạy ở tiến trình con)

def _open(path: str) -> "fitz.Document":
    with open(path, "rb") as fh:
        doc = fitz.open(stream=fh.read(), filetype="pdf")      # đọc vào RAM: không khoá file
    if doc.needs_pass:
        raise ValueError("File có mật khẩu – không kiểm tra được.")
    if doc.page_count == 0:
        raise ValueError("File không có trang nào.")
    return doc


def _is_blank(page: "fitz.Page") -> bool:
    pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), colorspace=fitz.csGRAY, alpha=False)
    data = pix.samples
    return not data or sum(1 for v in data[::2] if v < 140) / (len(data) / 2) < 0.0002


def check_file(path: str, cancelled=None) -> CheckResult:
    from PIL import Image
    from . import pagenum
    t0 = time.monotonic()
    res = CheckResult(path)
    try:
        doc = _open(path)
        res.pages = [PageInfo(blank=_is_blank(pg)) for pg in doc]

        def images():
            for i, pg in enumerate(doc):
                if res.pages[i].blank:
                    yield None
                    continue
                pix = pg.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY, alpha=False)
                yield Image.frombytes("L", (pix.width, pix.height), pix.samples)

        infos = pagenum.page_infos(images(), cancelled=cancelled)
        for p, (ang, num) in zip(res.pages, infos):
            p.angle, p.number = ang, num
        if len(infos) < len(res.pages):
            res.error = "Đã dừng giữa chừng."
        doc.close()
    except Exception as e:
        res.error = str(e) or "Không đọc được file."
    res.seconds = time.monotonic() - t0
    return res


def job_check(args) -> CheckResult:
    return check_file(args[0])


# ------------------------------------------------------------------ sửa file

def fix_file(src: str, dst: str, order: List[int], rotate: Dict[int, int], backup: bool = True) -> str:
    """Xoay + sắp lại trang rồi ghi ra `dst` (qua file tạm). dst == src → ghi đè, sao lưu gốc vào _backup_goc."""
    same = os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(src))
    doc = _open(src)
    n = doc.page_count
    if sorted(set(order)) != sorted(order) or any(not 0 <= i < n for i in order) or not order:
        raise ValueError("Thứ tự trang không hợp lệ.")
    for i, ang in rotate.items():
        if 0 <= i < n and ang % 360:
            pg = doc[i]
            pg.set_rotation((pg.rotation + 360 - ang % 360) % 360)    # /Rotate tính theo chiều kim đồng hồ
    if order != list(range(n)):
        doc.select(order)
    folder = os.path.dirname(os.path.abspath(dst))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".partial.pdf", dir=folder)
    os.close(fd)
    try:
        doc.save(tmp, garbage=3, deflate=True)
        doc.close()
        if same and backup:
            bdir = os.path.join(os.path.dirname(src), "_backup_goc")
            os.makedirs(bdir, exist_ok=True)
            bpath = os.path.join(bdir, os.path.basename(src))
            if not os.path.exists(bpath):
                shutil.copy2(src, bpath)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return dst


def job_fix(args) -> str:
    """args = (src, dst, order, rotate, backup); trả về '' nếu thành công, ngược lại là thông báo lỗi."""
    try:
        fix_file(*args)
        return ""
    except Exception as e:
        return str(e) or "Lỗi không rõ"
