"""Đọc SỐ TRANG in trên bản scan (đầu/chân trang) bằng OCR có sẵn của Windows 10/11 (Windows.Media.Ocr),
không cần cài thêm gì. Dùng để tự xác định thứ tự sổ gỡ ghim và mặt nào bị lộn ngược.

Windows OCR hay bỏ sót số 1 chữ số đứng riêng → cắt sát cụm mực rồi ghép sau chữ "Trang" để OCR đọc
theo ngữ cảnh ("Trang 7")."""
from __future__ import annotations

import asyncio
import contextvars
import re
from typing import Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

STRIP = 0.13            # tỉ lệ chiều cao dải đầu / chân trang được đọc
_PREFIX = "Trang"
_TO_DIGIT = str.maketrans({"l": "1", "I": "1", "|": "1", "i": "1", "!": "1", "O": "0", "o": "0"})

_engine = None
_checked = False
# nhóm engine dùng khi đọc song song nhiều trang (mỗi engine chỉ chạy 1 lệnh nhận dạng một lúc)
_POOL: "contextvars.ContextVar[Optional[asyncio.Queue]]" = contextvars.ContextVar("ocr_pool", default=None)


def _create_engine():
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine
    eng = None
    for tag in ("en-US", "en-GB", "vi-VN"):
        try:
            if OcrEngine.is_language_supported(Language(tag)):
                eng = OcrEngine.try_create_from_language(Language(tag))
                if eng:
                    break
        except Exception:
            pass
    return eng or OcrEngine.try_create_from_user_profile_languages()


def _get_engine():
    global _engine, _checked
    if _checked:
        return _engine
    _checked = True
    try:
        _engine = _create_engine()
    except Exception:
        _engine = None
    return _engine


def available() -> bool:
    """Máy có Windows OCR (Windows 10/11 có gói ngôn ngữ OCR) hay không."""
    return _get_engine() is not None


async def _ocr_lines(im: Image.Image) -> List[str]:
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter
    im = im.convert("L")
    w = DataWriter()
    w.write_bytes(im.tobytes())
    bmp = SoftwareBitmap.create_copy_from_buffer(w.detach_buffer(), BitmapPixelFormat.GRAY8, im.width, im.height)
    pool = _POOL.get()
    if pool is None:
        res = await _get_engine().recognize_async(bmp)
    else:
        eng = await pool.get()
        try:
            res = await eng.recognize_async(bmp)
        finally:
            pool.put_nowait(eng)
    return [ln.text for ln in res.lines]


# ------------------------------------------------------------------ phân tích chữ

def parse_number(lines: Sequence[str], max_page: int = 999, prefixed: bool = False) -> Optional[int]:
    """Lấy số trang từ các dòng OCR. Chỉ nhận dòng NGẮN chỉ chứa số (vd '7', '- 7 -', '(7)', 'Trang 7', '7/20')
    để không nhầm với ngày tháng, số hiệu văn bản…"""
    for raw in lines:
        t = raw.strip()
        if prefixed:
            if not t.lower().startswith(_PREFIX.lower()):
                continue
            t = t[len(_PREFIX):].strip()
            t = re.sub(r"^(trang|page)\s*", "", t, flags=re.I)   # dòng gốc đã có chữ "Trang"
            t = t.translate(_TO_DIGIT)
        m = (re.fullmatch(r"(?:trang|page|tr\.?)\s*(\d{1,3})(?:\s*/\s*\d{1,3})?", t, re.I)
             or re.fullmatch(r"[-–—~(\[.\s]*(\d{1,3})[-–—~)\].\s]*", t)
             or re.fullmatch(r"(\d{1,3})\s*/\s*\d{1,3}", t))
        if m:
            n = int(m.group(1))
            if 1 <= n <= max_page:
                return n
    return None


