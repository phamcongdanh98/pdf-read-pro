"""Bộ quy tắc mã số Hồ sơ 1361 (mã → tên mẫu tiêu chuẩn): nạp, lưu, nhập/xuất, khôi phục mặc định."""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Tuple

_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "default_rules_1361.json")


def _store_path() -> str:
    from ..paths import data_file
    return data_file("rules_1361.json")


def rule_sort_key(code: str):
    """Sắp xếp mã: 01, 02 … 61, 6123, 6124 … 70, 70cc, 70sc … 100 (mã 4 số = mã 2 số + năm)."""
    m = re.match(r"^(\d+)(.*)$", code)
    if not m:
        return (10 ** 6, code)
    digits, rest = m.groups()
    if len(digits) == 4:
        return (int(digits[:2]), digits[2:] + rest)
    return (int(digits), rest)


def default_rules() -> Dict[str, str]:
    with open(_DEFAULT, "r", encoding="utf-8") as fh:
        return json.load(fh)


def sorted_items(rules: Dict[str, str]) -> List[Tuple[str, str]]:
    return sorted(rules.items(), key=lambda kv: rule_sort_key(kv[0]))


def load_rules() -> Dict[str, str]:
    try:
        with open(_store_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data:
            return {str(k): str(v) for k, v in data.items()}
    except (OSError, ValueError):
        pass
    return default_rules()


def save_rules(rules: Dict[str, str]) -> None:
    p = _store_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted_items(rules)), fh, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def reset_defaults() -> Dict[str, str]:
    rules = default_rules()
    save_rules(rules)
    return rules


def normalize_key(key: str) -> str:
    return key.strip().lower()


def validate_rule(key: str, name: str) -> str:
    if not re.fullmatch(r"\d{1,4}[a-z]*", normalize_key(key)):
        return "Mã số phải bắt đầu bằng 1–4 chữ số, có thể kèm chữ thường (VD: 01, 07a, 86dh)."
    if not name.strip():
        return "Tên mẫu tiêu chuẩn không được để trống."
    if re.search(r'[<>:"/\\|?*]', name):
        return 'Tên mẫu không được chứa ký tự  < > : " / \\ | ? *'
    return ""


def parse_file(path: str) -> Dict[str, str]:
    """Đọc .json ({mã: tên}) hoặc .txt (mỗi dòng: `mã|tên`, `mã: tên`, `mã<TAB>tên` hoặc chỉ `tên` bắt đầu bằng mã)."""
    with open(path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()
    if path.lower().endswith(".json"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("File JSON phải là dạng {\"mã\": \"tên mẫu\"}.")
        rules = {normalize_key(str(k)): str(v).strip() for k, v in data.items()}
    else:
        rules = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^(\d{1,4}[a-zA-Z]*)\s*[|:\t=]\s*(.+)$", line)
            if m:
                rules[normalize_key(m.group(1))] = m.group(2).strip()
                continue
            m = re.match(r"^(\d{1,4}[a-zA-Z]*)[.\s_]", line)
            if m:
                rules[normalize_key(m.group(1))] = line
    bad = [k for k, v in rules.items() if validate_rule(k, v)]
    for k in bad:
        rules.pop(k)
    if not rules:
        raise ValueError("Không tìm thấy quy tắc hợp lệ nào trong file.")
    return rules


def export_file(rules: Dict[str, str], path: str) -> None:
    items = sorted_items(rules)
    with open(path, "w", encoding="utf-8") as fh:
        if path.lower().endswith(".txt"):
            fh.write("\n".join(f"{k}|{v}" for k, v in items) + "\n")
        else:
            json.dump(dict(items), fh, ensure_ascii=False, indent=2)


def normalize_name(key: str, name: str) -> str:
    """Chuẩn hoá tên mẫu như Hồ sơ 1361: bỏ dấu, khoảng trắng → _, có tiền tố mã số.
    VD: ('86dh', '86. Bang dai hoc') → '86.Bang_dai_hoc' ; ('87bd', 'QĐ bổ nhiệm') → '87.QD_bo_nhiem'."""
    from .renamer import remove_accents
    s = remove_accents(name.strip())
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    m = re.match(r"^(\d+)[a-zA-Z]*[\s._\-]*(.*)$", s)
    digits = re.match(r"\d+", normalize_key(key)).group(0) if re.match(r"\d+", normalize_key(key)) else ""
    major = digits[:2] if len(digits) == 4 else digits
    if m:
        s = f"{m.group(1)}.{m.group(2)}" if m.group(2) else m.group(1)
    elif major:
        s = f"{major}.{s}"
    return s
