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
from typing import List, Optional, Tuple

import warnings

import pikepdf
from pikepdf import Name, PdfImage

warnings.filterwarnings("ignore", message=".*form widget annotation.*")

# (chất lượng JPEG, tỉ lệ thu nhỏ cạnh ảnh)
# Bậc mịn, ưu tiên giữ nguyên độ phân giải (chữ scan sắc nét) – chỉ thu nhỏ ảnh khi hạ chất lượng không đủ.
LEVELS: List[Tuple[int, float]] = [
    (85, 1.0), (78, 1.0), (70, 1.0), (62, 1.0), (55, 1.0), (50, 0.9), (45, 0.8), (40, 0.7), (35, 0.6),
    (30, 0.5), (25, 0.4), (20, 0.33),
]
# Dung lượng ảnh ở từng bậc so với bậc đầu (đo trên ảnh scan) – để nhảy thẳng tới bậc dự đoán là đạt
# thay vì thử lần lượt. Sau mỗi lần nén vẫn đo lại thật; dự đoán thiếu thì nén tiếp bậc sau.
LEVEL_RATIO: List[float] = [1.0, 0.763, 0.616, 0.511, 0.456, 0.325, 0.23, 0.171, 0.121, 0.079, 0.045, 0.029]
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


def _recompress_images(orig: "pikepdf.Pdf", work: "pikepdf.Pdf", pages: List[int], quality: int,
                       scale: float) -> int:
    """Nén lại ảnh trên các trang `pages`: luôn giải mã từ ảnh GỐC (orig) rồi ghi vào bản đang sửa (work),
    nên mỗi bậc nén là nén 1 lần từ bản gốc, không nén chồng."""
    from PIL import Image

    changed = 0
    seen = set()
    for pi in pages:
        try:
            pairs = [(src, work.pages[pi].images[name]) for name, src in orig.pages[pi].images.items()]
        except Exception:
            continue
        for src, obj in pairs:
            try:
                key = src.objgen
                if key != (0, 0):
                    if key in seen:
                        continue
                    seen.add(key)
                if src.get("/Subtype") != Name.Image or src.get("/ImageMask", False):
                    continue
                w, h = int(src.Width), int(src.Height)
                if w * h < MIN_IMAGE_PIXELS:
                    continue
                old_len = len(src.read_raw_bytes())
                img = PdfImage(src).as_pil_image()
                if img.mode in ("L", "1"):
                    cs = Name.DeviceGray
                    if img.mode != "L":
                        img = img.convert("L")
                else:
                    cs = Name.DeviceRGB
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                if scale < 1.0:
                    img = img.resize((max(8, int(w * scale)), max(8, int(h * scale))), Image.LANCZOS,
                                     reducing_gap=2.0)
                out = io.BytesIO()
                img.save(out, "JPEG", quality=quality, optimize=True)
                data = out.getvalue()
                if len(data) >= old_len:
                    continue
                obj.write(data, filter=Name.DCTDecode)
                obj.Width, obj.Height = img.width, img.height
                obj.ColorSpace = cs
                obj.BitsPerComponent = 8
                for k in ("/Decode", "/DecodeParms", "/Mask"):
                    if k in obj:
                        del obj[k]
                changed += 1
            except Exception:
                continue
    return changed


def compress_file(src: str, dst: str, limit_kb: int, backup: bool = False) -> Result:
    """Nén `src` → `dst` (dst có thể trùng src = ghi đè an toàn qua file tạm)."""
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
        any_change = False
        with pikepdf.open(src) as orig, pikepdf.open(src) as work:
            level = {i: 0 for i in over}
            pending = list(over)
            while pending:
                groups: dict = {}
                for i in pending:
                    groups.setdefault(level[i], []).append(i)
                changed = 0
                for lv, pages in sorted(groups.items()):
                    changed += _recompress_images(orig, work, pages, *LEVELS[lv])
                if changed == 0:
                    break                          # các trang còn vượt không có ảnh nén thêm được
                any_change = True
                new_sizes = page_sizes(work, pending)
                sizes.update(new_sizes)
                nxt = []
                for i in pending:
                    s, lv = new_sizes[i], level[i]
                    if s <= limit or lv == len(LEVELS) - 1:
                        continue
                    j = lv + 1
                    while j < len(LEVELS) - 1 and s * LEVEL_RATIO[j] / LEVEL_RATIO[lv] > limit:
                        j += 1
                    level[i] = j
                    nxt.append(i)
                pending = nxt
            pending = [i for i in over if sizes[i] > limit]
            if not any_change:
                r.status = ST_NO_IMAGE
                r.message = STATUS_TEXT[ST_NO_IMAGE]
                return r
            buf = io.BytesIO()
            work.save(buf)
            data = buf.getvalue()
        still, mx = len(pending), max(sizes.values(), default=0)
        if len(data) >= r.before:
            r.status, r.message = ST_NO_GAIN, STATUS_TEXT[ST_NO_GAIN]
            return r
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
