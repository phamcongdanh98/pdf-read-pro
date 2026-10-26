"""Thống kê: MỘT nguồn số liệu duy nhất cho 5 thẻ, bảng và danh sách chi tiết."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from .models import FILTER_ALL, FileInfo, ScanResult, in_scope, match_filter


@dataclass
class Stats:
    # Thẻ 1 – thư mục
    dirs_with_pdf: int = 0          # thư mục có PDF TRỰC TIẾP (theo bộ lọc)
    dirs_container_only: int = 0    # chỉ chứa thư mục con có PDF, không có PDF trực tiếp
    dirs_total: int = 0             # tổng số thư mục trong phạm vi (không tính thư mục gốc phạm vi)
    # Thẻ 2 – file
    files: int = 0                  # theo bộ lọc
    files_signed_name: int = 0      # không phụ thuộc bộ lọc
    files_unsigned_name: int = 0
    # Thẻ 3 – trang
    pages: int = 0
    pages_signed_name: int = 0
    pages_unsigned_name: int = 0
    # Thẻ 4 – chữ ký số thật
    sig_files: int = 0
    sig_ok: int = 0
    sig_modified: int = 0
    sig_broken: int = 0
    # Thẻ 5 – cần xem lại
    review: int = 0
    review_sig_no_name: int = 0
    review_name_no_sig: int = 0
    review_unreadable: int = 0
    review_error: int = 0


def files_in(result: ScanResult, scope: Optional[str], mode: str = FILTER_ALL) -> List[FileInfo]:
    return [f for f in result.files if in_scope(f.dir_rel, scope) and match_filter(f, mode)]


def compute(result: ScanResult, scope: Optional[str], mode: str) -> Stats:
    st = Stats()
    scoped = [f for f in result.files if in_scope(f.dir_rel, scope)]
    direct_all = {f.dir_rel for f in scoped}
    st.dirs_total = sum(1 for d in result.dirs if d and in_scope(d, scope) and d != scope)
    ancestors = set()
    for d in direct_all:
        cur = d
        while cur and cur not in ancestors:
            cur = os.path.dirname(cur)
            ancestors.add(cur)
    for d in result.dirs:
        if d and d != scope and in_scope(d, scope) and d not in direct_all and d in ancestors:
            st.dirs_container_only += 1
    flt = [f for f in scoped if match_filter(f, mode)]
    st.dirs_with_pdf = len({f.dir_rel for f in flt})
    st.files = len(flt)
    for f in scoped:
        if f.name_signed:
            st.files_signed_name += 1
            st.pages_signed_name += f.pages or 0
        else:
            st.files_unsigned_name += 1
            st.pages_unsigned_name += f.pages or 0
    for f in flt:
        st.pages += f.pages or 0
        if f.has_real_sig:
            st.sig_files += 1
            if f.sig_status == "ok":
                st.sig_ok += 1
            elif f.sig_status == "modified":
                st.sig_modified += 1
            else:
                st.sig_broken += 1
        r = f.needs_review
        if r:
            st.review += 1
            if r == "sig_no_name":
                st.review_sig_no_name += 1
            elif r == "name_no_sig":
                st.review_name_no_sig += 1
            elif r == "unreadable":
                st.review_unreadable += 1
            else:
                st.review_error += 1
    return st


def folder_totals(result: ScanResult, mode: str):
    """{dir_rel: (trang_trực_tiếp, trang_cả_con, file_trực_tiếp, file_cả_con, file_ký_thật_cả_con)}"""
    out = {d: [0, 0, 0, 0, 0] for d in result.dirs}
    for f in result.files:
        if not match_filter(f, mode):
            continue
        pg = f.pages or 0
        sg = 1 if f.has_real_sig else 0
        d = f.dir_rel
        e = out.setdefault(d, [0, 0, 0, 0, 0])
        e[0] += pg
        e[2] += 1
        cur = d
        while True:
            e = out.setdefault(cur, [0, 0, 0, 0, 0])
            e[1] += pg
            e[3] += 1
            e[4] += sg
            if not cur:
                break
            cur = os.path.dirname(cur)
    return {k: tuple(v) for k, v in out.items()}
