"""Tạo BỘ DỮ LIỆU TEST cho PDF-Read Pro (file PDF thật, có chữ tiếng Việt, một phần dạng ảnh scan).

    py tests\\make_sample_data.py ["thư mục đích"]

Mặc định tạo tại Desktop\\Du_lieu_test_PDFReadPro (không đụng tới thư mục khác; nếu thư mục đích đã có
thì tạo bản mới " (2)", " (3)"…). Kèm file DANH_SACH_LOI_CO_Y.txt liệt kê các lỗi được cài sẵn để đối chiếu."""
from __future__ import annotations

import io
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf as fitz  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

from pdfread_pro.core import rules1361  # noqa: E402

FONT = r"C:\Windows\Fonts\times.ttf"
FONT_B = r"C:\Windows\Fonts\timesbd.ttf"
A4 = (595.276, 841.89)
A3L = (1190.55, 841.89)
RULES = rules1361.default_rules()
FIVE = ["01", "02", "03", "04", "05"]

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
DEM = ["Văn", "Thị", "Hữu", "Minh", "Ngọc", "Thanh", "Quốc", "Thu", "Đức", "Kim", "Xuân", "Hoài"]
TEN = ["An", "Bình", "Cường", "Dũng", "Giang", "Hà", "Hải", "Hùng", "Lan", "Linh", "Long", "Mai", "Nam", "Nga",
       "Phúc", "Quang", "Sơn", "Tâm", "Thảo", "Trang", "Tuấn", "Vy", "Yến", "Khoa", "Huyền", "Lộc"]
TINH = ["056", "079", "001", "048", "052", "054", "058", "060", "064", "066", "075", "082"]

LOG: list = []                       # (vị trí, lỗi cài sẵn)


def no_accent(s: str) -> str:
    from pdfread_pro.core.renamer import remove_accents
    return remove_accents(s)


def person(rng: random.Random):
    name = f"{rng.choice(HO)} {rng.choice(DEM)} {rng.choice(TEN)}"
    cccd = rng.choice(TINH) + str(rng.randint(0, 3)) + f"{rng.randint(0, 99):02d}" + f"{rng.randint(0, 999999):06d}"
    return name, cccd


def folder_name(name: str, cccd: str) -> str:
    return f"{cccd}_" + "".join(w.capitalize() for w in no_accent(name).split())


def text(page, xy, s, size=12, bold=False):
    page.insert_text(xy, s, fontsize=size, fontname="tb" if bold else "tr", fontfile=FONT_B if bold else FONT)


def doc_pdf(title: str, name: str, cccd: str, chibo: str, pages: int, rng: random.Random) -> fitz.Document:
    """Văn bản giả lập: quốc hiệu, tên giấy tờ, thông tin người, các dòng nội dung, số trang ở chân trang."""
    d = fitz.open()
    for p in range(1, pages + 1):
        pg = d.new_page(width=A4[0], height=A4[1])
        if p == 1:
            text(pg, (150, 70), "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", 13, True)
            text(pg, (205, 90), "Độc lập - Tự do - Hạnh phúc", 13, True)
            w = fitz.get_text_length(title.upper(), fontsize=16) * 1.05
            text(pg, (max(40, (A4[0] - w) / 2), 150), title.upper(), 16, True)
            y = 200
            for k, v in (("Họ và tên", name), ("Số CCCD", cccd), ("Chi bộ", chibo),
                         ("Ngày sinh", f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.randint(1960, 2002)}"),
                         ("Quê quán", rng.choice(["Khánh Hòa", "Phú Yên", "Ninh Thuận", "Bình Định", "Quảng Ngãi"]))):
                text(pg, (70, y), f"{k}: {v}", 13)
                y += 26
        else:
            y = 80
        while y < 760:
            text(pg, (70, y), "Nội dung kê khai " + "." * rng.randint(60, 95), 12)
            y += 24
        text(pg, (A4[0] / 2 - 10, 815), f"- {p} -", 11)
    return d


