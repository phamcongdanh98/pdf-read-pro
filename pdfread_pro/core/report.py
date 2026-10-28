"""Báo cáo HỒ SƠ SỐ HOÁ theo cấu trúc chuẩn:

    Hồ sơ số hóa/                       ← thư mục gốc (quét)
        Chi bo 1 Phuoc An Hoa/           ← thư mục chi bộ
            056123456789_PhamVanA/       ← hồ sơ: 12 số CCCD + "_" + Họ tên không dấu, viết hoa chữ cái đầu mỗi từ
                01.Ly_lich_nguoi_xin_vao_Dang.pdf
                02.Ly_lich_dang_vien.pdf … 05.QD_ket_nap_dang_vien.pdf   ← tên theo bộ quy tắc 1361

Kiểm tra từng hồ sơ (tên thư mục, đủ file bắt buộc, tên file đúng mẫu, file lỗi, file thừa…), phân loại và
xuất Excel nhiều trang (Tổng hợp · Danh sách hồ sơ · Chi tiết file · Cần xử lý · Quy chuẩn)."""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Sequence, Tuple

from .models import FileInfo, ScanResult
from .renamer import _SIGNED_TAIL, match_rule_code, natural_key, remove_accents

DEFAULT_REQUIRED = ("01", "02", "03", "04", "05")

# tên giấy tờ có dấu để hiển thị trong báo cáo (mã khác: lấy từ tên mẫu 1361)
DOC_TITLES = {
    "01": "Lý lịch người xin vào Đảng",
    "02": "Lý lịch đảng viên",
    "03": "Phiếu đảng viên",
    "04": "Phiếu bổ sung hồ sơ đảng viên",
    "05": "Quyết định kết nạp đảng viên",
}

RESULT_OK, RESULT_MISSING = "Đủ", "Thiếu"

# tính file nào: khi ký số thường có 2 bản – X.pdf (chưa ký) và X.signed.pdf (đã ký)
SIGN_ALL, SIGN_ONLY, SIGN_NONE = "all", "signed", "unsigned"
SIGN_LABELS = {SIGN_ALL: "Cả file đã ký và chưa ký", SIGN_ONLY: "Chỉ file đã ký (.signed)",
               SIGN_NONE: "Chỉ file chưa ký (không .signed)"}


def doc_title(code: str, rules: Dict[str, str]) -> str:
    return DOC_TITLES.get(code) or rules.get(code, code).split(".", 1)[-1].replace("_", " ")

# trạng thái hồ sơ (thứ tự = mức nghiêm trọng)
ST_OK = "Đạt chuẩn"
ST_WARN = "Đạt – có cảnh báo"
ST_FIX = "Cần xử lý"            # file lỗi / trùng CCCD…
ST_NAME = "Sai tên"
ST_MISSING = "Thiếu file"
ST_EMPTY = "Thư mục trống"
STATUS_ORDER = (ST_EMPTY, ST_MISSING, ST_NAME, ST_FIX, ST_WARN, ST_OK)

LV_ERROR, LV_WARN = "Lỗi", "Cảnh báo"

_DOSSIER = re.compile(r"^(\d{12})_((?:[A-Z][a-z]*)+)$")
_LEADING_DIGITS = re.compile(r"^\s*(\d+)\s*[_\-.\s]*(.*)$")

# mã tỉnh/thành (3 số đầu CCCD) – 63 tỉnh, thành theo Thông tư 07/2016/TT-BCA (vẫn dùng trên thẻ đã cấp)
PROVINCE_CODES = frozenset(
    "001 002 004 006 008 010 011 012 014 015 017 019 020 022 024 025 026 027 030 031 033 034 035 036 037 038 "
    "040 042 044 045 046 048 049 051 052 054 056 058 060 062 064 066 067 068 070 072 074 075 077 079 080 082 "
    "083 084 086 087 089 091 092 093 094 095 096".split())


@dataclass
class Issue:
    level: str                 # Lỗi | Cảnh báo
    text: str                  # vấn đề
    fix: str = ""              # cách xử lý gợi ý


@dataclass
class DocFile:
    fi: FileInfo
    code: str = ""             # mã quy tắc khớp ('' = không xác định)
    rule: str = ""             # tên mẫu chuẩn của mã
    name_ok: bool = False
    required: bool = False     # thuộc danh mục bắt buộc
    note: str = ""


