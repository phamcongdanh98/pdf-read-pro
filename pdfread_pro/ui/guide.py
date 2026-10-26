"""Nội dung tab HƯỚNG DẪN & THÔNG TIN."""
from .. import paths

GUIDE_HTML = f"""
<div style="font-family:'Segoe UI';font-size:10pt;color:#1E293B;line-height:150%">
<h2 style="color:#1E40AF;margin:0 0 6px 0">📘 Hướng dẫn sử dụng {paths.APP_NAME} v{paths.APP_VERSION}</h2>

<h3 style="color:#1D4ED8">1. Chọn thư mục và quét</h3>
<ul>
<li>Bấm <b>📁 Chọn thư mục…</b>, dán đường dẫn rồi Enter, hoặc <b>kéo thả thư mục</b> vào cửa sổ.</li>
<li><b>Quét tất cả thư mục con</b>: bật để quét cả cây thư mục. Thư mục <code>_backup_goc</code> luôn được bỏ qua.</li>
<li><b>Tính số trang</b>: <i>Tất cả</i> / <i>Chỉ file .signed</i> / <i>Không tính file .signed</i> – áp dụng cho bảng,
thẻ thống kê, tab Đổi tên và tab Giảm dung lượng.</li>
</ul>

<h3 style="color:#1D4ED8">2. Tab Tổng quan &amp; thống kê</h3>
<table cellpadding="4" style="border-collapse:collapse">
<tr><td><b>Thư mục có PDF</b></td><td>Số thư mục có file PDF <b>nằm trực tiếp</b> trong nó. Thư mục chỉ chứa thư mục con không được đếm (ghi ở dòng phụ).</td></tr>
<tr><td><b>Số file / Tổng số trang</b></td><td>Theo lựa chọn “Tính số trang”; dòng phụ luôn hiện cả 2 nhóm .signed / không .signed.</td></tr>
<tr><td><b>Chữ ký số</b></td><td>Đọc chữ ký <b>thật</b> trong file: ✔ còn nguyên · ⚠ có sửa sau khi ký · ✖ đã hỏng. Không kiểm tra độ tin cậy chứng thư (CA).</td></tr>
<tr><td><b>Cần xem lại</b></td><td>Đã ký nhưng tên chưa .signed · tên .signed nhưng không có chữ ký · không đọc được · file lỗi.</td></tr>
</table>
<ul>
<li><b>Bấm vào thẻ</b> để xem danh sách chi tiết. <b>Bấm vào thư mục</b> trong cây để thẻ chỉ tính thư mục đó (nút <b>✖ Xem toàn bộ</b> để quay lại).</li>
<li><b>Bấm vào file</b> để xem trước bên phải; bấm đôi để mở bằng phần mềm đọc PDF; chuột phải để mở thư mục chứa / sao chép đường dẫn.</li>
</ul>

<h3 style="color:#1D4ED8">3. Tab Xem trước &amp; đổi tên</h3>
<ul>
<li>Mặc định đổi tên theo <b>Bộ quy tắc mã số 1361</b> (chép nguyên 124 quy tắc của Hồ sơ 1361): lấy mã số ở đầu tên file
(<code>01</code>, <code>1.</code>, <code>07a</code>, <code>86dh</code>, <code>6124</code>…) → đổi thành tên mẫu tiêu chuẩn, ví dụ
<code>4. TB …signed.pdf</code> → <code>04.Phieu_bo_sung_ho_so_dang_vien.signed.pdf</code>.</li>
<li>Nhiều file cùng mã trong 1 thư mục → thêm hậu tố <code>.1</code>, <code>.2</code>…; tích <b>Luôn thêm hậu tố .1</b> để thêm cả khi chỉ có 1 file.
File đã đúng tên giữ nguyên số hậu tố của nó. Phần <code>.signed</code> ở cuối luôn được giữ.</li>
<li>Cột <b>Mã Số</b> · <b>Quy Tắc Khớp Tương Ứng</b> · <b>Tên File Mới Dự Kiến</b> · <b>Trạng Thái</b>
(<span style="color:#047857">✔ sẵn sàng</span>, ● đã đúng tên, <span style="color:#B45309">❓ chưa có quy tắc</span>,
<span style="color:#B91C1C">✖ không có mã số</span>). Bấm 1 dòng để xem trước file PDF bên phải.</li>
<li>Có thể chọn <b>Mẫu đổi tên tuỳ chỉnh</b> trong ô “Bộ quy tắc”.</li>
<li><b>🚀 BẮT ĐẦU ĐỔI TÊN HÀNG LOẠT</b>: chỉ đổi tên, không sửa nội dung (chữ ký số còn nguyên), <b>không bao giờ ghi đè</b>.
<b>↩️ HOÀN TÁC (UNDO)</b>: đưa lần đổi gần nhất về tên cũ; máy tắt đột ngột giữa chừng thì lần mở sau tự khôi phục.</li>
</ul>

<h3 style="color:#1D4ED8">4. Tab Quản lý bộ quy tắc</h3>
<ul>
<li><b>Bộ quy tắc mã số 1361</b>: bảng <i>Mã Số Key → Tên Mẫu Quy Tắc Tiêu Chuẩn</i>. Gõ mã + tên rồi <b>Thêm / Cập Nhật</b>
(tên tự chuẩn hoá: <code>86. Bang dai hoc</code> → <code>86.Bang_dai_hoc</code>), <b>Xóa Quy Tắc</b>, tìm kiếm,
<b>Nhập / Xuất tệp quy tắc (.json / .txt)</b>, <b>Reset bộ tiêu chí về mặc định</b>. Thay đổi áp dụng ngay cho tab Đổi tên.</li>
<li><b>Mẫu đổi tên tuỳ chỉnh (nâng cao)</b>: mẫu tên có biến <code>{{stem}}</code> <code>{{n}}</code> <code>{{n:3}}</code> <code>{{folder}}</code>
<code>{{parent}}</code> <code>{{pages}}</code> <code>{{date}}</code> <code>{{today}}</code> <code>{{signer}}</code> <code>{{code}}</code>; đánh số;
các bước tiền tố/hậu tố, thay thế (văn bản/regex), bỏ dấu, khoảng trắng, hoa/thường, dọn ký tự, chuẩn tên mã 1361; ô ví dụ trực tiếp; lưu/nhập/xuất.</li>
</ul>

<h3 style="color:#1D4ED8">Khung xem trước PDF</h3>
<ul>
<li>Mặc định <b>✦ Tự động</b> vừa khung: hiện trọn trang nếu chữ đủ rõ, ngược lại vừa chiều ngang để dễ đọc. Có <b>Vừa trang</b>, <b>Vừa ngang</b>, phóng to/thu nhỏ (hoặc Ctrl + lăn chuột).</li>
<li>Lăn chuột hết trang thì tự sang trang kế; phím PageUp/PageDown, Home/End. Xoay chỉ khi xem, không sửa file.</li>
</ul>

<h3 style="color:#1D4ED8">5. Tab Tách trang PDF (cắt &amp; ghép sổ lý lịch)</h3>
<ul>
<li>Chọn file ở ô <b>File</b> (danh sách file đang quét) hoặc <b>Chọn File PDF Khác…</b>; chuột phải 1 file ở tab Tổng quan → <b>Tách trang file này</b>.</li>
<li><b>Mẫu có sẵn</b>: <i>A3 ngang → 2 trang A4</i> · <i>A4 → 2 nửa, phóng thành 2 trang A4</i> ·
<i>Sổ lý lịch gỡ ghim (scan 2 mặt)</i>. App tự gợi ý mẫu theo khổ giấy của file.</li>
<li>Khung giữa: trang scan gốc với <b>đường cắt màu đỏ</b> (kéo “Vị trí đường cắt” nếu lệch); nhãn <b>GIỮ NGUYÊN (BÌA)</b>,
<b>MẶT SAU · XOAY 180°</b>. Khung phải: <b>xem trước kết quả giống 100% file xuất</b>, ghi rõ mỗi trang lấy từ đâu.</li>
<li><b>Thứ tự sổ gỡ ghim</b>: sổ tháo ghim, scan 2 mặt từng tờ → app sắp lại đúng trang 1, 2, 3… Nếu thấy mặt 2, 4… bị lộn ngược,
chọn <b>Xoay mặt sau (ADF): Có</b>. Số mặt scan (trừ bìa) phải chẵn.</li>
<li><b>🔢 Tự Đọc Số Trang &amp; Sắp Xếp</b> (tự chạy khi chọn mẫu Sổ gỡ ghim): app đọc <b>số trang in ở đầu/chân mỗi trang</b>
bằng OCR có sẵn của Windows, rồi tự chọn đúng cách xếp – tờ ngoài hay tờ giữa scan trước, mặt nào trước, mặt sau có lộn ngược không,
cả xấp có bị ngược không. Không cần đặt sổ đúng 1 chiều cố định như Hồ sơ 1361. Khung kết quả ghi <b>“số in: N”</b> (xanh = khớp,
cam = cần xem lại). Trang không in số vẫn được xếp đúng nếu đa số trang khác đọc được.</li>
<li>Tuỳ chọn: thứ tự nửa trang, xoay sau khi cắt, chuẩn hoá khổ A4, phạm vi trang scan, <b>bỏ trang trắng</b> (chỉ bỏ trang gần như trắng tinh, có liệt kê vị trí).</li>
<li><b>Lưu</b>: mặc định ra file mới <code>…_DaTach.pdf</code> cạnh file gốc (không bao giờ ghi đè); ô <b>Trang xuất</b> để xuất trang chỉ định (VD <code>1-4, 7</code>);
<b>Lưu đè file gốc</b> có sao lưu vào <code>_backup_goc</code>. File có chữ ký số: file tách ra không còn chữ ký hợp lệ (app cảnh báo).</li>
</ul>

<h3 style="color:#1D4ED8">6. Tab Giảm dung lượng PDF</h3>
<ul>
<li>Đặt <b>dung lượng tối đa mỗi trang</b> (KB). <b>Phân tích</b> để xem trang nặng nhất và số trang vượt.</li>
<li>Mặc định <b>lưu sang thư mục mới</b> (giữ nguyên file gốc) và <b>bỏ qua file đã ký số</b> (nén làm mất hiệu lực chữ ký).</li>
<li>Ghi đè file gốc: có tuỳ chọn sao lưu bản gốc vào <code>_backup_goc</code>.</li>
<li>Chỉ nén được ảnh; file toàn chữ/vector báo “Không có ảnh để nén”.</li>
</ul>

<h3 style="color:#1D4ED8">7. Tab Báo cáo hồ sơ (hồ sơ số hoá)</h3>
<ul>
<li>Cấu trúc chuẩn: <b>Hồ sơ số hóa</b> › <b>Chi bộ</b> › thư mục hồ sơ <b>CCCD_HoVaTen</b>
(12 số CCCD + “_” + họ tên không dấu, viết hoa chữ cái đầu mỗi từ, VD <code>056123456789_TranVanThai</code>)
› các file PDF đặt tên theo bộ quy tắc 1361. Quét thư mục <b>Hồ sơ số hóa</b> (hoặc 1 chi bộ) rồi mở tab này.</li>
<li><b>File bắt buộc</b> mặc định <code>01-05</code>: 01 Lý lịch người xin vào Đảng · 02 Lý lịch đảng viên · 03 Phiếu đảng viên ·
04 Phiếu bổ sung hồ sơ đảng viên · 05 Quyết định kết nạp đảng viên (sửa được, VD <code>01, 02</code>).</li>
<li>Mỗi người chỉ có 2 kết quả: <b>Đủ</b> = có đủ file bắt buộc · <b>Thiếu</b> = còn thiếu ít nhất 1 file (cột <b>Còn thiếu</b>
ghi rõ thiếu gì). Cột 01…05 ghi <b>Có</b> / <b>Thiếu</b>. Giấy tờ khác trong bộ quy tắc (06…) không ảnh hưởng kết quả.</li>
<li><b>Tính file</b>: khi ký số thường có 2 bản – <code>X.pdf</code> (chưa ký) và <code>X.signed.pdf</code> (đã ký).
<b>Cả 2</b>: có bản nào cũng tính “Có” · <b>Chỉ file đã ký</b>: mục chỉ có bản chưa ký vẫn tính “Thiếu”, ghi
“(mới có bản chưa ký)” · <b>Chỉ file chưa ký</b>: chỉ tính file không có .signed. Cặp bản chưa ký/đã ký không bị coi là trùng.</li>
<li><b>Ghi chú</b> = vấn đề khác cần xem lại nhưng không làm hồ sơ thành “Thiếu”: thư mục/file đặt sai tên, trùng số CCCD,
file hỏng, file chưa rõ loại…</li>
<li>Bảng nhóm theo chi bộ (“Đủ 9/12”). Lọc: Đủ · Thiếu · Thiếu 01 … Thiếu 05 · Có ghi chú; tìm theo CCCD / họ tên.
Bấm 1 chi bộ xem tổng hợp và danh sách người còn thiếu; bấm 1 người xem từng file.</li>
<li><b>Chuẩn hoá tên thư mục</b>: đổi tên thư mục sai chuẩn theo gợi ý, không ghi đè, có <b>Hoàn tác</b>.</li>
<li><b>Xuất báo cáo Excel</b>: <b>Tổng hợp chi bộ</b> (tổng hồ sơ, Đủ, Thiếu, số người thiếu từng mục 01…05, tỉ lệ đủ, dòng tổng) ·
<b>Danh sách toàn bộ</b> (mỗi người 1 dòng: chi bộ, CCCD, họ tên, 01…05 Có/Thiếu, Kết quả, Còn thiếu, Ghi chú) ·
<b>Danh sách thiếu</b> (chỉ người còn thiếu, cột “Đã bổ sung”) · <b>Giải thích</b>. Tick <b>Kèm báo cáo nâng cao</b> để thêm:
Chi tiết file · Thống kê giấy tờ (124 mã) · Vấn đề cần xử lý. Sẵn khổ A4 ngang, có nút lọc ở dòng tiêu đề.</li>
</ul>

<h3 style="color:#1D4ED8">8. Tab Đối chiếu danh sách (so với file Excel của hệ thống)</h3>
<ul>
<li>Quét thư mục <b>Hồ sơ số hóa</b> trước, rồi <b>Chọn File Excel…</b> (danh sách đảng viên đã số hoá xuất từ hệ thống, .xlsx).
App tự dò <b>dòng tiêu đề</b> và đoán <b>Cột Số CCCD · Cột Họ và tên · Cột Chi bộ</b>; sửa lại bằng các ô chọn nếu sai
– hoặc <b>bấm thẳng vào tiêu đề cột</b> trong bảng xem trước để gán 🔑 CCCD / 👤 Họ tên / 🏠 Chi bộ. Mỗi lựa chọn có kèm giá trị ví dụ; app báo nếu cột CCCD chọn nhầm (ít ô là số CCCD). Nếu tên cột lạ, app tự tìm cột chứa số CCCD theo dữ liệu. Lần sau app nhớ cột đã chọn.</li>
<li>CCCD bị Excel làm mất số 0 đầu (lưu dạng số) hoặc dạng 5,6E+10 được tự sửa lại thành 12 số.</li>
<li>Bấm <b>ĐỐI CHIẾU</b> – so theo số CCCD: <b>Khớp</b> · <b>Lệch tên</b> (CCCD khớp, tên thư mục khác danh sách) ·
<b>Khác chi bộ</b> · <b>Nghi gõ nhầm CCCD</b> (lệch 1 số / đảo 2 số, họ tên giống) · <b>Chưa có thư mục</b> (có trong danh sách) ·
<b>Ngoài danh sách</b> (có thư mục, không có trong danh sách). Cột <b>Hồ sơ 01–05</b> cho biết Đủ / Thiếu.
<b>Ghi chú</b>: trùng CCCD, CCCD gần giống nhưng tên khác, tên thư mục chưa chuẩn…</li>
<li>Tên chi bộ trong Excel được ghép gần đúng với thư mục chi bộ (bỏ dấu, bỏ chữ “Chi bộ”).</li>
<li>Thao tác (xem trước + xác nhận, không ghi đè, có <b>Hoàn tác</b>): <b>Đổi tên thư mục theo danh sách</b>
(CCCD_HoVaTen, sửa cả số CCCD gõ nhầm) · <b>Chuyển về đúng chi bộ</b> · <b>Tạo thư mục còn thiếu</b> (thư mục rỗng để scan bổ sung).</li>
<li><b>Xuất Excel đối chiếu</b>: Tổng hợp chi bộ · Đối chiếu chi tiết (họ tên có dấu theo danh sách) · Chưa có thư mục ·
Ngoài danh sách · Cần sửa · Giải thích.</li>
</ul>

<h3 style="color:#1D4ED8">9. Công cụ (cạnh ô thư mục)</h3>
<ul>
<li><b>Kiểm tra đủ 5 file</b>: mỗi thư mục có PDF phải có đủ <code>01.</code>–<code>05.</code>; copy riêng các thư mục thiếu ra thư mục mới.</li>
<li><b>Thư mục CCCD</b>: thư mục tên đúng 12 chữ số; xoá vào Thùng rác (ổ mạng/USB: xoá vĩnh viễn, hỏi lại 2 lần).</li>
<li><b>Copy nhóm file</b>: chép Tất cả / chỉ .signed / không .signed sang thư mục mới, giữ nguyên cây thư mục.</li>
<li><b>☰ Thêm</b>: mở thư mục nguồn, nhật ký thao tác, dữ liệu ứng dụng. Nút <b>📜 Nhật ký</b> ở góc dưới phải: hiện/ẩn nhật ký.</li>
</ul>

<h3 style="color:#1D4ED8">Dữ liệu ứng dụng</h3>
<p>Bộ quy tắc, nhật ký, lịch sử đổi tên: <code>{paths.data_dir()}</code></p>

<h2 style="color:#1E40AF;margin-top:18px">📋 Lịch sử phiên bản</h2>
<ul>
<li><b>1.6.1</b> – Mở app nhanh hơn (exe gọn 100 → 59 MB, bỏ thư viện không dùng; không còn đọc file Excel đối chiếu
lúc khởi động). Nén nhanh hơn khoảng 7 lần so với app Giamdungluong_Full cũ: trang đạt ở bậc nào dừng ở bậc đó, tự dự đoán bậc nén, bậc nén mịn ưu tiên giữ nguyên độ phân giải (chữ nét hơn).
Gán cột Excel bằng cách bấm tiêu đề cột. Icon mới trên thanh taskbar.</li>
<li><b>1.6.0</b> – Thêm tab <b>Đối chiếu danh sách</b>: so file Excel danh sách đảng viên của hệ thống với thư mục hồ sơ
theo số CCCD (khớp, lệch tên, khác chi bộ, nghi gõ nhầm CCCD, chưa có thư mục, ngoài danh sách), tự sửa CCCD mất số 0,
đổi tên / chuyển chi bộ / tạo thư mục còn thiếu (có hoàn tác), xuất Excel đối chiếu. Gán cột bằng cách bấm tiêu đề cột, tự tìm cột CCCD theo dữ liệu, cảnh báo chọn nhầm cột.</li>
<li><b>1.5.0</b> – Thêm tab <b>Báo cáo hồ sơ</b> (lựa chọn tính file đã ký / chưa ký / cả 2): kiểm tra cấu trúc Hồ sơ số hóa › Chi bộ › CCCD_HoVaTen › file 01–05,
kết quả Đủ / Thiếu cho từng người (ghi rõ thiếu gì), chuẩn hoá tên thư mục (có hoàn tác), xuất Excel: Tổng hợp chi bộ ·
Danh sách toàn bộ · Danh sách thiếu · Giải thích (+ báo cáo nâng cao tuỳ chọn). Giao diện gọn: banner 1 dòng, công cụ gom cạnh ô thư mục,
tab theo thứ tự công việc, nhật ký ẩn mặc định, tab Tách trang gom tuỳ chọn ít dùng vào “Nâng cao”.</li>
<li><b>1.4.0</b> – Tách trang: <b>tự đọc số trang in trên giấy</b> (Windows OCR, không cần cài thêm) để tự sắp thứ tự sổ gỡ ghim
và tự phát hiện mặt lộn ngược; thêm kiểu xếp tờ giữa trước / mặt kia trước; hiện “số in” ở khung kết quả.</li>
<li><b>1.3.0</b> – Thêm tab <b>Tách trang PDF</b>: A3 → A4, A4 → 2 trang A4 (chuẩn hoá khổ), sắp lại thứ tự sổ lý lịch gỡ ghim
scan 2 mặt (giữ bìa, xoay mặt sau ADF), xem trước trang gốc có đường cắt và kết quả giống 100% file xuất, bỏ trang trắng, xuất trang chỉ định,
không ghi đè file gốc; khung xem trước PDF hẹp &amp; cao như Hồ sơ 1361.</li>
<li><b>1.2.0</b> – Chép nguyên bộ 124 quy tắc mã số Hồ sơ 1361 và tab Quản lý bộ quy tắc như bản gốc; tab Đổi tên mặc định theo
bộ quy tắc 1361 (cột Mã Số / Quy Tắc Khớp, hậu tố .1 .2, tuỳ chọn “Luôn thêm hậu tố .1”); giao diện chép theo Hồ sơ 1361
(banner, màu nút, Segoe UI 9.5pt, tab gạch đỏ, ô tích riêng); khung xem trước tự vừa khung, nét theo DPI màn hình.</li>
<li><b>1.1.0</b> – Giao diện mới theo phong cách Hồ sơ 1361: khung Cấu hình &amp; thư mục nguồn, hàng nút công cụ màu,
các tab Tổng quan · Xem trước &amp; đổi tên · Quản lý bộ quy tắc · Giảm dung lượng · Hướng dẫn; nhật ký thao tác ngay dưới cửa sổ;
luôn giao diện sáng (sửa lỗi ô chọn bị nền đen khi Windows bật chế độ tối).</li>
<li><b>1.0.0</b> – Bản đầu: quét, đếm trang, chữ ký số, 5 thẻ thống kê, xem trước PDF, đổi tên theo quy tắc, nén PDF, công cụ hồ sơ.</li>
</ul>
</div>
"""
