"""Tách trang PDF: cắt đôi mỗi trang scan (A3 → 2 trang A4, A4 → 2 nửa), tuỳ chọn phóng ra khổ A4,
sắp lại thứ tự SỔ GỠ GHIM scan 2 mặt (như "Cắt & Ghép Sổ Lý Lịch" của Hồ sơ 1361), giữ nguyên bìa,
xoay mặt sau ADF, bỏ trang trắng. Không bao giờ ghi đè file gốc trừ khi được yêu cầu (có sao lưu)."""
from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

A4 = (595.276, 841.89)
_PAPERS = (("A3", 297, 420), ("A4", 210, 297), ("A5", 148, 210), ("Letter", 216, 279), ("Legal", 216, 356))
_ROT = {"none": 0, "cw": -90, "ccw": 90, "r180": 180}      # góc cho show_pdf_page (dương = ngược chiều kim đồng hồ)


class SplitError(Exception):
    pass


@dataclass
class SplitOptions:
    split_mode: str = "auto"          # auto | left_right | top_bottom | none (không cắt)
    cut_percent: float = 50.0         # vị trí đường cắt (% chiều rộng / chiều cao)
    half_order: str = "first"         # first = Trái/Trên trước · second = Phải/Dưới trước
    arrange: str = "sequential"       # sequential = tách lần lượt · booklet = sắp lại thứ tự sổ gỡ ghim
    keep_first: bool = False          # giữ nguyên trang scan đầu (bìa), không cắt
    keep_last: bool = False           # giữ nguyên trang scan cuối
    flip_back: str = "auto"           # auto | yes | no — xoay 180° các mặt sau (mặt scan thứ 2, 4…) do máy ADF lật giấy
    post_rotation: str = "auto"       # auto | none | cw | ccw | r180 — xoay mỗi nửa sau khi cắt
    page_size: str = "original"       # original = giữ kích thước nửa trang · a4 = chuẩn hoá khổ A4 (giữ tỉ lệ)
    remove_blank: bool = False
    page_from: Optional[int] = None   # phạm vi trang scan (1-based, gồm cả 2 đầu)
    page_to: Optional[int] = None
    sheet_order: str = "outer"        # sổ gỡ ghim: outer = tờ ngoài cùng (có bìa) scan trước · inner = tờ giữa trước
    face_first: str = "front"         # sổ gỡ ghim: front = mặt có bìa/trang 1 scan trước · back = mặt kia trước


PRESETS = {
    "a3_to_a4": ("A3 ngang → 2 trang A4", SplitOptions(split_mode="auto", page_size="original")),
    "a4_to_a4": ("A4 → 2 nửa, phóng thành 2 trang A4", SplitOptions(split_mode="auto", page_size="a4")),
    "booklet": ("Sổ lý lịch gỡ ghim (scan 2 mặt) → trang A4 đúng thứ tự",
                SplitOptions(split_mode="auto", arrange="booklet", keep_first=False, flip_back="auto",
                             post_rotation="auto", page_size="a4")),
}


@dataclass
class PdfInfo:
    pages: int
    sizes_mm: List[Tuple[float, float]]
    has_signature: bool
    label: str                         # vd "A3 ngang" / "A4 dọc ×12, A3 ngang ×2"


@dataclass
class Unit:
    """Một trang kết quả: cả trang scan (intact) hoặc một nửa."""
    src: int                           # chỉ số trang scan (0-based)
    clip: Optional["fitz.Rect"]        # None = cả trang
    rotate: int = 0                    # độ, cho show_pdf_page
    label: str = ""                    # mô tả nguồn, vd "Trang scan 3 · nửa trái"


@dataclass
class SplitResult:
    doc: "fitz.Document"
    units: List[Unit]
    removed_blank: List[int] = field(default_factory=list)   # vị trí (1-based) trang trắng đã bỏ
    warnings: List[str] = field(default_factory=list)


