"""Test giao diện tab Kiểm tra trang + nút Xoá trang ở khung xem trước (offscreen, tự tạo dữ liệu, không cần OCR)."""
import io
import os
import shutil
import sys
import tempfile
import time

# tiến trình con (spawn) chạy lại đầu file này → dùng chung 1 thư mục dữ liệu tạm qua biến môi trường
os.environ.setdefault("PDFREAD_TEST_APPDATA", tempfile.mkdtemp())
os.environ["APPDATA"] = os.environ["PDFREAD_TEST_APPDATA"]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# cài đặt của test nằm trong file .ini tạm – KHÔNG ghi / xoá cài đặt thật của người dùng trong Registry
os.environ.setdefault("PDFREADPRO_SETTINGS_INI", os.path.join(tempfile.mkdtemp(), "test_settings.ini"))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

OK = True


def check(cond, msg):
    global OK
    print(("  ✔ " if cond else "  ✘ ") + msg)
    OK &= bool(cond)


def pump(app, cond, timeout=60):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return cond()


def make_pdf(path):
    import pymupdf as fitz
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("arial.ttf", 34)

    def page(doc, im):
        b = io.BytesIO()
        im.convert("RGB").save(b, "JPEG", quality=85)
        doc.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), stream=b.getvalue())

    def text(seed):
        im = Image.new("L", (1240, 1754), 250)
        d = ImageDraw.Draw(im)
        for k, y in enumerate(range(150, 1500, 52)):
            d.text((110, y), f"Noi dung {seed} dong {k} ghi chep", fill=20, font=font)
        return im

    doc = fitz.open()
    for im in (text(1), Image.new("L", (1240, 1754), 252), Image.new("L", (1240, 1754), 10), text(2), text(3),
               text(2)):
        page(doc, im)
    doc.save(path)
    doc.close()


