"""KIỂM TRA TRANG: phát hiện trang bị ngược / nằm ngang, đọc số trang in (Windows OCR) để báo thiếu / trùng /
sai thứ tự, và tự sửa: xoay đúng chiều, sắp lại theo số trang, (tuỳ chọn) bỏ trang trắng.

Sửa KHÔNG nén lại ảnh: chỉ đổi thuộc tính xoay (/Rotate) và thứ tự trang → giữ nguyên chất lượng.
Chỉ tự sắp xếp khi đủ chắc chắn: đọc được số ở ≥ 1/2 số trang và không có số trùng (file ghép nhiều văn bản,
mỗi văn bản đánh số lại từ 1 → không sắp, chỉ báo để người dùng xem)."""
from __future__ import annotations

import os
import pickle
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

# --- nhận dạng nội dung trang (ảnh xám thu nhỏ 0,5×): trắng / đen / ít chữ
BLANK_INK = 0.0003         # tỉ lệ điểm "mực" (tối hơn nền ≥ 45 mức) dưới ngưỡng này → trắng hẳn
NEAR_INK = 0.0020          # dưới ngưỡng này → gần trắng (chỉ nhiễu / vết bẩn) – vẫn coi là trang trắng
SPARSE_INK = 0.0080        # dưới ngưỡng này → rất ít nội dung (chỉ cảnh báo, có thể là dấu / chữ ký)
BLACK_THR = 0.90           # tỉ lệ điểm tối (≤ 69) từ ngưỡng này trở lên → trang đen
PART_BLACK = 0.50          # từ ngưỡng này đến BLACK_THR → đen một phần (scan lỗi)
DETAIL_LOW = 0.02          # < 2% điểm có viền rõ = không chi tiết (đen đặc); ≥ → ảnh tối có chi tiết (vd ảnh chụp)
BORDER = 0.03              # bỏ 3% mép khi đo (lề đen do scan)
MIN_TEXT_CHARS = 5         # trang có lớp chữ ≥ ngần này ký tự thì không coi là trắng
BLUR_REL, BLUR_MIN_MEDIAN, BLUR_ABS = 0.5, 60, 25     # mờ: độ nét < 50% trung vị (khi trung vị ≥ 60) hoặc < 25
SIZE_TOL = 0.10            # khổ giấy lệch > 10% so với khổ phổ biến nhất
DUP_MAX_PAGES = 1500

# các kiểm tra người dùng có thể bật / tắt riêng
CHECK_KEYS = ("blank", "black", "orient", "numbers", "blur", "size", "dup")
ALL_CHECKS = frozenset(CHECK_KEYS)
OCR_CHECKS = frozenset({"orient", "numbers"})     # cần đọc chữ (Windows OCR)

ST_OK, ST_ISSUE, ST_ERROR, ST_FIXED = "ok", "issue", "error", "fixed"
ANGLE_TEXT = {0: "Thuận", 90: "Nằm ngang", 180: "Ngược 180°", 270: "Nằm ngang", None: "?"}


@dataclass
class PageInfo:
    angle: Optional[int] = None       # độ cần xoay (ngược chiều kim đồng hồ) để đứng thuận; None = không rõ
    number: Optional[int] = None      # số trang in đọc được
    blank: bool = False               # trắng hẳn / gần trắng
    edited: bool = False              # người dùng đã sửa tay số / hướng
    kind: str = ""                    # "" | blank | near | sparse | black | part_black | dark_img (theo ngưỡng hiện tại)
    dark: float = -1.0                # tỉ lệ điểm tối (-1 = chưa đo)
    ink: Optional[float] = None       # tỉ lệ điểm mực so với nền (None = trang tối, không có nền sáng)
    detail: float = 0.0               # tỉ lệ điểm có viền rõ
    has_text: bool = False            # có lớp chữ (PDF số)
    sharp: float = 0.0                # độ nét (đo ở 150 dpi, 0 = chưa đo)
    size: tuple = (0.0, 0.0)          # khổ giấy (pt)
    sig: bytes = b""                  # dấu vân tay nội dung (chữ + ảnh nhúng); trùng nhau = trang giống hệt
    marked: bool = False              # người dùng đánh dấu xoá
    manual_kind: bool = False         # người dùng đã khẳng định trang này không trắng / đen


