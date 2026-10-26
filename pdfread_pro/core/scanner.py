"""Quét thư mục: đếm trang + đọc chữ ký số, chạy song song, có huỷ và tiến trình."""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import pikepdf

from .models import BACKUP_DIR, FileInfo, ScanResult, name_is_signed
from .signature import inspect_signatures, summarize


def analyze_file(fi: FileInfo) -> FileInfo:
    """Điền pages, error, chữ ký cho một file (an toàn khi chạy trong thread)."""
    try:
        with open(fi.path, "rb") as fh:
            data = fh.read()
    except OSError as e:
        fi.error = f"Không đọc được file: {e.strerror or e}"
        return fi
    if not data.lstrip()[:5].startswith(b"%PDF") and b"%PDF" not in data[:1024]:
        fi.error = "Không phải file PDF hợp lệ"
        return fi
    try:
        with pikepdf.open(fi.path) as pdf:
            fi.pages = len(pdf.pages)
    except pikepdf.PasswordError:
        fi.error = "File có mật khẩu"
    except Exception:
        fi.error = "File PDF hỏng hoặc không đọc được"
    try:
        sigs = inspect_signatures(data)
        fi.sig_count = len(sigs)
        fi.sig_status, fi.signers, fi.sign_time = summarize(sigs)
    except Exception:
        fi.sig_status = "unreadable"
    return fi


def collect(root: str, recursive: bool):
    files, dirs = [], []
    root = os.path.abspath(root)
    stack = [""]
    while stack:
        rel = stack.pop()
        dirs.append(rel)
        cur = os.path.join(root, rel) if rel else root
        try:
            entries = list(os.scandir(cur))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if recursive and e.name != BACKUP_DIR:
                        stack.append(os.path.join(rel, e.name) if rel else e.name)
                elif e.is_file() and e.name.lower().endswith(".pdf"):
                    st = e.stat()
                    files.append(FileInfo(
                        path=e.path, rel=os.path.join(rel, e.name) if rel else e.name,
                        name=e.name, size=st.st_size, mtime=st.st_mtime,
                        name_signed=name_is_signed(e.name)))
            except OSError:
                continue
    return files, sorted(dirs)


def scan(root: str, recursive: bool = True,
         progress: Optional[Callable[[int, int, int], None]] = None,
         cancel: Optional[threading.Event] = None, workers: Optional[int] = None) -> ScanResult:
    t0 = time.time()
    files, dirs = collect(root, recursive)
    files.sort(key=lambda f: (f.dir_rel.lower(), f.name.lower()))
    res = ScanResult(root=os.path.abspath(root), files=files, dirs=dirs)
    total = len(files)
    pages = done = 0
    workers = workers or min(8, (os.cpu_count() or 2) * 2)
    if progress:
        progress(0, total, 0)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(analyze_file, f) for f in files]
        try:
            for fut in as_completed(futs):
                if cancel is not None and cancel.is_set():
                    res.cancelled = True
                    break
                fi = fut.result()
                done += 1
                pages += fi.pages or 0
                if progress:
                    progress(done, total, pages)
        finally:
            if res.cancelled:
                for f in futs:
                    f.cancel()
    res.seconds = time.time() - t0
    return res
