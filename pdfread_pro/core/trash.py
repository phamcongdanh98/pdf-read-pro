"""THÙNG RÁC: giữ lại những gì app đã xoá / ghi đè để xem lại, khôi phục hoặc xoá vĩnh viễn.

Có 3 loại mục (mỗi mục là 1 file JSON nhỏ trong `%APPDATA%\\PDFReadPro\\trash\\entries` → nhiều tiến trình cùng ghi không tranh chấp):
- `pages`  : các trang đã xoá (lưu thành 1 file PDF nhỏ). Khôi phục = chèn lại ĐÚNG vị trí cũ trong file gốc.
- `backup`: bản gốc trước khi sửa / nén / cắt ghi đè. Bản sao lưu nằm trong THƯ MỤC SAO LƯU CỦA APP (`%APPDATA%\\PDFReadPro\\backup`,
            đổi được) – KHÔNG nằm lẫn trong thư mục hồ sơ; mục chỉ trỏ tới đó. Khôi phục = trả file về như trước khi sửa
            (bản hiện tại được cất vào thùng rác). Các thư mục `_backup_goc` cũ (bản trước 1.9.1) vẫn đọc được và chuyển được (migrate_legacy).
- `file`  : cả file được cất (vd bản hiện tại bị thay khi khôi phục).
Mọi hàm ghi thùng rác không bao giờ ném lỗi ra ngoài (thùng rác hỏng không được làm hỏng việc chính)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from ..paths import data_dir

KIND_PAGES, KIND_BACKUP, KIND_FILE = "pages", "backup", "file"
KIND_TEXT = {KIND_PAGES: "Trang đã xoá", KIND_BACKUP: "Bản gốc trước khi sửa", KIND_FILE: "File"}


@dataclass
class Entry:
    id: str
    time: float
    kind: str
    name: str                              # tên file gốc
    orig_path: str                         # đường dẫn ban đầu
    stored: str                            # file đang giữ (trong thùng rác hoặc thư mục sao lưu của app)
    pages: List[int] = field(default_factory=list)       # (kind=pages) chỉ số trang gốc đã xoá, từ 0
    total_before: int = 0                  # (kind=pages) số trang của file trước khi xoá
    size: int = 0
    reason: str = ""

    @property
    def page_text(self) -> str:
        if self.kind != KIND_PAGES:
            return ""
        return ", ".join(str(p + 1) for p in self.pages[:12]) + ("…" if len(self.pages) > 12 else "")

    @property
    def exists(self) -> bool:
        return os.path.isfile(self.stored)


def _root() -> str:
    return os.path.join(data_dir(), "trash")


def _entries_dir() -> str:
    d = os.path.join(_root(), "entries")
    os.makedirs(d, exist_ok=True)
    return d


def _files_dir() -> str:
    d = os.path.join(_root(), "files")
    os.makedirs(d, exist_ok=True)
    return d


def _new_id() -> str:
    return f"{int(time.time() * 1000):013d}-{uuid.uuid4().hex[:6]}"


def _write(e: Entry) -> None:
    path = os.path.join(_entries_dir(), e.id + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(asdict(e), fh, ensure_ascii=False)
    os.replace(tmp, path)


LEGACY_DIR = "_backup_goc"                 # thư mục sao lưu kiểu cũ nằm cạnh file hồ sơ


def _config_file() -> str:
    return os.path.join(data_dir(), "config.json")


def _config() -> dict:
    try:
        with open(_config_file(), encoding="utf-8") as fh:
            c = json.load(fh)
        return c if isinstance(c, dict) else {}
    except Exception:
        return {}


def set_config(**kw) -> None:
    """Ghi cấu hình dùng chung (đọc được cả trong tiến trình con): backup_root…"""
    c = _config()
    for k, v in kw.items():
        if v in (None, ""):
            c.pop(k, None)
        else:
            c[k] = v
    tmp = _config_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(c, fh, ensure_ascii=False)
    os.replace(tmp, _config_file())


def default_backup_root() -> str:
    return os.path.join(data_dir(), "backup")


def backup_root() -> str:
    r = _config().get("backup_root") or default_backup_root()
    try:
        os.makedirs(r, exist_ok=True)
    except OSError:
        r = default_backup_root()
        os.makedirs(r, exist_ok=True)
    return r


def backup_path_for(src: str) -> str:
    """Nơi cất bản gốc của file `src`: <thư mục sao lưu>/<mã theo đường dẫn>/<tên file> (cố định theo đường dẫn)."""
    key = hashlib.sha1(os.path.normcase(os.path.abspath(src)).encode("utf-8")).hexdigest()[:16]
    return os.path.join(backup_root(), key, os.path.basename(src))


def find_backup(src: str) -> str:
    """Đường dẫn bản sao lưu gốc của `src` nếu có (kiểu mới, rồi kiểu cũ `_backup_goc`); '' nếu không."""
    for p in (backup_path_for(src), os.path.join(os.path.dirname(os.path.abspath(src)), LEGACY_DIR, os.path.basename(src))):
        if os.path.isfile(p):
            return p
    return ""


def make_backup(src: str, reason: str = "Trước khi sửa", register: bool = True) -> bool:
    """Chép bản gốc vào thư mục sao lưu của app (chỉ lần đầu – giữ bản gốc sớm nhất). True nếu vừa tạo bản mới."""
    if find_backup(src):
        return False
    dst = backup_path_for(src)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    if register:
        add_backup(src, dst, reason)
    return True


def migrate_legacy(root: str, progress=None) -> Tuple[int, int, List[str]]:
    """Chuyển mọi thư mục `_backup_goc` cũ dưới `root` vào thư mục sao lưu của app (đăng ký vào thùng rác).
    Trả về (số file đã chuyển, số file bỏ qua, các lỗi). Không chuyển nếu bản sao lưu mới của file đó đã tồn tại."""
    moved = skipped = 0
    errors: List[str] = []
    known = {os.path.normcase(e.stored) for e in list_entries() if e.kind == KIND_BACKUP}
    for dp, dns, fns in os.walk(root):
        if os.path.basename(dp) != LEGACY_DIR:
            continue
        dns[:] = []
        orig_dir = os.path.dirname(dp)
        for fn in fns:
            old = os.path.join(dp, fn)
            orig = os.path.join(orig_dir, fn)
            try:
                dst = backup_path_for(orig)
                if os.path.exists(dst):
                    skipped += 1
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(old, dst)
                if os.path.normcase(old) not in known:
                    add_backup(orig, dst, "Bản gốc chuyển từ _backup_goc cũ")
                else:                                           # mục cũ trỏ tới đường dẫn cũ → trỏ lại đường dẫn mới
                    for e in list_entries():
                        if os.path.normcase(e.stored) == os.path.normcase(old):
                            e.stored = dst
                            _write(e)
                moved += 1
                if progress:
                    progress(moved)
            except Exception as ex:
                errors.append(f"{fn}: {ex}")
        try:
            os.rmdir(dp)                                        # thư mục trống thì bỏ luôn
        except OSError:
            pass
    return moved, skipped, errors


def _in_trash(path: str) -> bool:
    return os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(os.path.abspath(_files_dir())) + os.sep)


# ------------------------------------------------------------------ ghi vào thùng rác

def add_pages(src, indices, reason: str = "Xoá trang", path: str = "") -> Optional[Entry]:
    """Cất các trang `indices` (từ 0) của `src` (đường dẫn hoặc tài liệu fitz đang mở) vào thùng rác."""
    try:
        own = isinstance(src, str)
        doc = fitz.open(src) if own else src
        try:
            idx = sorted({i for i in indices if 0 <= i < doc.page_count})
            if not idx:
                return None
            eid = _new_id()
            out = fitz.open()
            for i in idx:
                out.insert_pdf(doc, from_page=i, to_page=i)
            stored = os.path.join(_files_dir(), eid + ".pdf")
            out.save(stored, garbage=3, deflate=True)
            out.close()
            path = src if own else (path or doc.name or "")
            e = Entry(eid, time.time(), KIND_PAGES, os.path.basename(path), os.path.abspath(path) if path else "",
                      stored, idx, doc.page_count, os.path.getsize(stored), reason)
            _write(e)
            return e
        finally:
            if own:
                doc.close()
    except Exception:
        return None


def add_backup(orig_path: str, backup_path: str, reason: str = "Trước khi sửa") -> Optional[Entry]:
    """Đăng ký bản gốc đã sao lưu (không chép lại file)."""
    try:
        if not os.path.isfile(backup_path):
            return None
        e = Entry(_new_id(), time.time(), KIND_BACKUP, os.path.basename(orig_path), os.path.abspath(orig_path),
                  os.path.abspath(backup_path), [], 0, os.path.getsize(backup_path), reason)
        _write(e)
        return e
    except Exception:
        return None


def add_file(src: str, reason: str = "Bản trước khi thay") -> Optional[Entry]:
    """Chép nguyên file vào thùng rác."""
    try:
        eid = _new_id()
        stored = os.path.join(_files_dir(), eid + ".pdf")
        shutil.copy2(src, stored)
        e = Entry(eid, time.time(), KIND_FILE, os.path.basename(src), os.path.abspath(src), stored, [], 0,
                  os.path.getsize(stored), reason)
        _write(e)
        return e
    except Exception:
        return None


# ------------------------------------------------------------------ đọc
def list_entries() -> List[Entry]:
    out: List[Entry] = []
    d = _entries_dir()
    for fn in os.listdir(d):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn), encoding="utf-8") as fh:
                out.append(Entry(**json.load(fh)))
        except Exception:
            continue
    out.sort(key=lambda e: e.time, reverse=True)
    return out


def total_size(entries: Optional[List[Entry]] = None) -> int:
    return sum(e.size for e in (entries if entries is not None else list_entries()) if e.exists)


# ------------------------------------------------------------------ xoá vĩnh viễn
def _drop_entry_file(e: Entry) -> None:
    try:
        os.remove(os.path.join(_entries_dir(), e.id + ".json"))
    except OSError:
        pass


def delete(e: Entry) -> None:
    """Xoá vĩnh viễn: file đang giữ (trong thùng rác hoặc bản sao lưu _backup_goc) và mục."""
    try:
        if e.exists and (_in_trash(e.stored) or e.kind == KIND_BACKUP):
            os.remove(e.stored)
            if e.kind == KIND_BACKUP:
                try:
                    os.rmdir(os.path.dirname(e.stored))          # thư mục _backup_goc trống thì bỏ luôn
                except OSError:
                    pass
    except OSError:
        pass
    _drop_entry_file(e)


def clear() -> int:
    n = 0
    for e in list_entries():
        delete(e)
        n += 1
    return n


def purge_older_than(days: int) -> int:
    limit = time.time() - days * 86400
    n = 0
    for e in list_entries():
        if e.time < limit:
            delete(e)
            n += 1
    return n


def purge_missing() -> int:
    n = 0
    for e in list_entries():
        if not e.exists:
            _drop_entry_file(e)
            n += 1
    return n


# ------------------------------------------------------------------ khôi phục
def _unique(path: str) -> str:
    base, ext = os.path.splitext(path)
    k, cand = 2, path
    while os.path.exists(cand):
        cand = f"{base} ({k}){ext}"
        k += 1
    return cand


def _atomic_write(dst: str, writer) -> None:
    folder = os.path.dirname(os.path.abspath(dst))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".partial.pdf", dir=folder)
    os.close(fd)
    try:
        writer(tmp)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def restore(e: Entry, dest_dir: Optional[str] = None) -> Tuple[bool, str, str]:
    """Khôi phục 1 mục. Trả về (thành công, thông báo, đường dẫn file kết quả).
    dest_dir: nơi lưu khi thư mục / file gốc không còn (mặc định: chỗ cũ)."""
    if not e.exists:
        return False, "File lưu trong thùng rác đã bị mất (không khôi phục được).", ""
    try:
        orig_ok = os.path.isfile(e.orig_path)
        folder = os.path.dirname(e.orig_path)
        if e.kind == KIND_PAGES:
            if orig_ok:
                with open(e.orig_path, "rb") as fh:
                    doc = fitz.open(stream=fh.read(), filetype="pdf")      # đọc vào RAM: không khoá file khi thay
                bin_doc = fitz.open(e.stored)
                try:
                    if bin_doc.page_count != len(e.pages):
                        return False, "File lưu các trang đã xoá không khớp – không khôi phục được.", ""
                    for k, idx in enumerate(sorted(e.pages)):
                        doc.insert_pdf(bin_doc, from_page=k, to_page=k, start_at=min(idx, doc.page_count))
                    n_now = doc.page_count
                    _atomic_write(e.orig_path, lambda tmp: doc.save(tmp, garbage=3, deflate=True))
                finally:
                    doc.close()
                    bin_doc.close()
                _drop_entry_file(e)
                _remove_stored(e)
                return True, f"Đã chèn lại {len(e.pages)} trang vào {e.name} (nay {n_now} trang).", e.orig_path
            target_dir = dest_dir or (folder if os.path.isdir(folder) else "")
            if not target_dir:
                return False, "Thư mục gốc không còn – hãy chọn nơi lưu.", ""
            stem = os.path.splitext(e.name)[0]
            dst = _unique(os.path.join(target_dir, f"{stem}_trang_khoi_phuc.pdf"))
            shutil.copy2(e.stored, dst)
            _drop_entry_file(e)
            _remove_stored(e)
            return True, f"File gốc không còn – đã lưu các trang khôi phục thành {os.path.basename(dst)}.", dst
        # backup / file: cả file
        if orig_ok and e.kind == KIND_BACKUP:
            add_file(e.orig_path, "Bản hiện tại trước khi khôi phục bản gốc")     # để khôi phục xong vẫn quay lại được
            _atomic_write(e.orig_path, lambda tmp: shutil.copy2(e.stored, tmp))
            dst = e.orig_path
        else:
            target_dir = dest_dir or (folder if os.path.isdir(folder) else "")
            if not target_dir:
                return False, "Thư mục gốc không còn – hãy chọn nơi lưu.", ""
            dst = os.path.join(target_dir, e.name)
            if os.path.exists(dst):
                dst = _unique(os.path.join(target_dir, os.path.splitext(e.name)[0] + "_khoi_phuc.pdf"))
            shutil.copy2(e.stored, dst)
        _drop_entry_file(e)
        _remove_stored(e)
        return True, f"Đã khôi phục {os.path.basename(dst)}.", dst
    except Exception as ex:
        return False, f"Lỗi khi khôi phục: {ex}", ""


def _remove_stored(e: Entry) -> None:
    try:
        if e.exists and (_in_trash(e.stored) or e.kind == KIND_BACKUP):
            os.remove(e.stored)
            if e.kind == KIND_BACKUP:
                try:
                    os.rmdir(os.path.dirname(e.stored))
                except OSError:
                    pass
    except OSError:
        pass