@dataclass
class CheckResult:
    path: str
    pages: List[PageInfo] = field(default_factory=list)
    error: str = ""
    seconds: float = 0.0
    ocr: bool = True                  # đã đọc chữ (hướng + số trang)
    blur: bool = True                 # đã đo độ nét


@dataclass
class Plan:
    order: List[int]                                   # chỉ số trang gốc theo thứ tự mới
    rotate: Dict[int, int]                             # trang gốc → độ xoay cần (ngược chiều kim đồng hồ)
    blanks: List[int] = field(default_factory=list)
    suspicious: List[int] = field(default_factory=list)   # trang có số lệch hẳn dãy (bỏ qua khi sắp)
    missing: List[int] = field(default_factory=list)      # số trang không thấy trong dãy
    duplicates: List[int] = field(default_factory=list)
    blacks: List[int] = field(default_factory=list)       # trang đen (≥ ngưỡng, không chi tiết)
    dark_pages: List[int] = field(default_factory=list)   # đen một phần / ảnh tối có chi tiết (chỉ cảnh báo)
    sparse: List[int] = field(default_factory=list)       # rất ít nội dung (chỉ cảnh báo)
    blurry: List[int] = field(default_factory=list)
    odd_size: List[int] = field(default_factory=list)
    dup_pages: Dict[int, int] = field(default_factory=dict)   # trang → trang trước đó có thể trùng
    marked: List[int] = field(default_factory=list)       # người dùng đánh dấu xoá
    all_removed: bool = False
    unread: int = 0                                     # trang có chữ nhưng không đọc được số
    read: int = 0
    reordered: bool = False
    sort_note: str = ""                                 # lý do không tự sắp xếp (nếu có)
    total: int = 0

    @property
    def removed(self) -> List[int]:
        keep = set(self.order)
        return [i for i in range(self.total) if i not in keep]

    n_empty: int = 0                                    # trang trắng / đen (không đọc số), bất kể có bật kiểm tra hay không

    @property
    def text_pages(self) -> int:
        return self.total - self.n_empty

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
        if self.blacks:
            out.append(f"⬛ {len(self.blacks)} trang đen ({_pages(self.blacks)})")
        if self.dark_pages:
            out.append(f"◼ {len(self.dark_pages)} trang tối / đen một phần ({_pages(self.dark_pages)})")
        if self.sparse:
            out.append(f"▫ Rất ít nội dung ({_pages(self.sparse)})")
        if self.blurry:
            out.append(f"🌫 Có thể mờ ({_pages(self.blurry)})")
        if self.odd_size:
            out.append(f"📐 Khổ giấy lệch ({_pages(self.odd_size)})")
        if self.dup_pages:
            out.append(f"⧉ Trùng nội dung ({_pages(self.dup_pages)})")
        if self.marked:
            out.append(f"🗑 Đánh dấu xoá {len(self.marked)} trang ({_pages(self.marked)})")
        if self.all_removed:
            out.append("⚠ Không thể xoá hết mọi trang – bỏ qua việc xoá")
        return out


def _nums(ns) -> str:
    ns = sorted(ns)
    return ", ".join(map(str, ns[:8])) + ("…" if len(ns) > 8 else "")


def _pages(idx) -> str:
    return "tr. " + _nums(i + 1 for i in idx)


# ------------------------------------------------------------------ lập phương án sửa (không cần OCR)

def classify(p: PageInfo, black_thr: float = BLACK_THR) -> str:
    """Loại nội dung trang theo số đo đã lưu (đổi ngưỡng đen không cần đọc lại file)."""
    if p.dark < 0:
        return p.kind
    if p.ink is not None and not p.has_text:
        if p.ink < BLANK_INK:
            return "blank"
        if p.ink < NEAR_INK:
            return "near"
    if p.dark >= black_thr:
        return "black" if p.detail < DETAIL_LOW else "dark_img"
    if p.dark >= PART_BLACK:
        return "part_black"
    if p.ink is not None and p.ink < SPARSE_INK and not p.has_text:
        return "sparse"
    return ""


def _size_key(sz) -> tuple:
    a, b = sorted(sz)
    return (round(a / 10), round(b / 10))


