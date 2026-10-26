"""Engine đổi tên hàng loạt: mẫu tên có biến, đánh số, bước biến đổi, chống trùng,
giao dịch theo từng thư mục có nhật ký chống mất điện, hoàn tác, lưu bộ quy tắc."""
from __future__ import annotations

import copy
import json
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from .models import FileInfo, name_is_signed

# ---------------------------------------------------------------- tiện ích chuỗi

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}
MAX_NAME = 200


def remove_accents(text: str) -> str:
    text = text.replace("Đ", "D").replace("đ", "d")
    nfd = unicodedata.normalize("NFD", text)
    return unicodedata.normalize("NFC", "".join(c for c in nfd if unicodedata.category(c) != "Mn"))


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def validate_name(name: str) -> str:
    """Trả về thông báo lỗi hoặc chuỗi rỗng nếu tên hợp lệ trên Windows."""
    if not name or not name.strip():
        return "Tên rỗng"
    if _INVALID_CHARS.search(name):
        return "Chứa ký tự cấm  < > : \" / \\ | ? *"
    if name != name.rstrip(" .") :
        return "Tên không được kết thúc bằng dấu cách hoặc dấu chấm"
    if name.split(".")[0].upper() in _RESERVED:
        return "Trùng tên hệ thống Windows"
    if len(name) > MAX_NAME:
        return f"Tên quá dài (> {MAX_NAME} ký tự)"
    return ""


# ---------------------------------------------------------------- bộ quy tắc

STEP_TYPES = {
    "prefix": "Thêm tiền tố",
    "suffix": "Thêm hậu tố",
    "replace": "Thay thế chuỗi",
    "remove_accents": "Bỏ dấu tiếng Việt",
    "spaces": "Xử lý khoảng trắng",
    "case": "Đổi hoa/thường",
    "trim": "Dọn ký tự thừa",
    "code1361": "Chuẩn tên theo mã hồ sơ 1361",
}

VARIABLES = {
    "stem": "Tên gốc (không đuôi)",
    "ext": "Đuôi file (.pdf)",
    "n": "Số thứ tự (vd {n:3} = 001; {n} dùng số chữ số ở mục Đánh số)",
    "folder": "Tên thư mục chứa file",
    "parent": "Tên thư mục cha",
    "pages": "Số trang",
    "date": "Ngày sửa file (vd {date:%Y%m%d})",
    "today": "Ngày hôm nay (vd {today:%d-%m-%Y})",
    "signer": "Tên người ký đầu tiên",
    "code": "Mã số đầu tên (01, 86dh…)",
}

DEFAULT_RULES_1361 = ""   # rỗng = dùng bộ quy tắc 1361 của ứng dụng (tab Quản lý bộ quy tắc)


def new_ruleset(name: str = "Bộ quy tắc mới") -> dict:
    return {
        "name": name,
        "template": "{stem}",
        "numbering": {"start": 1, "step": 1, "pad": 0, "per_folder": True},
        "steps": [],
    }


def default_presets() -> List[dict]:
    p1 = new_ruleset("Bỏ dấu + khoảng trắng thành _")
    p1["steps"] = [{"type": "remove_accents"}, {"type": "spaces", "to": "_"}, {"type": "trim"}]
    p2 = new_ruleset("Đuôi .1 → .signed")
    p2["steps"] = [{"type": "replace", "find": r"\.1$", "repl": ".signed", "regex": True, "case": False}]
    p3 = new_ruleset("Đánh số 01, 02… trước tên")
    p3["template"] = "{n}.{stem}"
    p3["numbering"]["pad"] = 2
    return [p1, p2, p3]


def _presets_path() -> str:
    from ..paths import data_file
    return data_file("rename_presets.json")


def load_presets() -> List[dict]:
    out = default_presets()
    try:
        with open(_presets_path(), "r", encoding="utf-8") as fh:
            user = json.load(fh)
        names = {p["name"] for p in out}
        out += [p for p in user if isinstance(p, dict) and p.get("name") and p["name"] not in names]
    except (OSError, ValueError):
        pass
    return out


def save_user_presets(presets: List[dict]) -> None:
    builtin = {p["name"] for p in default_presets()}
    user = [p for p in presets if p["name"] not in builtin]
    with open(_presets_path(), "w", encoding="utf-8") as fh:
        json.dump(user, fh, ensure_ascii=False, indent=2)


