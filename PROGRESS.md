# Tiến độ dự án
_Cập nhật: 27/10/2026 20:45_

## Đang làm dở
- Không có (v1.8.0 đã xong, đã commit).

## Bước tiếp theo
1. Thử tab Gom ký số với **phần mềm ký thật** (vài file): bản ký thật phải được nhận "✔ ký bởi …"; nếu bị báo
   "không có chữ ký thật" → lấy 1 file mẫu để chỉnh `core/signgather.py` / `core/signature.py`.
2. Thử với bộ test `HoSoSoHoa_Test\…Gom ký số (test 3 - ký giả lập)` (4 lỗi mẫu ở Chi bộ 01), chọn thư mục mới riêng.
3. Gửi bản zip portable lên VirusTotal kiểm tra lại; nếu Microsoft vẫn báo nhầm → gửi false-positive cho Microsoft.
4. (Tuỳ chọn) chọn giữ 1 kiểu build (onefile hay onedir) trong `build.py`.

## Nhật ký (mới nhất ở trên)
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

## Vấn đề còn tồn tại
- Chưa kiểm chứng với chữ ký của phần mềm ký số thật — `core/signgather.py`
- Đổi giao diện sáng/tối còn ~0,7 s (Qt vẽ lại stylesheet) — `ui/main_window.py`
- Một số phần mềm diệt virus có thể vẫn báo nhầm exe PyInstaller (chưa có chữ ký code signing) — `build.py`