def make_plan(pages: List[PageInfo], remove_blank: bool = False, rotate: bool = True, reorder: bool = True,
              remove_black: bool = False, black_thr: float = BLACK_THR, checks=None) -> Plan:
    """checks: tập các kiểm tra đang bật (CHECK_KEYS); None = tất cả. Kiểm tra tắt thì không báo và không sửa theo nó."""
    ck = ALL_CHECKS if checks is None else frozenset(checks)
    n = len(pages)
    plan = Plan(order=list(range(n)), rotate={}, total=n)
    for p in pages:
        if p.dark >= 0 and not p.manual_kind:
            p.kind = classify(p, black_thr)
            p.blank = p.kind in ("blank", "near")
    blank_idx = [i for i, p in enumerate(pages) if p.blank]
    black_idx = [i for i, p in enumerate(pages) if p.kind == "black"]
    empty = set(blank_idx) | set(black_idx)                   # không đọc số / không xoay các trang này
    plan.n_empty = len(empty)
    if "blank" in ck:
        plan.blanks = blank_idx
        plan.sparse = [i for i, p in enumerate(pages) if p.kind == "sparse"]
    if "black" in ck:
        plan.blacks = black_idx
        plan.dark_pages = [i for i, p in enumerate(pages) if p.kind in ("part_black", "dark_img")]
    plan.marked = [i for i, p in enumerate(pages) if p.marked]
    _quality(pages, plan, ck)
    gone = set(plan.marked)
    if remove_blank and "blank" in ck:
        gone |= set(plan.blanks)
    if remove_black and "black" in ck:
        gone |= set(plan.blacks)
    if rotate and "orient" in ck:
        plan.rotate = {i: p.angle for i, p in enumerate(pages) if p.angle and i not in empty and i not in gone}

    nums = {i: p.number for i, p in enumerate(pages)
            if p.number is not None and i not in empty and i not in gone and "numbers" in ck}
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
    text_pages = plan.text_pages
    plan.read = len(nums)
    plan.unread = (text_pages - plan.read - len(gone - empty)) if "numbers" in ck else 0

    order = [i for i in range(n) if i not in gone]
    if gone and not order:
        order = list(range(n))                       # mọi trang đều bị xoá → không xoá gì
        plan.all_removed = True
        nums = {}
        plan.read = 0
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


