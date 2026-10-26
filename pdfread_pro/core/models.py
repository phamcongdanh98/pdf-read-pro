"""Mô hình dữ liệu dùng chung cho quét, thống kê và giao diện."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

# Từ "signed" đứng sau . _ - hoặc khoảng trắng; không nhầm "unsigned", "signedx".
_SIGNED_NAME = re.compile(r"(?:^|[.\s_\-])signed(?=$|[.\s_\-(])", re.I)

BACKUP_DIR = "_backup_goc"


def name_is_signed(filename: str) -> bool:
    stem = filename[:-4] if filename.lower().endswith(".pdf") else filename
    return bool(_SIGNED_NAME.search(stem))


@dataclass
class FileInfo:
    path: str
    rel: str                      # đường dẫn tương đối so với thư mục gốc
    name: str
    size: int = 0
    mtime: float = 0.0
    pages: Optional[int] = None
    error: str = ""               # rỗng = đọc được
    name_signed: bool = False
    sig_status: str = "none"      # none | ok | modified | broken | unreadable
    sig_count: int = 0
    signers: List[str] = field(default_factory=list)
    sign_time: Optional[datetime] = None

    @property
    def dir_rel(self) -> str:
        d = os.path.dirname(self.rel)
        return d

    @property
    def has_real_sig(self) -> bool:
        return self.sig_status in ("ok", "modified", "broken")

    @property
    def needs_review(self) -> str:
        """Trả về lý do cần xem lại hoặc chuỗi rỗng."""
        if self.error:
            return "error"
        if self.sig_status == "unreadable":
            return "unreadable"
        if self.has_real_sig and not self.name_signed:
            return "sig_no_name"
        if self.name_signed and not self.has_real_sig:
            return "name_no_sig"
        return ""


@dataclass
class ScanResult:
    root: str
    files: List[FileInfo] = field(default_factory=list)
    dirs: List[str] = field(default_factory=list)   # rel, '' = thư mục gốc
    seconds: float = 0.0
    cancelled: bool = False


FILTER_ALL = "all"
FILTER_SIGNED = "signed"
FILTER_UNSIGNED = "unsigned"


def match_filter(f: FileInfo, mode: str) -> bool:
    if mode == FILTER_SIGNED:
        return f.name_signed
    if mode == FILTER_UNSIGNED:
        return not f.name_signed
    return True


def in_scope(dir_rel: str, scope: Optional[str]) -> bool:
    if scope is None:
        return True
    if scope == "":
        return True
    return dir_rel == scope or dir_rel.startswith(scope + os.sep)
