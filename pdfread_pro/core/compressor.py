"""Nén PDF theo giới hạn dung lượng TỪNG TRANG (KB).

Cách làm: đo dung lượng từng trang (tách riêng trong RAM), với các trang vượt giới hạn thì nén lại
ảnh nằm trên các trang đó (JPEG, giảm dần chất lượng và kích thước) cho tới khi mọi trang đạt hoặc
hết bậc nén. Chỉ ghi file kết quả khi thực sự nhỏ hơn bản gốc; ghi qua file tạm rồi thay thế.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import warnings

import pikepdf
from pikepdf import Name, PdfImage

warnings.filterwarnings("ignore", message=".*form widget annotation.*")

# (chất lượng JPEG, tỉ lệ thu nhỏ cạnh ảnh). Nghiên cứu trên trang scan chữ tiếng Việt (README – "Nén rõ chữ"):
# cùng một dung lượng, hạ độ phân giải về ~250 rồi ~200 dpi và giữ chất lượng JPEG vừa phải cho chữ RÕ HƠN hẳn
# giữ 300 dpi mà ép chất lượng xuống rất thấp (vỡ khối quanh dấu). Nên bậc giảm chất lượng ở 300 dpi chỉ tới q45,
# sau đó hạ dần độ phân giải (0.83 ≈ 250 dpi, 0.67 ≈ 200 dpi, …).
LEVELS: List[Tuple[int, float]] = [
    (85, 1.0), (75, 1.0), (65, 1.0), (55, 1.0), (45, 1.0),
    (50, 0.83), (40, 0.83), (32, 0.83), (25, 0.83), (19, 0.83),
    (28, 0.67), (22, 0.67), (17, 0.67),
    (22, 0.55), (16, 0.55), (18, 0.45), (14, 0.38),
]
# Dung lượng ảnh ở từng bậc so với bậc đầu – để nhảy thẳng tới bậc dự đoán là đạt thay vì thử lần lượt.
# Đo trên scan chất lượng cao, JPEG đã nén sẵn q50 và trang chữ dày nhiễu mạnh (trung bình nhân), chế độ rõ chữ.
# Sau mỗi lần nén vẫn đo lại thật; thiếu thì nén tiếp.
LEVEL_RATIO: List[float] = [1.0, 0.772, 0.647, 0.57, 0.5, 0.397, 0.347, 0.31, 0.268, 0.228, 0.205, 0.178, 0.154,
                            0.13, 0.106, 0.08, 0.051]
MAX_DPI = 300              # ảnh scan > 300 dpi được hạ về 300 dpi trước (chữ không rõ hơn, chỉ nặng hơn)
MIN_IMAGE_PIXELS = 20_000

ST_OK_ALREADY = "already"      # mọi trang đã đạt
ST_COMPRESSED = "compressed"   # đã nén, mọi trang đạt
ST_PARTIAL = "partial"         # đã nén tối đa nhưng còn trang vượt
ST_NO_IMAGE = "noimage"        # trang vượt toàn chữ/vector, không nén được
ST_NO_GAIN = "nogain"          # nén không nhỏ hơn bản gốc
ST_SKIP_SIGNED = "signed"
ST_ENCRYPTED = "encrypted"
ST_ERROR = "error"

STATUS_TEXT = {
    ST_OK_ALREADY: "Đã đạt chuẩn",
    ST_COMPRESSED: "Đã nén đạt chuẩn",
    ST_PARTIAL: "Đã nén tối đa (còn trang vượt)",
    ST_NO_IMAGE: "Không có ảnh để nén",
    ST_NO_GAIN: "Không giảm thêm được",
    ST_SKIP_SIGNED: "Giữ nguyên: file đã ký số",
    ST_ENCRYPTED: "Có mật khẩu – bỏ qua",
    ST_ERROR: "Lỗi",
}


@dataclass
class Result:
    path: str
    status: str
    before: int = 0
    after: int = 0
    pages: int = 0
    max_before_kb: float = 0.0
    max_after_kb: float = 0.0
    over_before: int = 0
    over_after: int = 0
    message: str = ""
    out_path: str = ""


def available_ram() -> int:
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        ms = MS()
        ms.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return int(ms.ullAvailPhys)
    except Exception:
        return 4 << 30


def safe_workers() -> int:
    """Số tiến trình song song: mỗi tiến trình dự phòng ~1,5 GB RAM (ảnh scan giải mã rất nặng)."""
    by_cpu = max(1, (os.cpu_count() or 2) - 1)
    by_ram = max(1, int(available_ram() // (1.5 * (1 << 30))))
    return max(1, min(by_cpu, by_ram, 8))


def _page_size(pdf: "pikepdf.Pdf", idx: int) -> int:
    dst = pikepdf.new()
    dst.pages.append(pdf.pages[idx])
    buf = io.BytesIO()
    dst.save(buf)
    return buf.tell()


def page_sizes(pdf: "pikepdf.Pdf", only: Optional[List[int]] = None) -> dict:
    idxs = range(len(pdf.pages)) if only is None else only
    return {i: _page_size(pdf, i) for i in idxs}


def measure_file(path: str, limit_kb: int) -> Result:
    """Phân tích: số trang và trang nặng nhất, không sửa file."""
    r = Result(path=path, status=ST_OK_ALREADY)
    try:
        r.before = os.path.getsize(path)
        with pikepdf.open(path) as pdf:
            sizes = page_sizes(pdf)
        r.pages = len(sizes)
        limit = limit_kb * 1024
        r.max_before_kb = max(sizes.values(), default=0) / 1024
        r.over_before = sum(1 for s in sizes.values() if s > limit)
        r.after, r.max_after_kb, r.over_after = r.before, r.max_before_kb, r.over_before
    except pikepdf.PasswordError:
        r.status, r.message = ST_ENCRYPTED, STATUS_TEXT[ST_ENCRYPTED]
    except Exception as e:
        r.status, r.message = ST_ERROR, f"Không đọc được: {e}"
    return r


def _page_images(page) -> list:
    """Ảnh (object gián tiếp) trên trang, kể cả ảnh nằm lồng trong Form XObject (máy scan, đóng dấu, ghép trang
    hay tạo kiểu này – page.images chỉ thấy ảnh đặt trực tiếp)."""
    out, seen = [], set()

    def walk(res, depth):
        if res is None or depth > 8:
            return
        try:
            xobjs = res.get("/XObject")
            items = list(xobjs.items()) if xobjs is not None else []
        except Exception:
            return
        for _, o in items:
            try:
                key = o.objgen
                if key == (0, 0) or key in seen:
                    continue
                seen.add(key)
                sub = o.get("/Subtype")
                if sub == Name.Image:
                    out.append(o)
                elif sub == Name.Form:
                    walk(o.get("/Resources"), depth + 1)
            except Exception:
                continue

    try:
        walk(page.resources, 0)
    except Exception:
        walk(page.obj.get("/Resources"), 0)
    return out


# Bảng lượng tử độ sáng chuẩn JPEG (Annex K) – để ước lượng chất lượng của ảnh JPEG có sẵn.
_STD_LUMA_SUM = sum((16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
                     14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
                     49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99))


def jpeg_quality(src) -> Optional[int]:
    """Chất lượng (1–100) ước lượng của ảnh JPEG trong PDF; None nếu không phải JPEG / không đọc được."""
    try:
        f = src.get("/Filter")
        if [str(x) for x in (f if isinstance(f, pikepdf.Array) else [f])] != ["/DCTDecode"]:
            return None
        from PIL import Image
        with Image.open(io.BytesIO(src.read_raw_bytes())) as im:
            table = im.quantization.get(0)
        if not table:
            return None
        sc = sum(table) * 100 / _STD_LUMA_SUM
        return max(1, min(100, round(5000 / sc if sc > 100 else (200 - sc) / 2)))
    except Exception:
        return None


def start_level(orig: "pikepdf.Pdf", pi: int) -> int:
    """Bậc bắt đầu cho trang: ảnh JPEG đã nén sẵn (vd q50) thì bỏ qua các bậc chất lượng cao hơn nó – nén lại
    ở chất lượng cao hơn chỉ làm ảnh to ra (trước đây phải thử lần lượt từng bậc → rất chậm)."""
    best = None
    for src in _page_images(orig.pages[pi]):
        try:
            if int(src.Width) * int(src.Height) < MIN_IMAGE_PIXELS:
                continue
        except Exception:
            continue
        q = jpeg_quality(src)
        lv = 0 if q is None else next((i for i, (lq, sc) in enumerate(LEVELS) if lq < q - 3 or sc < 1.0),
                                      len(LEVELS) - 1)
        best = lv if best is None else min(best, lv)
    return best or 0


def _is_grayish(img) -> bool:
    """Trang chỉ có mực đen / xám (không dấu đỏ, chữ ký màu, ảnh màu) → lưu ảnh xám: nhẹ hơn, nén nhanh gấp ~3 lần.
    Xét ảnh thu nhỏ; chỉ cần vài chục điểm có màu rõ (dấu đỏ, nét ký xanh) là giữ màu."""
    t = img.copy()
    t.thumbnail((480, 480))
    t = t.convert("RGB")
    r, g, b = t.split()
    from PIL import ImageChops
    chroma = ImageChops.lighter(ImageChops.lighter(ImageChops.difference(r, g), ImageChops.difference(g, b)),
                                ImageChops.difference(r, b))
    colored = sum(chroma.histogram()[36:])
    return colored <= max(12, t.width * t.height // 10000)


def _clean_background(img):
    """Làm trắng nền giấy: tìm màu giấy (đỉnh sáng của biểu đồ độ sáng) và độ nhiễu → giấy & nhiễu thành trắng,
    mực đậm hơn → chữ rõ, nền sạch. Trang không phải giấy chữ (ảnh chụp, trang tối) → giữ nguyên."""
    g = img if img.mode == "L" else img.convert("L")
    h = g.histogram()
    n = sum(h)
    peak = max(range(140, 256), key=lambda v: h[v])
    win = range(max(0, peak - 40), min(256, peak + 41))
    m = sum(h[v] for v in win)
    if m < 0.35 * n:
        return img
    sd = (sum(h[v] * (v - peak) ** 2 for v in win) / m) ** 0.5
    acc, lo = 0, 0
    for v in range(256):
        acc += h[v]
        if acc >= 0.005 * n:
            lo = v
            break
    hi = int(max(lo + 60, peak - 2.2 * sd - 4))
    lut = [0 if v <= lo else 255 if v >= hi else round(255 * ((v - lo) / (hi - lo)) ** 1.15) for v in range(256)]
    return img.point(lut * (1 if img.mode == "L" else 3))


def _encode(img, w: int, h: int, quality: int, scale: float, clean: bool = False):
    """Chạy ở luồng phụ (Pillow nhả GIL khi giải mã / thu nhỏ / mã hoá): ảnh PIL → (JPEG bytes, rộng, cao, gray).
    clean = chế độ rõ chữ: trang không màu → ảnh xám, làm trắng nền giấy."""
    from PIL import Image

    tw, th = max(8, int(w * scale)), max(8, int(h * scale))
    if scale <= 0.5 and getattr(img, "format", "") == "JPEG":
        img.draft(img.mode, (tw, th))                 # giải mã thẳng ở 1/2, 1/4 độ phân giải: nhanh gấp nhiều lần
    gray = img.mode in ("L", "1") or (clean and img.mode in ("RGB", "CMYK", "P") and _is_grayish(img))
    want = "L" if gray else "RGB"
    if img.mode != want:
        img = img.convert(want)
    if img.size != (tw, th):
        img = img.resize((tw, th), Image.BICUBIC)
    if clean:
        img = _clean_background(img)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality, optimize=True)
    return out.getvalue(), img.width, img.height, gray


def _dpi_scale(page, w: int, h: int) -> float:
    """Hệ số đưa ảnh scan quá MAX_DPI về MAX_DPI (ảnh phủ cả trang); ảnh nhỏ hơn trang / ≤ MAX_DPI → 1."""
    try:
        box = page.mediabox
        pw, ph = abs(float(box[2]) - float(box[0])) / 72, abs(float(box[3]) - float(box[1])) / 72
        if pw <= 0 or ph <= 0:
            return 1.0
        dpi = min(max(w / pw, h / ph), max(w / ph, h / pw))   # bền với trang / ảnh xoay
        return min(1.0, MAX_DPI / dpi) if dpi > MAX_DPI * 1.1 else 1.0
    except Exception:
        return 1.0


def _recompress_images(orig: "pikepdf.Pdf", work: "pikepdf.Pdf", pages: List[int], quality: int,
                       scale: float, threads: int = 1, clean: bool = False, dry: bool = False):
    """Nén lại ảnh trên các trang `pages`: luôn giải mã từ ảnh GỐC (orig) rồi ghi vào bản đang sửa (work),
    nên mỗi bậc nén là nén 1 lần từ bản gốc, không nén chồng. Hai bản mở từ cùng 1 file nên ghép ảnh theo
    số hiệu object. Đọc / ghi PDF ở luồng gọi (pikepdf không dùng chung giữa luồng được), phần nặng
    (giải mã, thu nhỏ, mã hoá JPEG) chạy song song `threads` luồng. Trả (số ảnh nén được, số ảnh đã thử,
    {trang: số byte giảm được ở bậc này}) – thử mà không nhỏ hơn bản gốc thì không ghi, nhưng vẫn tính
    (số âm) để dự đoán bậc cần nén."""
    from concurrent.futures import ThreadPoolExecutor

    tasks = []                                   # (trang, object đích, độ dài gốc, ảnh gốc, rộng, cao)
    seen = set()
    for pi in pages:
        try:
            images = _page_images(orig.pages[pi])
        except Exception:
            continue
        for src in images:
            try:
                key = src.objgen
                if key in seen:
                    continue
                seen.add(key)
                if src.get("/ImageMask", False):
                    continue
                w, h = int(src.Width), int(src.Height)
                if w * h < MIN_IMAGE_PIXELS:
                    continue
                sc = scale * _dpi_scale(orig.pages[pi], w, h)
                tasks.append((pi, work.get_object(key), len(src.read_raw_bytes()), src, w, h, sc))
            except Exception:
                continue

    changed = 0
    saved: Dict[int, int] = {}
    staged: Dict[int, list] = {}                  # dry: {trang: [(task, res)]} – ghi sau bằng write_staged

    def apply(task, res):
        nonlocal changed
        pi, obj, old_len = task[0], task[1], task[2]
        data = res[0]
        saved[pi] = saved.get(pi, 0) + max(0, old_len - len(data)) if dry else saved.get(pi, 0) + old_len - len(data)
        if len(data) >= old_len:
            return
        if dry:
            staged.setdefault(pi, []).append((task, res))
            return
        _write_image(obj, res)
        changed += 1

    def run(item):
        t, img = item
        try:
            return _encode(img, t[4], t[5], quality, t[6], clean) if img is not None else None
        except Exception:
            return None

    def load(t):
        try:
            return PdfImage(t[3]).as_pil_image()      # ảnh không phải JPEG được giải mã ngay ở đây (luồng gọi)
        except Exception:
            return None

    # xử lý theo lô nhỏ để không giữ quá nhiều ảnh đã giải mã trong RAM cùng lúc
    step = max(1, threads * 2)
    ex = ThreadPoolExecutor(max_workers=threads) if threads > 1 and len(tasks) > 1 else None
    try:
        for k in range(0, len(tasks), step):
            batch = [(t, load(t)) for t in tasks[k:k + step]]
            results = ex.map(run, batch) if ex else map(run, batch)
            for (t, _), res in zip(batch, results):
                if res is not None:
                    try:
                        apply(t, res)
                    except Exception:
                        pass
    finally:
        if ex:
            ex.shutdown()
    return (changed, len(tasks), saved, staged) if dry else (changed, len(tasks), saved)


def _write_image(obj, res) -> None:
    data, nw, nh, gray = res
    obj.write(data, filter=Name.DCTDecode)
    obj.Width, obj.Height = nw, nh
    obj.ColorSpace = Name.DeviceGray if gray else Name.DeviceRGB
    obj.BitsPerComponent = 8
    for k in ("/Decode", "/DecodeParms", "/Mask"):
        if k in obj:
            del obj[k]


def compress_file(src: str, dst: str, limit_kb: int, backup: bool = False, threads: int = 0,
                  clean: bool = True) -> Result:
    """Nén `src` → `dst` (dst có thể trùng src = ghi đè an toàn qua file tạm).
    threads: số luồng xử lý ảnh trong 1 file (0 = tự chọn theo số nhân CPU).
    clean: chế độ RÕ CHỮ – làm trắng nền giấy, trang không màu lưu ảnh xám. Ảnh > 300 dpi luôn được hạ về 300 dpi."""
    if threads <= 0:
        threads = max(1, min(8, (os.cpu_count() or 2) - 1))
    limit = limit_kb * 1024
    r = Result(path=src, status=ST_ERROR, out_path=dst)
    tmp_path = ""
    try:
        r.before = os.path.getsize(src)
        with pikepdf.open(src) as pdf:
            sizes = page_sizes(pdf)
        r.pages = len(sizes)
        over = [i for i, s in sizes.items() if s > limit]
        r.max_before_kb = max(sizes.values(), default=0) / 1024
        r.over_before = len(over)
        r.after, r.max_after_kb, r.over_after = r.before, r.max_before_kb, r.over_before
        if not over:
            r.status = ST_OK_ALREADY
            if os.path.abspath(src) != os.path.abspath(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
            return r

        # Nén theo từng trang: trang đạt ở bậc nào thì dừng ở bậc đó (giữ chất lượng cao nhất có thể),
        # chỉ các trang còn vượt mới thử bậc mạnh hơn. Đo trang ngay trên bản trong RAM, không ghi cả file mỗi bậc.
        any_change = any_image = False
        with pikepdf.open(src) as orig, pikepdf.open(src) as work:
            orig_sizes = dict(sizes)
            level = {i: start_level(orig, i) for i in over}
            first = dict(level)
            over_lv = {i: level[i] - 1 for i in over}   # bậc cao nhất đã biết là còn vượt giới hạn
            pending = list(over)
            while pending:
                groups: dict = {}
                for i in pending:
                    groups.setdefault(level[i], []).append(i)
                changed = tried = 0
                saved: Dict[int, int] = {}
                for lv, pages in sorted(groups.items()):
                    c, t, sv = _recompress_images(orig, work, pages, *LEVELS[lv], threads=threads, clean=clean)
                    changed, tried = changed + c, tried + t
                    saved.update(sv)
                if tried == 0:
                    break                          # các trang còn vượt không có ảnh nào để nén
                any_image = True
                if changed:
                    any_change = True
                    new_sizes = page_sizes(work, pending)
                else:                              # ảnh đã nén sẵn: bậc này chưa nhỏ hơn bản gốc → thử bậc mạnh hơn
                    new_sizes = {i: sizes[i] for i in pending}
                nxt = []
                for i in pending:
                    s, lv = new_sizes[i], level[i]
                    if s > limit:
                        over_lv[i] = max(over_lv[i], lv)
                    if s <= limit or lv == len(LEVELS) - 1:
                        continue
                    # dung lượng trang NẾU dùng bậc này (kể cả khi ảnh chưa nhỏ hơn gốc nên chưa ghi)
                    # → nhảy thẳng tới bậc dự đoán là đạt
                    virt = max(1, orig_sizes[i] - saved.get(i, 0))
                    j = lv + 1
                    while j < len(LEVELS) - 1 and virt * LEVEL_RATIO[j] / LEVEL_RATIO[lv] > limit:
                        j += 1
                    level[i] = j
                    nxt.append(i)
                sizes.update(new_sizes)
                pending = nxt
            # Tinh chỉnh: dự đoán nhảy quá tay (trang chỉ còn < 75% giới hạn) → thử lùi 1 bậc nhẹ hơn (chữ rõ hơn).
            # Thử "khô" (chỉ mã hoá, tính dung lượng), chỉ ghi khi chắc chắn vẫn ≤ giới hạn.
            if any_change:
                for _ in range(2):
                    cand: dict = {}
                    for i in over:
                        j = level[i] - 1
                        if sizes[i] < 0.75 * limit and j > over_lv[i] and j >= first[i]:
                            cand.setdefault(j, []).append(i)
                    if not cand:
                        break
                    for j, pages in cand.items():
                        _, _, sv, staged = _recompress_images(orig, work, pages, *LEVELS[j], threads=threads,
                                                              clean=clean, dry=True)
                        for i in pages:
                            virt = orig_sizes[i] - sv.get(i, 0)
                            if virt <= 0.97 * limit and staged.get(i):
                                for task, res in staged[i]:
                                    _write_image(task[1], res)
                                level[i] = j
                            else:
                                over_lv[i] = j
                    real = page_sizes(work, [i for ps in cand.values() for i in ps])
                    for i, s2 in real.items():
                        if s2 > limit:                 # phòng hờ ước lượng sai: ghi lại bậc cũ đã đạt
                            over_lv[i] = level[i]
                            level[i] += 1
                            _recompress_images(orig, work, [i], *LEVELS[level[i]], threads=threads, clean=clean)
                            s2 = page_sizes(work, [i])[i]
                        sizes[i] = s2
            pending = [i for i in over if sizes[i] > limit]
            if not any_change:
                st = ST_NO_GAIN if any_image else ST_NO_IMAGE
                r.status, r.message = st, STATUS_TEXT[st]
                return r
            buf = io.BytesIO()
            work.save(buf)
            data = buf.getvalue()
        still, mx = len(pending), max(sizes.values(), default=0)
        if len(data) >= r.before:
            r.status, r.message = ST_NO_GAIN, STATUS_TEXT[ST_NO_GAIN]
            return r
        with pikepdf.open(io.BytesIO(data)) as chk:          # kết quả phải mở lại được và đủ số trang mới được ghi
            if len(chk.pages) != r.pages:
                raise ValueError(f"file nén sai số trang ({len(chk.pages)} ≠ {r.pages}) – giữ nguyên bản gốc")
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=os.path.dirname(dst) or ".")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        if backup and os.path.abspath(src) == os.path.abspath(dst):
            bdir = os.path.join(os.path.dirname(src), "_backup_goc")
            os.makedirs(bdir, exist_ok=True)
            bpath = os.path.join(bdir, os.path.basename(src))
            if not os.path.exists(bpath):
                shutil.copy2(src, bpath)
        os.replace(tmp_path, dst)
        tmp_path = ""
        r.after, r.over_after, r.max_after_kb = len(data), still, mx / 1024
        r.status = ST_COMPRESSED if still == 0 else ST_PARTIAL
        r.message = STATUS_TEXT[r.status]
    except pikepdf.PasswordError:
        r.status, r.message = ST_ENCRYPTED, STATUS_TEXT[ST_ENCRYPTED]
    except Exception as e:
        r.status, r.message = ST_ERROR, f"Lỗi: {e}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return r


def job_measure(args) -> Result:
    return measure_file(*args)


def job_compress(args) -> Result:
    return compress_file(*args)