def _quality(pages: List[PageInfo], plan: Plan, ck=ALL_CHECKS) -> None:
    """Cảnh báo chất lượng (không tự sửa): trang mờ, khổ giấy lệch, trang trùng nội dung."""
    n = len(pages)
    live = [i for i, p in enumerate(pages) if p.kind not in ("blank", "near", "black")]
    sharp = sorted(pages[i].sharp for i in live if pages[i].sharp > 0) if "blur" in ck else []
    if len(sharp) >= 4:
        med = sharp[len(sharp) // 2]
        plan.blurry = [i for i in live if 0 < pages[i].sharp < BLUR_ABS
                       or (med >= BLUR_MIN_MEDIAN and 0 < pages[i].sharp < BLUR_REL * med)]
    elif sharp:
        plan.blurry = [i for i in live if 0 < pages[i].sharp < BLUR_ABS]
    sized = [i for i in range(n) if pages[i].size[0] > 0] if "size" in ck else []
    if len(sized) >= 3:
        cnt: Dict[tuple, int] = {}
        for i in sized:
            k = _size_key(pages[i].size)
            cnt[k] = cnt.get(k, 0) + 1
        main, c = max(cnt.items(), key=lambda kv: kv[1])
        if c * 2 > len(sized):                                  # chỉ khi có khổ chiếm đa số (file khổ lẫn lộn thì bỏ qua)
            ref = sorted(next(pages[i].size for i in sized if _size_key(pages[i].size) == main))
            plan.odd_size = [i for i in sized
                             if any(abs(x - r) > SIZE_TOL * r for x, r in zip(sorted(pages[i].size), ref))]
    if n <= DUP_MAX_PAGES and "dup" in ck:
        first: Dict[bytes, int] = {}
        for i in live:
            if pages[i].sig:
                if pages[i].sig in first:
                    plan.dup_pages[i] = first[pages[i].sig]
                else:
                    first[pages[i].sig] = i


# ------------------------------------------------------------------ kiểm tra 1 file (chạy ở tiến trình con)

def _open(path: str) -> "fitz.Document":
    with open(path, "rb") as fh:
        doc = fitz.open(stream=fh.read(), filetype="pdf")      # đọc vào RAM: không khoá file
    if doc.needs_pass:
        raise ValueError("File có mật khẩu – không kiểm tra được.")
    if doc.page_count == 0:
        raise ValueError("File không có trang nào.")
    return doc


def _mode_level(h) -> int:
    """Mức sáng phổ biến nhất (cửa sổ 5 mức) = màu nền."""
    best, at = -1, 0
    for k in range(2, 254):
        v = h[k - 2] + h[k - 1] + h[k] + h[k + 1] + h[k + 2]
        if v > best:
            best, at = v, k
    return at


def _edge_hist(im):
    from PIL import ImageChops
    return ImageChops.difference(im, ImageChops.offset(im, 1, 0)).histogram()


def _signature(page: "fitz.Page") -> bytes:
    """Dấu vân tay nội dung: chữ + dữ liệu ảnh nhúng. Hai trang giống hệt (vd ghép trùng file) → cùng dấu.
    Trang scan lại 2 lần có ảnh khác byte nên không bị coi là trùng (tránh báo nhầm)."""
    import hashlib
    h = hashlib.md5()
    used = False
    try:
        txt = page.get_text("text").strip()
        if txt:
            h.update(txt.encode("utf-8", "ignore"))
            used = True
        doc = page.parent
        for img in page.get_images(full=True):
            data = doc.extract_image(img[0]).get("image")
            if data:
                h.update(data)
                used = True
    except Exception:
        return b""
    return h.digest() if used else b""


def analyze_page(page: "fitz.Page", black_thr: float = BLACK_THR) -> PageInfo:
    """Đo nội dung 1 trang ở ảnh xám 0,5× (nhanh): tỉ lệ mực, tỉ lệ tối, độ chi tiết, dấu vân tay trang."""
    from PIL import Image
    pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), colorspace=fitz.csGRAY, alpha=False)
    p = PageInfo(size=(page.mediabox.width, page.mediabox.height))
    if not pix.samples:
        p.dark, p.ink = 0.0, 0.0
        p.kind, p.blank = "blank", True
        return p
    im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    bx, by = int(pix.width * BORDER), int(pix.height * BORDER)
    core = im.crop((bx, by, pix.width - bx, pix.height - by)) if pix.width > 20 and pix.height > 20 else im
    h = core.histogram()
    n = max(1, core.width * core.height)
    p.dark = sum(h[:70]) / n
    bg = _mode_level(h)
    p.ink = sum(h[:max(0, bg - 45)]) / n if bg >= 150 else None
    eh = _edge_hist(core)
    p.detail = sum(eh[24:]) / n
    p.sig = _signature(page)
    if p.ink is not None and p.ink < NEAR_INK:                  # nghi trắng: PDF số còn lớp chữ thì không phải trắng
        try:
            p.has_text = len(page.get_text("text").strip()) >= MIN_TEXT_CHARS
        except Exception:
            pass
    p.kind = classify(p, black_thr)
    p.blank = p.kind in ("blank", "near")
    return p


def sharpness(im) -> float:
    """Độ nét: 99,7% điểm viền mạnh nhất (ảnh 150 dpi). Chữ nét ≈ 100–255, ảnh mờ thường < 60."""
    eh = _edge_hist(im)
    total = sum(eh)
    need, acc = max(1, int(total * 0.003)), 0
    for v in range(255, -1, -1):
        acc += eh[v]
        if acc >= need:
            return float(v)
    return 0.0


def check_file(path: str, cancelled=None, black_thr: float = BLACK_THR, ocr: bool = True,
               blur: bool = True, concurrency: int = 1) -> CheckResult:
    """Đo mọi trang (trắng / đen / khổ / trùng: rất nhanh). ocr=True: đọc hướng + số trang bằng Windows OCR (chậm hơn nhiều);
    blur=True: đo độ nét (cần vẽ trang 150 dpi). Cả hai tắt → chỉ ~3 ms / trang."""
    from PIL import Image
    from . import pagenum
    t0 = time.monotonic()
    res = CheckResult(path, ocr=ocr, blur=blur)
    try:
        doc = _open(path)
        res.pages = [analyze_page(pg, black_thr) for pg in doc]

        def images():
            for i, pg in enumerate(doc):
                if res.pages[i].kind in ("blank", "near", "black") or not (ocr or blur):
                    yield None                           # trang trắng / đen: không cần đọc chữ
                    continue
                pix = pg.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY, alpha=False)
                im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
                if blur:
                    res.pages[i].sharp = sharpness(im)
                yield im if ocr else None

        if ocr:
            infos = pagenum.page_infos(images(), cancelled=cancelled, concurrency=concurrency)
        else:
            infos = []
            for _ in images():
                if cancelled and cancelled():
                    break
                infos.append((None, None))
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
    """args = (path[, black_thr[, ocr[, blur[, concurrency]]]])"""
    a = list(args) + [None] * (5 - len(args))
    return check_file(a[0], black_thr=BLACK_THR if a[1] is None else a[1], ocr=True if a[2] is None else a[2],
                      blur=True if a[3] is None else a[3], concurrency=1 if a[4] is None else a[4])