# ------------------------------------------------------------------ thông tin file

def paper_name(w_pt: float, h_pt: float) -> str:
    w, h = w_pt * 25.4 / 72, h_pt * 25.4 / 72
    lo, hi = sorted((w, h))
    orient = "dọc" if h >= w else "ngang"
    for name, a, b in _PAPERS:
        if abs(lo - a) / a < 0.05 and abs(hi - b) / b < 0.05:
            return f"{name} {orient}"
    return f"{round(w)}×{round(h)} mm"


def open_source(path: str) -> "fitz.Document":
    if not path.lower().endswith(".pdf") or not os.path.isfile(path):
        raise SplitError("File PDF không tồn tại.")
    with open(path, "rb") as fh:
        data = fh.read()                          # đọc vào RAM: không khoá file, cho phép lưu đè an toàn
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise SplitError("Không mở được file – có thể file bị hỏng.")
    if doc.needs_pass:
        raise SplitError("File có mật khẩu – hãy mở khoá trước.")
    if doc.page_count == 0:
        raise SplitError("File không có trang nào.")
    doc._pr_has_sig = b"/ByteRange" in data      # type: ignore[attr-defined]
    return doc


def read_info(doc: "fitz.Document") -> PdfInfo:
    sizes, counts = [], {}
    for pg in doc:
        r = pg.rect
        sizes.append((r.width * 25.4 / 72, r.height * 25.4 / 72))
        name = paper_name(r.width, r.height)
        counts[name] = counts.get(name, 0) + 1
    label = next(iter(counts)) if len(counts) == 1 else ", ".join(f"{k} ×{v}" for k, v in counts.items())
    return PdfInfo(doc.page_count, sizes, bool(getattr(doc, "_pr_has_sig", False)), label)


def normalized_copy(doc: "fitz.Document") -> "fitz.Document":
    """Bản sao với mọi trang đã bỏ thuộc tính /Rotate (giữ nguyên hình thức hiển thị) → cắt theo đúng hướng nhìn."""
    norm = fitz.open()
    norm.insert_pdf(doc)
    for pg in norm:
        if pg.rotation:
            pg.remove_rotation()
    return norm


# ------------------------------------------------------------------ hình học

def resolve_mode(opts: SplitOptions, rect: "fitz.Rect") -> str:
    if opts.split_mode != "auto":
        return opts.split_mode
    return "left_right" if rect.width >= rect.height else "top_bottom"


def cut_rects(rect: "fitz.Rect", mode: str, percent: float) -> Tuple["fitz.Rect", "fitz.Rect"]:
    if not 5 <= percent <= 95:
        raise SplitError("Vị trí cắt phải trong khoảng 5–95%.")
    f = percent / 100.0
    if mode == "left_right":
        x = rect.x0 + rect.width * f
        return fitz.Rect(rect.x0, rect.y0, x, rect.y1), fitz.Rect(x, rect.y0, rect.x1, rect.y1)
    y = rect.y0 + rect.height * f
    return fitz.Rect(rect.x0, rect.y0, rect.x1, y), fitz.Rect(rect.x0, y, rect.x1, rect.y1)


def _post_angle(opts: SplitOptions, mode: str) -> int:
    if opts.post_rotation == "auto":
        # sổ đặt dọc trong máy scan: 2 trang nằm trên/dưới và bị xoay ngang → xoay trái 90° cho đứng lại
        return 90 if (mode == "top_bottom" and opts.arrange == "booklet") else 0
    return _ROT.get(opts.post_rotation, 0)


def _flip(opts: SplitOptions, mode: str, content_index: int) -> bool:
    if content_index % 2 == 0:
        return False
    if opts.flip_back == "yes":
        return True
    if opts.flip_back == "no":
        return False
    return opts.arrange == "booklet" and mode == "top_bottom"


