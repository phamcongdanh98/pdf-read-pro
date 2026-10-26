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