def step_summary(s: dict) -> str:
    t = s.get("type")
    if t == "prefix":
        return f"Thêm tiền tố: “{s.get('text', '')}”"
    if t == "suffix":
        return f"Thêm hậu tố: “{s.get('text', '')}”"
    if t == "replace":
        kind = "regex" if s.get("regex") else "văn bản"
        return f"Thay ({kind}): “{s.get('find', '')}” → “{s.get('repl', '')}”"
    if t == "remove_accents":
        return "Bỏ dấu tiếng Việt (Đ→D)"
    if t == "spaces":
        to = s.get("to", "_")
        return f"Khoảng trắng → “{to}”" if to else "Xoá khoảng trắng"
    if t == "case":
        return {"lower": "Chữ thường", "upper": "CHỮ HOA", "title": "Viết Hoa Mỗi Từ",
                "sentence": "Viết hoa chữ đầu"}.get(s.get("mode"), "Đổi hoa/thường")
    if t == "trim":
        return "Dọn khoảng trắng/dấu chấm/gạch thừa ở đầu, cuối"
    if t == "code1361":
        return "Chuẩn tên theo mã hồ sơ 1361"
    return str(t)


# ---------------------------------------------------------------- mã 1361

_rules_cache: Dict[str, Tuple[float, dict]] = {}


def load_rules_1361(path: str = "") -> dict:
    if not path:
        from . import rules1361
        return rules1361.load_rules()
    try:
        mt = os.path.getmtime(path)
        c = _rules_cache.get(path)
        if c and c[0] == mt:
            return c[1]
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            _rules_cache[path] = (mt, data)
            return data
    except (OSError, ValueError):
        pass
    return {}


def extract_code(stem: str, rules: Optional[dict] = None) -> str:
    """Mã ở đầu tên: ưu tiên mã tuỳ chỉnh dài nhất có trong rules (86dh), sau đó 1-3 chữ số."""
    low = stem.lower()
    if rules:
        for key in sorted(rules, key=len, reverse=True):
            if low.startswith(key.lower()) and re.match(r"(?:[\s._\-)(\]]|$)", low[len(key):]):
                return key
    m = re.match(r"^(\d{1,3})(?:[\s._\-)(\]]|$)", stem)
    return m.group(1) if m else ""


def match_rule_code(stem: str, rules: dict) -> str:
    """Mã quy tắc khớp với đầu tên ('' nếu không có). '1', '4' được hiểu là '01', '04'."""
    code = extract_code(stem, rules)
    if code and code not in rules and code.isdigit():
        padded = code.zfill(2)
        if padded in rules:
            return padded
    return code if code in rules else ""


_SIGNED_TAIL = re.compile(r"((?:[.\s_\-]+signed)+)$", re.I)


# ---------------------------------------------------------------- áp dụng quy tắc

class RuleError(Exception):
    pass


@dataclass
class Context:
    fi: FileInfo
    n: int
    today: datetime
    pad: int = 0


_VAR = re.compile(r"\{(\w+)(?::([^{}]*))?\}")


def _fmt_var(name: str, arg: Optional[str], ctx: Context, stem: str, ext: str, rules: dict) -> str:
    fi = ctx.fi
    folder = os.path.basename(os.path.dirname(fi.path))
    if name == "stem":
        return stem
    if name == "ext":
        return ext
    if name == "n":
        pad = int(arg) if arg and arg.isdigit() else ctx.pad
        return str(ctx.n).zfill(pad)
    if name == "folder":
        return folder
    if name == "parent":
        return os.path.basename(os.path.dirname(os.path.dirname(fi.path)))
    if name == "pages":
        return str(fi.pages if fi.pages is not None else "")
    if name == "date":
        return datetime.fromtimestamp(fi.mtime).strftime(arg or "%Y-%m-%d")
    if name == "today":
        return ctx.today.strftime(arg or "%Y-%m-%d")
    if name == "signer":
        return fi.signers[0] if fi.signers else ""
    if name == "code":
        return extract_code(stem, rules)
    raise RuleError(f"Biến không hợp lệ: {{{name}}}")