def booklet_order(n_halves: int, sheet_order: str = "outer", face_first: str = "front") -> List[int]:
    """Vị trí trang sổ (1-based) của từng nửa theo thứ tự scan: mặt trước tờ k = (P-2k, 1+2k),
    mặt sau tờ k = (2+2k, P-1-2k); tờ k = 0 là tờ ngoài cùng."""
    p = n_halves
    sheets = []
    for k in range(p // 4):
        front, back = [p - 2 * k, 1 + 2 * k], [2 + 2 * k, p - 1 - 2 * k]
        sheets.append(front + back if face_first == "front" else back + front)
    if sheet_order == "inner":
        sheets.reverse()
    return [x for sh in sheets for x in sh]


def plan_units(norm: "fitz.Document", opts: SplitOptions) -> Tuple[List[Unit], List[str]]:
    warnings: List[str] = []
    n = norm.page_count
    a = max(1, opts.page_from or 1)
    b = min(n, opts.page_to or n)
    if a > b:
        raise SplitError("Phạm vi trang không hợp lệ.")
    faces = list(range(a - 1, b))
    first = faces.pop(0) if opts.keep_first and faces else None
    last = faces.pop() if opts.keep_last and faces else None
    halves: List[Unit] = []
    for j, pi in enumerate(faces):
        rect = norm[pi].rect
        mode = resolve_mode(opts, rect)
        if mode == "none":
            halves.append(Unit(pi, None, _ROT.get(opts.post_rotation, 0) if opts.post_rotation != "auto" else 0,
                               f"Trang scan {pi + 1}"))
            continue
        r1, r2 = cut_rects(rect, mode, opts.cut_percent)
        names = ("trái", "phải") if mode == "left_right" else ("trên", "dưới")
        flip = _flip(opts, mode, j)
        pair = [(r1, names[0]), (r2, names[1])]
        base = 0
        if flip:                                   # mặt bị lộn ngược: nửa nhìn thấy đầu tiên là nửa thứ 2 của trang
            pair.reverse()
            base = 180
        if opts.half_order == "second":
            pair.reverse()
        rot = (base + _post_angle(opts, mode)) % 360
        for clip, nm in pair:
            halves.append(Unit(pi, clip, rot, f"Trang scan {pi + 1} · nửa {nm}" + (" · xoay 180° (mặt sau)" if flip else "")))
    if opts.arrange == "booklet":
        if any(u.clip is None for u in halves):
            raise SplitError("Sắp thứ tự sổ cần cắt đôi mọi trang (không chọn 'Không cắt').")
        if len(halves) % 4:
            raise SplitError(f"Sổ gỡ ghim phải có số mặt scan (trừ trang giữ nguyên) là số chẵn – hiện có "
                             f"{len(halves) // 2} mặt. Hãy kiểm tra lại file scan hoặc tuỳ chọn giữ nguyên bìa.")
        pos = booklet_order(len(halves), opts.sheet_order, opts.face_first)
        ordered: List[Optional[Unit]] = [None] * len(halves)
        for u, p in zip(halves, pos):
            u.label += f" → trang sổ {p}"
            ordered[p - 1] = u
        halves = [u for u in ordered if u is not None]
    units: List[Unit] = []
    if first is not None:
        units.append(Unit(first, None, 0, f"Trang scan {first + 1} · giữ nguyên (bìa)"))
    units += halves
    if last is not None:
        units.append(Unit(last, None, 0, f"Trang scan {last + 1} · giữ nguyên"))
    return units, warnings


# ------------------------------------------------------------------ tự nhận thứ tự bằng số trang in trên giấy

_ANGLE_NAME = {0: "none", 90: "ccw", 180: "r180", 270: "cw"}


def unit_key(u: Unit) -> Tuple[int, int, int]:
    return (u.src, round(u.clip.x0), round(u.clip.y0)) if u.clip is not None else (u.src, -1, -1)


@dataclass
class PageReads:
    """Số trang đọc được của từng nửa trang (theo hướng xoay `angle`): up = đọc thuận, down = khi xoay 180°."""
    reads: dict                       # unit_key → (up, down, angle)
    halves: int

    @property
    def count(self) -> int:
        return sum(1 for up, down, _ in self.reads.values() if up is not None or down is not None)


@dataclass
class OrderGuess:
    options: Optional[SplitOptions]   # None = không đủ căn cứ, giữ nguyên thiết lập
    matched: int
    read: int
    halves: int
    offset: int
    description: str


def _base_plan(norm: "fitz.Document", opts: SplitOptions) -> List[Unit]:
    """Các nửa trang theo thứ tự scan, chưa lật mặt sau, xoay theo hướng của thiết lập hiện tại
    ("tự động" của sổ dọc là xoay trái 90°) – dùng để OCR và đối chiếu."""
    from dataclasses import replace
    post = opts.post_rotation
    if post == "auto":
        n = norm.page_count
        first = max(1, opts.page_from or 1) - 1 + (1 if opts.keep_first else 0)
        rect = norm[min(first, n - 1)].rect
        post = _ANGLE_NAME[_post_angle(opts, resolve_mode(opts, rect)) % 360]
    units, _ = plan_units(norm, replace(opts, arrange="sequential", flip_back="no", half_order="first",
                                        post_rotation=post))
    return [u for u in units if u.clip is not None]


def iter_half_images(doc: "fitz.Document", opts: SplitOptions, dpi: int = 150):
    """Từng (khoá, ảnh xám) của các nửa trang (theo thứ tự scan, đúng hướng xoay của thiết lập) để OCR.
    Gọi ở luồng chính (PyMuPDF không an toàn đa luồng) – là generator nên giao diện lấy từng ít một, không bị đơ;
    ảnh PIL trả về dùng được ở luồng phụ."""
    from PIL import Image
    norm = normalized_copy(doc)
    for u in _base_plan(norm, opts):
        pix = norm[u.src].get_pixmap(dpi=dpi, clip=u.clip, colorspace=fitz.csGRAY, alpha=False)
        im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        if u.rotate % 360:
            im = im.rotate(u.rotate, expand=True, fillcolor=255)     # PIL: dương = ngược chiều kim đồng hồ, như PDF
        yield (unit_key(u), u.rotate % 360), im


def half_images(doc: "fitz.Document", opts: SplitOptions, dpi: int = 150):
    pairs = list(iter_half_images(doc, opts, dpi))
    return [k for k, _ in pairs], [im for _, im in pairs]


def make_reads(keys, results) -> PageReads:
    return PageReads({k: (up, down, ang) for (k, ang), (up, down) in zip(keys, results)}, len(keys))


def read_page_numbers(doc: "fitz.Document", opts: SplitOptions, progress=None, cancelled=None) -> PageReads:
    """OCR số trang ở đầu/chân mỗi nửa trang (Windows OCR)."""
    from . import pagenum
    keys, images = half_images(doc, opts)
    res = pagenum.read_pages(images, max_page=len(images) + 8, progress=progress, cancelled=cancelled)
    return make_reads(keys, res)


def _describe(o: SplitOptions, upside_down: bool) -> str:
    if o.arrange == "booklet":
        parts = ["sổ gỡ ghim", "tờ ngoài cùng scan trước" if o.sheet_order == "outer" else "tờ giữa scan trước",
                 "mặt có trang 1 trước" if o.face_first == "front" else "mặt kia trước"]
    else:
        parts = ["tách lần lượt"]
    if o.half_order == "second":
        parts.append("nửa phải/dưới trước")
    if o.flip_back == "yes":
        parts.append("mặt sau lộn ngược")
    if upside_down:
        parts.append("cả xấp scan bị ngược (xoay 180°)")
    return " · ".join(parts)


def guess_order(doc: "fitz.Document", opts: SplitOptions, pr: PageReads) -> OrderGuess:
    """Thử mọi cách xếp có thể (tách lần lượt / sổ gỡ ghim: tờ ngoài hay tờ giữa trước, mặt nào trước,
    nửa nào trước, mặt sau có lộn ngược không, cả xấp có bị ngược không) và chọn cách mà số trang đọc được
    khớp với vị trí nhiều nhất."""
    from dataclasses import replace
    read = pr.count
    if read < 2:
        return OrderGuess(None, 0, read, pr.halves, 0, "Không đọc được số trang (cần ít nhất 2 trang có số in rõ).")
    norm = normalized_copy(doc)
    base = _base_plan(norm, opts)
    p0 = base[0].rotate % 360 if base else 0
    cands: List[SplitOptions] = []
    for post in (p0, (p0 + 180) % 360):
        for flip in ("no", "yes"):
            for half in ("first", "second"):
                common = dict(post_rotation=_ANGLE_NAME[post], flip_back=flip, half_order=half)
                cands.append(replace(opts, arrange="sequential", **common))
                if pr.halves % 4 == 0:
                    for sh in ("outer", "inner"):
                        for face in ("front", "back"):
                            cands.append(replace(opts, arrange="booklet", sheet_order=sh, face_first=face, **common))

    # thiết lập hiện tại (đã quy "tự động" ra giá trị cụ thể) – khi hoà điểm, ưu tiên cách ít thay đổi nhất
    mode0 = resolve_mode(opts, norm[base[0].src].rect) if base else "left_right"
    cur = replace(opts, post_rotation=_ANGLE_NAME[p0], flip_back="yes" if _flip(opts, mode0, 1) else "no")

    def changes(c: SplitOptions) -> int:
        return sum(getattr(c, f) != getattr(cur, f) for f in
                   ("arrange", "sheet_order", "face_first", "half_order", "flip_back", "post_rotation"))

    best = None
    for c in cands:
        try:
            units, _ = plan_units(norm, c)
        except SplitError:
            continue
        nums = []
        for u in units:
            if u.clip is None:
                continue
            up, down, ang = pr.reads.get(unit_key(u), (None, None, 0))
            delta = (u.rotate - ang) % 360
            nums.append(up if delta == 0 else down if delta == 180 else None)
        for off in range(-3, 4):
            m = sum(1 for i, n in enumerate(nums) if n is not None and n == i + 1 + off)
            key = (m, -abs(off), -changes(c))
            if best is None or key > best[0]:
                best = (key, c, off)
    if best is None:
        return OrderGuess(None, 0, read, pr.halves, 0, "Không tìm được cách xếp phù hợp.")
    (m, _, _), c, off = best
    if m < 2 or m < 0.6 * read:
        return OrderGuess(None, m, read, pr.halves, off,
                          f"Số trang đọc được không khớp kiểu xếp nào (khớp {m}/{read}) – giữ nguyên thiết lập.")
    return OrderGuess(c, m, read, pr.halves, off, _describe(c, c.post_rotation != _ANGLE_NAME[p0]))


# ------------------------------------------------------------------ dựng file kết quả

def _is_blank(page: "fitz.Page") -> bool:
    """Trang trắng: gần như không có điểm đen (chịu được vài hạt bụi của bản scan)."""
    pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), colorspace=fitz.csGRAY, alpha=False)
    data = pix.samples
    if not data:
        return True
    dark = sum(1 for v in data if v < 140)
    return dark / len(data) < 0.0002          # ≈ 25 điểm đen trên trang A4 – chỉ bỏ trang gần như trắng tinh


