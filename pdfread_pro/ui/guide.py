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

<a name="split"></a><h3 style="color:#1D4ED8">5. Tab Tách trang PDF (cắt &amp; ghép sổ lý lịch)</h3>
<p><b>4 bước:</b> ① chọn file → ② bấm hình kiểu tách → ③ xem khung <b>Kết quả</b> (giống 100% file xuất) → ④ bấm <b>LƯU</b>.</p>
<table cellspacing="6" cellpadding="4">
<tr><td><img src="img:a3_to_a4" width="340" height="120"></td><td valign="middle"><b>A3 ngang → 2 trang A4</b><br>Bản scan khổ A3 nằm ngang,
mỗi bên là 1 trang → cắt đôi theo đường đỏ.</td></tr>
<tr><td><img src="img:a4_to_a4" width="340" height="120"></td><td valign="middle"><b>A4 → 2 nửa → 2 trang A4</b><br>Trang A4 in 2 trang nhỏ
(trên / dưới hoặc trái / phải) → mỗi nửa phóng thành 1 trang A4.</td></tr>
<tr><td><img src="img:booklet" width="340" height="120"></td><td valign="middle"><b>Sổ lý lịch gỡ ghim</b><br>Sổ tháo ghim, scan 2 mặt
từng tờ (mỗi mặt có 2 trang, mặt sau có thể bị lộn ngược) → app đọc số trang in và sắp lại đúng thứ tự 1, 2, 3…</td></tr>
</table>
<ul>
<li><b>Chọn file</b>: bấm <b>🔎 Chọn file…</b> – hộp chọn có ô tìm kiếm (gõ tên file, CCCD, tên người, thư mục; không cần
dấu) và cây theo thư mục; nút <b>◀ ▶</b> để sang file trước / sau; <b>📂 File khác…</b> chọn file bất kỳ; hoặc
<b>kéo thả</b> file PDF vào tab. Ở tab Tổng quan: chuột phải 1 file → <b>Tách trang file này</b>.</li>
<li><b>Kiểu tách</b>: bấm 1 trong 3 hình ở cột trái. App tự gợi ý theo khổ giấy của file. Chỉnh thêm ở
<b>Tuỳ chọn nâng cao</b> thì app chuyển sang “thiết lập tuỳ chỉnh”.</li>
<li>Khung giữa: trang scan gốc với <b>đường cắt màu đỏ</b> – lệch thì <b>dùng chuột kéo đường đỏ</b> (rê tới đường đỏ,
con trỏ đổi thành ↔, kéo; hiện số %), khung kết quả cập nhật ngay; nhãn <b>GIỮ NGUYÊN (BÌA)</b>,
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

<a name="check"></a><h3 style="color:#1D4ED8">5b. Tab Kiểm tra trang</h3>
<p><img src="img:check" width="340" height="120"></p>
<ul>
<li>Bấm <b>🔍 Kiểm tra</b> (giữ Ctrl khi bấm: chỉ file đang chọn). App đọc chữ và số trang in ở đầu / chân trang
bằng Windows OCR, báo: trang <b>ngược</b> / <b>nằm ngang</b>, <b>sai thứ tự</b>, <b>thiếu số</b>, <b>trùng số</b>, <b>trang trắng</b>.</li>
<li>Bấm 1 file để xem <b>Chi tiết từng trang</b> (số in đọc được, hướng, đề xuất sửa); bấm 1 trang để xem trang đó bên phải.
Đọc sai số: bấm đôi ô <b>Số in</b> để sửa; sai hướng: chuột phải vào trang.</li>
<li><b>🛠 Sửa tự động</b>: xoay đúng chiều, sắp xếp theo số trang, (tuỳ chọn) bỏ trang trắng – không nén lại ảnh.
Mặc định lưu sang thư mục mới; ghi đè có sao lưu <code>_backup_goc</code>. Bỏ qua file đã ký số.</li>
<li>File có số trùng (ghép nhiều văn bản) hoặc đọc được quá ít số sẽ <b>không tự sắp xếp</b> – app báo “Cần xem lại”.</li>
</ul>

