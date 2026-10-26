import os, sys, tempfile, unittest, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["APPDATA"] = tempfile.mkdtemp()
from pdfread_pro.core import renamer as R, scanner, stats
from pdfread_pro.core.models import FileInfo, name_is_signed

SAMPLE = r"C:\Users\Danh Pham\Desktop\test"


def rd(p):
    with open(p, "rb") as f:
        return f.read()


def mk(d, name, content=b"%PDF-1.4\n"):
    p = os.path.join(d, name)
    with open(p, "wb") as f:
        f.write(content)
    return FileInfo(path=p, rel=name, name=name, size=len(content), mtime=0, pages=1)


class NameTests(unittest.TestCase):
    def test_signed_name(self):
        for n in ["a.signed.pdf", "a.signed.signed.pdf", "a.signed (1).pdf", "a_signed.pdf", "a - signed.pdf", "a-signed.pdf"]:
            self.assertTrue(name_is_signed(n), n)
        for n in ["a_unsigned.pdf", "a.signedx.pdf", "a.pdf", "designed.pdf"]:
            self.assertFalse(name_is_signed(n), n)

    def test_accents(self):
        self.assertEqual(R.remove_accents("Đặng Thị Ánh"), "Dang Thi Anh")

    def test_validate(self):
        self.assertTrue(R.validate_name("a?.pdf"))
        self.assertTrue(R.validate_name("CON.pdf"))
        self.assertTrue(R.validate_name("a.pdf."))
        self.assertEqual(R.validate_name("ok.pdf"), "")


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def rs(self, **kw):
        r = R.new_ruleset()
        r.update(kw)
        return r

    def names(self):
        return sorted(os.listdir(self.d))

    def test_template_and_numbering(self):
        fs = [mk(self.d, "b.pdf"), mk(self.d, "a.pdf"), mk(self.d, "c10.pdf"), mk(self.d, "c2.pdf")]
        items = R.build_preview(fs, self.rs(template="{n:3}-{stem}"))
        got = {i.fi.name: i.new_name for i in items}
        self.assertEqual(got["a.pdf"], "001-a.pdf")
        self.assertEqual(got["b.pdf"], "002-b.pdf")
        self.assertEqual(got["c2.pdf"], "003-c2.pdf")
        self.assertEqual(got["c10.pdf"], "004-c10.pdf")

    def test_steps(self):
        fs = [mk(self.d, "Bản đồ Số 1.pdf")]
        rs = self.rs(steps=[{"type": "remove_accents"}, {"type": "spaces", "to": "_"},
                            {"type": "prefix", "text": "X_"}, {"type": "suffix", "text": "_v2"},
                            {"type": "replace", "find": "so", "repl": "SO", "regex": False, "case": False}])
        it = R.build_preview(fs, rs)[0]
        self.assertEqual(it.new_name, "X_Ban_do_SO_1_v2.pdf")

    def test_regex_dot1(self):
        fs = [mk(self.d, "01.Ly lich.1.pdf"), mk(self.d, "02.x.signed.pdf")]
        rs = self.rs(steps=[{"type": "replace", "find": r"\.1$", "repl": ".signed", "regex": True, "case": False}])
        it = R.build_preview(fs, rs)
        self.assertEqual(it[0].new_name, "01.Ly lich.signed.pdf")
        self.assertEqual(it[1].status, R.ST_SAME)

    def test_bad_variable_and_regex(self):
        f = [mk(self.d, "a.pdf")]
        self.assertEqual(R.build_preview(f, self.rs(template="{zzz}"))[0].status, R.ST_INVALID)
        rs = self.rs(steps=[{"type": "replace", "find": "(", "repl": "", "regex": True}])
        self.assertEqual(R.build_preview(f, rs)[0].status, R.ST_INVALID)

    def test_conflict_auto_and_skip(self):
        fs = [mk(self.d, "a.pdf"), mk(self.d, "b.pdf"), mk(self.d, "x.pdf")]
        rs = self.rs(template="x")
        it = R.build_preview(fs, rs, "auto")
        news = sorted(i.new_name for i in it)
        self.assertEqual(len(set(n.lower() for n in news)), 3)
        it = R.build_preview(fs, rs, "skip")
        st = {i.fi.name: i.status for i in it}
        self.assertEqual(st["x.pdf"], R.ST_SAME)
        self.assertEqual(st["a.pdf"], R.ST_CONFLICT)

    def test_apply_undo_chain_swap(self):
        a, b = mk(self.d, "a.pdf", b"AAA"), mk(self.d, "b.pdf", b"BBB")
        it_a = R.PreviewItem(a, "b.pdf", R.ST_READY)
        it_b = R.PreviewItem(b, "a.pdf", R.ST_READY)
        rep = R.apply_renames([it_a, it_b])
        self.assertEqual(rep.ok, 2, rep.failed)
        self.assertEqual(rd(os.path.join(self.d, "b.pdf")), b"AAA")
        self.assertEqual(rd(os.path.join(self.d, "a.pdf")), b"BBB")
        un = R.undo_last()
        self.assertEqual(un.ok, 2, un.failed)
        self.assertEqual(rd(os.path.join(self.d, "a.pdf")), b"AAA")
        self.assertIsNone(R.last_undoable())

    def test_case_only_rename(self):
        f = mk(self.d, "abc.pdf", b"Z")
        rep = R.apply_renames(R.build_preview([f], self.rs(steps=[{"type": "case", "mode": "upper"}])))
        self.assertEqual(rep.ok, 1)
        self.assertIn("ABC.pdf", os.listdir(self.d))

    def test_no_overwrite_existing(self):
        a = mk(self.d, "a.pdf", b"A")
        mk(self.d, "z.pdf", b"Z")
        it = R.build_preview([a], self.rs(template="z"), "skip")[0]
        self.assertEqual(it.status, R.ST_CONFLICT)
        it = R.build_preview([a], self.rs(template="z"), "auto")[0]
        self.assertEqual(it.new_name, "z (2).pdf")
        # nếu ép đổi vào tên đã tồn tại → không ghi đè
        forced = R.PreviewItem(a, "z.pdf", R.ST_READY)
        rep = R.apply_renames([forced])
        self.assertEqual(rep.ok, 0)
        self.assertEqual(rd(os.path.join(self.d, "z.pdf")), b"Z")

    def test_recover_journal(self):
        a = mk(self.d, "a.pdf")
        tmp = os.path.join(self.d, "~rn_x.tmp")
        os.rename(a.path, tmp)
        import json
        with open(R._journal_path(), "w", encoding="utf-8") as fh:
            json.dump({"state": "pending", "ops": [{"src": a.path, "dst": os.path.join(self.d, "b.pdf"), "tmp": tmp}]}, fh)
        self.assertEqual(R.recover_journal(), 1)
        self.assertTrue(os.path.exists(a.path))

    def test_code1361(self):
        import json
        rp = os.path.join(self.d, "rules.json")
        with open(rp, "w", encoding="utf-8") as fh:
            json.dump({"01": "01.Ly_lich", "86": "86.Bang_cap", "86dh": "86.Bang_dai_hoc"}, fh)
        fs = [mk(self.d, "01 scan.signed.pdf"), mk(self.d, "86dh abc.pdf"), mk(self.d, "xyz.pdf"),
              mk(self.d, "1.signed.pdf"), mk(self.d, "86. Bang.pdf")]
        it = R.build_preview(fs, self.rs(steps=[{"type": "code1361", "rules_path": rp}]))
        got = {i.fi.name: i.new_name for i in it}
        self.assertEqual(got["01 scan.signed.pdf"], "01.Ly_lich.signed.pdf")
        self.assertEqual(got["86dh abc.pdf"], "86.Bang_dai_hoc.pdf")
        self.assertEqual(got["xyz.pdf"], "xyz.pdf")
        self.assertEqual(got["86. Bang.pdf"], "86.Bang_cap.pdf")
        # "1" được hiểu là mã "01"; trùng tên với file 01 ở trên → tự thêm (2)
        self.assertEqual(got["1.signed.pdf"], "01.Ly_lich.signed (2).pdf")

    def test_mode_1361(self):
        rules = {"01": "01.Ly_lich", "02": "02.Phieu", "86dh": "86.Bang_dai_hoc", "6124": "61.Kiem_diem_2024"}
        fs = [mk(self.d, n) for n in ("1 scan.pdf", "01-b.pdf", "02.Phieu.1.pdf", "86dh x.signed.pdf",
                                      "6124 kd.pdf", "99 abc.pdf", "abc.pdf", "02 khac.signed.pdf")]
        it = {i.fi.name: i for i in R.build_preview_1361(fs, rules)}
        # 2 file mã 01 → .1 .2 theo thứ tự tự nhiên
        self.assertEqual(it["1 scan.pdf"].new_name, "01.Ly_lich.1.pdf")
        self.assertEqual(it["01-b.pdf"].new_name, "01.Ly_lich.2.pdf")
        self.assertEqual(it["86dh x.signed.pdf"].new_name, "86.Bang_dai_hoc.signed.pdf")
        self.assertEqual(it["6124 kd.pdf"].new_name, "61.Kiem_diem_2024.pdf")
        self.assertEqual(it["99 abc.pdf"].status, R.ST_NO_RULE)
        self.assertEqual(it["abc.pdf"].status, R.ST_NO_CODE)
        # mã 02: 2 file → .1 / .2 ; file đã có tên đúng giữ .1
        self.assertEqual(it["02.Phieu.1.pdf"].status, R.ST_SAME)
        self.assertEqual(it["02 khac.signed.pdf"].new_name, "02.Phieu.2.signed.pdf")
        one = R.build_preview_1361([fs[3]], rules, always_suffix=True)[0]
        self.assertEqual(one.new_name, "86.Bang_dai_hoc.1.signed.pdf")

    def test_rules1361_store(self):
        from pdfread_pro.core import rules1361 as RS
        d = RS.load_rules()
        self.assertGreaterEqual(len(d), 104)
        self.assertEqual(d["01"], "01.Ly_lich_nguoi_xin_vao_Dang")
        keys = [k for k, _ in RS.sorted_items(d)]
        self.assertLess(keys.index("61"), keys.index("6123"))
        self.assertLess(keys.index("6126"), keys.index("62"))
        d["999x"] = "999.Thu"
        RS.save_rules(d)
        self.assertIn("999x", RS.load_rules())
        txt = os.path.join(self.d, "r.txt")
        RS.export_file(RS.load_rules(), txt)
        self.assertEqual(RS.parse_file(txt)["999x"], "999.Thu")
        self.assertNotIn("999x", RS.reset_defaults())
        self.assertTrue(RS.validate_rule("ab", "x"))


@unittest.skipUnless(os.path.isdir(SAMPLE), "không có thư mục test mẫu")
class ScanTests(unittest.TestCase):
    def test_sample(self):
        r = scanner.scan(SAMPLE)
        self.assertEqual(len(r.files), 22)
        s = stats.compute(r, None, "all")
        self.assertEqual((s.files, s.pages, s.dirs_with_pdf, s.dirs_container_only, s.dirs_total), (22, 159, 6, 1, 7))
        self.assertEqual(s.files_signed_name + s.files_unsigned_name, 22)
        self.assertEqual(s.sig_files, 16)
        self.assertEqual(s.sig_ok, 16)
        sc = stats.compute(r, "Chibo2", "all")
        self.assertEqual((sc.files, sc.dirs_with_pdf), (5, 2))
        flt = stats.compute(r, None, "signed")
        self.assertEqual(flt.files, s.files_signed_name)


if __name__ == "__main__":
    unittest.main()
