"""Kiểm thử tích hợp giao diện (offscreen) trên BẢN SAO dữ liệu mẫu. Chạy: py tests/integration_gui.py"""
import os, sys, shutil, tempfile, time, warnings
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
    from PIL import Image
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
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
    assert os.path.exists(xlsx)
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
    assert os.path.exists(out_cmp)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    cp.do_rename()
    assert pump(app, lambda: not w.busy)
    assert cp.cmp.count(CP.K_NAME) == 0 and cp.cmp.count(CP.K_TYPO) == 0, (cp.cmp.count(CP.K_NAME), cp.cmp.count(CP.K_TYPO))
    cp.undo()
    assert pump(app, lambda: not w.busy)
    assert cp.cmp.count(CP.K_NAME) == 1
    print("compare:", {k: cp.cmp.count(k) for k in CP.KIND_ORDER})
    print("ALL OK")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
