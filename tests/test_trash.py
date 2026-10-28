import os
import shutil
import sys
import tempfile
import time
import unittest

os.environ["APPDATA"] = tempfile.mkdtemp()      # dữ liệu app (thùng rác) của test không lẫn vào dữ liệu thật
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf as fitz  # noqa: E402

from pdfread_pro.core import pagecheck as K, trash as T  # noqa: E402


def make_pdf(path, n=5, rotation=0):
    d = fitz.open()
    for k in range(n):
        pg = d.new_page(width=300, height=400)
        pg.insert_text((40, 60), f"TRANG-{k + 1}", fontsize=20)
        if rotation:
            pg.set_rotation(rotation)
    d.save(path)
    d.close()


def texts(path):
    d = fitz.open(path)
    out = [pg.get_text().strip() for pg in d]
    d.close()
    return out


class TrashTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        T.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        T.clear()

    def test_delete_pages_and_restore_in_place(self):
        f = os.path.join(self.tmp, "a.pdf")
        make_pdf(f, 5)
        self.assertEqual(K.delete_pages(f, [1, 3]), 3)
        self.assertEqual(texts(f), ["TRANG-1", "TRANG-3", "TRANG-5"])
        es = T.list_entries()
        by = {e.kind: e for e in es}
        self.assertEqual(set(by), {T.KIND_PAGES, T.KIND_BACKUP})
        pe = by[T.KIND_PAGES]
        self.assertEqual((pe.pages, pe.total_before, pe.name), ([1, 3], 5, "a.pdf"))
        self.assertTrue(pe.exists and pe.size > 0)
        ok, msg, path = T.restore(pe)
        self.assertTrue(ok, msg)
        self.assertEqual(texts(f), [f"TRANG-{k}" for k in range(1, 6)])         # về đúng vị trí cũ
        self.assertEqual([e.kind for e in T.list_entries()], [T.KIND_BACKUP])

    def test_restore_when_original_missing(self):
        f = os.path.join(self.tmp, "b.pdf")
        make_pdf(f, 3)
        K.delete_pages(f, [0])
        e = [x for x in T.list_entries() if x.kind == T.KIND_PAGES][0]
        os.remove(f)
        ok, msg, path = T.restore(e)
        self.assertTrue(ok and os.path.isfile(path) and path.endswith("_trang_khoi_phuc.pdf"), msg)
        self.assertEqual(texts(path), ["TRANG-1"])
        # thư mục cũng mất → phải chọn nơi lưu
        make_pdf(f, 3)
        K.delete_pages(f, [2])
        e = [x for x in T.list_entries() if x.kind == T.KIND_PAGES][0]
        gone = os.path.join(self.tmp, "nope")
        e.orig_path = os.path.join(gone, "b.pdf")
        ok, msg, _ = T.restore(e)
        self.assertFalse(ok)
        ok, msg, path = T.restore(e, dest_dir=self.tmp)
        self.assertTrue(ok, msg)

    def test_overwrite_fix_registers_pages_and_backup(self):
        f = os.path.join(self.tmp, "c.pdf")
        make_pdf(f, 4)
        K.fix_file(f, f, [0, 2, 3], {}, True)                                   # bỏ trang 2 (ghi đè)
        es = {e.kind: e for e in T.list_entries()}
        self.assertEqual(set(es), {T.KIND_PAGES, T.KIND_BACKUP})
        self.assertEqual(es[T.KIND_PAGES].pages, [1])
        self.assertEqual(os.path.basename(es[T.KIND_BACKUP].stored), "c.pdf")
        ok, msg, _ = T.restore(es[T.KIND_BACKUP])                                # trả file về bản gốc
        self.assertTrue(ok, msg)
        self.assertEqual(texts(f), [f"TRANG-{k}" for k in range(1, 5)])
        kinds = sorted(e.kind for e in T.list_entries())
        self.assertIn(T.KIND_FILE, kinds)                                        # bản hiện tại trước khi khôi phục được cất lại
        self.assertFalse(os.path.exists(T.backup_path_for(f)))               # bản sao lưu đã dùng xong
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "_backup_goc")))     # và không bao giờ nằm trong thư mục hồ sơ

    def test_new_folder_mode_leaves_trash_empty(self):
        f = os.path.join(self.tmp, "d.pdf")
        make_pdf(f, 3)
        K.fix_file(f, os.path.join(self.tmp, "out", "d.pdf"), [0, 1], {}, False)
        self.assertEqual(T.list_entries(), [])                                   # file gốc còn nguyên → không cần thùng rác

    def test_delete_clear_purge(self):
        f = os.path.join(self.tmp, "e.pdf")
        make_pdf(f, 6)
        K.delete_pages(f, [0])
        K.delete_pages(f, [0])
        K.crop_pages(f, {0: (0.1, 0.1, 0.9, 0.9)})
        es = T.list_entries()
        self.assertEqual(sorted(e.kind for e in es), [T.KIND_BACKUP, T.KIND_PAGES, T.KIND_PAGES])   # bản gốc đăng ký 1 lần
        self.assertEqual(T.total_size(es) > 0, True)
        old = es[-1]
        old.time = time.time() - 40 * 86400
        T._write(old)
        self.assertEqual(T.purge_older_than(30), 1)
        stored = es[0].stored
        T.delete(es[0])
        self.assertFalse(os.path.exists(stored))
        self.assertEqual(T.clear(), 1)
        self.assertEqual(T.list_entries(), [])

    def test_backup_entry_missing_file(self):
        f = os.path.join(self.tmp, "g.pdf")
        make_pdf(f, 3)
        K.crop_pages(f, {0: (0, 0, 0.5, 0.5)})
        e = [x for x in T.list_entries() if x.kind == T.KIND_BACKUP][0]
        os.remove(e.stored)
        self.assertFalse(e.exists)
        ok, msg, _ = T.restore(e)
        self.assertFalse(ok)
        self.assertEqual(T.purge_missing(), 1)


class BackupLocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        T.clear()

    def tearDown(self):
        T.set_config(backup_root="")
        shutil.rmtree(self.tmp, ignore_errors=True)
        T.clear()

    def test_backup_root_configurable_and_outside_dossier(self):
        f = os.path.join(self.tmp, "hs", "a.pdf")
        os.makedirs(os.path.dirname(f))
        make_pdf(f, 3)
        root = os.path.join(self.tmp, "kho_sao_luu")
        T.set_config(backup_root=root)
        K.crop_pages(f, {0: (0, 0, 0.5, 0.5)})
        bp = T.backup_path_for(f)
        self.assertTrue(bp.startswith(root) and os.path.isfile(bp))
        self.assertEqual(sorted(os.listdir(os.path.dirname(f))), ["a.pdf"])           # thư mục hồ sơ không có gì thêm
        self.assertEqual(T.find_backup(f), bp)
        T.set_config(backup_root="")
        self.assertTrue(T.backup_root().endswith("backup"))

    def test_migrate_legacy_backup_folders(self):
        d = os.path.join(self.tmp, "ho so", "Chi bo 1")
        os.makedirs(os.path.join(d, "_backup_goc"))
        f = os.path.join(d, "x.pdf")
        make_pdf(f, 2)
        shutil.copy2(f, os.path.join(d, "_backup_goc", "x.pdf"))
        self.assertEqual(T.find_backup(f), os.path.join(d, "_backup_goc", "x.pdf"))          # kiểu cũ vẫn đọc được
        moved, skipped, errors = T.migrate_legacy(os.path.join(self.tmp, "ho so"))
        self.assertEqual((moved, skipped, errors), (1, 0, []))
        self.assertFalse(os.path.exists(os.path.join(d, "_backup_goc")))                       # thư mục trống bị xoá
        self.assertEqual(T.find_backup(f), T.backup_path_for(f))
        es = [e for e in T.list_entries() if e.kind == T.KIND_BACKUP]
        self.assertEqual(len(es), 1)
        self.assertTrue(es[0].exists and es[0].orig_path == os.path.abspath(f))
        ok, msg, _ = T.restore(es[0])                                                          # khôi phục từ nơi mới
        self.assertTrue(ok, msg)
        self.assertEqual(T.migrate_legacy(os.path.join(self.tmp, "ho so")), (0, 0, []))

    def test_make_backup_keeps_earliest(self):
        f = os.path.join(self.tmp, "k.pdf")
        make_pdf(f, 2)
        self.assertTrue(T.make_backup(f, "lần 1"))
        make_pdf(f, 5)
        self.assertFalse(T.make_backup(f, "lần 2"))                                            # giữ bản gốc sớm nhất
        with fitz.open(T.backup_path_for(f)) as d:
            self.assertEqual(d.page_count, 2)
        self.assertEqual(len([e for e in T.list_entries() if e.kind == T.KIND_BACKUP]), 1)


class CropTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def quadrants(self, path, rotation=0):
        """Trang có 4 ô màu khác nhau (đỏ / xanh lá / xanh dương / vàng ở trái-trên / phải-trên / trái-dưới / phải-dưới)."""
        d = fitz.open()
        pg = d.new_page(width=300, height=400)
        for (x, y), col in (((0, 0), (1, 0, 0)), ((150, 0), (0, 1, 0)), ((0, 200), (0, 0, 1)), ((150, 200), (1, 1, 0))):
            pg.draw_rect(fitz.Rect(x, y, x + 150, y + 200), color=col, fill=col)
        if rotation:
            pg.set_rotation(rotation)
        d.save(path)
        d.close()

    def shown(self, path):
        d = fitz.open(path)
        pg = d[0]
        pix = pg.get_pixmap(dpi=36, alpha=False)
        out = (pix.width, pix.height, [tuple(pix.pixel(int(pix.width * fx), int(pix.height * fy)))
                                       for fx, fy in ((0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9))])
        d.close()
        return out

    def test_crop_matches_displayed_region(self):
        for rot in (0, 90, 180, 270):
            f = os.path.join(self.tmp, f"q{rot}.pdf")
            self.quadrants(f, rot)
            ref = fitz.open(f)
            whole = ref[0].get_pixmap(dpi=36, alpha=False)
            frac = (0.5, 0.0, 1.0, 0.5)                              # góc trên bên phải như đang HIỂN THỊ
            cx, cy = int(whole.width * 0.75), int(whole.height * 0.25)
            want = tuple(whole.pixel(cx, cy))
            ref.close()
            K.crop_pages(f, {0: frac})
            w, h, px = self.shown(f)
            self.assertAlmostEqual(w / h, (whole.width / 2) / (whole.height / 2), delta=0.08, msg=f"rot={rot}")
            self.assertTrue(all(p == want for p in px), f"rot={rot}: {px} ≠ {want}")      # cả khung chỉ còn đúng ô đó
            self.assertTrue(os.path.isfile(T.backup_path_for(f)))
            self.assertFalse(os.path.exists(os.path.join(self.tmp, "_backup_goc")))

    def test_crop_twice_and_all_pages(self):
        f = os.path.join(self.tmp, "t.pdf")
        make_pdf(f, 3)
        K.crop_pages(f, {0: (0, 0, 0.5, 1), 1: (0, 0, 0.5, 1), 2: (0, 0, 0.5, 1)})
        d = fitz.open(f)
        self.assertEqual([round(pg.rect.width) for pg in d], [150, 150, 150])
        d.close()
        K.crop_pages(f, {0: (0.5, 0, 1, 1)})                         # cắt tiếp trên trang đã cắt: tính theo khung hiện tại
        d = fitz.open(f)
        self.assertEqual((round(d[0].rect.width), round(d[1].rect.width)), (75, 150))
        self.assertEqual(round(d[0].cropbox.x0), 75)
        d.close()

    def test_invalid_rects(self):
        f = os.path.join(self.tmp, "i.pdf")
        make_pdf(f, 2)
        for bad in ({}, {5: (0, 0, 1, 1)}, {0: (0.5, 0.5, 0.5, 0.9)}, {0: (-0.1, 0, 1, 1)}, {0: (0, 0, 0.01, 0.01)}):
            with self.assertRaises(ValueError):
                K.crop_pages(f, bad)


if __name__ == "__main__":
    unittest.main()
