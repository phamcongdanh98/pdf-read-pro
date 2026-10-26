"""Công cụ hồ sơ: kiểm tra đủ 5 file, thư mục CCCD, copy theo nhóm, xoá vào Thùng rác."""
from __future__ import annotations

import ctypes
import os
import re
import shutil
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .models import BACKUP_DIR, FILTER_ALL, FILTER_SIGNED, FILTER_UNSIGNED, ScanResult, match_filter

# ------------------------------------------------------------------ kiểm tra đủ 5 file

_FIVE = re.compile(r"^0?([1-5])\.")


@dataclass
class FiveRow:
    rel: str
    count_pdf: int
    found: Dict[int, int] = field(default_factory=dict)

    @property
    def missing(self) -> List[int]:
        return [i for i in range(1, 6) if i not in self.found]

    @property
    def duplicates(self) -> List[int]:
        return [i for i, c in self.found.items() if c > 1]

    @property
    def complete(self) -> bool:
        return not self.missing


def check_five(result: ScanResult, scope: Optional[str] = None) -> List[FiveRow]:
    from .models import in_scope
    rows: Dict[str, FiveRow] = {}
    for f in result.files:
        if not in_scope(f.dir_rel, scope):
            continue
        row = rows.setdefault(f.dir_rel, FiveRow(rel=f.dir_rel, count_pdf=0))
        row.count_pdf += 1
        m = _FIVE.match(f.name)
        if m:
            n = int(m.group(1))
            row.found[n] = row.found.get(n, 0) + 1
    return sorted(rows.values(), key=lambda r: r.rel.lower())


# ------------------------------------------------------------------ thư mục CCCD

_CCCD = re.compile(r"^\d{12}$")


@dataclass
class CccdRow:
    rel: str
    path: str
    files: int = 0
    pdfs: int = 0
    size: int = 0


def find_cccd_dirs(result: ScanResult) -> List[CccdRow]:
    out: List[CccdRow] = []
    taken: List[str] = []
    for d in sorted(result.dirs, key=lambda x: (x.count(os.sep), x.lower())):
        if not d or not _CCCD.match(os.path.basename(d)):
            continue
        if any(d.startswith(t + os.sep) for t in taken):      # CCCD nằm trong CCCD khác → bỏ
            continue
        if BACKUP_DIR in d.split(os.sep):
            continue
        taken.append(d)
        row = CccdRow(rel=d, path=os.path.join(result.root, d))
        for dp, dn, fn in os.walk(row.path):
            for n in fn:
                row.files += 1
                if n.lower().endswith(".pdf"):
                    row.pdfs += 1
                try:
                    row.size += os.path.getsize(os.path.join(dp, n))
                except OSError:
                    pass
        out.append(row)
    return out


def drive_is_fixed(path: str) -> bool:
    try:
        root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
        return ctypes.windll.kernel32.GetDriveTypeW(root) == 3
    except Exception:
        return False


class _SHFILEOPSTRUCT(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]


def move_to_recycle_bin(path: str) -> bool:
    op = _SHFILEOPSTRUCT()
    op.wFunc = 3                       # FO_DELETE
    op.pFrom = os.path.abspath(path) + "\0"
    op.fFlags = 0x40 | 0x10 | 0x4 | 0x400   # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return rc == 0 and not op.fAnyOperationsAborted and not os.path.exists(path)


def delete_dir(path: str, permanent: bool) -> Tuple[bool, str]:
    try:
        if permanent:
            shutil.rmtree(path)
            return True, "Đã xoá vĩnh viễn"
        if move_to_recycle_bin(path):
            return True, "Đã chuyển vào Thùng rác"
        return False, "Không chuyển được vào Thùng rác"
    except OSError as e:
        return False, e.strerror or str(e)


# ------------------------------------------------------------------ copy

def unique_dir(path: str) -> str:
    if not os.path.exists(path):
        return path
    i = 2
    while os.path.exists(f"{path} ({i})"):
        i += 1
    return f"{path} ({i})"


def _inside(child: str, parent: str) -> bool:
    c, p = os.path.normcase(os.path.abspath(child)), os.path.normcase(os.path.abspath(parent))
    return c == p or c.startswith(p + os.sep)


GROUP_SUFFIX = {FILTER_ALL: "Tất cả", FILTER_SIGNED: "Signed", FILTER_UNSIGNED: "Không signed"}


def copy_group(result: ScanResult, mode: str, dest_parent: Optional[str] = None,
               progress: Optional[Callable[[int, int], None]] = None, cancel=None) -> Tuple[str, int, int]:
    """Copy nhóm file (theo tên .signed) sang thư mục mới `<nguồn> - <nhóm>`, giữ nguyên cây thư mục
    (kể cả thư mục rỗng). Chỉ copy byte-for-byte, không ghi đè, không đụng file gốc."""
    root = result.root
    parent = dest_parent or os.path.dirname(root)
    dest = unique_dir(os.path.join(parent, f"{os.path.basename(root.rstrip(os.sep))} - {GROUP_SUFFIX[mode]}"))
    if _inside(dest, root):
        raise ValueError("Thư mục đích không được nằm bên trong thư mục nguồn")
    os.makedirs(dest)
    for d in result.dirs:
        if d:
            os.makedirs(os.path.join(dest, d), exist_ok=True)
    files = [f for f in result.files if match_filter(f, mode)]
    n = 0
    for i, f in enumerate(files, 1):
        if cancel is not None and cancel():
            break
        target = os.path.join(dest, f.rel)
        shutil.copy2(f.path, target)
        n += 1
        if progress:
            progress(i, len(files))
    return dest, n, len(files)


def copy_dirs_flat(result: ScanResult, rels: List[str], label: str = "Thiếu file",
                   progress: Optional[Callable[[int, int], None]] = None) -> Tuple[str, int]:
    """Mỗi thư mục trong `rels` được chép ra RIÊNG, ngang hàng (chỉ file nằm trực tiếp trong đó)."""
    root = result.root
    dest = unique_dir(os.path.join(os.path.dirname(root), f"{os.path.basename(root.rstrip(os.sep))} - {label}"))
    os.makedirs(dest)
    count = 0
    for i, rel in enumerate(rels, 1):
        target = unique_dir(os.path.join(dest, os.path.basename(rel) or os.path.basename(root)))
        os.makedirs(target)
        src = os.path.join(root, rel) if rel else root
        for name in os.listdir(src):
            p = os.path.join(src, name)
            if os.path.isfile(p):
                shutil.copy2(p, os.path.join(target, name))
                count += 1
        if progress:
            progress(i, len(rels))
    return dest, count
