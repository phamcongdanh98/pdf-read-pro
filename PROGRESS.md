# Tiến độ dự án
_Cập nhật: 28/10/2026 22:00_

## Đang làm dở
- v1.9.1 (Kiểm tra trang: nhận dạng trắng / đen / mờ / khổ lệch / trùng + nút Xoá trang ở mọi khung xem trước) đã code + test xong, **chưa commit** (v1.9.0 đã push `60fe8e8`).
- v1.9.0 (tab **Quy trình 1 click**) đã code + test xong, **chưa commit** (v1.8.0 là commit `f389894` đã push).
  Cùng đợt có sửa: chọn nhầm thư mục hồ sơ làm thư mục gom (hỏi + tự quét), bộ lọc không còn nhớ/che bảng,
  sổ gom ghi thư mục gốc (`root`) để chép ra thư mục mới giữ đúng cây Chi bộ.

## Bước tiếp theo
0. Người dùng thử tab **Quy trình** trên hồ sơ thật (nhớ cần chỗ trống ≈ dung lượng hồ sơ cho bản chép); ổn → commit + push v1.9.0.
1. Thử tab Gom ký số với **phần mềm ký thật** (vài file): bản ký thật phải được nhận "✔ ký bởi …"; nếu bị báo
   "không có chữ ký thật" → lấy 1 file mẫu để chỉnh `core/signgather.py` / `core/signature.py`.
2. Thử với bộ test `HoSoSoHoa_Test\…Gom ký số (test 3 - ký giả lập)` (4 lỗi mẫu ở Chi bộ 01), chọn thư mục mới riêng.
3. Gửi bản zip portable lên VirusTotal kiểm tra lại; nếu Microsoft vẫn báo nhầm → gửi false-positive cho Microsoft.
4. (Tuỳ chọn) chọn giữ 1 kiểu build (onefile hay onedir) trong `build.py`.