@dataclass
class Dossier:
    chibo: str
    folder: str                # tên thư mục hồ sơ
    path: str
    cccd: str = ""
    name: str = ""             # họ tên dạng "Pham Van A"
    folder_ok: bool = False
    suggestion: str = ""       # tên thư mục gợi ý (nếu sai)
    files: List[DocFile] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    status: str = ST_OK
    have: Dict[str, List[DocFile]] = field(default_factory=dict)   # mã bắt buộc → các file
    missing: List[str] = field(default_factory=list)
    excluded: List[DocFile] = field(default_factory=list)          # file bị bỏ qua theo lựa chọn đã ký / chưa ký

    @property
    def pages(self) -> int:
        return sum(d.fi.pages or 0 for d in self.files)

    @property
    def size(self) -> int:
        return sum(d.fi.size for d in self.files)

    @property
    def complete(self) -> bool:
        """Đủ = có đủ mọi file bắt buộc (file có nhưng đặt sai tên vẫn tính là có)."""
        return not self.missing

    @property
    def result(self) -> str:
        return RESULT_OK if self.complete else RESULT_MISSING

    @property
    def notes(self) -> List[str]:
        """Vấn đề khác ngoài việc thiếu file (không làm hồ sơ thành 'Thiếu')."""
        return [i.text for i in self.issues
                if not i.text.startswith(("Thiếu file:", "Thư mục hồ sơ chưa có file"))]

    @property
    def other_docs(self) -> int:
        return sum(1 for f in self.files if not f.required)

    @property
    def signed(self) -> int:
        return sum(1 for d in self.files if d.fi.has_real_sig)


@dataclass
class Stray:
    path: str
    rel: str
    note: str


@dataclass
class ChiboSummary:
    name: str
    dossiers: int = 0
    counts: Counter = field(default_factory=Counter)
    files: int = 0
    pages: int = 0
    size: int = 0


@dataclass
class Report:
    root: str
    mode: str                                  # root | chibo | dossier
    required: Tuple[str, ...]
    rules: Dict[str, str]
    sign_filter: str = SIGN_ALL
    dossiers: List[Dossier] = field(default_factory=list)
    stray: List[Stray] = field(default_factory=list)
    chibos: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    created: datetime = field(default_factory=datetime.now)

    def counts(self) -> Counter:
        return Counter(d.status for d in self.dossiers)

    def by_chibo(self) -> List[ChiboSummary]:
        out: Dict[str, ChiboSummary] = {c: ChiboSummary(c) for c in self.chibos}
        for d in self.dossiers:
            s = out.setdefault(d.chibo, ChiboSummary(d.chibo))
            s.dossiers += 1
            s.counts[d.status] += 1
            s.files += len(d.files)
            s.pages += d.pages
            s.size += d.size
        return list(out.values())

    def all_issues(self) -> List[Tuple[str, str, Issue]]:
        """(chi bộ, hồ sơ, vấn đề) – lỗi trước, cảnh báo sau."""
        rows = [(d.chibo, d.folder, i) for d in self.dossiers for i in d.issues]
        rows += [("", s.rel, Issue(LV_WARN, s.note, "Chuyển file vào đúng thư mục hồ sơ")) for s in self.stray]
        return sorted(rows, key=lambda r: (r[2].level != LV_ERROR, natural_key(r[0]), natural_key(r[1])))


# ------------------------------------------------------------------ tên thư mục hồ sơ

def split_name(pascal: str) -> str:
    """'PhamVanA' → 'Pham Van A'."""
    return " ".join(re.findall(r"[A-Z][a-z]*", pascal))


def suggest_folder_name(folder: str) -> str:
    """Gợi ý tên chuẩn 'CCCD_HoVaTen' từ tên đang có (bỏ dấu, viết hoa chữ cái đầu mỗi từ, bỏ khoảng trắng).
    VD '056123456789 - Phạm văn a' → '056123456789_PhamVanA'. Trả '' nếu không đoán được."""
    m = _LEADING_DIGITS.match(folder)
    if not m or not m.group(2).strip():
        return ""
    digits, rest = m.group(1), remove_accents(m.group(2))
    words = []
    for w in re.split(r"[^A-Za-z0-9]+", rest):
        if not w:
            continue
        if w.isupper() or w.islower():
            w = w.capitalize()
        else:
            w = w[0].upper() + w[1:]                     # đã viết kiểu PhamVanA → giữ
        words.append(w)
    name = "".join(words)
    return f"{digits}_{name}" if name else ""