<h3 style="color:#1D4ED8">6. Tab Giảm dung lượng PDF</h3>
<ul>
<li>Đặt <b>dung lượng tối đa mỗi trang</b> (mặc định 250 KB, app nhớ lần chọn trước). <b>Phân tích</b> để xem trang
nặng nhất và số trang vượt.</li>
<li><b>✨ Rõ chữ</b> (khuyến nghị, mặc định bật): làm trắng nền giấy, chữ đậm và sắc hơn; trang không có màu lưu ảnh xám
(nhẹ, nhanh); trang có dấu đỏ / chữ ký màu / ảnh màu vẫn giữ màu. Bỏ chọn nếu cần giữ nguyên màu giấy.</li>
<li><b>Xem trước</b> bên phải: bấm 1 file để xem; nén xong bấm <b>Bản gốc</b> / <b>Bản đã nén</b> để so độ rõ của chữ
(giữ đúng trang đang xem). Bấm đôi để mở bằng phần mềm đọc PDF.</li>
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

<h3 style="color:#1D4ED8">7a. Tab Quy trình – 1 click (đổi tên → nén → gom để ký)</h3>
<ol>
<li>Quét thư mục hồ sơ (chi bộ hoặc cả Hồ sơ số hóa) ở ô trên cùng. Chọn quy tắc đổi tên ở tab <b>Đổi tên</b> (mặc định bộ 1361);
đặt dung lượng tối đa mỗi trang (mặc định <b>250 KB</b>).</li>
<li>Bấm <b>🚀 CHẠY CẢ QUY TRÌNH</b>. App <b>kiểm tra trước</b> (không ghi gì) và hiện tóm tắt: bao nhiêu file sẽ đổi tên, ước tính
bao nhiêu file cần nén, bao nhiêu file gom để ký, cảnh báo, dung lượng ổ cần. Đồng ý thì chạy.</li>
<li>App <b>chép hồ sơ sang bản làm việc</b> rồi đổi tên → nén → gom <b>trên bản chép</b>. <b>Hồ sơ gốc không bao giờ bị sửa.</b></li>
<li>Xong: xem bảng kết quả từng file (tích <b>⚠ Chỉ file cần xem</b>), <b>📊 Xuất Excel</b>, rồi <b>ký số hàng loạt</b> các file trong
thư mục gom. Ký xong bấm <b>➡ Sang tab Gom ký số</b> để chép bộ hồ sơ đã ký ra <code>… - Đã ký</code>.</li>
</ol>
<ul>
<li>File đã ký số được giữ nguyên (nén sẽ làm hỏng chữ ký). File nén ra bị hỏng / lệch số trang được <b>tự khôi phục từ hồ sơ gốc</b>.</li>
<li>Một bước lỗi → các bước sau không chạy; <b>■ Dừng</b> bất cứ lúc nào. Làm lại: <b>🗑 Xoá kết quả</b> (vào Thùng rác) rồi chạy lại;
chạy lần 2 mà chưa xoá thì app tự đặt tên thư mục mới <code>(2)</code>, không ghi chồng.</li>
<li>Cần thêm chỗ trống bằng đúng dung lượng hồ sơ (bản chép) – app báo trước nếu ổ không đủ.</li>
</ul>