## Nhật ký (mới nhất ở trên)
- 29/10 — Yêu cầu (5 mục): chọn cột hiển thị; tô cả hàng; bỏ «Cắt mọi trang» + hoàn tác; chuột phải theo dòng (cập nhật tay + tuỳ biến); `_backup_goc` không được nằm trong thư mục hồ sơ. Đã làm: `ui/tablekit.py` (chọn cột, menu dòng), `FilterBar.attach_columns`, `check/compress/rename/trash/overview` dùng; `check(rows, force)`, `fix(rows)`, `analyze/compress(rows)`; `trash.backup_root/backup_path_for/find_backup/make_backup/migrate_legacy` + `config.json` (đọc được từ tiến trình con); mọi chỗ ghi `_backup_goc` (pagecheck, compressor, splitter) đổi sang nơi sao lưu của app; menu 🧰 «Dọn thư mục _backup_goc cũ». Lưu ý test: tiến trình con (spawn) chạy lại đầu file test → APPDATA tạm phải qua biến PDFREAD_TEST_APPDATA, nếu không con ghi sang thư mục khác.
- 29/10 — Yêu cầu (5 mục): màu trạng thái; nút xoá trang xoá luôn (tuỳ chọn đánh dấu); tô dòng đã xử lý; hỏi «Bản gốc/Bản đã sửa» dùng được không; thùng rác thành tab. Đã làm: `STATUS_STYLE` + `_set_status/_tint_row` (check_panel), `PreviewPane.delete_pages_direct` + tín hiệu `pageDeleted/cropped`, ô «Nút 🗑 / Delete» + nút 🗑 Xoá ngay, `handled/fixed/_keep`, `MainWindow._file_edited` cập nhật tại chỗ (không rescan), `TrashPanel` (tab) thay hộp thoại. SỰ CỐ: test GUI cũ gọi `QSettings(...).clear()` nên đã xoá cài đặt thật trong Registry → thêm `paths.make_settings()` + biến `PDFREADPRO_SETTINGS_INI` (test dùng file .ini tạm), đã khôi phục last_folder + confirm_delete.
- 29/10 — Yêu cầu (6 mục): chữ to + đậm hơn; thùng rác kiểu Hồ sơ 1361; xoá trang không cần xác nhận (tuỳ chọn); nút Clear; bảng trang không cuộn được; cắt viền kéo khung. Đã làm: `styles.set_font/load_font_settings` + nút Aa (mặc định 112% + đậm); `core/trash.py` (mục JSON riêng lẻ → nhiều tiến trình không tranh chấp; kind pages / backup / file) gắn vào fix_file, delete_pages, compressor, splitter, crop; `ui/trash_dialog.py`; `PreviewPane`: ô «Hỏi xác nhận», thanh Hoàn tác, chế độ ✂ Cắt viền (`_CropOverlay`) + `pagecheck.crop_pages/get_cropboxes/set_cropboxes` (CropBox, đã kiểm chứng bằng pixel với 4 hướng xoay trang); nút 🧹 Làm sạch; `ptable` không còn bị khoá khi đang chạy (nguyên nhân lỗi cuộn chuột: widget bị setEnabled(False)). Test: `test_trash.py` (9), `gui_pagecheck.py` (+28 kiểm tra).
- 28/10 — Yêu cầu: tăng tốc quét / kiểm tra trang mà vẫn chuẩn. Nghiên cứu (dữ liệu thật 881 file/4.705 trang): quét 0,25 ms/file CPU – chỉ phụ thuộc đọc đĩa; kiểm tra trang ≈ OCR 63% + vẽ 27% + đo 10%. Đã làm: `pagenum.page_infos(concurrency)` (nhóm engine OCR, đọc song song, kết quả y hệt tuần tự), tab Kiểm tra dùng nhiều tiến trình hơn (trước tối đa 4) × 2–6 trang song song, bộ nhớ đệm kết quả `check_cache.pkl` (khoá: kích thước + mtime_ns + phiên bản thuật toán). Đo: 76 → 37 ms/trang (×2,1). Đã thử và BỎ: giải mã JPEG nhanh bằng PIL draft (khác kết quả OCR ở ~12% trang), rút gọn đọc hướng (bỏ lần OCR bị lật: không an toàn vì chữ rác khi lật vẫn tới 640 chữ).
- 28/10 — Yêu cầu: chọn từng kiểm tra (trắng, đen, lệch, ngược…) + thanh Hiển thị/Sắp xếp cho mọi tab. Đã làm: `pagecheck` tham số `checks` (CHECK_KEYS) + `check_file(ocr, blur)` (bỏ OCR khi chỉ kiểm tra nội dung), tab Kiểm tra có 7 ô tích + Chọn nhanh, kết quả cũ thiếu OCR báo "cần kiểm tra lại"; `ui/filterbar.py` (FilterBar: lọc + sắp xếp qua moveSection, chỉ số dòng giữ nguyên) gắn vào Đổi tên, Nén PDF, Kiểm tra trang; Tổng quan dùng cùng thanh (cây có `_SortItem`). Quy trình / Gom ký số / Báo cáo / Đối chiếu đã có bộ lọc riêng (chưa có ô Sắp xếp). Test: test_pagecheck 15, gui_pagecheck.
- 28/10 — Yêu cầu: tab Kiểm tra trang chuẩn hơn (quan tâm nhất trang trắng + đen gần hết trang) + nút xoá trang ở mọi tab có xem trước. Đã làm: `pagecheck.analyze_page/classify/_quality/delete_pages` (đo ảnh xám 0,5×: mực theo màu nền, % tối, độ chi tiết, độ nét 150 dpi, khổ giấy, dấu vân tay chữ+ảnh), tuỳ chọn Bỏ trang đen + ngưỡng, cột Nội dung, bộ lọc, Chọn nhanh, đánh dấu xoá (nút / Delete / chuột phải), `PreviewPane.btn_del` (tab Kiểm tra: đánh dấu; tab khác: hỏi → sao lưu → xoá → quét lại), test `test_pagecheck` (+6) và `tests/gui_pagecheck.py`. Lý do chọn dấu vân tay chữ+ảnh cho "trùng": so ảnh thu nhỏ báo nhầm các trang cùng mẫu khác chữ.
- 28/10 — Yêu cầu: sửa treo ~1 phút sau khi chép (kiểm tra lại so từng byte → so size + ngày sửa, 2,8 s với 6.903 file) và thêm chống sai sót: thư mục mới tự đặt không trùng, đối chiếu sau chép + tóm tắt, cảnh báo hồ sơ chưa ký (mặc định Không), xác nhận ghi số hồ sơ/dung lượng, nút ⏹ Dừng. Đã làm: `signgather.verify_copy/describe`, `sign_panel` (_auto_out, _confirm, _pending_text, stop_op), test.
- 28/10 — Yêu cầu: tab Gom ký số dễ thao tác, bớt rối + rà cải thiện chung. Đã làm: viết lại giao diện `ui/sign_panel.py`
  theo 2 bước (2 thẻ ①/②, chỉ hiện thiết lập của bước đang làm, "Tuỳ chọn nâng cao" gập, 1 nút chính, "⋯ Thêm" cho việc
  phụ, bảng 4 cột có biểu tượng, tóm tắt màu ✔⏳⚠, ô "Hiện" thay 2 ô tích, gợi ý bước tiếp theo); xếp lại thứ tự tab theo
  trình tự làm việc. Logic không đổi (81 test + `tests/gui_pipeline.py` đạt). Thử đổi cột bảng Đổi tên/Nén/Kiểm tra sang
  tự giãn → tệ hơn trên cửa sổ vừa nên đã hoàn lại.