# ------------------------------------------------------------------ sửa file

def fix_file(src: str, dst: str, order: List[int], rotate: Dict[int, int], backup: bool = True,
             reason: str = "Sửa tự động (kiểm tra trang)", trash_backup: bool = True) -> str:
    """Xoay + sắp lại trang rồi ghi ra `dst` (qua file tạm). dst == src → ghi đè, sao lưu gốc vào thư mục sao lưu của app
    và cất vào THÙNG RÁC: bản gốc (trash_backup) + các trang bị bỏ."""
    from . import trash
    same = os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(src))
    doc = _open(src)
    n = doc.page_count
    if sorted(set(order)) != sorted(order) or any(not 0 <= i < n for i in order) or not order:
        raise ValueError("Thứ tự trang không hợp lệ.")
    for i, ang in rotate.items():
        if 0 <= i < n and ang % 360:
            pg = doc[i]
            pg.set_rotation((pg.rotation + 360 - ang % 360) % 360)    # /Rotate tính theo chiều kim đồng hồ
    gone_entry = None
    if same and len(order) < n:                                   # ghi đè và có trang bị bỏ → cất các trang đó vào thùng rác
        gone_entry = trash.add_pages(doc, [i for i in range(n) if i not in set(order)], reason, path=src)
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
            _backup_original(src, reason, trash_backup)
        os.replace(tmp, dst)
    except Exception:
        if gone_entry is not None:
            trash.delete(gone_entry)                              # việc chính hỏng → không để lại mục thùng rác sai
        raise
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return dst


def _backup_original(src: str, reason: str, register: bool = True) -> None:
    """Chép bản gốc vào thư mục sao lưu của app (chỉ lần đầu – giữ bản gốc sớm nhất) và đăng ký vào thùng rác."""
    from . import trash
    trash.make_backup(src, reason, register)


def job_fix(args) -> str:
    """args = (src, dst, order, rotate, backup); trả về '' nếu thành công, ngược lại là thông báo lỗi."""
    try:
        fix_file(*args)
        return ""
    except Exception as e:
        return str(e) or "Lỗi không rõ"


def delete_pages(path: str, pages: List[int], backup: bool = True) -> int:
    """Xoá các trang (chỉ số từ 0) khỏi file, ghi đè an toàn qua file tạm; bản gốc sao lưu vào thư mục sao lưu của app.
    Trả về số trang còn lại. Không cho xoá hết trang."""
    doc = _open(path)
    n = doc.page_count
    doc.close()
    gone = set(pages)
    if not gone or any(not 0 <= i < n for i in gone):
        raise ValueError("Trang cần xoá không hợp lệ.")
    keep = [i for i in range(n) if i not in gone]
    if not keep:
        raise ValueError("Không thể xoá hết mọi trang của file.")
    fix_file(path, path, keep, {}, backup, reason="Xoá trang")      # trang xoá + bản gốc đều vào thùng rác
    return len(keep)