def apply_steps(stem: str, steps: List[dict]) -> str:
    for s in steps:
        t = s.get("type")
        if t == "prefix":
            stem = s.get("text", "") + stem
        elif t == "suffix":
            stem = stem + s.get("text", "")
        elif t == "replace":
            find = s.get("find", "")
            if not find:
                continue
            flags = 0 if s.get("case") else re.I
            try:
                if s.get("regex"):
                    stem = re.sub(find, s.get("repl", ""), stem, flags=flags)
                else:
                    stem = re.sub(re.escape(find), lambda _m, r=s.get("repl", ""): r, stem, flags=flags)
            except re.error as e:
                raise RuleError(f"Biểu thức regex lỗi: {e}")
        elif t == "remove_accents":
            stem = remove_accents(stem)
        elif t == "spaces":
            to = s.get("to", "_")
            stem = re.sub(r"\s+", to, stem)
            if to:
                stem = re.sub(re.escape(to) + r"{2,}", to, stem)
        elif t == "case":
            mode = s.get("mode")
            if mode == "lower":
                stem = stem.lower()
            elif mode == "upper":
                stem = stem.upper()
            elif mode == "title":
                stem = " ".join(w[:1].upper() + w[1:].lower() for w in stem.split(" "))
            elif mode == "sentence":
                stem = stem[:1].upper() + stem[1:].lower()
        elif t == "trim":
            stem = re.sub(r"\s{2,}", " ", stem)
            stem = re.sub(r"^[\s._\-]+|[\s._\-]+$", "", stem)
        elif t == "code1361":
            rules = load_rules_1361(s.get("rules_path") or DEFAULT_RULES_1361)
            if not rules:
                raise RuleError("Chưa đọc được bộ quy tắc mã số 1361")
            tail = ""
            m = _SIGNED_TAIL.search(stem)
            core = stem
            if m:
                tail = m.group(1)
                core = stem[:m.start()]
            code = match_rule_code(core, rules)
            if code:
                stem = rules[code] + tail
            # không có mã → giữ nguyên tên (xem trạng thái ở bảng xem trước)
    return stem


def compute_new_name(ctx: Context, ruleset: dict) -> str:
    fi = ctx.fi
    base, ext = os.path.splitext(fi.name)
    rules = {}
    for s in ruleset.get("steps", []):
        if s.get("type") == "code1361":
            rules = load_rules_1361(s.get("rules_path") or DEFAULT_RULES_1361)
    tpl = ruleset.get("template") or "{stem}"
    new = _VAR.sub(lambda m: _fmt_var(m.group(1), m.group(2), ctx, base, ext, rules), tpl)
    new = apply_steps(new, ruleset.get("steps", []))
    return new + ext


# ---------------------------------------------------------------- xem trước

ST_READY = "ready"
ST_SAME = "same"
ST_CONFLICT = "conflict"
ST_INVALID = "invalid"
ST_RENAMED_AUTO = "auto"       # đã tự thêm (2) để tránh trùng
ST_NO_RULE = "norule"          # có mã số nhưng chưa có quy tắc
ST_NO_CODE = "nocode"          # không có mã số ở đầu tên

STATUS_TEXT = {
    ST_READY: "Sẵn sàng đổi",
    ST_SAME: "Không đổi",
    ST_CONFLICT: "Trùng tên – bỏ qua",
    ST_INVALID: "Tên không hợp lệ",
    ST_RENAMED_AUTO: "Sẵn sàng (tự thêm số để tránh trùng)",
    ST_NO_RULE: "Chưa có quy tắc",
    ST_NO_CODE: "Không có mã số",
}


@dataclass
class PreviewItem:
    fi: FileInfo
    new_name: str = ""
    status: str = ST_SAME
    note: str = ""
    checked: bool = True
    code: str = ""                # mã số đọc được ở đầu tên
    rule: str = ""                # tên mẫu quy tắc khớp

    @property
    def new_path(self) -> str:
        return os.path.join(os.path.dirname(self.fi.path), self.new_name)

    @property
    def will_rename(self) -> bool:
        return self.checked and self.status in (ST_READY, ST_RENAMED_AUTO)


def _free_name(name: str, occupied: set) -> str:
    base, ext = os.path.splitext(name)
    i = 2
    while True:
        cand = f"{base} ({i}){ext}"
        if cand.lower() not in occupied:
            return cand
        i += 1