def check_folder(folder: str) -> Tuple[bool, str, str, List[Issue], str]:
    """(đúng chuẩn, cccd, họ tên, vấn đề, gợi ý)."""
    issues: List[Issue] = []
    m = _DOSSIER.match(folder)
    if m and re.search(r"[A-Z]{3,}", m.group(2)):        # PHAMVANA: viết hoa cả tên, không tách được từ
        m = None
    if m:
        cccd, name = m.group(1), split_name(m.group(2))
        if cccd[:3] not in PROVINCE_CODES:
            issues.append(Issue(LV_WARN, f"Mã tỉnh “{cccd[:3]}” ở đầu số CCCD không tồn tại",
                                "Kiểm tra lại số CCCD (có thể gõ nhầm)"))
        return True, cccd, name, issues, ""
    lm = _LEADING_DIGITS.match(folder)
    digits = lm.group(1) if lm else ""
    sug = suggest_folder_name(folder)
    unsure = ""
    if not digits:
        issues.append(Issue(LV_ERROR, "Tên thư mục không bắt đầu bằng số CCCD",
                            "Đặt tên dạng 056123456789_PhamVanA"))
    elif len(digits) != 12:
        issues.append(Issue(LV_ERROR, f"Số CCCD có {len(digits)} chữ số (phải đủ 12)",
                            "Kiểm tra và sửa lại số CCCD"))
    elif not sug:
        issues.append(Issue(LV_ERROR, "Thiếu họ tên sau số CCCD", "Thêm _HoVaTen sau số CCCD"))
    if digits and len(digits) == 12 and sug:
        if _DOSSIER.match(sug):
            # tên viết liền toàn chữ hoa/thường (VD PHAMVANA) không tách được từ → nhắc kiểm tra lại
            joined = re.sub(r"[^A-Za-z]", "", remove_accents(lm.group(2)))
            unsure = " – kiểm tra lại chữ hoa đầu mỗi từ" if (" " not in lm.group(2).strip() and "_" not in
                                                              lm.group(2).strip() and (joined.isupper() or joined.islower())
                                                              and len(joined) > 3) else ""
            issues.append(Issue(LV_ERROR, "Tên thư mục chưa đúng chuẩn (có dấu / khoảng trắng / ký tự lạ / chữ hoa-thường)",
                                f"Đổi tên thành “{sug}”{unsure}"))
        else:
            issues.append(Issue(LV_ERROR, "Họ tên chỉ được gồm chữ cái không dấu, viết hoa chữ cái đầu mỗi từ",
                                "Sửa tay, VD: 056123456789_PhamVanA"))
    name = split_name(sug.split("_", 1)[1]) if sug and "_" in sug else ""
    cccd = digits if len(digits) == 12 else ""
    if cccd and cccd[:3] not in PROVINCE_CODES:
        issues.append(Issue(LV_WARN, f"Mã tỉnh “{cccd[:3]}” ở đầu số CCCD không tồn tại",
                            "Kiểm tra lại số CCCD (có thể gõ nhầm)"))
    # gợi ý chắc chắn mới cho phép đổi tên hàng loạt; tên viết liền toàn hoa/thường phải sửa tay
    good_sug = sug if (sug and _DOSSIER.match(sug) and len(digits) == 12 and not unsure) else ""
    return False, cccd, name, issues, good_sug


# ------------------------------------------------------------------ file trong hồ sơ

def classify_file(fi: FileInfo, rules: Dict[str, str], required: Sequence[str]) -> DocFile:
    stem = os.path.splitext(fi.name)[0]
    m = _SIGNED_TAIL.search(stem)
    core = stem[:m.start()] if m else stem
    code = match_rule_code(core, rules)
    name_ok = bool(code) and _name_matches(core, rules[code])
    if not name_ok:
        # mã tuỳ chỉnh như '87bd' có tên mẫu '87.QD_bo_nhiem' → nhận theo tên mẫu trùng khớp
        base = re.sub(r"\.\d+$", "", core).lower()
        alt = _by_name(rules).get(base)
        if alt:
            code, name_ok = alt, True
    return DocFile(fi=fi, code=code, rule=rules.get(code, ""), name_ok=name_ok, required=code in required)


def _name_matches(core: str, rule: str) -> bool:
    return bool(re.fullmatch(re.escape(rule) + r"(?:\.\d+)?", core, re.I))


_NAME_CACHE: Dict[int, Dict[str, str]] = {}


