"""Kiểm thử tích hợp giao diện (offscreen) trên BẢN SAO dữ liệu mẫu. Chạy: py tests/integration_gui.py"""
import io, os, sys, shutil, tempfile, time, warnings
warnings.simplefilter("ignore")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE = r"C:\Users\Danh Pham\Desktop\test"


def pump(app, cond, timeout=60):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.01)
    return cond()


def main():
    # test không được đổi cài đặt thật của người dùng (giới hạn KB, giao diện, file Excel…): lưu lại rồi khôi phục
    from PySide6.QtCore import QSettings
    st = QSettings("PDFReadPro", "PDFReadPro")
    saved = {k: st.value(k) for k in st.allKeys()}
    st.clear()                                    # chạy test từ cài đặt mặc định
    try:
        _main()
    finally:
        st.clear()
        for k, v in saved.items():
            st.setValue(k, v)
        st.sync()


def _main():
    from PIL import Image
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from pdfread_pro.ui import theme as TH, styles as ST
    TH.install()
    from pdfread_pro.ui.main_window import MainWindow
    from pdfread_pro.ui import tools_dialogs as TD
    from pdfread_pro.core import tools as T, renamer as R, stats as S
    app = QApplication([])
    work = tempfile.mkdtemp()
    root = os.path.join(work, "test")
    shutil.copytree(SAMPLE, root)
    # file scan ảnh nặng + thư mục CCCD
    os.makedirs(os.path.join(root, "012345678901"))
    ims = [Image.effect_noise((1600, 2200), 60).convert("RGB") for _ in range(2)]
    scan_pdf = os.path.join(root, "012345678901", "scan1.pdf")
    ims[0].save(scan_pdf, save_all=True, append_images=ims[1:], quality=95)
    shutil.copy(scan_pdf, os.path.join(root, "PhamDanh", "scan2.pdf"))

    w = MainWindow(); w.show()
    w.path_edit.setText(root); w.start_scan()
    assert pump(app, lambda: not w.busy and w.result is not None), "scan timeout"
    res = w.result
    s = S.compute(res, None, "all")
    print("scan:", len(res.files), "files", s.pages, "pages")
    assert len(res.files) == 24

    # --- đổi tên qua tab: chọn preset đánh số, phạm vi thư mục PhamDanh
    w._set_scope("PhamDanh")
    w._show_tab(w.rename)                                         # tab ẩn chỉ nạp danh sách file khi được mở
    files = w._scoped_files()
    assert w.rename.mode == "1361"                                # mặc định: bộ quy tắc 1361
    w.rules.select_preset(R.default_presets()[2]["name"])        # {n}.{stem} pad 2
    w.rename.set_mode("custom")
    w.rename.refresh()
    assert len(w.rename.items) == len(files) == 7, len(w.rename.items)
    assert sum(1 for i in w.rename.items if i.will_rename) == len(files)
    before = sorted(os.listdir(os.path.join(root, "PhamDanh")))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    w.rename.apply()
    assert pump(app, lambda: not w.busy and w.result is not None)
    after = sorted(os.listdir(os.path.join(root, "PhamDanh")))
    print("rename:", after)
    assert any(n.startswith("01.") for n in after)
    w.rename.undo()
    assert pump(app, lambda: not w.busy)
    assert sorted(os.listdir(os.path.join(root, "PhamDanh"))) == before
    print("undo ok")
    w.clear_scope()

    # --- quy tắc: ví dụ hiển thị, bỏ dấu + _ trên tab Quy tắc
    w.rules.select_preset(R.default_presets()[0]["name"])
    w.rename.refresh()
    assert any(i.will_rename for i in w.rename.items)

    # --- chế độ 1361 (mặc định): đổi thật trong thư mục Ngao rồi hoàn tác
    w.rename.set_mode("1361")
    w._set_scope("Ngao")
    w.rename.refresh()
    ready = {i.fi.name: i.new_name for i in w.rename.items if i.will_rename}
    print("1361:", ready)
    assert ready.get("13. TB - UBND phường thông báo di dời tài sản - NGUYỄN THỊ THU HUYỀN - DA KĐT HH - 25.8.2026.signed.pdf", "").startswith("13.QD_huy")
    assert ready.get("4. TB - UBND phường thông báo di dời tài sản - NGUYỄN QUỐC LUỸ - NGUYỄN THỊ KIỀU LOAN (QĐ 3657( - DA KĐT HH - 25.8.2026.signed.pdf", "").startswith("04.")
    before = sorted(os.listdir(os.path.join(root, "Ngao")))
    w.rename.apply()
    assert pump(app, lambda: not w.busy)
    assert any(n.startswith("04.Phieu_bo_sung") for n in os.listdir(os.path.join(root, "Ngao")))
    w.rename.undo()
    assert pump(app, lambda: not w.busy)
    assert sorted(os.listdir(os.path.join(root, "Ngao"))) == before
    print("1361 rename + undo ok")
    w.clear_scope()

    # --- tab quy tắc 1361: thêm / xoá quy tắc
    rp = w.rules1361
    n0 = len(rp.rules)
    rp.ed_key.setText("199x"); rp.ed_name.setText("199. Thu nghiem quy tac")
    rp.add_update()
    assert rp.rules["199x"] == "199.Thu_nghiem_quy_tac" and len(rp.rules) == n0 + 1
    rp.delete()
    assert "199x" not in rp.rules

    # --- nén qua tab: chỉ các file scan, ghi đè + sao lưu
    cp = w.compress
    comp_files = [f for f in w.result.files if f.name.startswith("scan")]
    cp.set_files(comp_files, w.result.root, "test")
    cp.rb_over.setChecked(True); cp.sp.setValue(200)
    cp.analyze()
    assert pump(app, lambda: not cp.running and cp.worker is not None), "analyze timeout"
    app.processEvents()
    print("analyze:", cp.lbl.text())
    orig = {f.path: os.path.getsize(f.path) for f in comp_files}
    cp.compress()
    assert pump(app, lambda: not cp.running, 120), "compress timeout"
    app.processEvents()
    print("compress:", cp.lbl.text())
    for f in comp_files:
        now = os.path.getsize(f.path)
        print("  ", f.name, orig[f.path], "->", now)
        assert now < orig[f.path]
        assert os.path.exists(os.path.join(os.path.dirname(f.path), "_backup_goc", f.name))
    assert pump(app, lambda: not w.busy)

    # --- tách trang: A3 ngang 2 trang → 4 trang A4, lưu file mới, file gốc giữ nguyên
    import pymupdf as fitz
    from pdfread_pro.core import splitter as SP
    a3 = os.path.join(root, "PhamDanh", "scan_A3.pdf")
    d = fitz.open()
    for t in ("P1", "P3"):
        pg = d.new_page(width=1190.55, height=841.89)
        pg.insert_text((150, 400), t, fontsize=40)
        pg.insert_text((750, 400), "P" + str(int(t[1]) + 1), fontsize=40)
    d.save(a3)
    before_bytes = open(a3, "rb").read()
    sp = w.split
    sp.load_file(a3)
    assert sp.result is not None and sp.result.doc.page_count == 4, sp.lbl_sum.text()
    sp.ck_open.setChecked(False)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
    out_path = sp.ed_out.text()
    sp.save()
    assert os.path.exists(out_path) and fitz.open(out_path).page_count == 4
    assert open(a3, "rb").read() == before_bytes            # file gốc không bị đụng
    print("split:", os.path.basename(out_path), [SP.paper_name(p.rect.width, p.rect.height) for p in fitz.open(out_path)][:1])
    assert pump(app, lambda: not w.busy)                     # app tự quét lại
    os.remove(out_path); os.remove(a3)

    # --- tự đọc số trang: sổ gỡ ghim giả lập (tờ giữa scan trước, mặt sau lộn ngược) → tự sắp đúng 1…8
    from pdfread_pro.core import pagenum
    if pagenum.available():
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from dataclasses import replace
        from test_splitter import A3L as _A3L, body_order, numbered_booklet
        truth = replace(SP.PRESETS["booklet"][1], sheet_order="inner", flip_back="yes", post_rotation="none")
        bk = os.path.join(tempfile.mkdtemp(), "so_ly_lich.pdf")
        numbered_booklet(truth, 8, _A3L).save(bk)
        sp.cb_preset.setCurrentIndex(sp.cb_preset.findData("booklet"))
        sp.load_file(bk)
        assert pump(app, lambda: sp._guess is not None, 60), sp.lbl_auto.text()
        assert sp._guess.options is not None, sp.lbl_auto.text()
        assert [n for n, _ in body_order(sp.result.doc)] == list(range(1, 9)), body_order(sp.result.doc)
        assert "số in: 1" in sp.lbl_res.text(), sp.lbl_res.text()
        print("auto-order:", sp.lbl_auto.text()[:160])

    # --- quét lại: _backup_goc phải bị bỏ qua
    w.start_scan(); assert pump(app, lambda: not w.busy)
    assert not any("_backup_goc" in f.rel for f in w.result.files)
    res = w.result

    # --- copy nhóm .signed giữ cây thư mục
    dest, n, total = T.copy_group(res, "signed")
    print("copy:", n, "/", total, "->", os.path.basename(dest))
    assert n == total == sum(1 for f in res.files if f.name_signed)
    for dd in res.dirs:
        assert os.path.isdir(os.path.join(dest, dd)), dd

    # --- đủ 5 file
    rows = T.check_five(res)
    assert all(not r.complete for r in rows)
    d5, cnt = T.copy_dirs_flat(res, [r.rel for r in rows[:2]])
    print("copy thiếu:", os.path.basename(d5), cnt)

    # --- CCCD → thùng rác
    rows = T.find_cccd_dirs(res)
    assert [r.rel for r in rows] == ["012345678901"], rows
    ok, msg = T.delete_dir(rows[0].path, permanent=not T.drive_is_fixed(rows[0].path))
    print("cccd delete:", ok, msg); assert ok and not os.path.exists(rows[0].path)

    # --- 3 thẻ + danh sách khi bấm thẻ (không lỗi)
    w.card_clicked  # tồn tại

    # --- báo cáo hồ sơ số hoá: phân loại, lọc, xuất Excel, chuẩn hoá tên thư mục + hoàn tác
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from test_report import make_tree
    from pdfread_pro.core import report as RP
    hs = os.path.join(tempfile.mkdtemp(), "Hồ sơ số hóa")
    make_tree(hs)
    w.path_edit.setText(hs)
    w.start_scan()
    assert pump(app, lambda: not w.busy)
    rp = w.report
    cnt = rp.rep.counts()
    assert len(rp.rep.dossiers) == 5 and cnt[RP.ST_MISSING] == 1 and cnt[RP.ST_NAME] == 1, cnt
    assert rp.cards["all"].value.text() == "5"
    assert rp.cards["miss"].value.text() == "2" and rp.cards["ok"].value.text() == "3"
    rp.cb_status.setCurrentIndex(rp.cb_status.findData("miss:03"))
    assert sum(rp.tree.topLevelItem(i).childCount() for i in range(rp.tree.topLevelItemCount())) == 2
    rp.ed_search.setText("Nguyen Thi")
    assert rp.tree.topLevelItemCount() == 1 and rp.tree.topLevelItem(0).childCount() == 1
    rp.tree.setCurrentItem(rp.tree.topLevelItem(0).child(0))
    assert "Còn thiếu: 03 – Phiếu đảng viên" in rp.detail.toPlainText(), rp.detail.toPlainText()
    rp.ed_search.clear()
    rp.cb_sign.setCurrentIndex(rp.cb_sign.findData(RP.SIGN_ONLY))      # chỉ tính file đã ký → hầu hết thiếu
    assert rp.rep.sign_filter == RP.SIGN_ONLY and rp.cards["ok"].value.text() == "0"
    rp.cb_sign.setCurrentIndex(0)
    assert rp.cards["ok"].value.text() == "3"
    rp.cb_status.setCurrentIndex(rp.cb_status.findData("miss"))
    assert sum(rp.tree.topLevelItem(i).childCount() for i in range(rp.tree.topLevelItemCount())) == 2
    rp.cb_status.setCurrentIndex(0)
    xlsx = os.path.join(os.path.dirname(hs), "bao_cao.xlsx")
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (xlsx, ""))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    rp.export()
    assert pump(app, lambda: os.path.exists(xlsx) and rp.btn_excel.isEnabled()), "xuất Excel (luồng phụ) quá lâu"
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    rp.fix_folders()
    assert os.path.isdir(os.path.join(hs, "Chi bo Phu Tho Cuong", "079111222333_TranVanC"))
    assert pump(app, lambda: not w.busy)
    assert w.report.rep.counts()[RP.ST_NAME] == 0
    rp.undo_folders()
    assert os.path.isdir(os.path.join(hs, "Chi bo Phu Tho Cuong", "079111222333 - Trần văn c"))
    assert pump(app, lambda: not w.busy)
    print("report:", dict(w.report.rep.counts()), os.path.basename(xlsx))

    # --- đối chiếu danh sách hệ thống (Excel) ↔ thư mục: phân loại, sửa tên + hoàn tác, xuất Excel
    from test_compare import make_case
    from pdfread_pro.core import compare as CP
    case_root, case_xlsx = make_case(tempfile.mkdtemp())
    w.path_edit.setText(case_root)
    w.start_scan()
    assert pump(app, lambda: not w.busy)
    cp = w.compare
    cp.load_file(case_xlsx)
    assert cp.table.header_row == 3 and cp.cb_cols["cccd"].currentData() == 3
    assert "Số định danh cá nhân" in cp.cb_cols["cccd"].currentText() and "vd: 056123456789" in cp.cb_cols["cccd"].currentText()
    assert "CCCD ✔" in cp.preview.horizontalHeaderItem(3).text()
    cp.assign_column("cccd", 1)                       # gán nhầm cột Họ tên → đổi chỗ, báo cột không phải CCCD
    assert (cp._columns()["cccd"], cp._columns()["name"]) == (1, 3) and "chọn nhầm cột" in cp.lbl_info.text()
    cp.assign_column("cccd", 3)
    assert (cp._columns()["cccd"], cp._columns()["name"]) == (3, 1) and "hợp lệ" in cp.lbl_info.text()
    cp.assign_column("", 4)
    assert cp._columns()["chibo"] is None
    cp.assign_column("chibo", 4)
    cp.run()
    assert cp.cmp is not None and cp.cards["nofolder"].value.text() == "5", cp.cards["nofolder"].value.text()
    assert cp.cmp.count(CP.K_NAME) == 1 and cp.cmp.count(CP.K_TYPO) == 1 and cp.cmp.count(CP.K_CHIBO) == 1
    cp.cb_kind.setCurrentIndex(cp.cb_kind.findData("fix"))
    assert cp.tree.topLevelItemCount() == 3
    cp.cb_kind.setCurrentIndex(0)
    out_cmp = os.path.join(os.path.dirname(case_root), "doi_chieu.xlsx")
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out_cmp, ""))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    cp.export()
    assert pump(app, lambda: os.path.exists(out_cmp) and cp.btn_export.isEnabled()), "xuất đối chiếu quá lâu"
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    cp.do_rename()
    assert pump(app, lambda: not w.busy)
    assert cp.cmp.count(CP.K_NAME) == 0 and cp.cmp.count(CP.K_TYPO) == 0, (cp.cmp.count(CP.K_NAME), cp.cmp.count(CP.K_TYPO))
    cp.undo()
    assert pump(app, lambda: not w.busy)
    assert cp.cmp.count(CP.K_NAME) == 1
    print("compare:", {k: cp.cmp.count(k) for k in CP.KIND_ORDER})

    # --- giao diện tối: đổi qua lại, màu viết thẳng trong tab đổi theo và trả về đúng màu gốc
    card = cp.cards["match"].value
    item = next(cp.tree.topLevelItem(i) for i in range(cp.tree.topLevelItemCount())
                if cp.tree.topLevelItem(i).text(0) == CP.K_MATCH)
    light_fg = item.foreground(0).color().name().upper()
    assert "#15803D" in card.styleSheet() and light_fg == "#15803D", (card.styleSheet(), light_fg)
    w.toggle_theme()
    assert ST.current()["name"] == "dark" and w.btn_theme.text().startswith("☀")
    assert "#4ADE80" in card.styleSheet() and item.foreground(0).color().name().upper() == "#4ADE80"
    assert TH.LIGHT_TO_DARK["#DCFCE7"] == item.background(0).color().name().upper()
    cp.apply_filter()                                         # dòng tạo mới khi đang tối cũng đúng màu tối
    item = next(cp.tree.topLevelItem(i) for i in range(cp.tree.topLevelItemCount())
                if cp.tree.topLevelItem(i).text(0) == CP.K_MATCH)
    assert item.foreground(0).color().name().upper() == "#4ADE80"
    w.toggle_theme()
    assert ST.current()["name"] == "light" and "#15803D" in card.styleSheet()
    assert item.foreground(0).color().name().upper() == "#15803D"
    print("theme: sáng ↔ tối OK")

    # --- xem trước cao hết tab (như Tổng quan) ở tab Giảm dung lượng / Kiểm tra trang
    for page in (w.compress, w.check):
        w._show_tab(page)
        app.processEvents()
        assert page.preview.height() > 0.75 * page.height(), (page.preview.height(), page.height())

    # --- kiểm tra trang: trang xáo + lộn ngược → phát hiện, sửa sang thư mục mới, file gốc giữ nguyên
    from pdfread_pro.core import pagenum, pagecheck as PK
    from pdfread_pro.core.models import FileInfo
    from PIL import ImageDraw, ImageFont
    if pagenum.available():
        font = ImageFont.truetype("arial.ttf", 34)
        d = fitz.open()
        for n, rot in ((2, 0), (1, 180), (3, 0)):
            im = Image.new("L", (1240, 1754), 250)
            dr = ImageDraw.Draw(im)
            for y in range(150, 1500, 52):
                dr.text((110, y), "Ho so dang vien ghi chep qua trinh cong tac hoc tap", fill=20, font=font)
            dr.text((620, 1660), f"- {n} -", fill=20, font=font, anchor="mm")
            buf = io.BytesIO()
            im.rotate(rot).convert("RGB").save(buf, "JPEG", quality=80)
            d.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), stream=buf.getvalue())
        xp = os.path.join(root, "PhamDanh", "xao_tron.pdf")
        d.save(xp)
        raw = open(xp, "rb").read()
        kp = w.check
        kp.set_files([FileInfo(xp, os.path.join("PhamDanh", "xao_tron.pdf"), "xao_tron.pdf", pages=3)], root, "test")
        kp.table.selectRow(0)
        kp.check()
        assert pump(app, lambda: not kp.running and kp.worker is not None, 120), "check timeout"
        app.processEvents()
        print("check:", kp.lbl.text(), "|", kp.table.item(0, 5).text())
        assert kp.table.item(0, 6).text().startswith("🛠") and kp.ptable.rowCount() == 3
        assert "xoay 180°" in kp.ptable.item(1, 3).text()
        kp.ptable.item(2, 1).setText("3")                 # sửa tay số trang → vẫn hợp lệ
        out_dir = os.path.join(work, "da_kiem_tra")
        kp.rb_new.setChecked(True); kp.out_edit.setText(out_dir)
        kp.fix()
        assert pump(app, lambda: not kp.running, 60), "fix timeout"
        app.processEvents()
        print("fix:", kp.lbl.text())
        fixed = os.path.join(out_dir, "PhamDanh", "xao_tron.pdf")
        assert open(xp, "rb").read() == raw and os.path.isfile(fixed)
        assert [(p.angle, p.number) for p in PK.check_file(fixed).pages] == [(0, 1), (0, 2), (0, 3)]
        assert kp.btn_fixed.isEnabled() and kp.preview.path == fixed
        print("kiểm tra trang: OK")

    # --- tách trang: hộp chọn file có tìm kiếm, file trước / sau, thẻ hình chọn kiểu tách, hướng dẫn
    from pdfread_pro.ui import file_picker as FP
    fl = w.result.files
    dlg = FP.FilePickerDialog(None, fl, "")
    dlg.search.setText("tran van thai")
    dlg.fill()
    shown = sum(dlg.tree.topLevelItem(i).childCount() for i in range(dlg.tree.topLevelItemCount()))
    assert 0 < shown < len(fl) and all(dlg.tree.topLevelItem(i).text(0).lower().find("tranvanthai") >= 0
                                       for i in range(dlg.tree.topLevelItemCount())), shown
    assert FP.fold("TDP 1 An Hòa Đông") == "tdp 1 an hoa dong"
    sp.set_files(fl)
    sp._step_file(1)
    assert sp.src_path == fl[0].path and not sp.btn_prev.isEnabled()
    sp._step_file(1)
    assert sp.src_path == fl[1].path and fl[1].name in sp.lbl_file.toolTip() + sp.lbl_file._full
    sp.cards["booklet"].click()
    assert sp.cb_preset.currentData() == "booklet" and sp.cards["booklet"].isChecked()         and not sp.cards["a3_to_a4"].isChecked()
    sp.helpRequested.emit("split")
    assert w.tabs.currentWidget() is w.guide.parentWidget()
    # kéo đường cắt đỏ bằng chuột → đổi Vị trí đường cắt, kết quả cắt theo
    from PySide6.QtCore import QPoint, Qt as _Qt
    from PySide6.QtTest import QTest
    a3d = os.path.join(work, "keo_duong_cat.pdf")               # file A3 riêng (thư mục mẫu đã bị đổi ở bước trước)
    dd = fitz.open()
    dd.new_page(width=1190.55, height=841.89).insert_text((150, 400), "P1      P2", fontsize=40)
    dd.save(a3d)
    sp.load_file(a3d)
    sp._apply_preset("a3_to_a4"); sp.rebuild()
    pump(app, lambda: sp.view_src._base is not None, 10)
    v = sp.view_src
    rr = v._img_rect()
    x0, yy = int(rr.left() + rr.width() / 2), int(rr.center().y())
    QTest.mousePress(v, _Qt.LeftButton, _Qt.NoModifier, QPoint(x0, yy))
    QTest.mouseMove(v, QPoint(int(x0 + rr.width() * 0.10), yy))
    QTest.mouseRelease(v, _Qt.LeftButton, _Qt.NoModifier, QPoint(int(x0 + rr.width() * 0.10), yy))
    sp.rebuild()
    assert sp.sp_cut.value() == 60 and sp.btn_adv.isChecked(), sp.sp_cut.value()
    assert abs(sp.result.units[0].clip.width / sp.src_doc[0].rect.width - 0.60) < 0.01
    print("tách trang (chọn file, thẻ hình, hướng dẫn, kéo đường cắt): OK")

    # --- gom ký số: gom file chưa ký → (giả lập ký) → trả bản .signed về đúng hồ sơ → hoàn tác
    from pdfread_pro.core import scanner as SCN, signgather as SG
    cb = os.path.join(work, "gom_test", "Chi bo 1")
    for cccd, ten in (("056123456789", "TranVanThai"), ("079111222333", "LeThiChuyen")):
        hs_dir = os.path.join(cb, f"{cccd}_{ten}")
        os.makedirs(hs_dir, exist_ok=True)
        dd = fitz.open()
        dd.new_page().insert_text((72, 72), ten)
        dd.save(os.path.join(hs_dir, "01.Ly_lich_nguoi_xin_vao_Dang.pdf"))
    gp = w.sign
    w._show_tab(gp)
    gp.set_files(SCN.scan(cb).files, cb, "test")
    gdir = os.path.join(work, "gom_test", "Gom")
    gp.ed_dir.setText(gdir); gp.ed_dir.textEdited.emit(gdir); gp.refresh()      # người dùng tự gõ thư mục gom
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes if "Tiếp tục" in a[2] or "Hoàn tác" in a[1]
                                        else QMessageBox.No)
    gp.gather()
    assert pump(app, lambda: not gp.running and gp.journal is not None, 30), "gom timeout"
    gathered = sorted(n for n in os.listdir(gdir) if n.endswith(".pdf"))
    assert gathered == ["01.Ly_lich_nguoi_xin_vao_Dang_056123456789_TranVanThai.pdf",
                        "01.Ly_lich_nguoi_xin_vao_Dang_079111222333_LeThiChuyen.pdf"], gathered
    SG.BUSY_SECONDS = 0                                           # file test vừa tạo – không coi là "đang ký"
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from make_signed_sample import sign_pdf
    # chỉ đổi tên .signed (không ký thật) → KHÔNG được nhận
    shutil.copy(os.path.join(gdir, gathered[0]), os.path.join(gdir, gathered[0][:-4] + ".signed.pdf"))
    gp.rb_back.setChecked(True)                                   # cách 1: trả về thư mục hồ sơ gốc
    gp.check_return()                                             # chạy ở luồng phụ → chờ xong
    assert pump(app, lambda: not gp.running, 30), "kiểm tra trả về timeout"
    assert not gp.btn_return.isEnabled() and "không có chữ ký thật" in gp.lbl.text(), gp.lbl.text()
    gp.ck_issue.setChecked(True)
    assert gp.view_rows() == 1, gp.view_rows()                    # lọc "chỉ dòng cần xử lý"
    gp.ck_issue.setChecked(False)
    os.remove(os.path.join(gdir, gathered[0][:-4] + ".signed.pdf"))
    sign_pdf(os.path.join(gdir, gathered[0]), os.path.join(gdir, gathered[0][:-4] + ".signed.pdf"), "TRAN VAN THAI")
    assert pump(app, lambda: not gp.running and gp.btn_return.isEnabled(), 30), gp.lbl.text()   # tự cập nhật
    assert "Đã ký hợp lệ 1 / 2" in gp.lbl_mode.text(), gp.lbl_mode.text()
    gp.ed_search.setText("lethi")                                 # tìm không dấu
    assert pump(app, lambda: gp.view_rows() == 1, 5), gp.view_rows()
    gp.ed_search.setText("")
    assert pump(app, lambda: gp.view_rows() == 3, 5), gp.view_rows()
    gp.do_return()
    assert pump(app, lambda: not gp.running and gp.journal_kind == "return", 30), "trả về timeout"
    assert pump(app, lambda: not w.busy, 60)
    signed = os.path.join(cb, "056123456789_TranVanThai", "01.Ly_lich_nguoi_xin_vao_Dang.signed.pdf")
    assert os.path.isfile(signed)
    assert sorted(n for n in os.listdir(gdir) if n.endswith(".pdf")) == [gathered[1]]     # người chưa ký: giữ lại
    gp.undo()
    assert pump(app, lambda: not gp.running and gp.journal is None, 30), "hoàn tác timeout"
    assert not os.path.exists(signed) and len([n for n in os.listdir(gdir) if n.endswith(".pdf")]) == 3
    # cách 2: chép ra thư mục mới (cùng cây CCCD_HoVaTen, bỏ đuôi), hồ sơ gốc + thư mục gom không đổi
    out_new = os.path.join(work, "gom_test", "Da ky")
    assert pump(app, lambda: not w.busy, 60)                     # hoàn tác trả về → app tự quét lại
    gp.rb_copy.setChecked(True)
    gp.check_return()                                            # quét lại xong tab về xem gom → bấm Kiểm tra
    assert pump(app, lambda: not gp.running, 30)
    assert gp.out_dir() == cb + " - Đã ký", gp.out_dir()           # tự đặt theo sổ ghi (chưa tự chọn)
    gp.ed_out.setText(out_new); gp.ed_out.textEdited.emit(out_new); gp._out_changed()   # người dùng gõ thư mục khác
    assert pump(app, lambda: not gp.running and "Chép ra thư mục mới" in gp.lbl_mode.text(), 30), gp.lbl.text()
    src_before = sorted(os.listdir(os.path.join(cb, "056123456789_TranVanThai")))
    gp.do_return()
    assert pump(app, lambda: not gp.running and gp.journal_kind == "copy", 30), "chép ra thư mục mới timeout"
    got = sorted(os.listdir(os.path.join(out_new, "056123456789_TranVanThai")))
    assert got == ["01.Ly_lich_nguoi_xin_vao_Dang.pdf", "01.Ly_lich_nguoi_xin_vao_Dang.signed.pdf"], got
    assert sorted(os.listdir(os.path.join(cb, "056123456789_TranVanThai"))) == src_before
    assert len([n for n in os.listdir(gdir) if n.endswith(".pdf")]) == 3
    # nhật ký hoàn tác lưu ra file → mở lại tab (như mở lại app) vẫn hoàn tác được
    from pdfread_pro.ui.sign_panel import SignPanel, _journal_path
    assert os.path.isfile(_journal_path())
    gp2 = SignPanel()
    assert gp2.journal is not None and gp2.journal_kind == "copy" and gp2.btn_undo.isEnabled()
    gp2.deleteLater()
    # tách file cần ký lại: người chưa ký → "Ký lại …"
    assert pump(app, lambda: not gp.running and gp.btn_regroup.isEnabled(), 30), gp.lbl.text()
    gp.do_regroup()
    assert pump(app, lambda: not gp.running and gp.journal_kind == "regroup", 30), "tách file timeout"
    redo = [d for d in os.listdir(gdir) if d.startswith(SG.REDO_DIR)]
    assert redo and os.listdir(os.path.join(gdir, redo[0])) == [gathered[1]], redo
    # xuất Excel
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(work, "gom_test", "kq.xlsx"), ""))
    assert pump(app, lambda: not gp.running and gp.btn_excel.isEnabled(), 30)
    gp.export_excel()
    assert pump(app, lambda: os.path.isfile(os.path.join(work, "gom_test", "kq.xlsx")), 30), "xuất Excel"
    gp.undo()                                                     # hoàn tác tách → file về chỗ cũ
    assert pump(app, lambda: not gp.running and gp.journal is None, 30)
    assert gathered[1] in os.listdir(gdir)
    print("gom ký số: OK –", gp.lbl.text()[:80])
    # thư mục gom lớn (3.000 file): kiểm tra trả về không được làm đứng giao diện (đo khoảng nghỉ lớn nhất của vòng lặp)
    big = os.path.join(work, "gom_test", "Gom lon")
    os.makedirs(big)
    for i in range(1500):
        for tail in ("", ".signed"):
            with open(os.path.join(big, f"{i:04d}.Giay_to_056123456789_TranVanThai{tail}.pdf"), "wb") as fh:
                fh.write(b"%PDF x")
    from PySide6.QtCore import QElapsedTimer, QTimer
    gaps, clk = [0], QElapsedTimer()
    tick = QTimer()
    tick.timeout.connect(lambda: (gaps.append(clk.restart())))
    gp.rb_back.setChecked(True)
    gp.ed_dir.setText(big)
    clk.start(); tick.start(10)
    gp.check_return()
    assert pump(app, lambda: not gp.running and gp.view_rows() == 3000, 60), gp.lbl.text()
    tick.stop()
    print(f"kiểm tra trả về 3.000 file (kèm đọc chữ ký): khựng lớn nhất {max(gaps)} ms")
    assert max(gaps) < 700, max(gaps)
    gp.ed_dir.setText(gdir); gp.rb_copy.setChecked(True)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

    # --- nhớ cài đặt khi tắt app, khôi phục cài đặt gốc
    sp.cards["a4_to_a4"].click()
    w.compress.sp.setValue(321); w.compress.ck_clean.setChecked(False); w.check.ck_blank.setChecked(True)
    w.report.ed_req.setText("01-07"); w.report.ed_req.editingFinished.emit()
    w.close()
    w2 = MainWindow()
    assert w2.compress.sp.value() == 321 and not w2.compress.ck_clean.isChecked() and w2.check.ck_blank.isChecked()
    assert w2.split.cb_preset.currentData() == "a4_to_a4" and w2.split.cards["a4_to_a4"].isChecked()
    assert w2.report.ed_req.text() == "01-07"
    w2.reset_settings()
    assert w2.compress.sp.value() == 250 and w2.compress.ck_clean.isChecked() and not w2.check.ck_blank.isChecked()
    assert w2.split.cb_preset.currentData() == "a3_to_a4" and w2.report.ed_req.text() == "01-05"
    from PySide6.QtCore import QSettings
    assert not [k for k in QSettings("PDFReadPro", "PDFReadPro").allKeys() if k.startswith("ui/")]
    print("lưu / khôi phục cài đặt: OK")
    print("ALL OK")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