def build_preview(files: List[FileInfo], ruleset: dict, policy: str = "auto",
                  listdir: Callable[[str], List[str]] = None) -> List[PreviewItem]:
    """Tính tên mới cho từng file. policy: 'auto' (thêm (2)) hoặc 'skip' khi trùng."""
    listdir = listdir or (lambda d: os.listdir(d) if os.path.isdir(d) else [])
    numbering = ruleset.get("numbering", {})
    start, step = int(numbering.get("start", 1)), int(numbering.get("step", 1))
    per_folder = bool(numbering.get("per_folder", True))
    pad = int(numbering.get("pad", 0))
    today = datetime.now()

    items = [PreviewItem(fi=f) for f in files]
    # đánh số theo thứ tự tự nhiên trong từng thư mục
    order = sorted(range(len(items)), key=lambda i: (os.path.dirname(items[i].fi.path).lower(),
                                                    natural_key(items[i].fi.name)))
    counters: Dict[str, int] = {}
    glob_n = start
    for i in order:
        it = items[i]
        d = os.path.dirname(it.fi.path)
        if per_folder:
            n = counters.get(d, start)
            counters[d] = n + step
        else:
            n = glob_n
            glob_n += step
        try:
            it.new_name = compute_new_name(Context(it.fi, n, today, pad), ruleset)
            err = validate_name(it.new_name)
            if err:
                it.status, it.note = ST_INVALID, err
            elif it.new_name == it.fi.name:
                it.status = ST_SAME
            else:
                it.status = ST_READY
        except RuleError as e:
            it.new_name, it.status, it.note = it.fi.name, ST_INVALID, str(e)
        except Exception as e:  # lỗi bất ngờ ở một file không làm hỏng cả lô
            it.new_name, it.status, it.note = it.fi.name, ST_INVALID, f"Lỗi: {e}"

    _resolve_conflicts(items, order, policy, listdir)
    return items


def _resolve_conflicts(items: List[PreviewItem], order: List[int], policy: str,
                       listdir: Callable[[str], List[str]]) -> None:
    """Chống trùng theo từng thư mục (không phân biệt hoa/thường như Windows); không bao giờ ghi đè."""
    by_dir: Dict[str, List[int]] = {}
    for i in order:
        by_dir.setdefault(os.path.dirname(items[i].fi.path), []).append(i)
    for d, idxs in by_dir.items():
        batch_src = {items[i].fi.name.lower() for i in idxs}
        existing = {n.lower() for n in listdir(d)}
        occupied = existing - batch_src          # các tên sẽ không được giải phóng
        for i in idxs:                           # file không đổi chiếm chỗ tên cũ của nó
            if items[i].status != ST_READY:
                occupied.add(items[i].fi.name.lower())
        for i in idxs:
            it = items[i]
            if it.status != ST_READY:
                continue
            key = it.new_name.lower()
            if key in occupied:
                if policy == "auto":
                    it.new_name = _free_name(it.new_name, occupied)
                    it.status = ST_RENAMED_AUTO
                    it.note = "Trùng tên → tự thêm số"
                    occupied.add(it.new_name.lower())
                else:
                    it.status, it.note = ST_CONFLICT, "Trùng với file khác trong thư mục"
                    it.new_name = it.fi.name
                    occupied.add(it.fi.name.lower())
            else:
                occupied.add(key)