def _by_name(rules: Dict[str, str]) -> Dict[str, str]:
    key = id(rules)
    m = _NAME_CACHE.get(key)
    if m is None or len(m) != len(rules):
        m = {v.lower(): k for k, v in rules.items()}
        _NAME_CACHE.clear()
        _NAME_CACHE[key] = m
    return m


# ------------------------------------------------------------------ lập báo cáo

def _skip(name: str) -> bool:
    return name.startswith(("_", ".")) or name.lower() in ("$recycle.bin", "system volume information")


def _has_subdir(path: str) -> bool:
    try:
        with os.scandir(path) as it:
            return any(e.is_dir() and not _skip(e.name) for e in it)
    except OSError:
        return False


def detect_mode(root: str, dirs: Sequence[str]) -> str:
    """root = thư mục 'Hồ sơ số hóa' (chi bộ/hồ sơ) · chibo = đang quét 1 chi bộ · dossier = đang quét 1 hồ sơ."""
    looks = lambda n: bool(re.match(r"^\s*\d{6,}", n))
    d1 = [d for d in dirs if d and os.sep not in d]
    d2 = [d for d in dirs if d.count(os.sep) == 1]
    if looks(os.path.basename(root)) and not d1:
        return "dossier"
    a = sum(looks(os.path.basename(d)) for d in d1)
    b = sum(looks(os.path.basename(d)) for d in d2)
    return "chibo" if a > b else "root"


def _sign_ok(fi: FileInfo, sign_filter: str) -> bool:
    if sign_filter == SIGN_ONLY:
        return fi.name_signed
    if sign_filter == SIGN_NONE:
        return not fi.name_signed
    return True


def build_report(result: ScanResult, rules: Dict[str, str],
                 required: Sequence[str] = DEFAULT_REQUIRED, sign_filter: str = SIGN_ALL) -> Report:
    required = tuple(required)
    if sign_filter not in SIGN_LABELS:
        raise ValueError("Lựa chọn file đã ký / chưa ký không hợp lệ")
    root = result.root
    dirs = [d for d in result.dirs if not any(_skip(p) for p in d.split(os.sep) if p)]
    mode = detect_mode(root, dirs)
    rep = Report(root=root, mode=mode, required=required, rules=rules, sign_filter=sign_filter)
    if dirs == [""] and not result.files:
        rep.notes.append("Thư mục trống.")
    if len(result.dirs) == 1 and _has_subdir(root):
        rep.notes.append("Đang tắt “Quét thư mục con” – hãy bật để lập báo cáo đầy đủ.")

    # mức của thư mục: chi bộ / hồ sơ theo chế độ
    root_name = os.path.basename(root.rstrip("\\/"))
    parent_name = os.path.basename(os.path.dirname(root.rstrip("\\/")))

    def parts_of(rel: str) -> List[str]:
        p = [x for x in rel.split(os.sep) if x]
        if mode == "chibo":
            return [root_name] + p
        if mode == "dossier":
            return [parent_name, root_name] + p
        return p

    dossiers: Dict[Tuple[str, str], Dossier] = {}
    chibos: List[str] = []
    for rel in dirs:
        p = parts_of(rel)
        if len(p) >= 1 and p[0] not in chibos:
            chibos.append(p[0])
        if len(p) == 2:
            key = (p[0], p[1])
            if key not in dossiers:
                path = os.path.join(root, rel) if rel else root
                dossiers[key] = Dossier(chibo=p[0], folder=p[1], path=path)
        elif len(p) >= 3:
            d = dossiers.get((p[0], p[1]))
            if d is not None and len(p) == 3:
                d.issues.append(Issue(LV_WARN, f"Có thư mục con “{p[2]}” bên trong hồ sơ",
                                      "Đưa file ra thẳng thư mục hồ sơ, xoá thư mục con"))
    rep.chibos = sorted(chibos, key=natural_key) if mode == "root" else chibos

    for fi in result.files:
        p = parts_of(fi.dir_rel)
        if any(_skip(x) for x in fi.dir_rel.split(os.sep) if x):
            continue
        if len(p) == 2 and (p[0], p[1]) in dossiers:
            doc = classify_file(fi, rules, required)
            d = dossiers[(p[0], p[1])]
            (d.files if _sign_ok(fi, sign_filter) else d.excluded).append(doc)
        elif not _sign_ok(fi, sign_filter):
            continue
        elif len(p) == 0:
            rep.stray.append(Stray(fi.path, fi.rel, "File nằm thẳng trong thư mục gốc, chưa thuộc chi bộ/hồ sơ nào"))
        elif len(p) == 1:
            rep.stray.append(Stray(fi.path, fi.rel, f"File nằm thẳng trong chi bộ “{p[0]}”, chưa vào thư mục hồ sơ"))
        else:
            rep.stray.append(Stray(fi.path, fi.rel, "File nằm trong thư mục con của hồ sơ"))

    seen_cccd: Dict[str, List[Dossier]] = defaultdict(list)
    for d in dossiers.values():
        _evaluate(d, rules, required)
        if d.cccd:
            seen_cccd[d.cccd].append(d)
    for cccd, ds in seen_cccd.items():
        if len(ds) > 1:
            where = "; ".join(f"{x.chibo}/{x.folder}" for x in ds)
            for x in ds:
                x.issues.append(Issue(LV_ERROR, f"Trùng số CCCD {cccd} với hồ sơ khác: {where}",
                                      "Kiểm tra lại, gộp hoặc sửa số CCCD"))
                _set_status(x)
    rep.dossiers = sorted(dossiers.values(), key=lambda d: (rep.chibos.index(d.chibo) if d.chibo in rep.chibos
                                                             else 9999, natural_key(d.folder)))
    for c in rep.chibos:
        if not any(d.chibo == c for d in rep.dossiers):
            rep.notes.append(f"Chi bộ “{c}” chưa có hồ sơ nào.")
    return rep