- 28/10 — Yêu cầu: quy trình 1 click Đổi tên → Giảm dung lượng 250 KB/trang → Gom ký số, tab riêng, kiểm tra kỹ tránh lỗi.
  Đã làm: `core/pipeline.py` (kiểm tra trước, chép bản làm việc, đổi tên, nén có xác minh + khôi phục từ gốc, gom, `_guard`
  chặn ghi vào hồ sơ gốc), `core/pipeline_excel.py`, `ui/pipeline_panel.py`, 11 unit test + test giao diện + selftest exe.
  Lý do chọn làm trên bản chép: đổi tên + nén sửa file thật, bản chép giữ hồ sơ gốc an toàn tuyệt đối (người dùng chọn).
- 27/10 — Yêu cầu: tối ưu + chống lỗi Gom ký số. Đã làm: kiểm tra chữ ký số thật + số trang bản ký, phát hiện file
  đang ghi / bản gốc đổi / trùng tên hồ sơ, đường dẫn dài, chép qua .part + kiểm tra dung lượng, hoàn tác lưu ra file;
  chia lô, tự cập nhật khi ký, tìm kiếm + lọc (bảng ảo), tách file cần ký lại, xuất Excel, nhận nhiều kiểu tên bản ký.
  Lý do: tránh nộp hồ sơ có file chưa ký thật / ký nhầm.
- 27/10 — Kiểm tra trả về chạy nền (13 s đứng máy → 0,3 s, O(n²) → O(n)); không cần quét vẫn trả về được (suy thư mục
  gốc từ sổ ghi); sổ `_gom_ky_so.json` được ẩn.
- 27/10 — Tab Gom ký số: gom file chưa ký của nhiều hồ sơ CCCD_HoVaTen để ký hàng loạt, trả về hồ sơ gốc hoặc chép
  ra thư mục mới (đủ bộ hồ sơ).
- 27/10 — Chống báo nhầm virus (VERSIONINFO, bản onedir + zip), giảm khựng giao diện (nạp tab lười, xuất Excel chạy nền).
- 26/10 — Tab Kiểm tra trang (ngược / sai thứ tự / thiếu / trùng số trang, tự sửa); Tách trang dễ dùng hơn (chọn file
  có tìm kiếm, thẻ hình, kéo đường cắt); nhớ cài đặt + nút ↺ Mặc định; giao diện sáng/tối; nén PDF nhanh hơn.

## Quyết định kỹ thuật
- Kiểm tra chữ ký dùng lại `scanner.analyze_file` (pikepdf + băm lại ByteRange) – an toàn đa luồng, có bộ đệm theo
  (kích thước, ngày sửa) — lý do: 5.242 file chỉ ~2,5 s lần đầu, ~0,6 s lần sau.
- Bảng Gom ký số dùng QTableView + model ảo — lý do: hơn 5.000 dòng, tìm/lọc tức thì.
- Không bao giờ ghi đè: trùng tên khác nội dung → "xung đột", giữ lại — lý do: an toàn dữ liệu hồ sơ.
- Test chữ ký dùng `tests/make_signed_sample.py` (chữ ký giả lập đúng cấu trúc, không có giá trị pháp lý).

- Quy trình làm trên bản chép — lý do: hồ sơ gốc không bao giờ bị ghi; mọi lệnh ghi đi qua `pipeline._guard`.
- Nén xong luôn mở lại file kiểm tra đủ số trang; hỏng thì khôi phục từ hồ sơ gốc (không dùng `_backup_goc`).

## Vấn đề còn tồn tại
- Tab Quy trình cần chỗ trống ≈ dung lượng hồ sơ (bản chép); chưa có chế độ làm trực tiếp trên hồ sơ gốc — `core/pipeline.py`
- Test giao diện cũ `tests/integration_gui.py` cần thư mục mẫu `Desktop\test` (đã mất) — dùng `tests/gui_pipeline.py` (tự tạo dữ liệu)
- Chưa kiểm chứng với chữ ký của phần mềm ký số thật — `core/signgather.py`
- Đổi giao diện sáng/tối còn ~0,7 s (Qt vẽ lại stylesheet) — `ui/main_window.py`
- Một số phần mềm diệt virus có thể vẫn báo nhầm exe PyInstaller (chưa có chữ ký code signing) — `build.py`
