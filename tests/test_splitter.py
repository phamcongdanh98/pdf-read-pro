import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf as fitz  # noqa: E402

from pdfread_pro.core import splitter as S  # noqa: E402

A3L = (1190.55, 841.89)   # A3 ngang
A4P = (595.276, 841.89)


def labels(doc):
    out = []
    for pg in doc:
        words = [w[4] for w in pg.get_text("words") if w[4].startswith("P")]
        out.append(words[0] if words else "")
    return out


def face(doc, size, first, second, mode="left_right", upside_down=False):
    """Một mặt scan chứa 2 trang: `first` ở nửa trái/trên, `second` ở nửa phải/dưới (theo hướng đọc đúng).
    upside_down=True: cả mặt bị lộn ngược 180° như mặt sau qua máy ADF."""
    w, h = size
    p = doc.new_page(width=w, height=h)
    if mode == "left_right":
        spots = [(w * 0.2, h * 0.5), (w * 0.7, h * 0.5)]
    else:
        spots = [(w * 0.4, h * 0.25), (w * 0.4, h * 0.75)]
    for (x, y), t in zip(spots, (first, second)):
        if upside_down:
            p.insert_text((w - x, h - y), t, fontsize=40, rotate=180)
        else:
            p.insert_text((x, y), t, fontsize=40)
    return p


class SplitterTests(unittest.TestCase):
    def test_a3_to_a4_sequential(self):
        src = fitz.open()
        face(src, A3L, "P1", "P2")
        face(src, A3L, "P3", "P4")
        res = S.build(src, S.SplitOptions())
        self.assertEqual(labels(res.doc), ["P1", "P2", "P3", "P4"])
        for pg in res.doc:
            self.assertEqual(S.paper_name(pg.rect.width, pg.rect.height), "A4 dọc")

    def test_a4_halves_scaled_to_a4(self):
        src = fitz.open()
        face(src, A4P, "P1", "P2", mode="top_bottom")       # A4 dọc chứa 2 nửa A5 ngang
        res = S.build(src, S.SplitOptions(page_size="a4"))
        self.assertEqual(labels(res.doc), ["P1", "P2"])
        for pg in res.doc:
            self.assertEqual(S.paper_name(pg.rect.width, pg.rect.height), "A4 ngang")
        res2 = S.build(src, S.SplitOptions(page_size="a4", post_rotation="ccw"))
        self.assertEqual(S.paper_name(res2.doc[0].rect.width, res2.doc[0].rect.height), "A4 dọc")

    def test_booklet_left_right(self):
        # sổ 8 trang = 2 tờ; scan 2 mặt theo thứ tự tờ 1 trước, tờ 1 sau, tờ 2 trước, tờ 2 sau
        src = fitz.open()
        face(src, A3L, "P8", "P1")
        face(src, A3L, "P2", "P7")
        face(src, A3L, "P6", "P3")
        face(src, A3L, "P4", "P5")
        res = S.build(src, S.SplitOptions(arrange="booklet", page_size="a4"))
        self.assertEqual(labels(res.doc), [f"P{i}" for i in range(1, 9)])

    def test_booklet_with_cover_and_flipped_backs(self):
        src = fitz.open()
        c = src.new_page(width=A4P[0], height=A4P[1])
        c.insert_text((100, 400), "PBIA", fontsize=40)
        face(src, A3L, "P8", "P1")
        face(src, A3L, "P2", "P7", upside_down=True)       # mặt sau bị lộn ngược
        face(src, A3L, "P6", "P3")
        face(src, A3L, "P4", "P5", upside_down=True)
        res = S.build(src, S.SplitOptions(arrange="booklet", keep_first=True, flip_back="yes"))
        self.assertEqual(labels(res.doc), ["PBIA"] + [f"P{i}" for i in range(1, 9)])
        # trang mặt sau đã được xoay lại đứng
        self.assertIn("xoay 180°", res.units[2].label)

    def test_booklet_bad_count(self):
        src = fitz.open()
        for _ in range(3):
            face(src, A3L, "P1", "P2")
        with self.assertRaises(S.SplitError):
            S.build(src, S.SplitOptions(arrange="booklet"))

    def test_rotated_source_page(self):
        # trang lưu dạng dọc + /Rotate 90 nhưng hiển thị ngang: cắt theo hướng nhìn
        src = fitz.open()
        p = src.new_page(width=A3L[1], height=A3L[0])
        p.insert_text((200, 300), "PX", fontsize=40)
        p.set_rotation(90)
        res = S.build(src, S.SplitOptions())
        self.assertEqual(res.doc.page_count, 2)
        self.assertEqual(S.paper_name(res.doc[0].rect.width, res.doc[0].rect.height), "A4 dọc")
        txt = [pg.get_text().strip() for pg in res.doc]
        self.assertEqual(sum(1 for t in txt if "PX" in t), 1)

    def test_remove_blank_and_range(self):
        src = fitz.open()
        face(src, A3L, "P1", "")
        face(src, A3L, "P3", "P4")
        res = S.build(src, S.SplitOptions(remove_blank=True))
        self.assertEqual(labels(res.doc), ["P1", "P3", "P4"])
        self.assertEqual(res.removed_blank, [2])
        res = S.build(src, S.SplitOptions(page_from=2, page_to=2))
        self.assertEqual(labels(res.doc), ["P3", "P4"])

    def test_parse_pages(self):
        self.assertEqual(S.parse_pages("", 5), [0, 1, 2, 3, 4])
        self.assertEqual(S.parse_pages("1-2, 4", 5), [0, 1, 3])
        self.assertEqual(S.parse_pages("4-", 5), [3, 4])
        with self.assertRaises(S.SplitError):
            S.parse_pages("7", 5)
        with self.assertRaises(S.SplitError):
            S.parse_pages("abc", 5)

    def test_save_never_overwrites_without_flag(self):
        d = tempfile.mkdtemp()
        srcp = os.path.join(d, "so.pdf")
        src = fitz.open()
        face(src, A3L, "P1", "P2")
        src.save(srcp)
        doc = S.open_source(srcp)
        info = S.read_info(doc)
        self.assertEqual((info.pages, info.label, info.has_signature), (1, "A3 ngang", False))
        res = S.build(doc, S.SplitOptions())
        with self.assertRaises(S.SplitError):
            S.save(res, srcp, srcp)
        out = S.default_output(srcp)
        self.assertTrue(out.endswith("so_DaTach.pdf"))
        S.save(res, srcp, out, pages=[1])
        self.assertEqual(labels(fitz.open(out)), ["P2"])
        self.assertTrue(S.default_output(srcp).endswith("so_DaTach (2).pdf"))
        # lưu đè có chủ đích → có sao lưu bản gốc
        S.save(res, srcp, srcp, overwrite_source=True)
        self.assertEqual(fitz.open(srcp).page_count, 2)
        self.assertEqual(fitz.open(os.path.join(d, "_backup_goc", "so.pdf")).page_count, 1)


