"""Tạo BỘ HỒ SƠ SỐ HOÁ CHUẨN cỡ lớn để thử báo cáo:

    py tests\\make_big_dataset.py ["thư mục đích"] [số người] [số chi bộ]

Mặc định: 60 chi bộ, 450 người tại Desktop\\HoSoSoHoa_Test\\Hồ sơ số hóa.
- Thư mục hồ sơ đặt chuẩn: 12 số CCCD (không trùng) + "_" + Họ tên không dấu, viết hoa chữ cái đầu mỗi từ
  (VD 056123456789_TranVanThai).
- File PDF đặt tên theo bộ quy tắc 1361 (124 mã): 01–05 bắt buộc + vài giấy tờ khác ngẫu nhiên trong bộ quy tắc.
- Mô phỏng ký số: bản X.signed.pdf nằm cạnh X.pdf (60% hồ sơ ký hết 01–05, 20% ký 1 phần, 20% chưa ký)
  → thử lựa chọn "Tính file: Cả 2 / Chỉ đã ký / Chỉ chưa ký" ở tab Báo cáo.
- Cố ý cho một số người THIẾU file 01 và/hoặc 02. Danh sách đáp án ghi ở DAP_AN_THIEU_FILE.csv để đối chiếu."""
from __future__ import annotations

import csv
import os
import random
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf as fitz  # noqa: E402

from pdfread_pro.core import rules1361  # noqa: E402
from pdfread_pro.core.renamer import remove_accents  # noqa: E402

FONT = r"C:\Windows\Fonts\times.ttf"
FONT_B = r"C:\Windows\Fonts\timesbd.ttf"
A4 = (595.276, 841.89)
RULES = rules1361.default_rules()
REQUIRED = ["01", "02", "03", "04", "05"]
OPTIONAL = [k for k in RULES if k not in REQUIRED]

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô",
      "Dương", "Lý", "Đinh", "Trương", "Lâm", "Mai", "Tô", "Hà", "Châu", "Cao"]
DEM = ["Văn", "Thị", "Hữu", "Minh", "Ngọc", "Thanh", "Quốc", "Thu", "Đức", "Kim", "Xuân", "Hoài", "Công", "Bảo",
       "Thùy", "Gia", "Anh", "Phương", "Mỹ", "Trung"]
TEN = ["An", "Bình", "Cường", "Dũng", "Giang", "Hà", "Hải", "Hùng", "Lan", "Linh", "Long", "Mai", "Nam", "Nga",
       "Phúc", "Quang", "Sơn", "Tâm", "Thảo", "Trang", "Tuấn", "Vy", "Yến", "Khoa", "Huyền", "Lộc", "Thái", "Hiếu",
       "Nhung", "Tín", "Khánh", "Duy", "Hạnh", "Phát", "Quyên", "Thịnh", "Uyên", "Việt", "Như", "Đạt"]
NOI = ["Phước Hải", "Phước Long", "Phước Tân", "Phước Hòa", "Phước Tiến", "Phước Tín", "Phương Sài", "Phương Sơn",
       "Ngọc Hiệp", "Vĩnh Hải", "Vĩnh Phước", "Vĩnh Thọ", "Vĩnh Nguyên", "Vĩnh Trường", "Xương Huân", "Vạn Thắng",
       "Vạn Thạnh", "Lộc Thọ", "Tân Lập", "Phước An Hòa", "Phú Thọ Cường", "Bắc Thành", "Nam Hải", "Đông Hòa"]
TINH = ["056", "079", "001", "048", "052", "054", "058", "060", "064", "066", "075", "082", "040", "044", "046"]


def chibo_names(n: int, rng: random.Random):
    out, used = [], set()
    while len(out) < n:
        kind = rng.choice(["Khu phố", "Tổ dân phố", "Thôn", "Tổ"])
        num = rng.randint(1, 12)
        place = rng.choice(NOI)
        name = f"Chi bộ {len(out) + 1:02d} {kind} {num} {place}"
        if (kind, num, place) not in used:
            used.add((kind, num, place))
            out.append(name)
    return out


def pascal(name: str) -> str:
    return "".join(w.capitalize() for w in remove_accents(name).split())


def text(page, xy, s, size=12, bold=False):
    page.insert_text(xy, s, fontsize=size, fontname="tb" if bold else "tr", fontfile=FONT_B if bold else FONT)