def build(doc: "fitz.Document", opts: SplitOptions,
          progress: Optional[Callable[[int, int], None]] = None) -> SplitResult:
    norm = normalized_copy(doc)
    units, warnings = plan_units(norm, opts)
    out = fitz.open()
    for i, u in enumerate(units):
        rect = u.clip if u.clip is not None else norm[u.src].rect
        w, h = (rect.height, rect.width) if u.rotate % 180 else (rect.width, rect.height)
        if opts.page_size == "a4":
            w, h = A4 if h >= w else (A4[1], A4[0])
        page = out.new_page(width=w, height=h)
        page.show_pdf_page(page.rect, norm, u.src, clip=u.clip, rotate=u.rotate, keep_proportion=True)
        if progress:
            progress(i + 1, len(units))
    removed: List[int] = []
    if opts.remove_blank and out.page_count > 1:
        keep = [i for i in range(out.page_count) if not _is_blank(out[i])]
        if not keep:
            warnings.append("Mọi trang đều trống – không bỏ trang nào.")
        elif len(keep) < out.page_count:
            removed = [i + 1 for i in range(out.page_count) if i not in keep]
            out.select(keep)
            units = [units[i] for i in keep]
    return SplitResult(out, units, removed, warnings)


# ------------------------------------------------------------------ chọn trang + lưu