def numbered_booklet(true_opts, n_pages, face_size, number_style="- {} -"):
    """Dựng file scan sổ gỡ ghim giả lập: trang sổ i có chữ "TRANG-i" ở thân và số trang in ở chân trang.
    Mặt scan được dựng NGƯỢC từ kế hoạch tách của `true_opts` → tách đúng bằng true_opts phải ra trang 1…P."""
    content = fitz.open()
    for i in range(1, n_pages + 1):
        pg = content.new_page(width=420, height=595)
        for k in range(14):
            pg.insert_text((40, 80 + k * 28), f"TRANG-{i} Ho va ten khai sinh Nguyen Van A", fontsize=11)
        pg.insert_text((200, 575), number_style.format(i), fontsize=11, fontname="tiro")
    scan = fitz.open()
    for _ in range(n_pages // 2):
        scan.new_page(width=face_size[0], height=face_size[1])
    units, _ = S.plan_units(scan, true_opts)
    for i, u in enumerate(units):
        scan[u.src].show_pdf_page(u.clip, content, i, rotate=-u.rotate)
    out = fitz.open("pdf", scan.tobytes())
    return out


def body_order(doc):
    out = []
    for pg in doc:
        t = [w[4] for w in pg.get_text("words") if w[4].startswith("TRANG-")]
        lines = [ln for b in pg.get_text("dict")["blocks"] for ln in b.get("lines", [])]
        upright = all(abs(ln["dir"][0] - 1) < 0.01 for ln in lines)
        out.append((int(t[0].split("-")[1]) if t else 0, upright))
    return out


@unittest.skipUnless(__import__("pdfread_pro.core.pagenum", fromlist=["x"]).available(), "cần Windows OCR")
class AutoOrderTests(unittest.TestCase):
    """Tự đọc số trang in trên giấy → tự chọn cách xếp sổ gỡ ghim."""

    def check(self, true_opts, face_size, user_opts, n=8, style="- {} -"):
        doc = numbered_booklet(true_opts, n, face_size, style)
        pr = S.read_page_numbers(doc, user_opts)
        self.assertGreaterEqual(pr.count, n - 1, pr.reads)
        g = S.guess_order(doc, user_opts, pr)
        self.assertIsNotNone(g.options, g.description)
        res = S.build(doc, g.options)
        self.assertEqual(body_order(res.doc), [(i, True) for i in range(1, n + 1)], g.description)
        return g

    def test_left_right_variants(self):
        base = S.PRESETS["booklet"][1]
        from dataclasses import replace
        for sh, face_, half, flip in (("outer", "front", "first", "no"), ("inner", "back", "second", "yes"),
                                      ("inner", "front", "first", "yes"), ("outer", "back", "second", "no")):
            t = replace(base, sheet_order=sh, face_first=face_, half_order=half, flip_back=flip, post_rotation="none")
            g = self.check(t, A3L, base)
            self.assertEqual((g.options.sheet_order, g.options.face_first), (sh, face_))

    def test_top_bottom_portrait_scan(self):
        base = S.PRESETS["booklet"][1]
        from dataclasses import replace
        t = replace(base, flip_back="yes", post_rotation="ccw", sheet_order="inner")
        self.check(t, A4P, base, n=12, style="{}")
        t2 = replace(base, flip_back="no", post_rotation="cw")        # cả xấp đặt ngược chiều
        self.check(t2, A4P, base, n=8, style="Trang {}")

    def test_sequential_a3(self):
        base = S.PRESETS["a3_to_a4"][1]
        from dataclasses import replace
        t = replace(base, half_order="second")
        g = self.check(t, A3L, base, n=6)
        self.assertEqual(g.options.arrange, "sequential")

    def test_unreadable_keeps_settings(self):
        doc = fitz.open()
        for _ in range(2):
            doc.new_page(width=A3L[0], height=A3L[1])
        pr = S.read_page_numbers(doc, S.PRESETS["booklet"][1])
        g = S.guess_order(doc, S.PRESETS["booklet"][1], pr)
        self.assertIsNone(g.options)


if __name__ == "__main__":
    unittest.main()
