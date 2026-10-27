import io
import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pikepdf  # noqa: E402
import pymupdf as fitz  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from pdfread_pro.core import compressor as C  # noqa: E402


def scan_page(doc, rnd, w, h, quality=95):
    """Trang 'scan' giả lập: chữ + nhiễu, chèn ảnh JPEG cỡ w×h."""
    img = Image.new("RGB", (w, h), (250, 248, 240))
    d = ImageDraw.Draw(img)
    for y in range(40, h - 40, 30):
        d.text((40, y), "Dong van ban scan thu nghiem " * 4, fill=(20, 20, 20))
    px = img.load()
    for _ in range(w * h // 60):
        px[rnd.randrange(w), rnd.randrange(h)] = (rnd.randrange(150, 256),) * 3
    b = io.BytesIO()
    img.save(b, "JPEG", quality=quality)
    pg = doc.new_page(width=595, height=842)
    pg.insert_image(pg.rect, stream=b.getvalue())


class CompressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        rnd = random.Random(5)
        doc = fitz.open()
        scan_page(doc, rnd, 300, 420)            # trang 0: nhẹ, đã đạt
        scan_page(doc, rnd, 1240, 1754)          # trang 1: nặng
        scan_page(doc, rnd, 700, 990)            # trang 2: vượt vừa
        doc.new_page().insert_text((72, 72), "Trang chữ")   # trang 3: không có ảnh
        self.src = os.path.join(self.tmp, "scan.pdf")
        doc.save(self.src)
        with pikepdf.open(self.src) as pdf:
            self.before = C.page_sizes(pdf)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_per_page_levels(self):
        limit_kb = int(self.before[2] / 1024 * 0.8)          # trang 2 chỉ vượt nhẹ
        self.assertLess(self.before[0], limit_kb * 1024)
        self.assertGreater(self.before[1], limit_kb * 1024)
        dst = os.path.join(self.tmp, "out", "scan.pdf")
        r = C.compress_file(self.src, dst, limit_kb)
        self.assertEqual(r.status, C.ST_COMPRESSED, r.message)
        self.assertEqual(r.over_after, 0)
        with pikepdf.open(dst) as pdf:
            after = C.page_sizes(pdf)
            self.assertEqual(len(pdf.pages), 4)
        self.assertTrue(all(s <= limit_kb * 1024 for s in after.values()), after)
        self.assertEqual(after[0], self.before[0])              # trang đã đạt: giữ nguyên
        self.assertEqual(after[3], self.before[3])
        # trang chỉ vượt nhẹ không bị nén mạnh như trang nặng (nén theo từng trang, không chung 1 bậc)
        self.assertGreater(after[2] / self.before[2], after[1] / self.before[1])
        self.assertLess(r.after, r.before)
        self.assertAlmostEqual(r.max_after_kb, max(after.values()) / 1024, delta=1)

    def _check(self, path, ratio=0.5):
        with pikepdf.open(path) as pdf:
            mx = max(C.page_sizes(pdf).values())
        limit_kb = int(mx / 1024 * ratio)
        dst = path.replace(".pdf", "_out.pdf")
        r = C.compress_file(path, dst, limit_kb)
        self.assertEqual(r.status, C.ST_COMPRESSED, r.message)
        with pikepdf.open(dst) as pdf:
            self.assertTrue(all(s <= limit_kb * 1024 for s in C.page_sizes(pdf).values()))
        a, b = fitz.open(path)[0].get_pixmap(dpi=30), fitz.open(dst)[0].get_pixmap(dpi=30)
        diff = sum(abs(x - y) for x, y in zip(a.samples, b.samples)) / len(a.samples)
        self.assertLess(diff, 10)                                 # ảnh vẫn đúng nội dung, không hỏng

    def test_low_quality_jpeg(self):
        """Lỗi cũ: JPEG đã nén sẵn (q50) → bậc đầu q85 không nhỏ hơn → báo nhầm 'Không có ảnh để nén'."""
        doc = fitz.open()
        scan_page(doc, random.Random(7), 1240, 1754, quality=50)
        p = os.path.join(self.tmp, "lowq.pdf")
        doc.save(p)
        self._check(p)

    def test_image_inside_form_xobject(self):
        """Lỗi cũ: ảnh nằm trong Form XObject (máy scan / đóng dấu / ghép trang) không được tìm thấy."""
        src = fitz.open()
        scan_page(src, random.Random(8), 1240, 1754)
        doc = fitz.open()
        pg = doc.new_page(width=595, height=842)
        pg.show_pdf_page(pg.rect, src, 0)
        p = os.path.join(self.tmp, "form.pdf")
        doc.save(p)
        with pikepdf.open(p) as pdf:
            self.assertEqual(len(pdf.pages[0].images), 0)        # page.images không thấy ảnh lồng trong Form
        self._check(p)

    def _first_image(self, path):
        with pikepdf.open(path) as pdf:
            obj = C._page_images(pdf.pages[0])[0]
            return str(obj.ColorSpace), int(obj.Width), pikepdf.PdfImage(obj).as_pil_image().convert("RGB")

    def test_clean_mode_gray_white_and_keeps_red_stamp(self):
        rnd = random.Random(9)
        for stamp in (False, True):
            img = Image.new("RGB", (1240, 1754), (236, 230, 214))           # giấy ngả vàng
            d = ImageDraw.Draw(img)
            for y in range(60, 1700, 26):
                d.text((40, y), "Ho so dang vien " * 8, fill=(25, 25, 30))
            if stamp:
                d.ellipse((700, 1200, 1100, 1600), outline=(210, 25, 35), width=14)
            px = img.load()
            for _ in range(60000):
                x, y = rnd.randrange(1240), rnd.randrange(1754)
                r, g, b = px[x, y]
                v = rnd.randint(-12, 12)
                px[x, y] = (r + v, g + v, b + v)
            b = io.BytesIO()
            img.save(b, "JPEG", quality=95)
            doc = fitz.open()
            doc.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), stream=b.getvalue())
            p = os.path.join(self.tmp, f"clean_{stamp}.pdf")
            doc.save(p)
            with pikepdf.open(p) as pdf:
                limit_kb = int(max(C.page_sizes(pdf).values()) / 1024 * 0.6)
            dst = p.replace(".pdf", "_out.pdf")
            r = C.compress_file(p, dst, limit_kb, clean=True)
            self.assertEqual(r.status, C.ST_COMPRESSED, r.message)
            cs, _, out = self._first_image(dst)
            self.assertEqual(cs, "/DeviceRGB" if stamp else "/DeviceGray")    # có dấu đỏ → giữ màu
            sx, sy = out.width / 1240, out.height / 1754
            self.assertGreater(min(out.getpixel((int(20 * sx), int(1720 * sy)))), 239)   # nền giấy (214–236) → trắng
            if stamp:
                rr, gg, bb = out.getpixel((int(707 * sx), int(1400 * sy)))
                self.assertTrue(rr > 150 and gg < 110 and bb < 110, (rr, gg, bb))

    def test_caps_600dpi_to_300(self):
        doc = fitz.open()
        scan_page(doc, random.Random(3), 4960, 7016, quality=80)        # A4 600 dpi
        p = os.path.join(self.tmp, "dpi600.pdf")
        doc.save(p)
        with pikepdf.open(p) as pdf:
            limit_kb = int(max(C.page_sizes(pdf).values()) / 1024 * 0.9)
        dst = p.replace(".pdf", "_out.pdf")
        r = C.compress_file(p, dst, limit_kb)
        self.assertEqual(r.status, C.ST_COMPRESSED, r.message)
        _, w, _ = self._first_image(dst)
        self.assertLessEqual(w, 2480 + 4)                                  # ≤ 300 dpi (A4 rộng 8,27")

    def test_already_ok_and_no_image(self):
        r = C.compress_file(self.src, os.path.join(self.tmp, "o1.pdf"), 100000)
        self.assertEqual(r.status, C.ST_OK_ALREADY)
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "x" * 50)
        p = os.path.join(self.tmp, "text.pdf")
        doc.save(p)
        self.assertEqual(C.compress_file(p, os.path.join(self.tmp, "o2.pdf"), 0).status, C.ST_NO_IMAGE)


if __name__ == "__main__":
    unittest.main()