def scanify(d: fitz.Document, dpi: int, rng: random.Random, quality: int = 55) -> fitz.Document:
    """Biến thành bản 'scan': ảnh xám, nghiêng nhẹ, nhiễu, nén JPEG."""
    out = fitz.open()
    for pg in d:
        pix = pg.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        im = im.rotate(rng.uniform(-0.8, 0.8), fillcolor=250, resample=Image.BICUBIC)
        im = Image.blend(im, Image.effect_noise(im.size, 20), 0.1).filter(ImageFilter.GaussianBlur(0.5))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=quality)
        np_ = out.new_page(width=pg.rect.width, height=pg.rect.height)
        np_.insert_image(np_.rect, stream=b.getvalue())
    return out


def save(d: fitz.Document, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    d.save(path, garbage=3, deflate=True)


def write_doc(folder, filename, code, name, cccd, chibo, rng, scan=None):
    title = RULES.get(code, "Giấy tờ khác").split(".", 1)[-1].replace("_", " ")
    d = doc_pdf(title, name, cccd, chibo, rng.randint(1, 4), rng)
    if scan if scan is not None else rng.random() < 0.35:
        d = scanify(d, 110, rng)
    save(d, os.path.join(folder, filename))


# ------------------------------------------------------------------ 1. Hồ sơ số hóa (báo cáo)

def make_hoso(root: str, rng: random.Random):
    base = os.path.join(root, "Hồ sơ số hóa")
    plan = {"Chi bo 1 Phuoc An Hoa": 9, "Chi bo Phu Tho Cuong": 8, "Chi bo 3 Vinh Hai": 7, "Chi bo Khu pho 4": 0}
    used = []
    errors = ["missing", "badfile", "badfolder_accent", "extra", "multipart", "signed", "noname", "missing2",
              "cccd11", "badfolder_caps", "nested", "empty", "corrupt", "dupcccd", "unknown", "wrongprov"]
    slots = [(cb, i) for cb, n in plan.items() for i in range(n)]
    rng.shuffle(slots)
    err_for = {s: e for s, e in zip(slots, errors)}
    for cb, n in plan.items():
        cbdir = os.path.join(base, cb)
        os.makedirs(cbdir, exist_ok=True)
        if n == 0:
            LOG.append((cb, "Chi bộ chưa có hồ sơ nào"))
        for i in range(n):
            name, cccd = person(rng)
            err = err_for.get((cb, i), "")
            if err == "dupcccd" and used:
                cccd = used[0][1]
            if err == "wrongprov":
                cccd = "999" + cccd[3:]
            used.append((name, cccd))
            fname = folder_name(name, cccd)
            if err == "badfolder_accent":
                fname = f"{cccd} - {name}"
            elif err == "badfolder_caps":
                fname = f"{cccd}_{no_accent(name).replace(' ', '').upper()}"
            elif err == "cccd11":
                fname = folder_name(name, cccd[:-1])
            elif err == "noname":
                fname = "".join(w.capitalize() for w in no_accent(name).split())
            d = os.path.join(cbdir, fname)
            os.makedirs(d, exist_ok=True)
            rel = f"{cb}\\{fname}"
            if err == "empty":
                LOG.append((rel, "Thư mục hồ sơ trống"))
                continue
            codes = list(FIVE)
            if err == "missing":
                drop = rng.choice(FIVE)
                codes.remove(drop)
                LOG.append((rel, f"Thiếu file {drop}"))
            if err == "missing2":
                codes = ["01", "02", "04"]
                LOG.append((rel, "Thiếu file 03, 05"))
            for c in codes:
                fn = RULES[c] + ".pdf"
                if err == "badfile" and c == "02":
                    fn = "2 ly lich dang vien.pdf"
                    LOG.append((rel, "Sai tên file 02 (2 ly lich dang vien.pdf)"))
                if err == "signed" and c in ("01", "05"):
                    fn = RULES[c] + ".signed.pdf"
                if err == "multipart" and c == "03":
                    for k in (1, 2):
                        write_doc(d, f"{RULES[c]}.{k}.pdf", c, name, cccd, cb, rng)
                    continue
                write_doc(d, fn, c, name, cccd, cb, rng)
            if err == "signed":
                LOG.append((rel, "File 01, 05 có đuôi .signed nhưng không có chữ ký số thật → Tổng quan báo 'Cần xem lại'"))
            if err == "multipart":
                LOG.append((rel, "File 03 gồm 2 phần .1 .2 (hợp lệ)"))
            if err == "extra":
                write_doc(d, RULES["06"] + ".pdf", "06", name, cccd, cb, rng)
                LOG.append((rel, "Có giấy tờ khác mã 06 đúng tên (hợp lệ, không bắt buộc) → vẫn Đạt chuẩn"))
            if err == "unknown":
                write_doc(d, "scan moi 2026.pdf", "", name, cccd, cb, rng, scan=True)
                LOG.append((rel, "Có file không xác định loại (scan moi 2026.pdf)"))
            if err == "nested":
                write_doc(os.path.join(d, "Ban cu"), RULES["01"] + ".pdf", "01", name, cccd, cb, rng)
                LOG.append((rel, "Có thư mục con 'Ban cu' bên trong hồ sơ"))
            if err == "corrupt":
                with open(os.path.join(d, RULES["04"] + ".pdf"), "wb") as fh:
                    fh.write(b"%PDF-1.7\n% file bi hong\n" + os.urandom(3000))
                LOG.append((rel, "File 04 bị hỏng (không mở được)"))
            for e, msg in (("badfolder_accent", "Tên thư mục có dấu, khoảng trắng → chuẩn hoá được"),
                           ("badfolder_caps", "Tên viết HOA liền → phải sửa tay"),
                           ("cccd11", "Số CCCD chỉ có 11 chữ số"), ("noname", "Tên thư mục thiếu số CCCD"),
                           ("dupcccd", "Trùng số CCCD với hồ sơ khác"), ("wrongprov", "Mã tỉnh 999 không tồn tại")):
                if err == e:
                    LOG.append((rel, msg))
    write_doc(os.path.join(base, "Chi bo Phu Tho Cuong"), "scan chua phan loai.pdf", "", "Không rõ", "", "", rng, scan=True)
    LOG.append(("Chi bo Phu Tho Cuong\\scan chua phan loai.pdf", "File nằm thẳng trong chi bộ (lạc chỗ)"))


# ------------------------------------------------------------------ 2. Chưa đổi tên (tab Đổi tên 1361)

def make_rename(root: str, rng: random.Random):
    for k in range(3):
        name, cccd = person(rng)
        d = os.path.join(root, "Chua doi ten", folder_name(name, cccd))
        for c, fn in (("01", "1.pdf"), ("02", "2 ly lich.pdf"), ("03", "03-phieu dang vien.pdf"),
                      ("04", "4. phieu bo sung.pdf"), ("05", "5.QD ket nap.signed.pdf"), ("13", "13 QD huy.pdf"),
                      ("02", "2 ly lich (trang sau).pdf")):
            if k == 2 and c == "13":
                continue
            write_doc(d, fn, c, name, cccd, "", rng)
    write_doc(os.path.join(root, "Chua doi ten"), "Tai lieu khong co ma.pdf", "", "", "", "", rng)
    LOG.append(("Chua doi ten\\", "Tên file thô (1.pdf, 2 ly lich.pdf…) → dùng tab Đổi tên (bộ quy tắc 1361); "
                                  "2 file mã 02 trong 1 thư mục → .1, .2"))


# ------------------------------------------------------------------ 3. Tách trang (A3, A4, sổ gỡ ghim)

def content_page(i: int, title: str, w=420.0, h=595.0) -> fitz.Document:
    d = fitz.open()
    pg = d.new_page(width=w, height=h)
    text(pg, (40, 55), f"{title} – TRANG {i}", 13, True)
    for k in range(17):
        text(pg, (40, 90 + k * 25), f"Dòng {k + 1}: thông tin kê khai trang {i} " + "." * 30, 11)
    text(pg, (w / 2 - 8, h - 20), f"- {i} -", 11)
    return d


def booklet(n_pages: int, face_size, opts, title: str, rng) -> fitz.Document:
    from pdfread_pro.core import splitter as S
    scan = fitz.open()
    for _ in range(n_pages // 2):
        scan.new_page(width=face_size[0], height=face_size[1])
    units, _ = S.plan_units(scan, opts)
    for i, u in enumerate(units):
        scan[u.src].show_pdf_page(u.clip, content_page(i + 1, title), 0, rotate=-u.rotate)
    return scanify(fitz.open("pdf", scan.tobytes()), 150, rng, 60)


def make_split(root: str, rng: random.Random):
    from dataclasses import replace
    from pdfread_pro.core import splitter as S
    d = os.path.join(root, "Tach trang")
    base = S.PRESETS["booklet"][1]
    save(booklet(12, A3L, replace(base, post_rotation="none"), "SỔ LÝ LỊCH (A3 ngang, tờ ngoài trước)", rng),
         os.path.join(d, "So_ly_lich_A3_go_ghim.pdf"))
    save(booklet(16, A3L, replace(base, post_rotation="none", sheet_order="inner", flip_back="yes"),
                 "SỔ ĐẢNG VIÊN (tờ giữa trước, mặt sau lộn ngược)", rng),
         os.path.join(d, "So_dang_vien_dat_nguoc.pdf"))
    save(booklet(12, A4, replace(base, post_rotation="ccw", flip_back="yes"),
                 "SỔ A5 (giấy A4 dọc, 2 trang trên-dưới)", rng),
         os.path.join(d, "So_A5_scan_A4_doc.pdf"))
    save(booklet(8, A3L, S.SplitOptions(), "A3 TÁCH LẦN LƯỢT", rng), os.path.join(d, "A3_ngang_2_trang_A4.pdf"))
    save(booklet(6, A4, S.SplitOptions(split_mode="top_bottom"), "A4 CHIA ĐÔI", rng),
         os.path.join(d, "A4_chia_doi_tren_duoi.pdf"))
    LOG.append(("Tach trang\\", "5 file: sổ gỡ ghim A3 (12 tr), sổ đặt ngược + mặt sau lộn (16 tr), sổ A5 scan dọc (12 tr), "
                                "A3 → A4 lần lượt, A4 chia đôi → mẫu Sổ lý lịch + Tự đọc số trang phải ra đúng 1→N"))


# ------------------------------------------------------------------ 4. Giảm dung lượng (ảnh nặng)

def make_heavy(root: str, rng: random.Random):
    d = os.path.join(root, "Giam dung luong")
    for k in range(1, 4):
        name, cccd = person(rng)
        doc = doc_pdf(f"Bản scan màu chất lượng cao {k}", name, cccd, "", 3 + k, rng)
        out = fitz.open()
        for pg in doc:
            pix = pg.get_pixmap(dpi=200)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            im = Image.blend(im, Image.effect_noise(im.size, 40).convert("RGB"), 0.15)
            b = io.BytesIO()
            im.save(b, "JPEG", quality=95)
            p = out.new_page(width=pg.rect.width, height=pg.rect.height)
            p.insert_image(p.rect, stream=b.getvalue())
        save(out, os.path.join(d, f"Scan_mau_nang_{k}.pdf"))
    LOG.append(("Giam dung luong\\", "3 file ảnh màu nặng (>200 KB/trang) để thử nén"))


def main():
    rng = random.Random(2026)
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "Desktop",
                                                                "Du_lieu_test_PDFReadPro")
    root, i = target, 2
    while os.path.exists(root):
        root = f"{target} ({i})"
        i += 1
    os.makedirs(root)
    make_hoso(root, rng)
    make_rename(root, rng)
    make_split(root, rng)
    make_heavy(root, rng)
    with open(os.path.join(root, "DANH_SACH_LOI_CO_Y.txt"), "w", encoding="utf-8-sig") as fh:
        fh.write("DỮ LIỆU TEST PDF-Read Pro – các lỗi được cài sẵn để đối chiếu\n")
        fh.write("Quét thư mục 'Hồ sơ số hóa' → tab Báo cáo hồ sơ; thư mục 'Chua doi ten' → tab Đổi tên;\n")
        fh.write("'Tach trang' → tab Tách trang (mẫu Sổ lý lịch); 'Giam dung luong' → tab Giảm dung lượng.\n\n")
        for where, what in LOG:
            fh.write(f"- {where}: {what}\n")
    n = sum(len([f for f in fs if f.endswith(".pdf")]) for _, _, fs in os.walk(root))
    size = sum(os.path.getsize(os.path.join(a, f)) for a, _, fs in os.walk(root) for f in fs)
    print(f"{root}\n{n} file PDF · {size / 1048576:.1f} MB · {len(LOG)} lỗi cài sẵn")


if __name__ == "__main__":
    main()