<h3 style="color:#1D4ED8">7b. Tab Gom ký số (ký hàng loạt nhiều hồ sơ)</h3>
<ol>
<li>Quét thư mục <b>chi bộ</b> (hoặc cả Hồ sơ số hóa) có các thư mục hồ sơ <code>CCCD_HoVaTen</code>
(vd <code>056123456789_TranVanThai</code>).</li>
<li>Bấm <b>① GOM ĐỂ KÝ</b>: app <b>chép</b> các file <b>chưa ký</b> vào thư mục gom, tên thêm đuôi hồ sơ:
<code>01.Ly_lich_nguoi_xin_vao_Dang_056123456789_TranVanThai.pdf</code>. File gốc giữ nguyên.</li>
<li>Mở thư mục gom, <b>ký số hàng loạt</b> bằng phần mềm ký (phần mềm tạo thêm file <code>….signed.pdf</code>).</li>
<li>Bấm thẻ <b>② Trả về sau ký</b> (bảng hiện ngay các bản đã ký), rồi nút <b>② CHÉP RA THƯ MỤC MỚI</b> /
<b>② TRẢ VỀ HỒ SƠ GỐC</b>: bản đã ký về đúng hồ sơ, bỏ đuôi
(<code>01.Ly_lich_nguoi_xin_vao_Dang.signed.pdf</code>); bản sao chưa ký giống bản gốc được xoá; file chưa ký xong
giữ lại trong thư mục gom để ký tiếp.</li>
</ol>
<ul><li>Tab chia làm <b>2 bước</b> (2 thẻ ở đầu tab): mỗi bước chỉ hiện thiết lập và nút của nó; các tuỳ chọn ít dùng nằm trong
<b>▸ Tuỳ chọn nâng cao</b> (bấm để mở). Nút to màu ở góc phải dưới là việc chính; việc phụ (mở thư mục, tách file, xuất Excel)
nằm trong menu <b>⋯ Thêm</b>. Dòng chữ xanh ở dưới trái luôn nói bước tiếp theo.</li>
<li><b>② Sau ký</b> có 2 cách: <b>Chép ra thư mục mới</b> (khuyên dùng): hồ sơ gốc và thư mục gom giữ nguyên, thư mục mới có
cùng cây <code>Chi bộ\\CCCD_HoVaTen</code>, chứa bản <code>.signed</code> + bản chưa ký đã bỏ đuôi (nâng cao: <b>Chép kèm đủ bộ
hồ sơ</b> để chép thêm các file khác của hồ sơ); hoặc <b>Trả về thẳng thư mục hồ sơ gốc</b> (như trên).</li>
<li>Không bao giờ ghi đè: trùng tên mà khác nội dung → báo <b>xung đột</b>, giữ lại. Có <b>↶ Hoàn tác</b>.</li>
<li>File <code>_gom_ky_so.json</code> trong thư mục gom là <b>sổ ghi</b> (file nào của hồ sơ nào), được ẩn; cứ để nguyên khi ký
– phần mềm ký chỉ ký PDF. Lỡ xoá sổ vẫn trả về được theo đuôi <code>_CCCD_HoVaTen</code>.</li>
<li><b>🛡 Kiểm tra chữ ký số thật + số trang</b> (bật sẵn): bản ký chỉ được nhận khi có chữ ký số thật (không chỉ đổi
tên .signed), chữ ký không hỏng, mở được, cùng số trang bản gốc, phần mềm ký đã ghi xong và bản gốc không bị thay sau khi
gom. Sai → giữ lại, cột <b>Ghi chú</b> nói lý do; ô <b>Hiện</b> chọn <i>Cần xử lý</i> để xem nhanh các dòng lỗi
(<i>Việc sẽ làm</i> = chỉ các file app sẽ chép / trả về).</li>
<li><b>Chia lô</b> khi gom (nâng cao): theo chi bộ hoặc mỗi lô N file (thư mục con) – ký từng lô. Phần mềm ký ghi ra thư mục con
<code>Signed\\</code>, đặt đuôi <code>_signed</code> / <code>_ky</code> hay ký đè lên file đều được nhận.</li>
<li><b>👁 Tự cập nhật khi đang ký</b> (nâng cao, bật sẵn): bảng tự kiểm tra lại khi có file mới; dòng tóm tắt màu trên bảng ghi
<span style="color:#15803D">✔ bản đã ký hợp lệ</span> · <span style="color:#B45309">⏳ chưa ký</span> ·
<span style="color:#DC2626">⚠ cần xử lý</span>.</li>
<li><b>⋯ Thêm ▸ 📦 Tách file cần ký lại</b>: file chưa ký → thư mục <code>Ký lại &lt;ngày giờ&gt;</code> để ký riêng phần còn thiếu;
bản ký lỗi → <code>_Bản ký lỗi</code>. <b>⋯ Thêm ▸ 📊 Xuất Excel</b>: tổng hợp theo hồ sơ + chi tiết. Ô tìm kiếm không cần dấu.</li>
<li><b>↶ Hoàn tác</b> nhớ cả sau khi tắt app. Ổ không đủ chỗ → báo trước khi chép; đường dẫn quá dài → cảnh báo.</li>
<li>Trả về / chép ra <b>không cần quét lại</b>: chỉ cần <b>📁 Chọn…</b> đúng thư mục gom – bảng ② hiện ngay (bấm
<b>🔄 Kiểm tra lại</b> khi cần đọc lại) – app đọc sổ ghi để biết thư mục hồ sơ gốc và tự đặt thư mục mới là <code>&lt;thư mục hồ sơ&gt; - Đã ký</code>.</li></ul>

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
<li><b>1.9.0</b> – Tab mới <b>Quy trình</b>: 1 click chạy tuần tự <b>đổi tên → giảm dung lượng (250 KB/trang) → gom file
chưa ký để ký số</b> trên bản chép (hồ sơ gốc không bị sửa), kiểm tra trước + xác nhận, tự khôi phục file nén lỗi, dừng được
bất cứ lúc nào, bảng kết quả + xuất Excel, bàn giao sang tab Gom ký số. Sổ gom ghi thư mục gốc nên chép ra thư mục mới giữ
đúng cây Chi bộ. Tab <b>Gom ký số làm lại gọn</b> theo 2 bước (2 thẻ, tuỳ chọn nâng cao gập lại, 1 nút chính, bảng 4 cột có
biểu tượng, gợi ý bước tiếp theo); thứ tự tab xếp theo trình tự làm việc. Chép ra thư mục mới: <b>tự đặt tên thư mục không trùng</b> (thêm (2)), hộp xác nhận ghi số hồ sơ + dung lượng và <b>cảnh báo hồ sơ chưa ký / bản ký lỗi</b> (mặc định “Không”), nút <b>⏹ Dừng</b>, tóm tắt đối chiếu sau chép (đủ N/M file, 0 lỗi); kiểm tra lại sau chép nhanh hơn nhiều. <b>Giao diện gọn hơn:</b> thanh thư mục nguồn còn 1 hàng (nút ✕ trong ô thay “Clear”, việc phụ gom vào menu 🧰 Công cụ), khung xem trước ở tab Đổi tên / Nén PDF / Kiểm tra trang <b>gập được</b> (tự mở khi chọn file, nút 👁 Xem trước), tên tab ngắn gọn, chữ tiếng Việt thống nhất.</li>
<li><b>1.8.0</b> – Tab mới <b>Kiểm tra trang</b>: phát hiện trang ngược / nằm ngang, sai thứ tự, thiếu / trùng số trang,
trang trắng và sửa tự động. Tab Giảm dung lượng: khung xem trước <b>cao hết tab</b> như Tổng quan. Tab Tách trang:
hộp <b>chọn file có tìm kiếm</b> (thay danh sách thả xuống dài), nút file trước / sau, kéo thả, chọn kiểu tách bằng
<b>hình minh hoạ</b>. Hướng dẫn có hình. App <b>nhớ mọi lựa chọn</b> khi tắt; nút <b>↺ Mặc định</b> khôi phục cài đặt gốc.</li>
<li><b>1.8.0</b> – Tab mới <b>Gom ký số</b>: gom file chưa ký của nhiều hồ sơ vào 1 thư mục (tên thêm đuôi
_CCCD_HoVaTen) để ký hàng loạt, ký xong trả bản .signed về đúng hồ sơ hoặc chép ra thư mục mới. Kiểm tra trả về
hàng nghìn file chạy nền, không đứng máy (13 s → 0,3 s); sổ ghi được ẩn. Kiểm tra chữ ký số thật + số trang của bản
ký, phát hiện file đang ký / bản gốc đã đổi / trùng tên hồ sơ, chia lô, tự cập nhật khi ký, tìm kiếm + lọc, tách file cần
ký lại, xuất Excel, hoàn tác nhớ sau khi tắt app, chép an toàn (.part, kiểm tra dung lượng, đường dẫn dài).</li>
<li><b>1.8.0 (tối ưu)</b> – Đỡ khựng với thư mục hàng nghìn file: đổi bộ lọc / phạm vi chỉ nạp tab đang mở
(tab khác nạp khi mở tới); tự đọc số trang chuẩn bị ảnh từng phần; xuất Excel (báo cáo, đối chiếu) chạy nền.
Exe có thông tin phiên bản, có bản zip portable (ít bị phần mềm diệt virus báo nhầm hơn).</li>
<li><b>1.7.0</b> – <b>Giao diện tối</b> (nút 🌙 / ☀ trên banner). Tab Giảm dung lượng có <b>xem trước</b> và so
<b>Bản gốc ↔ Bản đã nén</b>; mặc định <b>250 KB/trang</b>; chế độ <b>✨ Rõ chữ</b> (làm trắng nền, tự chuyển ảnh xám,
hạ ảnh &gt; 300 dpi) với bậc nén mới dựa trên nghiên cứu độ rõ chữ tiếng Việt; tinh chỉnh để nén sát giới hạn. Sửa lỗi
màn hình nhỏ bị mất phần dưới (mỗi tab tự cuộn, thanh công cụ thu gọn).</li>
<li><b>1.6.2</b> – Sửa lỗi giảm dung lượng báo nhầm “Không có ảnh để nén” với file PDF scan bình thường:
ảnh JPEG đã nén sẵn và ảnh nằm trong Form XObject (máy scan, đóng dấu, ghép trang). Nén nhanh hơn: đọc chất lượng JPEG có sẵn để bỏ qua bậc vô ích, xử lý nhiều ảnh song song trong 1 file, bậc nén mịn hơn (sát giới hạn hơn).</li>
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