def build_preview_1361(files: List[FileInfo], rules: Dict[str, str], always_suffix: bool = False,
                       policy: str = "auto", listdir: Callable[[str], List[str]] = None) -> List[PreviewItem]:
    """Đổi tên theo bộ quy tắc mã số 1361: mã ở đầu tên → tên mẫu tiêu chuẩn.
    Nhiều file cùng mã trong một thư mục → thêm hậu tố .1, .2… (theo thứ tự tên tự nhiên);
    `always_suffix` → luôn thêm .1 kể cả khi chỉ có 1 file. Phần .signed ở cuối được giữ nguyên."""
    listdir = listdir or (lambda d: os.listdir(d) if os.path.isdir(d) else [])
    items = [PreviewItem(fi=f) for f in files]
    order = sorted(range(len(items)), key=lambda i: (os.path.dirname(items[i].fi.path).lower(),
                                                    natural_key(items[i].fi.name)))
    parts = {}
    groups: Dict[Tuple[str, str], List[int]] = {}
    for i in order:
        it = items[i]
        stem, ext = os.path.splitext(it.fi.name)
        m = _SIGNED_TAIL.search(stem)
        tail, core = (m.group(1), stem[:m.start()]) if m else ("", stem)
        code = match_rule_code(core, rules)
        if not code:
            raw = extract_code(core)
            it.new_name = it.fi.name
            if raw:
                it.code, it.status, it.note = raw, ST_NO_RULE, f"Không có quy tắc cho mã [{raw}]"
            else:
                it.status, it.note = ST_NO_CODE, "Không tìm thấy mã số ở đầu tên file"
            continue
        it.code, it.rule = code, rules[code]
        parts[i] = (core, tail, ext)
        groups.setdefault((os.path.dirname(it.fi.path).lower(), code), []).append(i)
    for idxs in groups.values():
        # file đã có hậu tố .N đúng mẫu giữ nguyên số đó; file còn lại lấp số trống nhỏ nhất
        keep: Dict[int, int] = {}
        for i in idxs:
            core = parts[i][0]
            m = re.fullmatch(re.escape(items[i].rule) + r"[.](\d+)", core, re.I)
            if m and int(m.group(1)) > 0 and int(m.group(1)) not in keep.values():
                keep[i] = int(m.group(1))
        used = set(keep.values())
        nxt = 1
        for i in idxs:
            it = items[i]
            core, tail, ext = parts[i]
            if i in keep:
                suffix = f".{keep[i]}"
            elif len(idxs) > 1 or always_suffix:
                while nxt in used:
                    nxt += 1
                used.add(nxt)
                suffix = f".{nxt}"
            else:
                suffix = ""
            it.new_name = f"{it.rule}{suffix}{tail}{ext}"
            err = validate_name(it.new_name)
            if err:
                it.status, it.note, it.new_name = ST_INVALID, err, it.fi.name
            elif it.new_name == it.fi.name:
                it.status, it.note = ST_SAME, "Đã đúng tên"
            else:
                it.status = ST_READY
    _resolve_conflicts(items, order, policy, listdir)
    return items


# ---------------------------------------------------------------- áp dụng + nhật ký + hoàn tác

def _journal_path() -> str:
    from ..paths import data_file
    return data_file("rename_journal.json")


def _history_path() -> str:
    from ..paths import data_file
    return data_file("rename_history.json")


def _write_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


@dataclass
class ApplyReport:
    ok: int = 0
    failed: List[Tuple[str, str]] = field(default_factory=list)   # (đường dẫn, lý do)
    batch_id: str = ""

    @property
    def summary(self) -> str:
        return f"Đổi thành công {self.ok} file" + (f", lỗi {len(self.failed)}" if self.failed else "")


def _rename_ops(ops: List[Tuple[str, str]], journal: dict, report: ApplyReport) -> List[Tuple[str, str]]:
    """Đổi một thư mục. Nếu có chuỗi/xoay vòng tên (a→b, b→c) hoặc đổi chỉ khác hoa/thường
    thì đổi 2 pha qua tên tạm; ngược lại đổi trực tiếp. Trả về các cặp (src, dst) thành công."""
    done: List[Tuple[str, str]] = []
    srcs = {os.path.basename(s).lower() for s, _ in ops}
    use_tmp = any(
        os.path.basename(d).lower() in srcs or os.path.basename(d).lower() == os.path.basename(s).lower()
        for s, d in ops)
    if not use_tmp:
        for s, d in ops:
            journal["ops"].append({"src": s, "dst": d, "tmp": ""})
            _write_json(_journal_path(), journal)
            try:
                if os.path.exists(d):
                    raise OSError("Tên đích đã tồn tại")
                os.rename(s, d)
                done.append((s, d))
            except OSError as e:
                report.failed.append((s, getattr(e, "strerror", None) or str(e)))
        return done
    stage1: List[Tuple[str, str, str]] = []
    for s, d in ops:
        tmp = os.path.join(os.path.dirname(s), f"~rn_{uuid.uuid4().hex[:10]}.tmp")
        journal["ops"].append({"src": s, "dst": d, "tmp": tmp})
        _write_json(_journal_path(), journal)
        try:
            os.rename(s, tmp)
            stage1.append((s, d, tmp))
        except OSError as e:
            report.failed.append((s, getattr(e, "strerror", None) or str(e)))
    for s, d, tmp in stage1:
        try:
            if os.path.exists(d):
                raise OSError("Tên đích đã tồn tại")
            os.rename(tmp, d)
            done.append((s, d))
        except OSError as e:
            try:
                os.rename(tmp, s)
            except OSError:
                pass
            report.failed.append((s, getattr(e, "strerror", None) or str(e)))
    return done


