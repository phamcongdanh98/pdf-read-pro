import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf as fitz  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from pdfread_pro.core import pagecheck as K, pagenum  # noqa: E402
from pdfread_pro.core.pagecheck import PageInfo as P  # noqa: E402


def pages(*spec):
    """spec: số trang (int / None) hoặc 'b' = trang trắng; số âm = trang lộn ngược."""
    out = []
    for s in spec:
        if s == "b":
            out.append(P(blank=True))
        elif s is None:
            out.append(P(angle=0))
        else:
            out.append(P(angle=180 if s < 0 else 0, number=abs(s)))
    return out


class PlanTests(unittest.TestCase):
    def test_ok(self):
        pl = K.make_plan(pages(1, 2, 3, 4))
        self.assertFalse(pl.needs_fix)
        self.assertEqual(pl.issues(), [])

    def test_sort_rotate_and_unnumbered_follows_previous(self):
        pl = K.make_plan(pages(None, 1, 3, None, 2, -4))    # bìa không số, trang 3 + trang phụ, trang 4 ngược
        self.assertEqual(pl.order, [0, 1, 4, 2, 3, 5])
        self.assertEqual(pl.rotate, {5: 180})
        self.assertTrue(pl.reordered and pl.needs_fix)

    def test_missing_and_blank(self):
        pl = K.make_plan(pages(1, 2, "b", 4), remove_blank=True)
        self.assertEqual(pl.missing, [3])
        self.assertEqual(pl.order, [0, 1, 3])
        self.assertEqual(pl.removed, [2])
        self.assertFalse(pl.reordered)
        self.assertFalse(K.make_plan(pages(1, 2, "b", 4)).needs_fix)       # không chọn bỏ trang trắng

    def test_duplicates_no_sort(self):
        """File ghép 2 văn bản, mỗi văn bản đánh số lại từ 1 → không được trộn trang."""
        pl = K.make_plan(pages(1, 2, 3, 1, 2))
        self.assertEqual(pl.order, [0, 1, 2, 3, 4])
        self.assertEqual(pl.duplicates, [1, 2])
        self.assertTrue(pl.sort_note)

    def test_outlier_ignored_and_few_reads(self):
        pl = K.make_plan(pages(2, 1, 87, 3))                 # 87: đọc nhầm (số hiệu văn bản…)
        self.assertEqual(pl.suspicious, [2])
        self.assertEqual(pl.order, [1, 2, 0, 3])                # trang số lạ coi như không số: đi sau trang trước nó
        pl = K.make_plan(pages(3, None, None, None, 1))      # chỉ đọc được 2/5 trang → không tự sắp
        self.assertFalse(pl.reordered)
        self.assertIn("2/5", pl.sort_note)

    def test_options_off(self):
        pl = K.make_plan(pages(2, -1), rotate=False, reorder=False)
        self.assertFalse(pl.needs_fix)


def _page_img(n, rot, font):
    im = Image.new("L", (1240, 1754), 250)
    d = ImageDraw.Draw(im)
    for k, y in enumerate(range(150, 1500, 52)):
        d.text((110, y), f"Ho so dang vien muc {k} ghi chep qua trinh cong tac hoc tap", fill=20, font=font)
    d.text((620, 1660), f"- {n} -", fill=20, font=font, anchor="mm")
    return im.rotate(rot, expand=True)


@unittest.skipUnless(pagenum.available(), "máy không có Windows OCR")
class OcrFixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_check_and_fix(self):
        font = ImageFont.truetype("arial.ttf", 34)
        doc = fitz.open()
        for n, rot in ((1, 0), (3, 180), (2, 0), (4, 90)):
            b = io.BytesIO()
            _page_img(n, rot, font).save(b, "JPEG", quality=80)
            w, h = (842, 595) if rot == 90 else (595, 842)
            doc.new_page(width=w, height=h).insert_image(fitz.Rect(0, 0, w, h), stream=b.getvalue())
        src = os.path.join(self.tmp, "a.pdf")
        doc.save(src)
        r = K.check_file(src)
        self.assertEqual(r.error, "")
        self.assertEqual([(p.angle, p.number) for p in r.pages], [(0, 1), (180, 3), (0, 2), (270, 4)])
        pl = K.make_plan(r.pages)
        dst = os.path.join(self.tmp, "out", "a.pdf")
        self.assertEqual(K.job_fix((src, dst, pl.order, pl.rotate, False)), "")
        r2 = K.check_file(dst)
        self.assertEqual([(p.angle, p.number) for p in r2.pages], [(0, 1), (0, 2), (0, 3), (0, 4)])
        # ghi đè có sao lưu
        self.assertEqual(K.job_fix((src, src, pl.order, pl.rotate, True)), "")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "_backup_goc", "a.pdf")))
        self.assertFalse(K.make_plan(K.check_file(src).pages).needs_fix)


if __name__ == "__main__":
    unittest.main()