def crop_pages(path: str, rects: Dict[int, tuple], backup: bool = True) -> int:
    """CẮT XÉN VIỀN: đặt khung hiển thị (CropBox) cho các trang. rects: {trang (từ 0): (x0, y0, x1, y1)} là TỈ LỆ 0..1 trên trang
    như đang hiển thị (đã tính /Rotate, gốc ở góc trên trái). Không nén lại ảnh – phần ngoài khung bị ẩn (mọi trình đọc PDF / OCR
    đều chỉ thấy trong khung). Ghi đè an toàn qua file tạm, bản gốc sao lưu + cất vào thùng rác. Trả về số trang đã cắt."""
    if not rects:
        raise ValueError("Chưa có khung cắt.")
    doc = _open(path)
    n = doc.page_count
    done = 0
    for i, (x0, y0, x1, y1) in rects.items():
        if not 0 <= i < n:
            raise ValueError("Trang cần cắt không hợp lệ.")
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1) or (x1 - x0) < 0.02 or (y1 - y0) < 0.02:
            raise ValueError("Khung cắt không hợp lệ (quá nhỏ hoặc nằm ngoài trang).")
        pg = doc[i]
        r = pg.rect                                              # trang đang hiển thị (đã xoay), gốc (0, 0)
        shown = fitz.Rect(x0 * r.width, y0 * r.height, x1 * r.width, y1 * r.height)
        box = shown * pg.derotation_matrix                       # → toạ độ trang chưa xoay
        cb = pg.cropbox
        box = fitz.Rect(box.x0 + cb.x0, box.y0 + cb.y0, box.x1 + cb.x0, box.y1 + cb.y0)   # tính cả khung cũ
        box &= pg.mediabox
        if box.is_empty or box.width < 5 or box.height < 5:
            raise ValueError("Khung cắt quá nhỏ.")
        pg.set_cropbox(box)
        done += 1
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(suffix=".partial.pdf", dir=folder)
    os.close(fd)
    try:
        doc.save(tmp, garbage=3, deflate=True)
        doc.close()
        if backup:
            _backup_original(path, "Trước khi cắt viền")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return done


def get_cropboxes(path: str, pages: List[int]) -> Dict[int, tuple]:
    """Khung hiển thị (CropBox) hiện tại của các trang – dùng để hoàn tác cắt viền."""
    doc = _open(path)
    try:
        return {i: tuple(doc[i].cropbox) for i in pages if 0 <= i < doc.page_count}
    finally:
        doc.close()


def set_cropboxes(path: str, boxes: Dict[int, tuple]) -> None:
    """Đặt lại CropBox đã lưu (hoàn tác cắt viền). Không sao lưu / không ghi thùng rác."""
    doc = _open(path)
    for i, b in boxes.items():
        if 0 <= i < doc.page_count:
            doc[i].set_cropbox(fitz.Rect(*b))
    fd, tmp = tempfile.mkstemp(suffix=".partial.pdf", dir=os.path.dirname(os.path.abspath(path)))
    os.close(fd)
    try:
        doc.save(tmp, garbage=3, deflate=True)
        doc.close()
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ------------------------------------------------------------------ bộ nhớ đệm kết quả (qua các lần mở app)
# Kiểm tra lại file KHÔNG đổi (cùng kích thước + ngày sửa) thì dùng ngay kết quả cũ – không vẽ / OCR lại.
CACHE_VERSION = 3                 # tăng khi thuật toán đo đổi (để bỏ kết quả cũ)
CACHE_LIMIT = 60000


def cache_path() -> str:
    from ..paths import data_dir
    return os.path.join(data_dir(), "check_cache.pkl")


def file_key(path: str) -> Optional[tuple]:
    try:
        st = os.stat(path)
        return st.st_size, st.st_mtime_ns
    except OSError:
        return None


def load_cache() -> dict:
    """{đường dẫn: (kích thước, mtime_ns, ocr, blur, dữ liệu nén)}; rỗng nếu chưa có / hỏng / khác phiên bản."""
    try:
        with open(cache_path(), "rb") as fh:
            data = pickle.load(fh)
        if isinstance(data, dict) and data.get("v") == CACHE_VERSION and isinstance(data.get("items"), dict):
            return data["items"]
    except Exception:
        pass
    return {}


def save_cache(items: dict) -> None:
    try:
        if len(items) > CACHE_LIMIT:
            for k in list(items)[:len(items) - CACHE_LIMIT]:
                del items[k]
        path = cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            pickle.dump({"v": CACHE_VERSION, "items": items}, fh, protocol=4)
        os.replace(tmp, path)
    except Exception:
        pass


def cache_put(items: dict, path: str, res: CheckResult) -> None:
    """Lưu kết quả vừa kiểm tra (trước khi người dùng sửa tay số / hướng / đánh dấu)."""
    key = file_key(path)
    if key and not res.error and res.pages:
        items.pop(path, None)
        items[path] = (key[0], key[1], res.ocr, res.blur, pickle.dumps(res, protocol=4))


def cache_get(items: dict, path: str, need_ocr: bool, need_blur: bool) -> Optional[CheckResult]:
    e = items.get(path)
    key = file_key(path)
    if not e or not key or (e[0], e[1]) != key or (need_ocr and not e[2]) or (need_blur and not e[3]):
        return None
    try:
        res = pickle.loads(e[4])
    except Exception:
        return None
    return res if isinstance(res, CheckResult) else None
