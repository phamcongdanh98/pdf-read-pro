"""Điểm khởi chạy PDF-Read Pro."""
import multiprocessing
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def selftest(out_path: str) -> int:
    """Tự kiểm tra các thành phần lõi (chạy được cả trong exe đóng gói)."""
    import io
    import shutil
    import tempfile
    import traceback
    from concurrent.futures import ProcessPoolExecutor

    lines, ok = [], True
    try:
        from PIL import Image
        from pdfread_pro.core import compressor as C, scanner, stats, renamer as R
        import pymupdf
        work = tempfile.mkdtemp()
        sub = os.path.join(work, "A")
        os.makedirs(sub)
        ims = [Image.effect_noise((1400, 1900), 60).convert("RGB") for _ in range(2)]
        pdf = os.path.join(sub, "01.scan.pdf")
        ims[0].save(pdf, save_all=True, append_images=ims[1:], quality=95)
        res = scanner.scan(work)
        lines.append(f"scan: {len(res.files)} file, {res.files[0].pages} trang")
        ok &= len(res.files) == 1 and res.files[0].pages == 2
        with ProcessPoolExecutor(max_workers=2) as ex:
            r = ex.submit(C.job_compress, (pdf, pdf, 200, False)).result()
        lines.append(f"compress (tiến trình con): {r.status} {r.before} -> {r.after}")
        ok &= r.status == C.ST_COMPRESSED and r.after < r.before
        doc = pymupdf.open(pdf)
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(0.3, 0.3))
        lines.append(f"render: {pix.width}x{pix.height}")
        ok &= pix.width > 0
        rs = R.new_ruleset()
        rs["template"] = "{n:2}.{stem}"
        it = R.build_preview(scanner.scan(work).files, rs)[0]
        lines.append(f"rename preview: {it.fi.name} -> {it.new_name}")
        ok &= it.new_name == "01.01.scan.pdf"
        from pdfread_pro.core import rules1361
        rules = rules1361.default_rules()
        it2 = R.build_preview_1361(scanner.scan(work).files, rules)[0]
        lines.append(f"bộ quy tắc 1361: {len(rules)} quy tắc · {it2.fi.name} -> {it2.new_name}")
        ok &= len(rules) >= 104 and it2.new_name == "01.Ly_lich_nguoi_xin_vao_Dang.pdf"
        from pdfread_pro.core import splitter
        sres = splitter.build(splitter.open_source(pdf), splitter.SplitOptions(page_size="a4"))
        sp_out = splitter.save(sres, pdf, splitter.default_output(pdf))
        lines.append(f"tách trang: 2 trang → {sres.doc.page_count} trang A4 · {os.path.basename(sp_out)}")
        ok &= sres.doc.page_count == 4 and os.path.exists(sp_out)
        from pdfread_pro.core import pagenum
        if pagenum.available():
            d = pymupdf.open()
            pg = d.new_page(width=420, height=595)
            pg.insert_text((50, 100), "Ho va ten khai sinh Nguyen Van A", fontsize=12)
            pg.insert_text((205, 575), "- 7 -", fontsize=11)
            pix = pg.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
            n = pagenum.read_pages([Image.frombytes("L", (pix.width, pix.height), pix.samples)], 20)[0]
            lines.append(f"đọc số trang (Windows OCR): {n}")
            ok &= n == (7, None)
        else:
            lines.append("đọc số trang: máy không có Windows OCR – bỏ qua")
        from pdfread_pro.core import report as RP, scanner as SC
        from pdfread_pro.core.report_excel import export_excel
        hs = os.path.join(work, "Ho so so hoa", "Chi bo 1", "056123456789_PhamVanA")
        os.makedirs(hs)
        for name in list(rules.values())[:5]:
            shutil.copy(pdf, os.path.join(hs, name + ".pdf"))
        rep = RP.build_report(SC.scan(os.path.join(work, "Ho so so hoa")), rules)
        xl = export_excel(rep, os.path.join(work, "bao_cao.xlsx"))
        lines.append(f"báo cáo hồ sơ: {len(rep.dossiers)} hồ sơ · {rep.dossiers[0].status} · {os.path.basename(xl)}")
        ok &= rep.dossiers[0].status == RP.ST_OK and os.path.getsize(xl) > 5000
        from openpyxl import Workbook
        from pdfread_pro.core import compare as CP
        wbx = Workbook()
        wbx.active.append(["STT", "Họ và tên", "Số CCCD", "Chi bộ"])
        wbx.active.append([1, "Phạm Văn A", 56123456789, "Chi bộ 1"])
        wbx.active.append([2, "Lê Thị B", "056000000001", "Chi bộ 1"])
        xs = os.path.join(work, "ds.xlsx")
        wbx.save(xs)
        tb = CP.read_table(xs)
        cm = CP.compare(tb, CP.guess_columns(tb.headers), rep)
        lines.append(f"đối chiếu danh sách: khớp {cm.count(CP.K_MATCH)} · chưa có thư mục {cm.count(CP.K_NO_FOLDER)}")
        ok &= cm.count(CP.K_MATCH) == 1 and cm.count(CP.K_NO_FOLDER) == 1
        shutil.rmtree(work, ignore_errors=True)
    except Exception:
        ok = False
        lines.append(traceback.format_exc())
    lines.append("SELFTEST " + ("OK" if ok else "FAIL"))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(os.linesep.join(lines))
    return 0 if ok else 1


def main() -> int:
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication
    from pdfread_pro import paths
    from pdfread_pro.ui.main_window import MainWindow
    from pdfread_pro.ui.styles import apply_light_palette, full_style

    if sys.platform == "win32":
        try:                                 # để thanh taskbar hiện icon của app thay vì icon Python/Qt mặc định
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PDFReadPro.App")
        except (AttributeError, OSError):
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(paths.APP_NAME)
    if os.path.isfile(paths.icon_path()):
        app.setWindowIcon(QIcon(paths.icon_path()))
    app.setStyle("Fusion")
    apply_light_palette(app)
    font = QFont("Segoe UI")
    font.setPointSizeF(9.5)
    app.setFont(font)
    app.setStyleSheet(full_style())
    win = MainWindow()
    win.showMaximized()
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        win.path_edit.setText(os.path.normpath(sys.argv[1]))
        win.start_scan()
    return app.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2]))
    try:
        sys.exit(main())
    except Exception:
        import traceback
        from pdfread_pro import paths
        with open(paths.data_file("error.log"), "w", encoding="utf-8") as fh:
            fh.write(traceback.format_exc())
        raise