def parse_pages(spec: str, total: int) -> List[int]:
    """'1-3, 5, 8-' → chỉ số 0-based. Rỗng / 'tất cả' → mọi trang."""
    spec = spec.strip().lower()
    if not spec or spec in ("tất cả", "tat ca", "all", "*"):
        return list(range(total))
    out: List[int] = []
    for part in re.split(r"[,;\s]+", spec):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else total
        elif part.isdigit():
            a = b = int(part)
        else:
            raise SplitError(f"Không hiểu phần “{part}”. Ví dụ hợp lệ: 1-3, 5, 8-")
        if a < 1 or b > total or a > b:
            raise SplitError(f"Trang “{part}” nằm ngoài 1–{total}.")
        out += [i - 1 for i in range(a, b + 1) if i - 1 not in out]
    if not out:
        raise SplitError("Chưa chọn trang nào.")
    return out


def default_output(src_path: str, suffix: str = "_DaTach") -> str:
    d, name = os.path.split(src_path)
    stem = os.path.splitext(name)[0]
    cand = os.path.join(d, f"{stem}{suffix}.pdf")
    i = 2
    while os.path.exists(cand):
        cand = os.path.join(d, f"{stem}{suffix} ({i}).pdf")
        i += 1
    return cand


def save(result: SplitResult, src_path: str, out_path: str, pages: Optional[List[int]] = None,
         overwrite_source: bool = False) -> str:
    """Ghi file kết quả (qua file tạm rồi thay thế). Ghi đè file gốc chỉ khi overwrite_source=True,
    và khi đó bản gốc được sao lưu vào _backup_goc."""
    same = os.path.normcase(os.path.abspath(out_path)) == os.path.normcase(os.path.abspath(src_path))
    if same and not overwrite_source:
        raise SplitError("Không được lưu đè lên file gốc (hãy chọn 'Lưu đè file gốc' nếu thật sự muốn).")
    if overwrite_source:
        out_path = src_path
    if not out_path.lower().endswith(".pdf"):
        out_path += ".pdf"
    folder = os.path.dirname(os.path.abspath(out_path))
    if not os.path.isdir(folder):
        raise SplitError("Thư mục lưu không tồn tại.")
    doc = result.doc
    if pages is not None and len(pages) != doc.page_count:
        sub = fitz.open()
        for i in pages:
            sub.insert_pdf(doc, from_page=i, to_page=i)
        doc = sub
    buf = io.BytesIO()
    doc.save(buf, garbage=3, deflate=True)
    fd, tmp = tempfile.mkstemp(suffix=".partial.pdf", dir=folder)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(buf.getvalue())
        if overwrite_source:
            bdir = os.path.join(os.path.dirname(src_path), "_backup_goc")
            os.makedirs(bdir, exist_ok=True)
            bpath = os.path.join(bdir, os.path.basename(src_path))
            if not os.path.exists(bpath):
                shutil.copy2(src_path, bpath)
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return out_path
