"""Test giao diện tab Quy trình 1 click (offscreen, tự tạo dữ liệu): quét → chạy → kết quả → sang tab Gom ký số → trả về."""
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
sys.path.insert(0, HERE)

A, B = "056123456789_TranVanThai", "079111222333_LeThiChuyen"


def pump(app, cond, timeout=120):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return cond()


def main():
    from PySide6.QtCore import Qt, QElapsedTimer, QTimer
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from pdfread_pro.ui import theme as TH, styles as ST
    TH.install()
    from pdfread_pro.core import signgather as G, tools
    from pdfread_pro.ui.main_window import MainWindow
    from test_pipeline import heavy_pdf, text_pdf, tree_hash
    from make_signed_sample import sign_pdf

    G.BUSY_SECONDS = 0
    __import__('pdfread_pro.paths', fromlist=['x']).make_settings().clear()
    work = tempfile.mkdtemp()
    src = os.path.join(work, "Ho so")
    a, b = os.path.join(src, "Chi bo 1", A), os.path.join(src, "Chi bo 1", B)
    heavy_pdf(os.path.join(a, "03 phieu dang vien.pdf"))
    text_pdf(os.path.join(a, "1.ly lich.pdf"))
    text_pdf(os.path.join(a, "xyz_lung_tung.pdf"))
    text_pdf(os.path.join(a, "t.pdf"), 2)
    sign_pdf(os.path.join(a, "t.pdf"), os.path.join(a, "05.QD_ket_nap_dang_vien.signed.pdf"), "TEST")
    os.remove(os.path.join(a, "t.pdf"))
    text_pdf(os.path.join(b, "02 ly lich dang vien.pdf"), 3)
    before = tree_hash(src)

    app = QApplication([])
    ST.set_theme(app, "light")
    asked, warned = [], []
    QMessageBox.question = staticmethod(lambda *x, **k: (asked.append(x[1]), QMessageBox.Yes)[1])
    QMessageBox.warning = staticmethod(lambda *x, **k: (warned.append(x[2]), QMessageBox.Ok)[1])
    QMessageBox.information = staticmethod(lambda *x, **k: QMessageBox.Ok)
    tools.delete_dir = lambda d, permanent=False: (shutil.rmtree(d, ignore_errors=True), (True, "ok"))[1]

    w = MainWindow()
    w.resize(1500, 900)
    w.show()
    pp = w.pipeline
    w._show_tab(pp)
    assert not pp.btn_run.isEnabled(), "chưa quét mà nút chạy đã bật"
    w.path_edit.setText(src)
    w.start_scan()
    assert pump(app, lambda: not w.busy and w.result is not None), "quét timeout"
    assert pp.btn_run.isEnabled() and "6 file PDF" in pp.lbl_src.text() or "file PDF" in pp.lbl_src.text(), pp.lbl_src.text()
    assert pp.ed_work.text().endswith(" - Quy trình") and pp.ed_gather.text().endswith("Gom ký số"), pp.ed_work.text()
    assert "1361" in pp.lbl_rule.text(), pp.lbl_rule.text()

    # --- giao diện gọn: khung xem trước gập (tự mở khi chọn file), ô thư mục có nút ✕, thanh thư mục ẩn ở tab Hướng dẫn
    from PySide6.QtWidgets import QSplitter
    w._show_tab(w.compress); pump(app, lambda: False, 0.3)
    spl = [x for x in w.compress.findChildren(QSplitter) if x.orientation() == Qt.Horizontal][0]
    assert spl.sizes()[1] == 0, spl.sizes()                                  # mặc định gập
    w.compress.preview.shown.emit(); pump(app, lambda: False, 0.2)
    assert spl.sizes()[1] > 0, spl.sizes()                                   # chọn file → tự mở
    assert w.cfg.isVisibleTo(w) and w.path_edit.isClearButtonEnabled()
    w.show_help(); assert not w.cfg.isVisibleTo(w)
    w._show_tab(pp); assert w.cfg.isVisibleTo(w)

    # --- kiểm tra trước chặn khi thư mục làm việc nằm trong hồ sơ gốc
    good_work, good_gather = pp.ed_work.text(), pp.ed_gather.text()
    pp.ed_work.setText(os.path.join(src, "lam viec")); pp.ed_work.textEdited.emit("x")
    pp.start()
    assert pump(app, lambda: not pp.running, 30)
    assert warned and "trùng / lồng" in warned[-1], warned
    assert not os.path.exists(os.path.join(src, "lam viec")) and tree_hash(src) == before
    pp.ed_work.setText(good_work); pp.ed_gather.setText(good_gather)
    pp._work_auto = pp._gather_auto = True                                  # quay lại tên tự đặt

    # --- chạy thật (đo giao diện không bị đứng)
    gaps, clk = [0], QElapsedTimer()
    tick = QTimer()
    tick.timeout.connect(lambda: gaps.append(clk.restart()))
    clk.start(); tick.start(10)
    asked.clear()
    pp.start()
    assert pump(app, lambda: pp.rep is not None and not pp.running, 180), pp.lbl.text()
    tick.stop()
    rep = pp.rep
    print("khựng lớn nhất khi chạy:", max(gaps), "ms")
    assert "Xác nhận chạy quy trình" in asked, asked
    assert rep.ok, (rep.error, [(s.name, s.status, s.summary) for s in rep.stages])
    assert tree_hash(src) == before, "HỒ SƠ GỐC BỊ ĐỔI!"
    assert os.path.isdir(rep.cfg.work) and os.path.isdir(rep.cfg.gather)
    assert sorted(n for n in os.listdir(rep.cfg.gather) if n.endswith(".pdf")) == [
        f"01.Ly_lich_nguoi_xin_vao_Dang_{A}.pdf", f"02.Ly_lich_dang_vien_{B}.pdf",
        f"03.Phieu_dang_vien_{A}.pdf", f"xyz_lung_tung_{A}.pdf"]
    assert pp.model.rowCount() == 5 and pp.view_rows() == 5, pp.model.rowCount()
    assert all("✔" in lb.text() or "⚠" in lb.text() for lb in pp.step_lbl), [lb.text() for lb in pp.step_lbl]
    pp.ck_issue.setChecked(True)
    assert pump(app, lambda: pp.view_rows() == 1, 5), pp.view_rows()        # chỉ xyz_lung_tung (giữ tên cũ)
    pp.ck_issue.setChecked(False)
    for btn in (pp.btn_open_g, pp.btn_open_w, pp.btn_excel, pp.btn_sign, pp.btn_del):
        assert btn.isEnabled(), btn.text()
    print("kết quả:", pp.lbl.text()[:140])

    # --- Excel
    QFileDialog.getSaveFileName = staticmethod(lambda *x, **k: (os.path.join(work, "kq.xlsx"), ""))
    pp.export_excel()
    assert pump(app, lambda: os.path.isfile(os.path.join(work, "kq.xlsx")), 30), "xuất Excel"

    # --- bàn giao sang tab Gom ký số, "ký" giả lập rồi chép ra thư mục mới
    pp.to_sign()
    sg = w.sign
    assert pump(app, lambda: not sg.running and sg.mode == "return" and sg.model.rowCount() > 0, 30), sg.lbl.text()
    assert w.tabs.currentWidget().widget() is sg
    assert sg.gather_dir() == os.path.normpath(rep.cfg.gather)
    assert sg.out_dir() == os.path.normpath(rep.cfg.work + " - Đã ký")
    # giao diện 2 bước: đang ở bước ② → chỉ thấy thiết lập + nút của bước ②
    assert sg.card_return.isChecked() and not sg.card_gather.isChecked()
    assert sg.pg_return.isVisibleTo(sg) and not sg.pg_gather.isVisibleTo(sg)
    assert sg.btn_return.isVisibleTo(sg) and sg.btn_check.isVisibleTo(sg) and not sg.btn_gather.isVisibleTo(sg)
    sg.card_gather.click()                                                    # người dùng bấm thẻ ① → về bước gom
    assert pump(app, lambda: sg.mode == "gather" and sg.btn_gather.isVisibleTo(sg), 10)
    assert sg.pg_gather.isVisibleTo(sg) and not sg.pg_return.isVisibleTo(sg) and not sg.btn_return.isVisibleTo(sg)
    sg.card_return.click()                                                    # rồi bấm thẻ ② → kiểm tra lại
    assert pump(app, lambda: sg.mode == "return" and not sg.running and sg.model.rowCount() > 0, 30), sg.lbl.text()
    n_all = sg.view_rows()
    sg.cb_show.setCurrentIndex(sg.cb_show.findData("issue"))                  # chưa ký thật nên chưa có lỗi nào
    assert pump(app, lambda: sg.view_rows() == 0, 5), sg.view_rows()
    sg.cb_show.setCurrentIndex(sg.cb_show.findData("todo"))                   # chưa có bản ký → chưa có việc để làm
    assert pump(app, lambda: sg.view_rows() == 0, 5), sg.view_rows()
    sg.cb_show.setCurrentIndex(0)
    assert pump(app, lambda: sg.view_rows() == n_all, 5)
    g = rep.cfg.gather
    sign_pdf(os.path.join(g, f"01.Ly_lich_nguoi_xin_vao_Dang_{A}.pdf"),
             os.path.join(g, f"01.Ly_lich_nguoi_xin_vao_Dang_{A}.signed.pdf"), "TEST")
    sg.check_return()
    assert pump(app, lambda: not sg.running and sg.btn_return.isEnabled(), 60), sg.lbl.text()
    sg.cb_show.setCurrentIndex(sg.cb_show.findData("todo"))                   # giờ đã có bản ký → có việc sẽ làm
    assert pump(app, lambda: sg.view_rows() > 0, 5), sg.view_rows()
    assert "Sẵn sàng" in sg.lbl.text(), sg.lbl.text()
    sg.cb_show.setCurrentIndex(0)
    # thư mục mới tự điền không trùng: thư mục “… - Đã ký” đã có file → tự thêm (2); không đổi khi kiểm tra lại
    first = sg.out_dir()
    os.makedirs(first, exist_ok=True)
    open(os.path.join(first, "x.txt"), "w").close()
    sg._out_base = ""
    sg._auto_out(rep.cfg.work)
    assert sg.out_dir() == first + " (2)", sg.out_dir()
    sg._auto_out(rep.cfg.work)
    assert sg.out_dir() == first + " (2)"
    os.remove(os.path.join(first, "x.txt"))
    sg.ed_out.setText(first); sg._out_base = rep.cfg.work                    # quay lại thư mục trống như cũ
    # xác nhận ghi rõ số hồ sơ + dung lượng và cảnh báo hồ sơ chưa ký (mặc định “Không”)
    asked.clear(); defaults = []
    QMessageBox.question = staticmethod(lambda *x, **k: (asked.append(x[2]), defaults.append(x[4] if len(x) > 4 else None),
                                                         QMessageBox.Yes)[2])
    sg.do_return()
    assert any("hồ sơ," in t and "chưa có bản ký" in t for t in asked), asked
    assert defaults and defaults[0] == QMessageBox.No, defaults
    assert pump(app, lambda: not sg.running and sg.journal_kind == "copy", 60), "chép ra thư mục mới"
    out = sg.out_dir()
    got = sorted(os.listdir(os.path.join(out, "Chi bo 1", A)))          # giữ đúng cây Chi bộ\CCCD_HoVaTen
    assert "01.Ly_lich_nguoi_xin_vao_Dang.signed.pdf" in got and "01.Ly_lich_nguoi_xin_vao_Dang.pdf" in got, got
    assert tree_hash(src) == before, "HỒ SƠ GỐC BỊ ĐỔI sau khi trả về!"
    assert not sg.btn_stop.isVisibleTo(sg), "nút Dừng phải ẩn khi không chạy"

    # --- chạy lần 2: tên thư mục tự thêm (2), không ghi chồng lên kết quả cũ
    w._show_tab(pp)
    w.start_scan()
    assert pump(app, lambda: not w.busy)
    assert pp.ed_work.text().endswith("(2)"), pp.ed_work.text()
    # --- xoá kết quả (làm lại)
    pp.rep = rep
    pp._enable()
    pp.delete_results()
    assert not os.path.exists(rep.cfg.work) and not os.path.exists(rep.cfg.gather) and tree_hash(src) == before
    assert pp.rep is None

    # --- dừng giữa chừng: hồ sơ gốc không đổi, các bước sau không chạy
    pp.start()
    assert pump(app, lambda: pp.thread is not None, 30), "chưa bắt đầu chạy"
    pp.stop()
    assert pump(app, lambda: pp.rep is not None and not pp.running, 120)
    assert tree_hash(src) == before and (pp.rep.cancelled or pp.rep.ok)
    print("dừng giữa chừng:", "đã dừng" if pp.rep.cancelled else "kịp chạy xong", "· gốc nguyên vẹn")

    # --- đóng app khi đang chạy bị chặn
    w.close()
    shutil.rmtree(work, ignore_errors=True)
    print("ALL OK")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
