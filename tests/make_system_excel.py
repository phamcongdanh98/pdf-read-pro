"""Tạo file Excel "DANH SÁCH ĐẢNG VIÊN ĐÃ SỐ HÓA" giả lập (như xuất từ hệ thống) từ một thư mục Hồ sơ số hóa,
cài sẵn các kiểu lệch để thử tab Đối chiếu danh sách:

    py tests\\make_system_excel.py "<thư mục Hồ sơ số hóa>" ["<file xlsx đầu ra>"]

Họ tên có dấu đọc từ dòng "Họ và tên: …" trong PDF của từng hồ sơ (dữ liệu do make_big_dataset tạo).
Kèm DAP_AN_DOI_CHIEU.csv cạnh file Excel."""
from __future__ import annotations

import csv
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf as fitz  # noqa: E402
from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font  # noqa: E402

from pdfread_pro.core import report as R  # noqa: E402

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Võ", "Đặng"]
TEN = ["Khôi", "Ngân", "Phong", "Diệp", "Kiên", "Trâm", "Hưng", "Oanh"]


def person_name(folder: str) -> str:
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith(".pdf"):
            try:
                with fitz.open(os.path.join(folder, f)) as d:
                    text = d[0].get_text().replace("\u00a0", " ")     # PDF dùng dấu cách không ngắt
                    m = re.search(r"Họ và tên:\s*(.+)", text)
                    if m:
                        return m.group(1).strip()
            except Exception:
                continue
    return ""


def chibo_variant(name: str, rng: random.Random) -> str:
    """Tên chi bộ trong hệ thống hơi khác tên thư mục (~90% giống)."""
    m = re.match(r"Chi bộ (\d+) (.+)", name)
    if not m:
        return name
    return rng.choice([f"Chi bộ {m.group(2)}", f"Chi bộ {int(m.group(1))} - {m.group(2)}", name, f"CB {m.group(2)}"])


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "Desktop", "HoSoSoHoa_Test",
                                                              "Hồ sơ số hóa")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(root), "Danh_sach_he_thong_mau.xlsx")
    rng = random.Random(77)
    people = []
    for cb in sorted(os.listdir(root)):
        cbp = os.path.join(root, cb)
        if not os.path.isdir(cbp):
            continue
        for hs in sorted(os.listdir(cbp)):
            m = re.match(r"(\d{12})_", hs)
            if m and os.path.isdir(os.path.join(cbp, hs)):
                people.append({"cccd": m.group(1), "name": person_name(os.path.join(cbp, hs)) or hs, "chibo": cb,
                               "folder": f"{cb}\\{hs}"})
    if not people:
        raise SystemExit("Không thấy thư mục hồ sơ nào")
    chibos = sorted({p["chibo"] for p in people})
    cb_text = {c: chibo_variant(c, rng) for c in chibos}
    answers = []
    rng.shuffle(people)
    n = len(people)
    removed = people[:15]                       # có thư mục nhưng không có trong hệ thống
    rows = people[15:]
    for p in rows[:10]:                         # lệch tên
        old = p["name"]
        p["name"] = f"{rng.choice(HO)} {old.split()[1] if len(old.split()) > 2 else 'Văn'} {rng.choice(TEN)}"
        answers.append(("Lệch tên", p["cccd"], p["name"], p["folder"],
                        f"Tên thư mục khác (cũ: {old})"))
    for p in rows[10:20]:                       # khác chi bộ
        other = rng.choice([c for c in chibos if c != p["chibo"]])
        answers.append(("Khác chi bộ", p["cccd"], p["name"], p["folder"], f"Hệ thống ghi {cb_text[other]}"))
        p["chibo"] = other
    for p in rows[20:28]:                       # gõ nhầm CCCD (1 chữ số)
        i = rng.randrange(4, 12)
        new = p["cccd"][:i] + str((int(p["cccd"][i]) + rng.randint(1, 8)) % 10) + p["cccd"][i + 1:]
        answers.append(("Nghi gõ nhầm CCCD", new, p["name"], p["folder"], f"Thư mục {p['cccd']}"))
        p["cccd"] = new
    for p in removed:
        answers.append(("Ngoài danh sách", p["cccd"], p["name"], p["folder"], "Không có trong hệ thống"))
    used = {p["cccd"] for p in people}
    for _ in range(20):                         # có trong hệ thống, chưa có thư mục
        while True:
            c = rng.choice(["056", "079", "058"]) + f"{rng.randint(0, 999999999):09d}"
            if c not in used:
                used.add(c)
                break
        p = {"cccd": c, "name": f"{rng.choice(HO)} Thị {rng.choice(TEN)}", "chibo": rng.choice(chibos), "folder": ""}
        rows.append(p)
        answers.append(("Chưa có thư mục", c, p["name"], "", cb_text[p["chibo"]]))
    rows.sort(key=lambda p: (p["chibo"], p["name"].split()[-1]))

    wb = Workbook()
    ws = wb.active
    ws.title = "Danh sach"
    ws.append(["ĐẢNG BỘ PHƯỜNG (DỮ LIỆU GIẢ LẬP)"])
    ws.append(["DANH SÁCH ĐẢNG VIÊN ĐÃ SỐ HÓA HỒ SƠ"])
    ws.append([])
    ws.append(["STT", "Họ và tên", "Ngày sinh", "Giới tính", "Số CCCD", "Ngày vào Đảng", "Số thẻ đảng", "Chi bộ",
               "Trạng thái số hóa"])
    for c in ws[4]:
        c.font = Font(bold=True)
    for i, p in enumerate(rows, 1):
        cccd = int(p["cccd"]) if rng.random() < 0.3 else p["cccd"]      # 30% lưu dạng số → mất số 0 đầu
        ws.append([i, p["name"], f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/{rng.randint(1960, 2000)}",
                   rng.choice(["Nam", "Nữ"]), cccd, f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/"
                   f"{rng.randint(1985, 2024)}", f"{rng.randint(10000000, 99999999)}", cb_text[p["chibo"]], "Đã số hóa"])
    for col, w in zip("ABCDEFGHI", (6, 26, 12, 9, 16, 14, 13, 40, 16)):
        ws.column_dimensions[col].width = w
    wb.save(out)
    with open(os.path.join(os.path.dirname(out), "DAP_AN_DOI_CHIEU.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Kết quả mong đợi", "Số CCCD (hệ thống)", "Họ và tên (hệ thống)", "Thư mục", "Chi tiết"])
        w.writerows(answers)
    print(f"{out}\n{len(rows)} người trong danh sách · {n} thư mục · {len(answers)} lệch cài sẵn")


if __name__ == "__main__":
    main()