def main():
    from PySide6.QtCore import QItemSelectionModel
    from PySide6.QtWidgets import QApplication, QMessageBox
    from pdfread_pro.ui import theme as TH
    TH.install()
    import pymupdf as fitz
    from pdfread_pro.core import pagecheck as K
    from pdfread_pro.core.models import FileInfo
    from pdfread_pro.ui.check_panel import CheckPanel
    from pdfread_pro.ui.preview import PreviewPane

    app = QApplication.instance() or QApplication([])
    work = tempfile.mkdtemp()
    src = os.path.join(work, "src")
    os.makedirs(src)
    f = os.path.join(src, "a.pdf")
    make_pdf(f)

    print("Tab Kiểm tra trang")
    p = CheckPanel()
    p.resize(1300, 800)
    p.show()
    fi = FileInfo(path=f, rel="a.pdf", name="a.pdf", pages=6)
    p.set_files([fi], src, "test")
    doc = fitz.open(f)
    pages = [K.analyze_page(pg) for pg in doc]
    doc.close()
    for pg in pages:
        pg.angle = 0
    p.results[f] = K.CheckResult(f, pages=pages)
    p._refresh_all()
    p.table.selectRow(0)
    app.processEvents()
    kinds = [pg.kind for pg in pages]
    check(kinds[:3] == ["", "blank", "black"], f"nhận ra trang trắng và đen: {kinds}")
    check(p.ptable.rowCount() == 6, "bảng trang đủ 6 dòng")
    cell = lambda r, c: p.ptable.item(r, c).text()   # noqa: E731
    check("Trắng" in cell(1, 3) and "Đen" in cell(2, 3), f"cột Nội dung: {cell(1, 3)!r}, {cell(2, 3)!r}")
    check("Trùng nội dung" in cell(5, 3), f"trang 6 trùng trang 4: {cell(5, 3)!r}")
    p.cmb_show.setCurrentIndex(2)
    check(p.ptable.rowCount() == 2, "bộ lọc “chỉ trắng / đen” còn 2 dòng")
    p.cmb_show.setCurrentIndex(1)
    check(p.ptable.rowCount() == 3, f"bộ lọc “có vấn đề” còn {p.ptable.rowCount()} dòng (trắng, đen, 1 trang trùng)")
    p.cmb_show.setCurrentIndex(0)
    check(not p.btn_fix.isEnabled(), "chưa chọn bỏ trắng / đen → chưa cần sửa")

    p.ck_blank.setChecked(True)
    check(p._plan(f).removed == [1] and p.btn_fix.isEnabled(), "bật bỏ trang trắng → xoá trang 2")
    p.ck_black.setChecked(True)
    check(p._plan(f).removed == [1, 2], "bật bỏ trang đen → xoá thêm trang 3")
    p.sp_black.setValue(99)
    check(p._plan(f).blacks == ([2] if pages[2].dark >= 0.99 else []), "đổi ngưỡng đen áp dụng ngay, không đọc lại file")
    p.sp_black.setValue(90)

    # đánh dấu tay: chọn 2 dòng + nút
    p.ck_blank.setChecked(False)
    p.ck_black.setChecked(False)
    check(not p.btn_fix.isEnabled(), "tắt các tuỳ chọn → không còn gì cần sửa")
    p.ptable.selectRow(3)
    p.ptable.selectionModel().select(p.ptable.model().index(4, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
    p.btn_mark.click()
    check([i for i, x in enumerate(pages) if x.marked] == [3, 4], "đánh dấu xoá 2 trang chọn bằng nút")
    check(p._plan(f).removed == [3, 4] and p.btn_fix.isEnabled(), "trang đánh dấu vào kế hoạch sửa")
    p.btn_unmark.click()
    check(not any(x.marked for x in pages), "bỏ đánh dấu")
    p.btn_pick.menu().actions()[2].trigger()          # trắng + đen
    check([i for i, x in enumerate(pages) if x.marked] == [1, 2], "chọn nhanh mọi trang trắng + đen")
    p.btn_pick.menu().actions()[3].trigger()          # trùng
    check(pages[5].marked, "chọn nhanh trang trùng")
    for x in pages:
        x.marked = False

    # nút Xoá ở khung xem trước (bản gốc) = đánh dấu
    p.cb_del.setCurrentIndex(p.cb_del.findData("mark"))            # chế độ «chỉ đánh dấu xoá»
    p.preview.show_file(f)
    check(pump(app, lambda: p.preview.total == 6), "khung xem trước đã nạp file")
    p.preview.goto(2)
    check(pump(app, lambda: p.preview.page == 2), "xem trang 3")
    p.preview.btn_del.click()
    check(pages[2].marked and os.path.isfile(f) and fitz.open(f).page_count == 6,
          "🗑 ở khung xem trước chỉ đánh dấu, chưa xoá file")
    p.preview.btn_del.click()
    check(not pages[2].marked, "bấm lần nữa để bỏ đánh dấu")
    pages[2].marked = True
    p.ck_blank.setChecked(False)

    # sửa thật sang thư mục mới
    out = os.path.join(work, "out")
    p.out_edit.setText(out)
    p.rb_new.setChecked(True)
    p.fix()
    check(pump(app, lambda: not p.running, 120), "chạy sửa xong")
    got = os.path.join(out, "a.pdf")
    check(os.path.isfile(got) and fitz.open(got).page_count == 5, "file sửa còn 5 trang (đã xoá trang đánh dấu)")
    check(fitz.open(f).page_count == 6, "file gốc nguyên vẹn")
    p.preview.release()
    p.close()

    print("Chọn kiểm tra + thanh lọc / sắp xếp (tab Kiểm tra)")
    p = CheckPanel()
    p.resize(1300, 800)
    p.show()
    f2 = os.path.join(src, "b.pdf")
    d2 = fitz.open()
    for k in range(2):
        pg2 = d2.new_page()
        for line in range(40):
            pg2.insert_text((60, 60 + line * 18), f"Trang {k} dong {line}: noi dung van ban rieng cua trang so {k * 7}", fontsize=11)
    d2.save(f2)
    d2.close()
    fi2 = FileInfo(path=f2, rel="b.pdf", name="b.pdf", pages=2, size=os.path.getsize(f2))
    fi.pages, fi.size = 6, os.path.getsize(f)
    p.set_files([fi, fi2], src, "test")
    check(set(p.CHECKS) == set(K.CHECK_KEYS) and all(c.isChecked() for c in p.CHECKS.values()), "mặc định bật đủ 7 kiểm tra")
    p.btn_quick.menu().actions()[1].trigger()                      # chỉ trắng + đen
    check(p.checks == {"blank", "black"}, f"chọn nhanh “chỉ trắng + đen”: {sorted(p.checks)}")
    check(not p.ck_rot.isEnabled() and not p.ck_sort.isEnabled() and p.ck_blank.isEnabled(),
          "tuỳ chọn sửa phụ thuộc mục kiểm tra (xoay / sắp xếp bị khoá)")
    p.check()
    check(pump(app, lambda: not p.running, 120) and len(p.results) == 2, "kiểm tra xong 2 file (không OCR)")
    r1 = p.results[f]
    check(not r1.ocr and [x.kind for x in r1.pages][:3] == ["", "blank", "black"], "kết quả không OCR đúng loại trang")
    p.ck_blank.setChecked(True)                                  # bật “bỏ trang trắng” → file a thành “cần sửa”
    check(p.table.item(0, 6).text().startswith("🛠") and p.table.item(1, 6).text().startswith("✔"),
          f"file 1 có vấn đề / file 2 đạt: {p.table.item(0, 6).text()!r} {p.table.item(1, 6).text()!r}")
    check(p.table.item(0, 4).text() == "—", "cột số trang hiện — khi không kiểm tra số trang")
    p.results.clear()
    p.table.item(0, 6).setText("")
    p.check()                                                    # lần 2: file không đổi → dùng kết quả đã lưu, không chạy tiến trình
    check(not p.running and p.cached_n == 2 and len(p.results) == 2, f"kiểm tra lại dùng kết quả đã lưu ({p.cached_n}/2 file)")
    check(p.table.item(0, 6).text().startswith("🛠") and "♻" in p.lbl.text(), "kết quả hiển thị đúng + báo ♻")
    p._cache = {}                                                # (bỏ đệm để các bước sau chạy như thường)
    p.c_orient.setChecked(True)
    check(p.table.item(0, 6).text().startswith("⏳ Cần kiểm tra lại"), "bật thêm mục cần OCR → báo cần kiểm tra lại")
    p.c_orient.setChecked(False)
    check(not p.table.item(0, 6).text().startswith("⏳"), "tắt lại → hết báo")
    vis = lambda: [r for r in range(2) if not p.table.isRowHidden(r)]   # noqa: E731
    pick = lambda bar, key: bar.cb_show.setCurrentIndex(bar.cb_show.findData(key))   # noqa: E731
    pick(p.fbar, "blank")
    check(vis() == [0], "lọc “có trang trắng” chỉ còn file a")
    pick(p.fbar, "ok")
    check(vis() == [1], "lọc “đạt” chỉ còn file b")
    pick(p.fbar, "problem")
    check(vis() == [0], "lọc “file có vấn đề”")
    pick(p.fbar, "all")
    check(vis() == [0, 1], "lọc “tất cả”")
    p.fbar.cb_sort.setCurrentIndex(p.fbar.cb_sort.findData("pages"))
    vh = p.table.verticalHeader()
    check(p.files[vh.logicalIndex(0)].pages == 6, "sắp xếp số trang nhiều → ít")
    p.fbar.cb_sort.setCurrentIndex(p.fbar.cb_sort.findData("name"))
    p.fbar.cb_sort.setCurrentIndex(p.fbar.cb_sort.findData("problem"))
    check(vh.logicalIndex(0) == 0, "sắp xếp “vấn đề lên trước”: file a trước")
    p.fbar.search.setText("b.pdf")
    check(vis() == [1], "tìm theo tên")
    p.fbar.search.setText("")
    p.fbar.cb_sort.setCurrentIndex(0)
    check([vh.logicalIndex(v) for v in range(2)] == [0, 1], "về thứ tự gốc")
    p.table.selectRow(1)
    app.processEvents()
    check(p._row() == 1 and p.files[p._row()].name == "b.pdf", "chọn dòng vẫn đúng file khi đổi thứ tự hiển thị")
    p.preview.release()
    p.close()

    print("Thanh lọc ở tab Nén PDF và Đổi tên")
    from pdfread_pro.core import compressor as C
    from pdfread_pro.ui.compress_panel import CompressPanel
    cp = CompressPanel()
    cp.resize(1200, 700)
    cp.show()
    fl = [FileInfo(path=os.path.join(src, n), rel=n, name=n, pages=pg, size=sz)
          for n, pg, sz in (("x1.pdf", 3, 300), ("x2.pdf", 9, 100), ("x3.pdf", 5, 900), ("x4.pdf", 1, 50))]
    fl[3].error = "File hỏng"
    cp.set_files(fl, src, "test")
    cp.memory[fl[0].path] = ("measure", C.Result(fl[0].path, C.ST_OK_ALREADY, over_before=2, max_before_kb=400))
    cp.memory[fl[1].path] = ("measure", C.Result(fl[1].path, C.ST_OK_ALREADY, over_before=0, max_before_kb=100))
    cp.set_files(fl, src, "test")
    cvis = lambda: [r for r in range(4) if not cp.table.isRowHidden(r)]   # noqa: E731
    pick(cp.fbar, "need")
    check(cvis() == [0], "Nén: lọc “cần nén”")
    pick(cp.fbar, "ok")
    check(cvis() == [1], "Nén: lọc “đã đạt chuẩn”")
    pick(cp.fbar, "error")
    check(cvis() == [3], "Nén: lọc “lỗi”")
    pick(cp.fbar, "pending")
    check(cvis() == [2], "Nén: lọc “chưa phân tích”")
    pick(cp.fbar, "all")
    cp.fbar.cb_sort.setCurrentIndex(cp.fbar.cb_sort.findData("size"))
    cvh = cp.table.verticalHeader()
    check([cvh.logicalIndex(v) for v in range(4)] == [2, 0, 1, 3], "Nén: sắp xếp dung lượng lớn → nhỏ")
    cp.table.selectRow(2)
    app.processEvents()
    cp.close()

    from pdfread_pro.ui.rename_panel import RenamePanel
    from pdfread_pro.ui.rules1361_panel import Rules1361Panel
    from pdfread_pro.ui.rules_panel import RulesPanel
    rp = RenamePanel(Rules1361Panel(), RulesPanel())
    rp.resize(1200, 700)
    rp.show()
    names = ["d1/01.scan.pdf", "d2/zzz_khong_ma.pdf", "d3/01.Ly_lich_nguoi_xin_vao_Dang.pdf"]
    rfl = [FileInfo(path=os.path.join(src, *n.split("/")), rel=n.replace("/", os.sep), name=n.split("/")[1], pages=1, size=10)
           for n in names]
    rp.set_files(rfl, "test")
    pump(app, lambda: len(rp.items) == 3 and not rp._timer.isActive(), 10)
    total = rp.table.rowCount()
    check(total == 3, f"Đổi tên: có {total} dòng")
    pick(rp.fbar, "ready")
    check(rp.table.rowCount() == 1 and rp.table.item(0, 3).text() == "01.scan.pdf", "Đổi tên: lọc “sẽ đổi tên”")
    pick(rp.fbar, "same")
    check(rp.table.rowCount() == 1, "Đổi tên: lọc “không đổi”")
    pick(rp.fbar, "norule")
    check(rp.table.rowCount() >= 0 and all(rp.table.item(r, 3).text() == "zzz_khong_ma.pdf" for r in range(rp.table.rowCount())),
          f"Đổi tên: lọc “chưa có quy tắc / mã số” còn {rp.table.rowCount()} dòng")
    pick(rp.fbar, "all")
    rp.fbar.cb_sort.setCurrentIndex(rp.fbar.cb_sort.findData("name"))
    col = [rp.table.item(r, 3).text() for r in range(rp.table.rowCount())]
    check(col == sorted(col, key=str.lower), "Đổi tên: sắp xếp theo tên")
    rp.fbar.search.setText("zzz")
    check(rp.table.rowCount() == 1, "Đổi tên: tìm theo tên")
    rp.preview.release()
    rp.close()

    print("Tổng quan: thanh lọc + sắp xếp cây thư mục")
    from pdfread_pro.ui.main_window import MainWindow
    __import__('pdfread_pro.paths', fromlist=['x']).make_settings().clear()
    tree_dir = os.path.join(work, "tong_quan")
    os.makedirs(os.path.join(tree_dir, "A"))
    os.makedirs(os.path.join(tree_dir, "B"))
    for rel, pages_n in (("A/zeta.pdf", 2), ("A/alpha.pdf", 5), ("B/beta.pdf", 1)):
        dd = fitz.open()
        for k in range(pages_n):
            dd.new_page().insert_text((72, 72), f"{rel} trang {k}")
        dd.save(os.path.join(tree_dir, *rel.split("/")))
        dd.close()
    with open(os.path.join(tree_dir, "B", "hong.pdf"), "wb") as fh:
        fh.write(b"khong phai pdf")
    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    win.path_edit.setText(tree_dir)
    win.start_scan()
    check(pump(app, lambda: not win.scanning and win.result is not None, 60), "quét xong thư mục thử")
    leaf = lambda: [(it.text(0)[2:], it.isHidden()) for it, _ in win.file_items]   # noqa: E731
    shown = lambda: sorted(n for n, h in leaf() if not h)   # noqa: E731
    pick(win.fbar, "error")
    check(shown() == ["hong.pdf"], f"Tổng quan: lọc “file lỗi”: {shown()}")
    pick(win.fbar, "nosig")
    check(shown() == ["alpha.pdf", "beta.pdf", "zeta.pdf"], f"Tổng quan: lọc “chưa có chữ ký số”: {shown()}")
    pick(win.fbar, "all")
    check(len(shown()) == 4, "Tổng quan: tất cả 4 file")
    win.fbar.cb_sort.setCurrentIndex(win.fbar.cb_sort.findData("pages"))
    order = [win.tree.topLevelItem(i).text(0)[2:] for i in range(win.tree.topLevelItemCount())]
    check(order == ["A", "B"], f"Tổng quan: thứ tự thư mục giữ nguyên khi sắp theo số trang: {order}")
    folder_a = next(it for d, it in win.dir_items.items() if d == "A")
    check([folder_a.child(i).text(0)[2:] for i in range(folder_a.childCount())] == ["alpha.pdf", "zeta.pdf"],
          "Tổng quan: trong thư mục A sắp theo số trang nhiều → ít")
    win.fbar.cb_sort.setCurrentIndex(win.fbar.cb_sort.findData("name"))
    check([folder_a.child(i).text(0)[2:] for i in range(folder_a.childCount())] == ["alpha.pdf", "zeta.pdf"], "sắp theo tên A → Z")
    win.fbar.cb_sort.setCurrentIndex(0)
    check(win.tree.topLevelItemCount() >= 1, "về thứ tự gốc, cây còn nguyên")
    win.preview.release()
    win.close()

    print("Kiểm tra trang: xoá ngay · tô màu trạng thái · dòng đã xử lý · tab Thùng rác · cập nhật tại chỗ")
    from PySide6.QtGui import QColor as _QC
    from pdfread_pro.core import trash as T
    from pdfread_pro.ui import preview as PV
    T.clear()
    PV.prefs().set_confirm(False)
    pc = CheckPanel()
    pc.resize(1300, 800)
    pc.show()
    gdir = os.path.join(work, "xoa_ngay")
    os.makedirs(gdir)
    fx, fy = os.path.join(gdir, "x.pdf"), os.path.join(gdir, "y.pdf")
    make_pdf(fx)
    make_pdf(fy)
    fis = [FileInfo(path=q, rel=os.path.basename(q), name=os.path.basename(q), pages=6, size=os.path.getsize(q))
           for q in (fx, fy)]
    pc.set_files(fis, gdir, "t")
    pc.btn_quick.menu().actions()[1].trigger()
    pc._cache = {}
    pc.check()
    pump(app, lambda: not pc.running, 60)
    check(pc.cb_del.currentData() == "now", "mặc định nút 🗑 / Delete = xoá ngay")
    bgc = lambda r: pc.table.item(r, 6).background().color().name().upper()   # noqa: E731
    check(pc.table.item(0, 6).text().startswith("⚠") and bgc(0) == "#FEF9C3", f"“Cần xem lại” nền vàng: {bgc(0)}")
    pc.ck_blank.setChecked(True)
    check(pc.table.item(0, 6).text().startswith("🛠") and bgc(0) == "#FFEDD5", f"“Cần sửa” nền cam: {bgc(0)}")
    check(pc.table.item(1, 6).text().startswith("🛠"), "file y cũng cần sửa (có trang trắng)")
    pc.ck_blank.setChecked(False)
    check(pc._set_status.__func__ is not None and pc.table.item(0, 6).foreground().color() != _QC("#15803D"), "màu chữ trạng thái khác nhau")
    pc.table.selectRow(0)
    pc.preview.show_file(fx)
    check(pump(app, lambda: pc.preview.total == 6 and pc.preview.path == fx), "xem trước file x")
    pc.preview.goto(1)
    pump(app, lambda: pc.preview.page == 1)
    pc.preview.btn_del.click()                              # xoá ngay (không hỏi vì đã tắt xác nhận)
    d = fitz.open(fx)
    check(d.page_count == 5, "🗑 ở khung xem trước xoá LUÔN trang (không chỉ đánh dấu)")
    d.close()
    check(len(pc.results[fx].pages) == 5, "kết quả kiểm tra bỏ đúng trang đã xoá (không cần kiểm tra lại)")
    left = pc._plan(fx)
    if left and (left.needs_fix or left.issues()):
        # file còn trang lỗi khác → KHÔNG được coi là xong, vẫn hiện trong «File có vấn đề»
        check("còn vấn đề" in pc.table.item(0, 6).text() and "đã xoá 1 trang" in pc.table.item(0, 6).text(),
              f"còn trang lỗi → vẫn là việc cần làm: {pc.table.item(0, 6).text()!r}")
        check("problem" in pc._info(0)[0] and "done" not in pc._info(0)[0], "vẫn thuộc nhóm «File có vấn đề»")
        pick(pc.fbar, "problem")
        check(not pc.table.isRowHidden(0), "bộ lọc «File có vấn đề»: file còn lỗi không bị ẩn")
        pick(pc.fbar, "all")
        pc._set_done([0], True)                             # người dùng tự đánh dấu xong
    check("Đã xử lý" in pc.table.item(0, 6).text() and bgc(0) == "#DCFCE7", f"dòng đã xử lý: {pc.table.item(0, 6).text()!r}")
    check(pc.table.item(0, 1).background().color().name().upper() == "#DCFCE7", "cả dòng tô nền xanh lá")
    check(pc.table.item(1, 1).background().color().name().upper() != "#DCFCE7", "file khác không bị tô")
    check(pc.btn_fixed.isEnabled() and pc.btn_orig.isEnabled(), "đã có «Bản gốc» ↔ «Bản đã sửa» sau khi xoá trang")
    pc.btn_orig.click()
    app.processEvents()
    pump(app, lambda: pc.preview.total == 6 and pc.preview.path == T.backup_path_for(fx), 20)
    check(pc.preview.path == T.backup_path_for(fx) and pc.preview.total == 6, "«Bản gốc» mở bản sao lưu (6 trang)")
    pc.btn_fixed.click()
    pump(app, lambda: pc.preview.total == 5, 20)
    check(pc.preview.path == fx and pc.preview.total == 5, "«Bản đã sửa» mở file hiện tại (5 trang)")
    pc.table.selectRow(0)
    app.processEvents()
    pc.cmb_show.setCurrentIndex(0)
    pump(app, lambda: pc.ptable.rowCount() == 5, 10)
    pump(app, lambda: pc.preview.total == 5, 20)
    for want in (3, 0, 4):                                  # sau khi xoá trang, bấm dòng ở bảng chi tiết → khung xem trước nhảy đúng trang
        pc.ptable.selectRow(want)
        pump(app, lambda: pc.preview.page == want, 10)
        check(pc.preview.page == want, f"sau khi xoá trang: bấm dòng trang {want + 1} → xem trước đúng trang {pc.preview.page + 1}")
    # xoá ngay nhiều trang đang chọn trong bảng
    pc.table.selectRow(1)
    app.processEvents()
    pc.check()                                              # kiểm tra lại y (x dùng kết quả cũ)
    pump(app, lambda: not pc.running, 60)
    pc.table.selectRow(1)
    app.processEvents()
    pc.ptable.selectionModel().clearSelection()
    for rr in (1, 2):
        pc.ptable.selectionModel().select(pc.ptable.model().index(rr, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
    check(sorted(pc._selected_pages()) == [1, 2], "chọn 2 trang trong bảng chi tiết")
    pc.btn_now.click()
    d = fitz.open(fy)
    check(d.page_count == 4, "«🗑 Xoá ngay» xoá 2 trang đang chọn")
    d.close()
    check(len(pc.results[fy].pages) == 4 and "xoá 2 trang" in pc.table.item(1, 6).text().replace("đã ", ""),
          f"kết quả cập nhật: {pc.table.item(1, 6).text()!r}")
    check(sorted(e.kind for e in T.list_entries()).count(T.KIND_PAGES) == 2, "mỗi lần xoá đều có mục trong thùng rác")
    check(not any(pc.table.isRowHidden(r) for r in range(2)), "không dòng nào bị ẩn")
    pc.preview.release()
    pc.close()
    PV.prefs().set_confirm(True)

    win3 = MainWindow()
    win3.resize(1400, 900)
    win3.show()
    titles = [win3.tabs.tabText(i) for i in range(win3.tabs.count())]
    check(titles[-2:] == ["🗑 Thùng rác", "📖 Hướng dẫn"] and "Quy tắc" in titles[-3], f"tab Thùng rác nằm giữa Quy tắc và Hướng dẫn: {titles[-3:]}")
    win3.path_edit.setText(tree_dir)
    win3.start_scan()
    pump(app, lambda: not win3.scanning and win3.result is not None, 60)
    fa_item = next(it for it, ff in win3.file_items if ff.name == "alpha.pdf")
    win3.tree.setCurrentItem(fa_item)
    pump(app, lambda: win3.preview.total == 5 and win3.preview.path.endswith("alpha.pdf"), 20)
    PV.prefs().set_confirm(False)
    win3.preview.btn_del.click()
    pump(app, lambda: False, 0.5)
    ff = next(ff for it, ff in win3.file_items if ff.name == "alpha.pdf")
    check(ff.pages == 4 and fa_item.text(1) == "4", f"Tổng quan: dòng alpha.pdf cập nhật tại chỗ → {fa_item.text(1)} trang (không quét lại)")
    check(win3.tree.currentItem() is fa_item, "dòng đang chọn được giữ nguyên")
    check("Thùng rác (" in win3.btn_trash.text(), f"nút thùng rác cập nhật số mục: {win3.btn_trash.text()}")
    # xoá trang ở tab KHÁC khi tab Kiểm tra trang đã có kết quả → bảng Kiểm tra không được giữ số trang cũ
    win3._pending.pop(win3.check)()                         # như khi mở tab Kiểm tra trang (nạp danh sách file)
    win3.check.check()
    pump(app, lambda: not win3.check.running, 60)
    crow = next(i for i, x in enumerate(win3.check.files) if x.name == "alpha.pdf")
    check(win3.check.table.item(crow, 3).text() == "4", "tab Kiểm tra: alpha.pdf 4 trang trước khi xoá")
    win3.tree.setCurrentItem(fa_item)
    pump(app, lambda: win3.preview.total == 4 and win3.preview.path.endswith("alpha.pdf"), 20)
    win3.preview.btn_del.click()
    pump(app, lambda: False, 0.5)
    txt = win3.check.table.item(crow, 3).text()
    check(txt in ("3", "") and "Chưa kiểm tra" in win3.check.table.item(crow, 6).text() + "Chưa kiểm tra",
          f"xoá ở tab khác → tab Kiểm tra không giữ số trang cũ (cột Trang = {txt!r}, trạng thái = {win3.check.table.item(crow, 6).text()!r})")
    check(txt != "4", "cột Trang của tab Kiểm tra không còn 4")
    win3.tabs.setCurrentIndex(win3.tabs.count() - 2)
    app.processEvents()
    check(win3.trash.table.rowCount() >= 2, "mở tab Thùng rác thấy các mục vừa tạo")
    PV.prefs().set_confirm(True)
    win3.tabs.setCurrentIndex(0)
    win3.preview.release()
    win3.close()

    print("Chọn cột hiển thị · menu chuột phải · tô cả hàng · bản sao lưu ngoài thư mục hồ sơ")
    from pdfread_pro.ui import tablekit as TK
    from pdfread_pro.core import trash as T
    T.clear()
    pm = CheckPanel()
    pm.resize(1300, 800)
    pm.show()
    mdir = os.path.join(work, "menu")
    os.makedirs(mdir)
    fm = [os.path.join(mdir, f"m{k}.pdf") for k in range(3)]
    for q in fm:
        make_pdf(q)
    pm.set_files([FileInfo(path=q, rel=os.path.basename(q), name=os.path.basename(q), pages=6, size=os.path.getsize(q))
                  for q in fm], mdir, "t")
    pm.btn_quick.menu().actions()[1].trigger()
    pm._cache = {}
    pm.check()
    pump(app, lambda: not pm.running, 60)
    pm.ck_blank.setChecked(True)
    row_bg = {pm.table.item(1, c).background().color().name().upper() for c in range(len(pm.COLS))}
    check(row_bg == {"#FFEDD5"}, f"cả hàng 'Cần sửa' cùng một nền cam: {row_bg}")
    # ---- chọn cột
    menu = TK.build_column_menu(pm.table, "check_files", (1,), pm)
    acts = {a.text(): a for a in menu.actions() if a.text()}
    acts["Thư mục"].trigger()
    check(pm.table.isColumnHidden(2) and 2 in TK.load_hidden("check_files"), "ẩn cột «Thư mục» và nhớ lựa chọn")
    check(not acts["Tên file"].isEnabled(), "cột Tên file được bảo vệ (không ẩn được)")
    for a in TK.build_column_menu(pm.table, "check_files", (1,), pm).actions():
        if a.text().startswith("👁"):
            a.trigger()
    check(not pm.table.isColumnHidden(2) and TK.load_hidden("check_files") == set(), "«Hiện tất cả cột»")
    check(pm.fbar.layout().count() >= 6, "thanh Hiển thị có nút ▦ Cột")
    # ---- menu chuột phải theo dòng
    extras = {it[0] if it else None: it for it in pm._row_extras([1])}
    labels = [k for k in extras if k]
    check(any("Cập nhật dòng này" in k for k in labels) and any("Sửa tự động riêng" in k for k in labels)
          and any("Kiểm tra lại file này" in k for k in labels), f"menu dòng có các việc riêng: {len(labels)} mục")
    fix_item = next(v for k, v in extras.items() if k and "Sửa tự động riêng" in k)
    check(len(fix_item) > 2 and fix_item[2] is True, "«Sửa tự động riêng» bật vì dòng này cần sửa")
    done_item = next(v for k, v in extras.items() if k and "Đánh dấu là đã xử lý" in k)
    done_item[1]()
    check("Đã xử lý" in pm.table.item(1, 6).text() and {pm.table.item(1, c).background().color().name().upper()
          for c in range(len(pm.COLS))} == {"#DCFCE7"}, "đánh dấu tay «đã xử lý» → cả hàng xanh lá")
    undone = next(v for it in pm._row_extras([1]) if it and "Bỏ đánh dấu" in it[0] for v in [it])
    undone[1]()
    check("Cần sửa" in pm.table.item(1, 6).text(), "bỏ đánh dấu → trở lại trạng thái cũ")
    # cập nhật riêng 1 dòng (kiểm tra lại, bỏ qua bộ nhớ đệm) + sửa riêng 1 dòng
    refreshed = []
    pm.refreshRequested.connect(refreshed.append)
    pm.refresh_rows([1])
    pump(app, lambda: not pm.running, 60)
    check(refreshed == [fm[1]] and pm.results[fm[1]].pages, "«Cập nhật dòng này» phát yêu cầu đọc lại file + kiểm tra lại")
    out_dir = os.path.join(work, "menu_out")
    pm.out_edit.setText(out_dir)
    pm.rb_new.setChecked(True)
    pm.fix([1])
    pump(app, lambda: not pm.running, 60)
    check(os.path.isfile(os.path.join(out_dir, "m1.pdf")) and not os.path.exists(os.path.join(out_dir, "m0.pdf")),
          "«Sửa tự động riêng file này» chỉ sửa đúng file đó")
    # ---- sao lưu KHÔNG nằm trong thư mục hồ sơ; khôi phục bản gốc từ menu
    pm.rb_over.setChecked(True)
    pm.ck_backup.setChecked(True)
    real_q2 = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    pm.fix([2])
    pump(app, lambda: not pm.running, 60)
    check(fitz.open(fm[2]).page_count == 5, "ghi đè: file m2 còn 5 trang (đã bỏ trang trắng)")
    check(not os.path.exists(os.path.join(mdir, "_backup_goc")) and os.path.isfile(T.backup_path_for(fm[2])),
          f"bản sao lưu nằm ở nơi sao lưu của app, KHÔNG có _backup_goc trong thư mục hồ sơ ({sorted(os.listdir(mdir))}, "
          f"{T.backup_path_for(fm[2])} → {os.path.isfile(T.backup_path_for(fm[2]))})")
    restore_item = next(it for it in pm._row_extras([2]) if it and "Khôi phục bản gốc" in it[0])
    check(restore_item[2] is True, "menu có «Khôi phục bản gốc» khi đã có bản sao lưu")
    restore_item[1]()
    check(fitz.open(fm[2]).page_count == 6, "khôi phục bản gốc từ menu → 6 trang")
    QMessageBox.question = real_q2
    pm.preview.release()
    pm.close()

    print("Nút Xoá trang trực tiếp (các tab khác)")
    g = os.path.join(work, "b.pdf")
    shutil.copy2(f, g)
    pv = PreviewPane(title="")
    pv.resize(400, 700)
    pv.show()
    edited = []
    pv.fileEdited.connect(edited.append)
    pv.show_file(g)
    check(pump(app, lambda: pv.total == 6), "nạp file")
    pv.goto(1)
    pump(app, lambda: pv.page == 1)
    real = QMessageBox.question
    asked = []
    QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(a[2]), QMessageBox.No)[1])
    pv.btn_del.click()
    check(asked and fitz.open(g).page_count == 6 and not edited, "chọn Không → không xoá")
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    pv.btn_del.click()
    QMessageBox.question = real
    check(fitz.open(g).page_count == 5, "chọn Có → còn 5 trang")
    check(os.path.isfile(T.backup_path_for(g)) and not os.path.exists(os.path.join(work, "_backup_goc")), "bản sao lưu nằm trong thư mục của app, KHÔNG trong thư mục hồ sơ")
    check(edited == [g], "phát tín hiệu fileEdited")
    check(pump(app, lambda: pv.total == 5), "khung xem trước nạp lại 5 trang")
    import pymupdf
    one = os.path.join(work, "one.pdf")
    d1 = pymupdf.open()
    d1.new_page()
    d1.save(one)
    pv.show_file(one)
    pump(app, lambda: pv.total == 1)
    warned = []
    real_w = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(1))
    pv.btn_del.click()
    QMessageBox.warning = real_w
    check(warned and pymupdf.open(one).page_count == 1, "file 1 trang: không cho xoá")
    pv.release()
    pv.close()
    print("Xoá không hỏi · hoàn tác · cắt viền · thùng rác · cỡ chữ · nút Làm sạch")
    from PySide6.QtCore import QPoint, Qt as _Qt
    from PySide6.QtTest import QTest
    from pdfread_pro.core import trash as T
    from pdfread_pro.ui import preview as PV, styles as ST
    from pdfread_pro.ui.trash_dialog import TrashPanel
    from make_signed_sample import sign_pdf
    T.clear()
    base = os.path.join(work, "base.pdf")
    make_pdf(base)
    h = os.path.join(work, "h.pdf")
    shutil.copy2(base, h)
    pv = PreviewPane(title="")
    pv.resize(420, 760)
    pv.show()
    pv.show_file(h)
    check(pump(app, lambda: pv.total == 6), "nạp file thử")
    check(pv.ck_confirm.isChecked() and PV.prefs().confirm, "mặc định có hỏi xác nhận")
    asked = []
    real_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(1), QMessageBox.No)[1])
    PV.prefs().set_confirm(False)
    check(not pv.ck_confirm.isChecked(), "tắt hỏi xác nhận → ô tích đồng bộ")
    pv.goto(2)
    pump(app, lambda: pv.page == 2)
    pv.btn_del.click()
    check(not asked and fitz.open(h).page_count == 5, "xoá thẳng, không hỏi")
    check(pump(app, lambda: pv.total == 5) and not pv.undo_bar.isHidden(), "hiện thanh hoàn tác")
    kinds = sorted(e.kind for e in T.list_entries())
    check(kinds == [T.KIND_BACKUP, T.KIND_PAGES], f"thùng rác có trang xoá + bản gốc: {kinds}")
    pv.btn_undo.click()
    check(fitz.open(h).page_count == 6 and pv.undo_bar.isHidden(), "↩ Hoàn tác trả lại trang")
    check(pump(app, lambda: pv.total == 6), "khung xem trước nạp lại 6 trang")
    # file đã ký số luôn hỏi
    hs = os.path.join(work, "signed.pdf")
    sign_pdf(base, hs)
    pv.show_file(hs)
    pump(app, lambda: pv.total == 6 and pv.path == hs)
    pv.btn_del.click()
    check(asked and fitz.open(hs).page_count == 6, "file đã ký số vẫn hỏi dù tắt xác nhận (chọn Không → giữ nguyên)")
    QMessageBox.question = real_q
    # ---- cắt viền
    pv.show_file(h)
    pump(app, lambda: pv.total == 6 and pv.path == h)
    pv.btn_crop.setChecked(True)
    app.processEvents()
    check(pv.crop_bar.isVisible() and pv.overlay.isVisible(), "bật chế độ cắt: thanh cắt + khung hiện")
    ov = pv.overlay
    check(ov.width() == pv.canvas.width() > 0, "khung phủ đúng cỡ trang đang xem")
    # kéo góc trên-trái của khung vào trong bằng chuột
    pt = ov._points()["tl"]
    QTest.mousePress(ov, _Qt.LeftButton, _Qt.NoModifier, QPoint(int(pt.x()), int(pt.y())))
    QTest.mouseMove(ov, QPoint(int(ov.width() * 0.5), int(ov.height() * 0.5)))
    QTest.mouseRelease(ov, _Qt.LeftButton, _Qt.NoModifier, QPoint(int(ov.width() * 0.5), int(ov.height() * 0.5)))
    check(abs(ov.rect_n[0] - 0.5) < 0.03 and abs(ov.rect_n[1] - 0.5) < 0.03, f"kéo góc trái-trên: {ov.rect_n}")
    ov.rect_n = [0.0, 0.0, 0.5, 0.5]
    pv.btn_crop_one.click()
    d = fitz.open(h)
    check(abs(d[pv.page].rect.width - 595 / 2) < 2, f"trang {pv.page + 1} đã cắt còn một nửa bề ngang: {d[pv.page].rect.width:.0f}")
    others = [round(d[i].rect.width) for i in range(6) if i != pv.page]
    check(all(w == 595 for w in others), "các trang khác giữ nguyên")
    d.close()
    check(not pv.undo_bar.isHidden() and not pv.crop_bar.isVisible(), "cắt xong: thoát chế độ cắt, hiện hoàn tác")
    pv.btn_undo.click()
    check(round(fitz.open(h)[pv.page].rect.width) == 595, "↩ Hoàn tác cắt viền")
    pump(app, lambda: pv.total == 6)
    check(not hasattr(pv, "btn_crop_all"), "đã bỏ nút «Cắt mọi trang»")
    pv.btn_crop.setChecked(True)
    check(pv.btn_crop.isHidden() and not pv.crop_bar.isHidden(), "đang cắt viền: nút «✂ Cắt viền» ẩn, thanh cắt hiện")
    pv.btn_crop.setChecked(False)
    check(not pv.btn_crop.isHidden() and pv.crop_bar.isHidden(), "thoát chế độ cắt: nút «✂ Cắt viền» hiện lại")
    # cắt 2 lần liên tiếp rồi hoàn tác từng bước (thanh hoàn tác không tự ẩn)
    pv.btn_crop.setChecked(True)
    pv.overlay.rect_n = [0.1, 0.1, 0.9, 0.9]
    pv.btn_crop_one.click()
    pump(app, lambda: False, 0.3)
    pv.btn_crop.setChecked(True)
    pv.overlay.rect_n = [0.0, 0.0, 0.5, 0.5]
    check(pv.btn_crop_undo.isEnabled(), "trong chế độ cắt có nút ↩ Hoàn tác")
    pv.btn_crop_one.click()
    d = fitz.open(h)
    w2 = d[pv.page].rect.width
    d.close()
    check(abs(w2 - 595 * 0.8 * 0.5) < 3, f"cắt lần 2 tính theo khung đã cắt: {w2:.0f}")
    check(not pv.undo_bar.isHidden() and "còn 1 bước" in pv.lbl_undo.text(), f"nhớ 2 bước hoàn tác: {pv.lbl_undo.text()!r}")
    pv.btn_undo.click()
    d = fitz.open(h)
    check(abs(d[pv.page].rect.width - 595 * 0.8) < 3, "hoàn tác bước 1 → về khung cắt lần đầu")
    d.close()
    pv.btn_undo.click()
    d = fitz.open(h)
    check(abs(d[pv.page].rect.width - 595) < 1 and pv.undo_bar.isHidden(), "hoàn tác bước 2 → về trang gốc, thanh ẩn")
    d.close()
    pv.release()
    pv.close()
    PV.prefs().set_confirm(True)

    # ---- thùng rác (cửa sổ)
    T.clear()
    g2 = os.path.join(work, "g2.pdf")
    make_pdf(g2)
    from pdfread_pro.core import pagecheck as KK
    KK.delete_pages(g2, [1, 4])
    KK.delete_pages(g2, [0])
    dlg = TrashPanel()
    dlg.resize(1300, 700)
    dlg.show()
    app.processEvents()
    check(dlg.table.rowCount() == 3, f"thùng rác hiện {dlg.table.rowCount()} mục (2 lần xoá trang + 1 bản gốc)")
    dlg.fbar.cb_show.setCurrentIndex(dlg.fbar.cb_show.findData(T.KIND_PAGES))
    shown = [r for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
    check(len(shown) == 2, "lọc “trang đã xoá”")
    dlg.fbar.cb_show.setCurrentIndex(0)
    dlg.table.selectRow(next(r for r in range(3) if dlg.entries[r].kind == T.KIND_PAGES and dlg.entries[r].pages == [0]))
    app.processEvents()
    check(dlg.btn_restore.isEnabled() and "Đã chọn 1" in dlg.lbl_sel.text(), "chọn 1 mục: bật nút khôi phục")
    real_i, real_w = QMessageBox.information, QMessageBox.warning
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    dlg.restore_selected()
    d = fitz.open(g2)
    check(d.page_count == 4, "khôi phục: file có lại 4 trang (đã chèn trang 1 về đầu file)")
    d.close()
    check(dlg.table.rowCount() == 2, "mục đã khôi phục biến khỏi danh sách")
    dlg.table.selectRow(next(r for r in range(2) if dlg.entries[r].kind == T.KIND_PAGES))
    dlg.delete_selected()
    check(dlg.table.rowCount() == 1, "xoá vĩnh viễn 1 mục")
    dlg.clear_all()
    check(dlg.table.rowCount() == 0 and T.list_entries() == [], "dọn sạch thùng rác")
    QMessageBox.question, QMessageBox.information, QMessageBox.warning = real_q, real_i, real_w
    dlg.preview.release()
    dlg.close()

    # ---- cỡ chữ
    css0 = ST.full_style()
    ST.set_font(app, 1.25, True)
    css1 = ST.full_style()
    check("font-size: 11.9pt" in css1 and "font-size: 11.9pt" not in css0, "cỡ chữ 125% nhân vào stylesheet")
    check("font-weight: 600" in css1, "chữ đậm")
    check(abs(app.font().pointSizeF() - 9.5 * 1.25) < 0.1, "cỡ chữ ứng dụng đổi theo")
    ST.set_font(app, ST.DEFAULT_SCALE, ST.DEFAULT_BOLD)

    # ---- bảng trang cuộn được khi đang kiểm tra + nút Làm sạch
    cp2 = CheckPanel()
    cp2.show()
    fa = os.path.join(src, "a.pdf")
    cp2.set_files([FileInfo(path=fa, rel="a.pdf", name="a.pdf", pages=6, size=os.path.getsize(fa))], src, "t")
    cp2.btn_quick.menu().actions()[1].trigger()
    cp2._cache = {}                                              # không dùng kết quả đã lưu → thật sự chạy tiến trình
    cp2.check()
    check(cp2.running and cp2.ptable.isEnabled(), "đang kiểm tra mà bảng trang vẫn bật (cuộn chuột được)")
    pump(app, lambda: not cp2.running, 60)
    cp2.preview.release()
    cp2.close()
    win2 = MainWindow()
    win2.show()
    win2.path_edit.setText(tree_dir)
    win2.start_scan()
    pump(app, lambda: not win2.scanning and win2.result is not None, 60)
    check(win2.btn_clear.isVisible() and win2.result is not None, "có nút 🧹 Làm sạch")
    win2.btn_clear.click()
    check(win2.result is None and not win2.file_items, "bấm Làm sạch → xoá danh sách đã quét")
    win2.preview.release()
    win2.close()

    shutil.rmtree(work, ignore_errors=True)
    print("\nKẾT QUẢ:", "ĐẠT" if OK else "CÓ LỖI")
    return 0 if OK else 1


if __name__ == "__main__":
    sys.exit(main())