def _runs(profile: bytes, min_gap: int = 1) -> List[Tuple[int, int]]:
    """Các đoạn liên tiếp có mực (giá trị > 0), gộp các khe hở ngắn hơn min_gap."""
    runs: List[Tuple[int, int]] = []
    start = None
    for i, v in enumerate(profile):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(profile)))
    merged: List[Tuple[int, int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(r)
    return merged


def _ink_clusters(strip: Image.Image) -> List[Tuple[int, int, int, int]]:
    """Các cụm mực (từ) trong dải: tách theo dòng rồi theo khoảng trống ngang; bỏ dấu gạch '-' ở hai đầu."""
    bw = strip.point(lambda v: 255 if v < 150 else 0)
    w, h = bw.size
    out = []
    for y0, y1 in _runs(bytes(bw.getprojection()[1]), min_gap=3):
        bh = y1 - y0
        if bh < 5:
            continue
        line = bw.crop((0, y0, w, y1))
        cols = bytes(line.getprojection()[0])
        for x0, x1 in _runs(cols, min_gap=max(4, int(bh * 0.6))):
            # trong cụm: bỏ các mảnh thấp (gạch ngang) ở hai đầu
            parts = []
            for a, b in _runs(cols[x0:x1]):
                box = line.crop((x0 + a, 0, x0 + b, bh)).getbbox()
                if box:
                    parts.append((x0 + a, box[1], x0 + b, box[3]))
            tall = max((p[3] - p[1] for p in parts), default=0)
            while parts and parts[0][3] - parts[0][1] < tall * 0.45:
                parts.pop(0)
            while parts and parts[-1][3] - parts[-1][1] < tall * 0.45:
                parts.pop()
            if not parts:
                continue
            bx0, bx1 = parts[0][0], parts[-1][2]
            by0, by1 = min(p[1] for p in parts) + y0, max(p[3] for p in parts) + y0
            cw, ch = bx1 - bx0, by1 - by0
            if ch < 5 or cw > ch * 4.5:
                continue                                # quá dài: câu chữ, không phải số trang
            out.append((bx0, by0, bx1, by1))
    return out


def _font(size: int):
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _with_prefix(ink: Image.Image, target: int) -> Image.Image:
    """Ghép chữ 'Trang' (cao bằng chữ số) trước cụm mực, cùng đường chân chữ, phóng tới chiều cao `target`
    và chừa lề rộng (Windows OCR đọc kém ảnh nhỏ / sát mép)."""
    ink = ink.point(lambda v: 0 if v < 160 else 255)
    k = target / ink.height
    ink = ink.resize((max(1, int(ink.width * k)), target), Image.LANCZOS)
    h = ink.height
    font = _font(max(8, int(h / 0.72)))              # chữ hoa Arial cao ≈ 0,72 cỡ chữ
    pad = max(40, h)
    tw = int(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(_PREFIX + " ", font=font))
    canvas = Image.new("L", (pad + tw + ink.width + pad, h + 2 * pad), 255)
    base = pad + h
    ImageDraw.Draw(canvas).text((pad, base), _PREFIX, fill=0, font=font, anchor="ls")
    canvas.paste(ink, (pad + tw, base - h))
    return canvas


async def _read_strip(strip: Image.Image, max_page: int) -> Optional[int]:
    lines = await _ocr_lines(ImageOps.expand(strip, border=40, fill=255))
    n = parse_number(lines, max_page)
    if n is not None:
        return n
    clusters = _ink_clusters(strip)
    cx = strip.width / 2
    # ưu tiên cụm ở giữa và hai góc – nơi thường in số trang
    clusters.sort(key=lambda b: min(abs((b[0] + b[2]) / 2 - cx), b[0], strip.width - b[2]))
    for b in clusters[:3]:
        ink = strip.crop(b)
        for target in (36, 60):
            n = parse_number(await _ocr_lines(_with_prefix(ink, target)), max_page, prefixed=True)
            if n is not None:
                return n
    return None


def _letters(lines: Sequence[str]) -> int:
    return sum(len(w) for ln in lines for w in re.findall(r"[^\W\d_]{3,}", ln))


async def _orientation(img: Image.Image) -> Optional[int]:
    """0 = trang đứng thuận, 180 = lộn ngược, None = không đủ chữ để biết. Dựa vào chữ thân trang
    (tránh nhầm số 6 lộn ngược thành 9)."""
    w, h = img.size
    band = img.crop((0, int(h * 0.25), w, int(h * 0.75)))
    a = _letters(await _ocr_lines(band))
    b = _letters(await _ocr_lines(band.rotate(180)))
    # chữ lộn ngược vẫn bị OCR đọc ra "chữ rác" → chiều đúng thường nhiều chữ hơn ≥ 1,5 lần
    if max(a, b) >= 20 and max(a, b) >= 1.35 * min(a, b):
        return 0 if a >= b else 180
    return None


async def _read_page(img: Image.Image, max_page: int) -> Tuple[Optional[int], Optional[int]]:
    """(số đọc theo chiều hiện tại, số đọc khi xoay 180°)."""
    img = img.convert("L")
    orient = await _orientation(img)
    if orient == 180:
        n = await _read_upright(img.rotate(180), max_page)
        return None, n
    n = await _read_upright(img, max_page)
    if n is not None or orient == 0:
        return n, None
    return None, await _read_upright(img.rotate(180), max_page)


async def _read_upright(img: Image.Image, max_page: int) -> Optional[int]:
    w, h = img.size
    s = max(1, int(h * STRIP))
    top, bottom = img.crop((0, 0, w, s)), img.crop((0, h - s, w, h))
    n = await _read_strip(bottom, max_page)
    return n if n is not None else await _read_strip(top, max_page)


async def _orientation4(img: Image.Image) -> Optional[int]:
    """Góc (độ, ngược chiều kim đồng hồ – như PIL rotate) cần xoay để trang đứng thuận: 0 / 90 / 180 / 270,
    None = không đủ chữ để biết. Thử chiều dọc trước; chỉ thử nằm ngang khi chưa rõ (đỡ tốn thời gian)."""
    w, h = img.size
    band = img.crop((0, int(h * 0.25), w, int(h * 0.75)))
    a = _letters(await _ocr_lines(band))
    b = _letters(await _ocr_lines(band.rotate(180)))
    if max(a, b) >= 20 and max(a, b) >= 1.35 * min(a, b):
        return 0 if a >= b else 180
    side = img.rotate(90, expand=True)
    sw, sh = side.size
    band = side.crop((0, int(sh * 0.25), sw, int(sh * 0.75)))
    c = _letters(await _ocr_lines(band))
    d = _letters(await _ocr_lines(band.rotate(180)))
    hi, lo = max(c, d), min(c, d)
    if hi >= 20 and hi >= 1.35 * max(a, b, lo):
        return 90 if c >= d else 270
    return None


async def _page_info(img: Image.Image, max_page: int) -> Tuple[Optional[int], Optional[int]]:
    img = img.convert("L")
    ang = await _orientation4(img)
    n = await _read_upright(img.rotate(ang, expand=True) if ang else img, max_page)
    if ang is None:
        if n is not None:
            return 0, n
        n = await _read_upright(img.rotate(180), max_page)      # trang ít chữ (bìa…) nhưng có số in
        return (180 if n is not None else None), n
    return ang, n


def page_infos(images: Iterable[Image.Image], max_page: int = 999,
               progress=None, cancelled=None, concurrency: int = 1) -> List[Tuple[Optional[int], Optional[int]]]:
    """Mỗi ảnh trang → (góc cần xoay để đứng thuận 0/90/180/270 hoặc None, số trang in hoặc None).
    `images` có thể là generator (vẽ từng trang khi cần – đỡ tốn RAM với file nhiều trang).
    concurrency > 1: đọc song song tối đa ngần ấy trang (mỗi trang một engine OCR) – kết quả GIỐNG HỆT đọc tuần tự,
    nhanh gấp ~2–3 lần (vẽ trang tiếp theo trong lúc OCR đang chạy)."""
    if not available():
        raise RuntimeError("Máy không có Windows OCR (cần Windows 10/11).")
    if concurrency > 1:
        return asyncio.run(_page_infos_parallel(images, max_page, progress, cancelled, concurrency))

    async def run():
        out = []
        for im in images:
            if cancelled and cancelled():
                break
            out.append(await _page_info(im, max_page) if im is not None else (None, None))
            if progress:
                progress(len(out))
        return out

    return asyncio.run(run())


def read_pages(images: Sequence[Image.Image], max_page: int = 999,
               progress=None, cancelled=None) -> List[Tuple[Optional[int], Optional[int]]]:
    """Đọc số trang cho từng ảnh trang. Mỗi phần tử: (số theo chiều thuận, số khi xoay 180°) –
    chỉ một trong hai có giá trị, hoặc cả hai None nếu không đọc được."""
    if not available():
        raise RuntimeError("Máy không có Windows OCR (cần Windows 10/11).")

    async def run():
        out = []
        for i, im in enumerate(images):
            if cancelled and cancelled():
                break
            out.append(await _read_page(im, max_page))
            if progress:
                progress(i + 1, len(images))
        return out

    return asyncio.run(run())


async def _page_infos_parallel(images, max_page, progress, cancelled, n):
    engines = [_get_engine()]
    for _ in range(n - 1):
        try:
            e = _create_engine()
        except Exception:
            e = None
        if e is not None:
            engines.append(e)
    pool: asyncio.Queue = asyncio.Queue()
    for e in engines:
        pool.put_nowait(e)
    n = len(engines)
    token = _POOL.set(pool)
    out: dict = {}

    async def one(i: int, im: Image.Image):
        out[i] = await _page_info(im, max_page)
        if progress:
            progress(len(out))

    try:
        tasks: set = set()
        idx = 0
        sentinel = object()
        it = iter(images)
        while not (cancelled and cancelled()):
            while len(tasks) >= n:
                done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for d in done:
                    d.result()
            im = next(it, sentinel)                      # vẽ trang kế tiếp trong lúc các trang trước đang OCR
            if im is sentinel:
                break
            if im is None:
                out[idx] = (None, None)
                if progress:
                    progress(len(out))
            else:
                tasks.add(asyncio.create_task(one(idx, im)))
            idx += 1
            await asyncio.sleep(0)
        if tasks:
            await asyncio.gather(*tasks)
    finally:
        _POOL.reset(token)
    done_n = 0
    while done_n in out:
        done_n += 1
    return [out[i] for i in range(done_n)]
