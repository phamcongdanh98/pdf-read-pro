"""Tạo file PDF mẫu: SỔ LÝ LỊCH GỠ GHIM scan 2 mặt (để thử tab Tách trang → mẫu "Sổ lý lịch gỡ ghim").

Sổ 12 trang A4 = 3 tờ A3 gập đôi, đóng ghim giữa. Gỡ ghim rồi scan 2 mặt từng tờ (tờ ngoài cùng trước):
  tờ 1: mặt trước [12 | 1]   mặt sau [2 | 11]
  tờ 2: mặt trước [10 | 3]   mặt sau [4 | 9]
  tờ 3: mặt trước [8 | 5]    mặt sau [6 | 7]
Mặt sau bị lộn ngược 180° như máy scan ADF lật giấy. Số trang in ở chân trang ("- 7 -").
Mỗi mặt là ẢNH scan (có nhiễu, giấy ngả màu) → app phải đọc số trang bằng OCR như bản scan thật.

Chạy: py tests/make_booklet_sample.py [đường_dẫn.pdf] [số_trang (bội của 4)]"""
import io
import os
import random
import sys

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DPI = 150
A4 = (int(8.27 * DPI), int(11.69 * DPI))       # 1240 × 1754 điểm ảnh

CONTENT = [
    ("LÝ LỊCH ĐẢNG VIÊN", ["Họ và tên khai sinh: NGUYỄN VĂN AN", "Tên gọi khác: không", "Ngày sinh: 12/05/1985",
                           "Quê quán: Phường Phước Hải, tỉnh Khánh Hòa", "Nơi ở hiện nay: Tổ dân phố 1 An Hòa"]),
    ("I. TÓM TẮT QUÁ TRÌNH", ["Từ 1991 đến 2003: học phổ thông tại địa phương",
                             "Từ 2003 đến 2007: sinh viên Trường Đại học Nha Trang",
                             "Từ 2007 đến nay: công tác tại Ủy ban nhân dân phường"]),
    ("II. HOÀN CẢNH GIA ĐÌNH", ["Họ tên cha: Nguyễn Văn Bình, sinh năm 1955, nông dân",
                               "Họ tên mẹ: Trần Thị Cúc, sinh năm 1958, nội trợ",
                               "Vợ: Lê Thị Dung, sinh năm 1987, giáo viên"]),
    ("III. KHEN THƯỞNG, KỶ LUẬT", ["Năm 2015: Giấy khen của Ủy ban nhân dân phường",
                                  "Năm 2019: Chiến sĩ thi đua cơ sở", "Kỷ luật: không"]),
]


def _font(size, bold=False):
    for n in (("arialbd.ttf" if bold else "arial.ttf"), "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def page_image(n: int, total: int) -> Image.Image:
    """1 trang A4 của sổ: tiêu đề, nội dung, số trang ở chân trang."""
    im = Image.new("L", A4, 238)
    d = ImageDraw.Draw(im)
    title, lines = CONTENT[(n - 1) % len(CONTENT)]
    if n == 1:
        d.text((A4[0] // 2, 230), "ĐẢNG CỘNG SẢN VIỆT NAM", fill=25, font=_font(44, True), anchor="mm")
        d.text((A4[0] // 2, 330), "SỔ LÝ LỊCH ĐẢNG VIÊN", fill=25, font=_font(56, True), anchor="mm")
        y = 520
    else:
        d.text((A4[0] // 2, 170), f"{title} (tiếp theo)" if n > len(CONTENT) else title, fill=25,
               font=_font(38, True), anchor="mm")
        y = 290
    body = _font(30)
    k = 0
    while y < A4[1] - 300:
        d.text((120, y), lines[k % len(lines)] + ("" if k < len(lines) else f" – ghi chú {k}"), fill=30, font=body)
        y += 62
        k += 1
    d.text((A4[0] // 2, A4[1] - 110), f"- {n} -", fill=20, font=_font(34), anchor="mm")
    return im


def booklet_faces(total: int):
    """Thứ tự các mặt scan: [(trang nửa trái, trang nửa phải, lộn ngược?)] – tờ ngoài cùng trước."""
    faces = []
    for s in range(total // 4):
        faces.append((total - 2 * s, 1 + 2 * s, False))          # mặt trước
        faces.append((2 + 2 * s, total - 1 - 2 * s, True))       # mặt sau (ADF lật ngược)
    return faces


def make(path: str, total: int = 12, seed: int = 7) -> str:
    assert total % 4 == 0 and total >= 4, "số trang sổ phải là bội của 4"
    rnd = random.Random(seed)
    pages = {n: page_image(n, total) for n in range(1, total + 1)}
    doc = fitz.open()
    for left, right, upside in booklet_faces(total):
        face = Image.new("L", (A4[0] * 2, A4[1]), 238)
        face.paste(pages[left], (0, 0))
        face.paste(pages[right], (A4[0], 0))
        ImageDraw.Draw(face).line([(A4[0], 0), (A4[0], A4[1])], fill=200, width=3)       # nếp gập giữa
        if upside:
            face = face.rotate(180)
        face = face.rotate(rnd.uniform(-0.6, 0.6), fillcolor=238, resample=Image.BICUBIC)  # scan hơi lệch
        px = face.load()
        for _ in range(face.width * face.height // 400):                                      # bụi / nhiễu
            px[rnd.randrange(face.width), rnd.randrange(face.height)] = rnd.randrange(120, 230)
        face = face.filter(ImageFilter.GaussianBlur(0.5)).convert("RGB")
        buf = io.BytesIO()
        face.save(buf, "JPEG", quality=75, dpi=(DPI, DPI))
        pg = doc.new_page(width=1190.55, height=841.89)
        pg.insert_image(pg.rect, stream=buf.getvalue())
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    doc.save(path, garbage=3, deflate=True)
    return path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "Desktop",
                                                               "Mau_so_ly_lich_go_ghim.pdf")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 12
    print("Đã tạo:", make(out, n))
    for i, (l, r, up) in enumerate(booklet_faces(n), 1):
        print(f"  mặt scan {i}: [{l} | {r}]" + ("  (lộn ngược)" if up else ""))