def apply_renames(items: List[PreviewItem], progress: Optional[Callable[[int, int], None]] = None,
                  cancel=None) -> ApplyReport:
    """Đổi tên các mục `will_rename`. Mỗi thư mục là một giao dịch độc lập."""
    todo = [it for it in items if it.will_rename]
    report = ApplyReport(batch_id=uuid.uuid4().hex[:12])
    by_dir: Dict[str, List[PreviewItem]] = {}
    for it in todo:
        by_dir.setdefault(os.path.dirname(it.fi.path), []).append(it)
    journal = {"id": report.batch_id, "time": datetime.now().isoformat(timespec="seconds"),
               "state": "pending", "ops": []}
    all_done: List[Tuple[str, str]] = []
    n = 0
    for d, group in by_dir.items():
        if cancel is not None and cancel():
            break
        ops = [(it.fi.path, it.new_path) for it in group]
        all_done += _rename_ops(ops, journal, report)
        n += len(group)
        if progress:
            progress(n, len(todo))
    report.ok = len(all_done)
    journal["state"] = "done"
    try:
        os.remove(_journal_path())
    except OSError:
        pass
    if all_done:
        hist = _read_json(_history_path(), [])
        hist.append({"id": report.batch_id, "time": journal["time"], "ops": [list(x) for x in all_done],
                     "undone": False})
        _write_json(_history_path(), hist[-30:])
    return report


def pending_journal() -> Optional[dict]:
    j = _read_json(_journal_path(), None)
    return j if j and j.get("state") == "pending" and j.get("ops") else None


def recover_journal() -> int:
    """Khôi phục sau khi app tắt đột ngột giữa lúc đổi tên: đưa mọi file về tên gốc."""
    j = pending_journal()
    if not j:
        return 0
    restored = 0
    for op in reversed(j["ops"]):
        src, dst, tmp = op["src"], op["dst"], op.get("tmp", "")
        try:
            if tmp and os.path.exists(tmp) and not os.path.exists(src):
                os.rename(tmp, src)
                restored += 1
            elif os.path.exists(dst) and not os.path.exists(src):
                os.rename(dst, src)
                restored += 1
        except OSError:
            pass
    try:
        os.remove(_journal_path())
    except OSError:
        pass
    return restored


def last_undoable() -> Optional[dict]:
    for b in reversed(_read_json(_history_path(), [])):
        if not b.get("undone") and b.get("ops"):
            return b
    return None


def undo_last() -> ApplyReport:
    hist = _read_json(_history_path(), [])
    batch = None
    for b in reversed(hist):
        if not b.get("undone") and b.get("ops"):
            batch = b
            break
    report = ApplyReport()
    if batch is None:
        return report
    ops = [(d, s) for s, d in batch["ops"]]       # đảo chiều
    by_dir: Dict[str, List[Tuple[str, str]]] = {}
    for s, d in ops:
        if not os.path.exists(s):
            report.failed.append((s, "File không còn tồn tại (đã bị di chuyển/đổi tên?)"))
            continue
        by_dir.setdefault(os.path.dirname(s), []).append((s, d))
    journal = {"id": uuid.uuid4().hex[:12], "time": datetime.now().isoformat(timespec="seconds"),
               "state": "pending", "ops": []}
    done = []
    for d, o in by_dir.items():
        done += _rename_ops(o, journal, report)
    report.ok = len(done)
    try:
        os.remove(_journal_path())
    except OSError:
        pass
    failed_dst = {s for s, _ in report.failed}
    remaining = [[s, d] for s, d in batch["ops"] if d in failed_dst]
    if remaining:
        batch["ops"] = remaining
    else:
        batch["undone"] = True
    _write_json(_history_path(), hist)
    return report