def _evaluate(d: Dossier, rules: Dict[str, str], required: Sequence[str]):
    ok, d.cccd, d.name, issues, d.suggestion = check_folder(d.folder)
    d.folder_ok = ok
    d.issues = issues + d.issues
    d.files.sort(key=lambda x: natural_key(x.fi.name))
    d.have = {c: [] for c in required}
    for f in d.files:
        if f.fi.error:
            f.note = f.fi.error
            d.issues.append(Issue(LV_ERROR, f"File lỗi: {f.fi.name} ({f.fi.error})", "Scan / xuất lại file"))
        elif f.fi.pages == 0:
            f.note = "File không có trang"
            d.issues.append(Issue(LV_ERROR, f"File không có trang: {f.fi.name}", "Scan lại file"))
        if f.required:
            d.have[f.code].append(f)
            if not f.name_ok:
                f.note = f.note or f"Nên đặt tên “{f.rule}.pdf”"
                d.issues.append(Issue(LV_ERROR, f"Sai tên file: {f.fi.name}",
                                      f"Đổi thành “{f.rule}{f.fi.name[len(os.path.splitext(f.fi.name)[0]):]}” "
                                      "(dùng tab Đổi tên – bộ quy tắc 1361)"))
        elif f.code:
            # giấy tờ khác trong bộ quy tắc: hợp lệ (không bắt buộc); chỉ nhắc khi đặt sai tên mẫu
            if f.name_ok:
                f.note = f.note or "Giấy tờ khác (không bắt buộc)"
            else:
                f.note = f.note or f"Nên đặt tên “{f.rule}.pdf”"
                d.issues.append(Issue(LV_WARN, f"Sai tên file (giấy tờ không bắt buộc): {f.fi.name}",
                                      f"Đổi thành “{f.rule}.pdf” (tab Đổi tên – bộ quy tắc 1361)"))
        else:
            f.note = f.note or "Không xác định được loại giấy tờ (thiếu mã ở đầu tên)"
            d.issues.append(Issue(LV_WARN, f"Không xác định loại giấy tờ: {f.fi.name}",
                                  "Đặt tên bắt đầu bằng mã 01–05, VD 01.Ly_lich_nguoi_xin_vao_Dang.pdf"))
    for c, fs in d.have.items():
        # X.pdf + X.signed.pdf là 2 bản (chưa ký / đã ký) của cùng 1 giấy tờ – không phải trùng
        cores = {_core(x.fi.name).lower() for x in fs}
        if len(cores) > 1:
            suffixed = all(re.search(r"\.\d+$", c2) for c2 in cores)
            if not suffixed:
                d.issues.append(Issue(LV_WARN, f"Có {len(fs)} file cùng mã {c}: " + ", ".join(x.fi.name for x in fs),
                                      "Nếu là nhiều phần của cùng giấy tờ, đặt hậu tố .1, .2 (tab Đổi tên)"))
    d.missing = [c for c in required if not d.have.get(c)]
    if d.missing and d.files:
        names = ", ".join(f"{c} ({rules.get(c, '').split('.', 1)[-1].replace('_', ' ')})" for c in d.missing)
        d.issues.append(Issue(LV_ERROR, f"Thiếu file: {names}", "Scan bổ sung, đặt tên theo mẫu 1361"))
    if not d.files:
        if d.excluded:
            kind = "đã ký (.signed)" if any(not x.fi.name_signed for x in d.excluded) else "chưa ký"
            d.issues.append(Issue(LV_ERROR, f"Thư mục hồ sơ chưa có file {kind}", "Ký số / bổ sung file"))
        else:
            d.issues.append(Issue(LV_ERROR, "Thư mục hồ sơ chưa có file PDF nào", "Scan và lưu hồ sơ vào thư mục"))
    _set_status(d)