def make_pdf(path: str, code: str, name: str, cccd: str, chibo: str, pages: int):
    title = RULES[code].split(".", 1)[-1].replace("_", " ")
    d = fitz.open()
    for p in range(1, pages + 1):
        pg = d.new_page(width=A4[0], height=A4[1])
        if p == 1:
            text(pg, (150, 70), "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", 13, True)
            text(pg, (205, 90), "Độc lập - Tự do - Hạnh phúc", 13, True)
            text(pg, (60, 150), f"[{code}] {title.upper()}"[:70], 14, True)
            for k, (lab, v) in enumerate((("Họ và tên", name), ("Số CCCD", cccd), ("Đơn vị", chibo))):
                text(pg, (70, 200 + k * 26), f"{lab}: {v}", 13)
        text(pg, (70, 320), "Nội dung giấy tờ (bản số hoá dùng để thử nghiệm).", 12)
        text(pg, (A4[0] / 2 - 10, 815), f"- {p} -", 11)
    d.subset_fonts()                                  # nhúng tập con font → file nhỏ
    d.save(path, garbage=3, deflate=True)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "Desktop", "HoSoSoHoa_Test")
    n_people = int(sys.argv[2]) if len(sys.argv) > 2 else 450
    n_chibo = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    if not 1 <= n_chibo <= n_people <= 5000:
        raise SystemExit("Số người / chi bộ không hợp lệ")
    rng = random.Random(1361)
    top, i = target, 2
    while os.path.exists(top):                       # không đụng dữ liệu cũ
        top = f"{target} ({i})"
        i += 1
    root = os.path.join(top, "Hồ sơ số hóa")
    chibos = chibo_names(n_chibo, rng)
    # chia người cho chi bộ: mỗi chi bộ ≥ 3 người, phần còn lại ngẫu nhiên
    sizes = [3] * n_chibo
    for _ in range(n_people - 3 * n_chibo):
        sizes[rng.randrange(n_chibo)] += 1
    used_cccd, answers, t0, n_files = set(), [], time.time(), 0
    for cb, size in zip(chibos, sizes):
        for _ in range(size):
            name = f"{rng.choice(HO)} {rng.choice(DEM)} {rng.choice(TEN)}"
            while True:
                cccd = (rng.choice(TINH) + str(rng.choice([0, 1, 2, 3])) + f"{rng.randint(50, 99) if rng.random() < .5 else rng.randint(0, 5):02d}"
                        + f"{rng.randint(0, 999999):06d}")
                if cccd not in used_cccd:
                    used_cccd.add(cccd)
                    break
            folder = os.path.join(root, cb, f"{cccd}_{pascal(name)}")
            os.makedirs(folder)
            r = rng.random()
            missing = ["01"] if r < 0.07 else ["02"] if r < 0.14 else ["01", "02"] if r < 0.17 else []
            codes = [c for c in REQUIRED if c not in missing]
            codes += rng.sample(OPTIONAL, rng.choice([0, 0, 1, 1, 2, 2, 3, 4]))
            # ký số: khi ký sinh thêm bản X.signed.pdf bên cạnh X.pdf – 60% ký hết, 20% ký 1 phần, 20% chưa ký
            sr = rng.random()
            sign_mode = "full" if sr < 0.6 else "partial" if sr < 0.8 else "none"
            for c in codes:
                if c == "03" and rng.random() < 0.05:        # vài hồ sơ có giấy tờ nhiều phần .1 .2 (hợp lệ)
                    for k in (1, 2):
                        make_pdf(os.path.join(folder, f"{RULES[c]}.{k}.pdf"), c, name, cccd, cb, 1)
                        n_files += 1
                    continue
                src = os.path.join(folder, f"{RULES[c]}.pdf")
                make_pdf(src, c, name, cccd, cb, rng.randint(1, 3))
                n_files += 1
                if c in REQUIRED and (sign_mode == "full" or (sign_mode == "partial" and rng.random() < 0.5)):
                    shutil.copy2(src, src[:-4] + ".signed.pdf")
                    n_files += 1
            if missing:
                answers.append((cb, f"{cccd}_{pascal(name)}", cccd, name, ", ".join(missing)))
        print(f"  {cb}: {size} hồ sơ", flush=True)
    with open(os.path.join(top, "DAP_AN_THIEU_FILE.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Chi bộ", "Thư mục hồ sơ", "Số CCCD", "Họ và tên", "Thiếu mã"])
        w.writerows(answers)
    size_mb = sum(os.path.getsize(os.path.join(a, f)) for a, _, fs in os.walk(top) for f in fs) / 1048576
    print(f"\n{root}\n{n_chibo} chi bộ · {n_people} hồ sơ · {n_files} file PDF · {size_mb:.1f} MB · "
          f"{len(answers)} hồ sơ thiếu file · {time.time() - t0:.0f} giây")


if __name__ == "__main__":
    main()
