import copy
import io
import os
import tempfile as _tf
os.environ["APPDATA"] = _tf.mkdtemp()      # thùng rác / dữ liệu app của test không lẫn vào dữ liệu thật
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf as fitz  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from pdfread_pro.core import pagecheck as K, pagenum, trash  # noqa: E402
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
        self.assertTrue(os.path.isfile(trash.backup_path_for(src)))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "_backup_goc")))        # không để thư mục sao lưu trong thư mục hồ sơ
        self.assertFalse(K.make_plan(K.check_file(src).pages).needs_fix)

    def test_parallel_ocr_same_as_sequential(self):
        """Đọc song song nhiều trang phải cho đúng kết quả như đọc tuần tự (cả hướng lẫn số trang)."""
        font = ImageFont.truetype("arial.ttf", 34)
        doc = fitz.open()
        for n, rot in ((1, 0), (2, 180), (3, 0), (4, 90), (5, 0), (6, 180), (7, 0)):
            b = io.BytesIO()
            _page_img(n, rot, font).save(b, "JPEG", quality=80)
            w, h = (842, 595) if rot == 90 else (595, 842)
            doc.new_page(width=w, height=h).insert_image(fitz.Rect(0, 0, w, h), stream=b.getvalue())
        src = os.path.join(self.tmp, "p.pdf")
        doc.save(src)
        sig = lambda r: [(p.kind, p.angle, p.number) for p in r.pages]   # noqa: E731
        seq = K.check_file(src)
        for n in (2, 4):
            par = K.check_file(src, concurrency=n)
            self.assertEqual((par.error, sig(par)), (seq.error, sig(seq)))
        self.assertEqual([p.number for p in seq.pages], [1, 2, 3, 4, 5, 6, 7])


def _jpg_page(doc, im, size=(595, 842)):
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=85)
    doc.new_page(width=size[0], height=size[1]).insert_image(fitz.Rect(0, 0, *size), stream=b.getvalue())


def _text_img(font, seed=0, w=1240, h=1754):
    im = Image.new("L", (w, h), 250)
    d = ImageDraw.Draw(im)
    for k, y in enumerate(range(150, 1500, 52)):
        d.text((110, y), f"Noi dung {seed} dong {k} ghi chep cong tac", fill=20, font=font)
    return im