def missing_hint(d: Dossier, code: str, sign_filter: str) -> str:
    """Gợi ý khi mục bị tính 'Thiếu' chỉ vì lựa chọn đã ký / chưa ký (file vẫn có ở bản kia)."""
    if any(x.code == code for x in d.excluded):
        return " (mới có bản chưa ký)" if sign_filter == SIGN_ONLY else " (chỉ có bản đã ký)"
    return ""


def _core(name: str) -> str:
    stem = os.path.splitext(name)[0]
    m = _SIGNED_TAIL.search(stem)
    return stem[:m.start()] if m else stem


def _set_status(d: Dossier):
    if not d.files:
        d.status = ST_EMPTY
    elif d.missing:
        d.status = ST_MISSING
    elif not d.folder_ok or any(f.required and not f.name_ok for f in d.files):
        d.status = ST_NAME
    elif any(i.level == LV_ERROR for i in d.issues):
        d.status = ST_FIX
    elif d.issues:
        d.status = ST_WARN
    else:
        d.status = ST_OK


def parse_required(text: str) -> Tuple[str, ...]:
    """'01-05' | '01, 02, 05' → ('01', '02', '05')."""
    out: List[str] = []
    for part in re.split(r"[,;\s]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d{1,3})\s*-\s*(\d{1,3})", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b or b - a > 200:
                raise ValueError(f"Khoảng mã “{part}” không hợp lệ")
            out += [str(i).zfill(2) for i in range(a, b + 1)]
        elif re.fullmatch(r"\d{1,3}[a-zA-Z]*", part):
            out.append(part.zfill(2) if part.isdigit() else part.lower())
        else:
            raise ValueError(f"Mã “{part}” không hợp lệ")
    if not out:
        raise ValueError("Chưa nhập mã bắt buộc")
    return tuple(dict.fromkeys(out))


# ------------------------------------------------------------------ đổi tên thư mục hồ sơ theo gợi ý

@dataclass
class FolderRename:
    old: str                   # đường dẫn cũ
    new: str                   # đường dẫn mới
    ok: bool = False
    message: str = ""


def rename_folders(pairs: Sequence[Tuple[str, str]]) -> List[FolderRename]:
    """Đổi tên thư mục (đường dẫn cũ, tên mới). Không ghi đè thư mục đã có; đổi khác hoa/thường đi qua tên tạm.
    Trả về kết quả từng mục – dùng `undo_renames` để hoàn tác."""
    out: List[FolderRename] = []
    for old, new_name in pairs:
        new = os.path.join(os.path.dirname(old), new_name)
        r = FolderRename(old, new)
        out.append(r)
        if not re.fullmatch(r"[^\/:*?\"<>|]+", new_name) or new_name.strip() != new_name:
            r.message = "Tên mới không hợp lệ"
            continue
        if not os.path.isdir(old):
            r.message = "Thư mục không còn tồn tại"
            continue
        same = os.path.normcase(old) == os.path.normcase(new)
        if os.path.exists(new) and not same:
            r.message = "Đã có thư mục trùng tên mới – bỏ qua"
            continue
        try:
            if same:                                   # chỉ khác hoa/thường: Windows cần đi qua tên tạm
                tmp = old + ".~doiten"
                os.rename(old, tmp)
                os.rename(tmp, new)
            else:
                os.rename(old, new)
            r.ok, r.message = True, "Đã đổi tên"
        except OSError as e:
            r.message = f"Không đổi được: {e.strerror or e}"
    return out


def undo_renames(done: Sequence[FolderRename]) -> List[FolderRename]:
    return rename_folders([(r.new, os.path.basename(r.old)) for r in reversed(done) if r.ok])