class ContentTests(unittest.TestCase):
    """Trắng / đen / ít nội dung / mờ / khổ lệch / trùng + xoá trang."""

    @classmethod
    def setUpClass(cls):
        font = ImageFont.truetype("arial.ttf", 34)
        cls.tmp = tempfile.mkdtemp()
        doc = fitz.open()
        stamp = Image.new("L", (1240, 1754), 250)
        ImageDraw.Draw(stamp).ellipse([800, 1200, 1050, 1450], outline=30, width=6)
        gray = Image.new("L", (1240, 1754), 215)                       # scan ám xám, lề đen
        ImageDraw.Draw(gray).rectangle([0, 0, 20, 1754], fill=10)
        half = _text_img(font, 9)
        ImageDraw.Draw(half).rectangle([0, 0, 1240, 1100], fill=8)
        cls.kinds = ["", "blank", "blank", "sparse", "black", "part_black", ""]
        for im in (_text_img(font, 1), Image.new("L", (1240, 1754), 252), gray, stamp,
                   Image.new("L", (1240, 1754), 10), half, _text_img(font, 2)):
            _jpg_page(doc, im)
        cls.src = os.path.join(cls.tmp, "c.pdf")
        doc.save(cls.src)
        d = fitz.open(cls.src)
        cls.base = [K.analyze_page(pg) for pg in d]
        d.close()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.infos = copy.deepcopy(self.base)          # make_plan phân loại lại theo ngưỡng → mỗi test dùng bản riêng

    def test_kinds(self):
        self.assertEqual([p.kind for p in self.infos], self.kinds)
        self.assertEqual([p.blank for p in self.infos], [False, True, True, False, False, False, False])

    def test_black_threshold_and_options(self):
        pl = K.make_plan(self.infos, remove_blank=True, remove_black=True)
        self.assertEqual(pl.blanks, [1, 2])
        self.assertEqual(pl.blacks, [4])
        self.assertEqual(pl.removed, [1, 2, 4])                       # trang ít nội dung / đen một phần giữ lại
        self.assertEqual(pl.sparse, [3])
        self.assertEqual(pl.dark_pages, [5])
        self.assertEqual(K.make_plan(self.infos).removed, [])             # không bật → không bỏ
        pl = K.make_plan(self.infos, remove_black=True, black_thr=0.55)   # hạ ngưỡng: nửa đen (63%) có chữ → ảnh tối, giữ
        self.assertEqual((pl.blacks, pl.dark_pages), ([4], [5]))
        pl = K.make_plan(self.infos, black_thr=0.99)
        self.assertEqual(pl.blacks, [4] if self.infos[4].dark >= 0.99 else [])

    def test_text_layer_not_blank(self):
        d = fitz.open()
        d.new_page().insert_text((72, 72), "Van ban so co lop chu day du", fontsize=1)   # chữ cực nhỏ: ảnh gần như trắng
        info = K.analyze_page(d[0])
        self.assertNotIn(info.kind, ("blank", "near"))

    def test_marked_pages(self):
        pg = pages(1, 2, 3, 4)
        pg[2].marked = True
        pl = K.make_plan(pg)
        self.assertEqual(pl.removed, [2])
        self.assertEqual(pl.order, [0, 1, 3])
        self.assertTrue(pl.needs_fix)
        self.assertIn("🗑", " ".join(pl.issues()))
        self.assertEqual(pl.missing, [3])                                 # trang bị xoá không tính số
        for p in pg:
            p.marked = True
        pl = K.make_plan(pg)                                              # không bao giờ xoá hết
        self.assertTrue(pl.all_removed)
        self.assertEqual(pl.order, [0, 1, 2, 3])

    def test_duplicates_blur_size(self):
        font = ImageFont.truetype("arial.ttf", 34)
        d = fitz.open()
        a, b = _text_img(font, 1), _text_img(font, 2)
        for im in (a, b, a, b, a):
            _jpg_page(d, im)
        _jpg_page(d, a, size=(420, 595))                                  # A5 giữa các trang A4
        infos = [K.analyze_page(pg) for pg in d]
        pl = K.make_plan(infos)
        self.assertEqual(pl.dup_pages, {2: 0, 3: 1, 4: 0, 5: 0})
        self.assertEqual(pl.odd_size, [5])
        blurry = [PageInfo(sharp=v) for v in (200, 190, 210, 195, 40)]
        self.assertEqual(K.make_plan(blurry).blurry, [4])
        self.assertEqual(K.make_plan([PageInfo(sharp=v) for v in (200, 190, 210, 195)]).blurry, [])


    def test_selectable_checks(self):
        pg = [PageInfo(angle=0, number=1), PageInfo(blank=True, kind="blank"), PageInfo(angle=180, number=3),
              PageInfo(angle=0, number=4)]
        pl = K.make_plan(pg, remove_blank=True)
        self.assertEqual((pl.blanks, list(pl.rotate), pl.missing), ([1], [2], [2]))
        pl = K.make_plan(pg, remove_blank=True, checks={"blank"})          # chỉ kiểm tra trang trắng
        self.assertEqual((pl.blanks, pl.rotate, pl.missing, pl.reordered), ([1], {}, [], False))
        self.assertEqual(pl.removed, [1])
        pl = K.make_plan(pg, remove_blank=True, checks={"orient"})         # không kiểm tra trắng → không bỏ, không báo
        self.assertEqual((pl.blanks, pl.removed, list(pl.rotate)), ([], [], [2]))
        pl = K.make_plan(self.infos, checks={"dup", "size"})
        self.assertEqual((pl.blanks, pl.blacks, pl.sparse, pl.dark_pages), ([], [], [], []))
        self.assertEqual(K.make_plan(self.infos, checks=set()).issues(), [])

    def test_check_file_without_ocr(self):
        r = K.check_file(self.src, ocr=False, blur=False)
        self.assertEqual((r.error, r.ocr, r.blur), ("", False, False))
        self.assertEqual([p.kind for p in r.pages], self.kinds)
        self.assertTrue(all(p.angle is None and p.number is None and p.sharp == 0 for p in r.pages))
        r = K.job_check((self.src, 0.9, False, True))                      # có đo độ nét, vẫn không OCR
        self.assertTrue(r.blur and not r.ocr and r.pages[0].sharp > 0 and r.pages[1].sharp == 0)
        self.assertEqual(K.job_check((self.src,)).ocr, True)               # mặc định như cũ



    def test_result_cache(self):
        r = K.check_file(self.src, ocr=False, blur=False)
        items = {}
        K.cache_put(items, self.src, r)
        self.assertEqual([p.kind for p in K.cache_get(items, self.src, False, False).pages], self.kinds)
        self.assertIsNone(K.cache_get(items, self.src, True, False))        # cần OCR mà kết quả cũ không có
        self.assertIsNone(K.cache_get(items, self.src, False, True))
        got = K.cache_get(items, self.src, False, False)
        got.pages[0].marked = True                                           # sửa trên bản lấy ra không ảnh hưởng bản lưu
        self.assertFalse(K.cache_get(items, self.src, False, False).pages[0].marked)
        other = os.path.join(self.tmp, "mut.pdf")
        shutil.copy2(self.src, other)
        K.cache_put(items, other, K.check_file(other, ocr=False, blur=False))
        self.assertIsNotNone(K.cache_get(items, other, False, False))
        with open(other, "ab") as fh:
            fh.write(b"%x")                                                  # file đổi → kết quả cũ bị bỏ
        self.assertIsNone(K.cache_get(items, other, False, False))

    def test_delete_pages(self):
        d = fitz.open()
        for n in range(4):
            d.new_page().insert_text((72, 72), f"trang {n}")
        f = os.path.join(self.tmp, "del.pdf")
        d.save(f)
        self.assertEqual(K.delete_pages(f, [1, 3]), 2)
        out = fitz.open(f)
        self.assertEqual([pg.get_text().strip() for pg in out], ["trang 0", "trang 2"])
        out.close()
        self.assertTrue(os.path.isfile(trash.backup_path_for(f)))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "_backup_goc")))
        with self.assertRaises(ValueError):
            K.delete_pages(f, [0, 1])                                      # xoá hết
        with self.assertRaises(ValueError):
            K.delete_pages(f, [7])


PageInfo = K.PageInfo


if __name__ == "__main__":
    unittest.main()
