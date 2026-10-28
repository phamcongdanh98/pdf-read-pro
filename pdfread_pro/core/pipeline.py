"""QUY TRÌNH 1 CLICK: chép bản làm việc → đổi tên → giảm dung lượng (≤ N KB/trang) → gom file chưa ký để ký số.

An toàn là trên hết – hồ sơ GỐC không bao giờ bị ghi:
  0. Chép toàn bộ cây hồ sơ sang thư mục làm việc (qua .part, đối chiếu kích thước, kiểm tra dung lượng ổ trước).
  1. Đổi tên TRÊN BẢN CHÉP theo bộ quy tắc đang chọn ở tab Đổi tên (không ghi đè, không ghi lịch sử hoàn tác).
  2. Nén TRÊN BẢN CHÉP; mở lại từng file đã nén, lệch số trang / không mở được → khôi phục từ hồ sơ gốc.
     File đã ký số được giữ nguyên (nén sẽ làm hỏng chữ ký).
  3. Gom file CHƯA KÝ vào thư mục gom (ghi sổ để "Trả về sau ký" ở tab Gom ký số), đối chiếu kích thước.
Mọi lệnh ghi đều đi qua `_guard` – đường dẫn phải nằm trong thư mục làm việc / thư mục gom; nằm trong hồ sơ gốc là dừng.
Mỗi bước lỗi → các bước sau không chạy (không để dữ liệu dở dang), bản chép giữ nguyên để xem."""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import pikepdf

from . import compressor as C, renamer as R, scanner, signgather as G
from .models import BACKUP_DIR, FileInfo

MANIFEST = "_quy_trinh.json"
STEPS = ("Chép bản làm việc", "Đổi tên", "Giảm dung lượng", "Gom để ký số")
OK, WARN, FAIL, SKIP, CANCEL = "ok", "warn", "fail", "skip", "cancel"
DEFAULT_LIMIT_KB = 250


class PipelineError(Exception):
    """Lỗi chặn quy trình (cấu hình sai, nguy cơ ghi vào hồ sơ gốc…)."""


@dataclass
class Config:
    source: str
    work: str
    gather: str
    limit_kb: int = DEFAULT_LIMIT_KB
    clean: bool = True
    batch: str = G.BATCH_NONE
    batch_size: int = 300
    mode: str = "1361"                    # 1361 | custom (lấy từ tab Đổi tên)
    rules: dict = field(default_factory=dict)
    always_suffix: bool = False
    ruleset: dict = field(default_factory=dict)
    policy: str = "auto"
    rule_label: str = ""


@dataclass
class Hooks:
    stage: Callable[[int, str], None] = lambda i, t: None       # bước i bắt đầu
    done: Callable[[int, "StageResult"], None] = lambda i, s: None   # bước i kết thúc (kể cả lỗi / dừng)
    progress: Callable[[int, int], None] = lambda a, b: None
    log: Callable[[str], None] = lambda m: None
    cancelled: Callable[[], bool] = lambda: False


@dataclass
class Rec:
    """1 file PDF đi qua quy trình."""
    rel: str                              # đường dẫn tương đối trong hồ sơ gốc
    folder: str                           # thư mục chứa nó (CCCD_HoVaTen)
    old_name: str
    path: str = ""                        # đường dẫn hiện tại trong bản làm việc
    new_name: str = ""
    rename: str = ""
    rename_level: str = OK
    before: int = 0
    after: int = 0
    pages: int = 0
    comp: str = ""
    comp_level: str = OK
    max_after_kb: float = 0.0
    over_after: int = 0
    gather: str = ""
    gather_level: str = OK
    gather_to: str = ""
    note: str = ""

    @property
    def level(self) -> str:
        lv = (self.rename_level, self.comp_level, self.gather_level)
        return FAIL if FAIL in lv else (WARN if WARN in lv else OK)


@dataclass
class StageResult:
    name: str
    status: str = SKIP
    summary: str = ""
    seconds: float = 0.0


@dataclass
class Report:
    cfg: Config
    stages: List[StageResult] = field(default_factory=lambda: [StageResult(n) for n in STEPS])
    recs: List[Rec] = field(default_factory=list)
    cancelled: bool = False
    error: str = ""
    started: str = ""
    seconds: float = 0.0
    saved_bytes: int = 0
    gathered: int = 0

    @property
    def ok(self) -> bool:
        return not self.error and not self.cancelled and all(s.status in (OK, WARN) for s in self.stages)

    @property
    def level(self) -> str:
        if not self.ok:
            return FAIL
        return WARN if any(s.status == WARN for s in self.stages) else OK


@dataclass
class Preflight:
    """Kết quả kiểm tra trước (KHÔNG ghi gì): tóm tắt để người dùng xác nhận, hoặc lý do không chạy được."""
    files: int = 0
    other_files: int = 0
    total_bytes: int = 0
    signed: int = 0
    broken: int = 0
    rename_ready: int = 0
    rename_same: int = 0
    rename_norule: int = 0
    rename_bad: int = 0
    est_compress: int = 0
    gather_new: int = 0
    gather_skip_signed: int = 0
    gather_not_dossier: int = 0
    gather_dup: int = 0
    need_bytes: int = 0
    free_bytes: int = 0
    problems: List[str] = field(default_factory=list)     # chặn không cho chạy
    warnings: List[str] = field(default_factory=list)     # chạy được nhưng cần biết


# ------------------------------------------------------------------ đường dẫn

def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def _inside(child: str, parent: str) -> bool:
    c, p = _norm(child), _norm(parent)
    return c == p or c.startswith(p + os.sep)


def default_dirs(source: str) -> Tuple[str, str]:
    """(thư mục làm việc, thư mục gom) chưa tồn tại: `<nguồn> - Quy trình` + `<…> - Gom ký số`, thêm (2), (3)… nếu trùng."""
    base = source.rstrip("\\/")
    i = 1
    while True:
        tag = "" if i == 1 else f" ({i})"
        work = f"{base} - Quy trình{tag}"
        gather = f"{work} - Gom ký số"
        if not os.path.exists(work) and not os.path.exists(gather):
            return work, gather
        i += 1


def unique_dir(path: str) -> str:
    """`path` nếu chưa tồn tại, ngược lại thêm (2), (3)…"""
    if not os.path.exists(path):
        return path
    i = 2
    while os.path.exists(f"{path} ({i})"):
        i += 1
    return f"{path} ({i})"


def _is_empty_or_missing(d: str) -> bool:
    try:
        return not os.path.isdir(G._lp(d)) or not os.listdir(G._lp(d))
    except OSError:
        return False


def validate_dirs(source: str, work: str, gather: str) -> List[str]:
    """Các lỗi về thư mục (rỗng = hợp lệ). Hồ sơ gốc, thư mục làm việc và thư mục gom phải tách rời nhau."""
    errs = []
    if not source or not os.path.isdir(source):
        return ["Chưa có thư mục hồ sơ – hãy chọn thư mục ở ô trên cùng và bấm Quét."]
    if not work:
        errs.append("Chưa chọn thư mục làm việc.")
    if not gather:
        errs.append("Chưa chọn thư mục gom.")
    if errs:
        return errs
    pairs = (("thư mục làm việc", work, "hồ sơ gốc", source), ("thư mục gom", gather, "hồ sơ gốc", source),
             ("thư mục gom", gather, "thư mục làm việc", work))
    for na, a, nb, b in pairs:
        if _inside(a, b) or _inside(b, a):
            errs.append(f"{na.capitalize()} không được trùng / lồng với {nb}.")
    for n, d in (("Thư mục làm việc", work), ("Thư mục gom", gather)):
        if not _is_empty_or_missing(d):
            errs.append(f"{n} đã tồn tại và KHÔNG rỗng: {d}\nChọn thư mục mới (app không ghi chồng lên kết quả cũ).")
    return errs


def _guard(path: str, *allowed: str) -> str:
    """Chặn ghi nếu `path` không nằm trong các thư mục được phép – chốt cuối để hồ sơ gốc không bao giờ bị đụng."""
    if not any(_inside(path, a) for a in allowed):
        raise PipelineError(f"Từ chối ghi ngoài thư mục làm việc: {path}")
    return path


def _tree(source: str) -> Tuple[List[str], List[str]]:
    """(các thư mục con tương đối, các file tương đối) của cây hồ sơ; bỏ thư mục _backup_goc."""
    dirs, files = [], []
    for dp, dns, fns in os.walk(source):
        dns[:] = [d for d in dns if d != BACKUP_DIR]
        rel = os.path.relpath(dp, source)
        rel = "" if rel == "." else rel
        for d in dns:
            dirs.append(os.path.join(rel, d))
        for f in fns:
            files.append(os.path.join(rel, f))
    return dirs, files


def _free_bytes(path: str) -> int:
    import shutil
    p = os.path.abspath(path)
    while p and not os.path.isdir(G._lp(p)) and os.path.dirname(p) != p:
        p = os.path.dirname(p)
    try:
        return shutil.disk_usage(G._lp(p)).free
    except OSError:
        return 1 << 62


# ------------------------------------------------------------------ kiểm tra trước (không ghi gì)

def _rename_preview(files: List[FileInfo], cfg: Config):
    if cfg.mode == "1361":
        return R.build_preview_1361(files, cfg.rules, cfg.always_suffix, cfg.policy)
    return R.build_preview(files, cfg.ruleset, cfg.policy)


def preflight(cfg: Config, files: List[FileInfo]) -> Preflight:
    pf = Preflight(files=len(files))
    pf.problems += validate_dirs(cfg.source, cfg.work, cfg.gather)
    if pf.problems and not os.path.isdir(cfg.source or ""):
        return pf
    if not files:
        pf.problems.append("Thư mục hồ sơ không có file PDF nào.")
    if cfg.mode == "1361" and not cfg.rules:
        pf.problems.append("Bộ quy tắc mã số 1361 đang trống – hãy nạp bộ quy tắc ở tab Bộ quy tắc.")
    if not 20 <= cfg.limit_kb <= 20000:
        pf.problems.append("Dung lượng tối đa mỗi trang phải từ 20 đến 20.000 KB.")
    _, rels = _tree(cfg.source)
    pdfs = {os.path.normcase(f.rel) for f in files}
    pf.other_files = sum(1 for r in rels if os.path.normcase(r) not in pdfs)
    disk_pdfs = sum(1 for r in rels if r.lower().endswith(".pdf"))
    if disk_pdfs != len(files):
        pf.warnings.append(f"Trên ổ đĩa có {disk_pdfs} file PDF nhưng lần quét có {len(files)} – thư mục đã thay đổi "
                           "sau khi quét. Quy trình luôn đọc lại bản chép nên kết quả vẫn đúng; nên bấm Quét lại.")
    sizes = {}
    for r in rels:
        try:
            sizes[r] = os.path.getsize(G._lp(os.path.join(cfg.source, r)))
        except OSError:
            sizes[r] = 0
    pf.total_bytes = sum(sizes.values())
    pf.signed = sum(1 for f in files if f.has_real_sig or f.name_signed)
    pf.broken = sum(1 for f in files if f.error)
    lim = cfg.limit_kb * 1024
    pf.est_compress = sum(1 for f in files if not f.error and not (f.has_real_sig or f.name_signed)
                          and f.pages and f.size / f.pages > lim)
    try:
        items = _rename_preview([f for f in files if not f.error], cfg)
    except Exception as e:                                  # quy tắc tuỳ chỉnh hỏng
        pf.problems.append(f"Không tính được tên mới: {e}")
        items = []
    for it in items:
        if it.will_rename:
            pf.rename_ready += 1
        elif it.status == R.ST_SAME:
            pf.rename_same += 1
        elif it.status in (R.ST_NO_RULE, R.ST_NO_CODE):
            pf.rename_norule += 1
        else:
            pf.rename_bad += 1
    gplan = G.plan_gather([f for f in files], cfg.gather)
    for it in gplan:
        if it.status == G.G_NEW:
            pf.gather_new += 1
        elif it.status == G.G_SIGNED:
            pf.gather_skip_signed += 1
        elif it.status == G.G_NOT_DOSSIER:
            pf.gather_not_dossier += 1
        elif it.status == G.G_DUPNAME:
            pf.gather_dup += 1
    unsigned_bytes = sum(f.size for f in files if not (f.has_real_sig or f.name_signed))
    same_drive = _norm(cfg.work)[:2] == _norm(cfg.gather)[:2]
    pf.need_bytes = int(pf.total_bytes * 1.05) + (int(unsigned_bytes * 1.02) if same_drive else 0) + (200 << 20)
    pf.free_bytes = _free_bytes(cfg.work)
    if pf.free_bytes < pf.need_bytes:
        pf.problems.append(f"Ổ đĩa không đủ chỗ: cần khoảng {pf.need_bytes / 2 ** 20:,.0f} MB, "
                           f"chỉ còn {pf.free_bytes / 2 ** 20:,.0f} MB.")
    if not same_drive and _free_bytes(cfg.gather) < int(unsigned_bytes * 1.02) + (100 << 20):
        pf.problems.append("Ổ chứa thư mục gom không đủ chỗ.")
    if pf.broken:
        pf.warnings.append(f"{pf.broken} file PDF lỗi / có mật khẩu: vẫn chép nhưng không nén, không gom.")
    if pf.rename_norule:
        pf.warnings.append(f"{pf.rename_norule} file chưa có quy tắc đổi tên: giữ nguyên tên cũ.")
    if pf.rename_bad:
        pf.warnings.append(f"{pf.rename_bad} file trùng tên / tên không hợp lệ: không đổi tên.")
    if pf.gather_not_dossier:
        pf.warnings.append(f"{pf.gather_not_dossier} file không nằm trong thư mục CCCD_HoVaTen: không được gom.")
    if pf.gather_dup:
        pf.warnings.append(f"{pf.gather_dup} file thuộc thư mục hồ sơ trùng tên ở 2 nơi: không được gom.")
    long_p = max((len(os.path.join(cfg.work, r)) for r in rels), default=0)
    if long_p > G.LONG_PATH:
        pf.warnings.append(f"Có đường dẫn dài {long_p} ký tự (> {G.LONG_PATH}): một số phần mềm khác có thể không mở được.")
    return pf


# ------------------------------------------------------------------ bước 0: chép bản làm việc

def _stage_copy(cfg: Config, rep: Report, hk: Hooks) -> None:
    dirs, rels = _tree(cfg.source)
    G.check_space((os.path.join(cfg.source, r), os.path.join(cfg.work, r)) for r in rels)
    os.makedirs(G._lp(cfg.work), exist_ok=True)
    for d in dirs:
        os.makedirs(G._lp(_guard(os.path.join(cfg.work, d), cfg.work)), exist_ok=True)
    n = bad = 0
    for i, r in enumerate(rels, 1):
        if hk.cancelled():
            raise InterruptedError
        src, dst = os.path.join(cfg.source, r), _guard(os.path.join(cfg.work, r), cfg.work)
        try:
            if not G._copy_new(src, dst):
                raise OSError("Tên đích đã tồn tại")
            if os.path.getsize(G._lp(src)) != os.path.getsize(G._lp(dst)):
                raise OSError("Kích thước sau khi chép không khớp")
            n += 1
        except OSError as e:
            bad += 1
            rep.recs.append(Rec(r, os.path.basename(os.path.dirname(r)), os.path.basename(r), "", "",
                                f"❌ Chép lỗi: {e.strerror or e}", FAIL))
        if i % 25 == 0 or i == len(rels):
            hk.progress(i, len(rels))
    if bad:
        raise PipelineError(f"Chép bản làm việc lỗi {bad} file – dừng, hồ sơ gốc vẫn nguyên vẹn.")
    pdfs = [r for r in rels if r.lower().endswith(".pdf")]
    for r in pdfs:
        rep.recs.append(Rec(r, os.path.basename(os.path.dirname(r)), os.path.basename(r), os.path.join(cfg.work, r)))
    rep.stages[0].summary = f"Đã chép {n:,} file ({len(pdfs):,} PDF) sang bản làm việc".replace(",", ".")


# ------------------------------------------------------------------ bước 1: đổi tên

def _by_path(rep: Report) -> Dict[str, Rec]:
    return {_norm(r.path): r for r in rep.recs if r.path}


def _stage_rename(cfg: Config, rep: Report, hk: Hooks) -> None:
    files = scanner.scan(cfg.work).files
    recs = _by_path(rep)
    items = _rename_preview(files, cfg)
    for it in items:
        _guard(it.fi.path, cfg.work)
        _guard(it.new_path, cfg.work)
        rec = recs.get(_norm(it.fi.path))
        if rec is None:
            continue
        if it.will_rename:
            rec.rename, rec.new_name = "Sẽ đổi tên", it.new_name
        elif it.status == R.ST_SAME:
            rec.rename = "Đã đúng tên"
        elif it.status in (R.ST_NO_RULE, R.ST_NO_CODE):
            rec.rename, rec.rename_level = f"⚠ {it.note or R.STATUS_TEXT[it.status]} – giữ tên cũ", WARN
        else:
            rec.rename, rec.rename_level = f"⚠ {it.note or R.STATUS_TEXT[it.status]} – không đổi", WARN
    todo = [it for it in items if it.will_rename]
    hk.progress(0, max(1, len(todo)))
    rp = R.apply_renames(todo, lambda a, b: hk.progress(a, b), hk.cancelled, record_history=False)
    failed = {_norm(p): why for p, why in rp.failed}
    done = 0
    for it in todo:
        rec = recs.get(_norm(it.fi.path))
        if rec is None:
            continue
        if _norm(it.fi.path) in failed:
            rec.rename, rec.rename_level = f"❌ Đổi tên lỗi: {failed[_norm(it.fi.path)]}", FAIL
        elif os.path.exists(G._lp(it.new_path)) and not os.path.exists(G._lp(it.fi.path)):
            rec.path = it.new_path
            rec.rename = f"✔ Đã đổi: {it.fi.name} → {it.new_name}"
            done += 1
        else:                                                # bị huỷ giữa chừng / không đổi được
            rec.rename, rec.rename_level, rec.new_name = "⚠ Chưa đổi (bị dừng)", WARN, ""
    if hk.cancelled():
        raise InterruptedError
    nr = sum(1 for r in rep.recs if r.rename_level == WARN)
    nf = sum(1 for r in rep.recs if r.rename_level == FAIL)
    rep.stages[1].summary = (f"Đã đổi tên {done:,} file".replace(",", ".")
                             + (f" · {nr} file giữ tên cũ (chưa có quy tắc / trùng)" if nr else "")
                             + (f" · {nf} lỗi" if nf else ""))
    rep.stages[1].status = FAIL if nf else (WARN if nr else OK)
    if nf:
        raise PipelineError(f"Có {nf} file đổi tên lỗi – dừng để kiểm tra (bản chép giữ nguyên).")


# ------------------------------------------------------------------ bước 2: giảm dung lượng

def _verify_pdf(path: str, pages: int) -> str:
    """'' nếu file nén mở được và đủ số trang, ngược lại là lý do lỗi."""
    try:
        with pikepdf.open(G._lp(path)) as pdf:
            n = len(pdf.pages)
        return "" if n == pages else f"lệch số trang ({n} ≠ {pages})"
    except Exception as e:
        return f"không mở được ({e})"


def _restore(rec: Rec, cfg: Config) -> bool:
    """Khôi phục bản nén lỗi từ hồ sơ GỐC (chép qua file tạm rồi thay thế)."""
    import shutil
    src = os.path.join(cfg.source, rec.rel)
    dst = _guard(rec.path, cfg.work)
    tmp = dst + ".restore"
    try:
        shutil.copy2(G._lp(src), G._lp(tmp))
        os.replace(G._lp(tmp), G._lp(dst))
        return True
    except OSError:
        return False
    finally:
        if os.path.exists(G._lp(tmp)):
            try:
                os.remove(G._lp(tmp))
            except OSError:
                pass


def _stage_compress(cfg: Config, rep: Report, hk: Hooks) -> None:
    files = scanner.scan(cfg.work).files
    recs = _by_path(rep)
    jobs = []
    for f in files:
        rec = recs.get(_norm(f.path))
        if rec is None:
            continue
        rec.before = rec.after = f.size
        rec.pages = f.pages or 0
        if f.error:
            rec.comp, rec.comp_level = f"Bỏ qua: {f.error}", WARN
        elif f.has_real_sig or f.name_signed:
            rec.comp = "Giữ nguyên: đã ký số"
        else:
            jobs.append((f.path, _guard(f.path, cfg.work), cfg.limit_kb, False))
    procs = max(1, min(C.safe_workers(), len(jobs))) if jobs else 1
    threads = max(1, min(8, ((os.cpu_count() or 2) - 1) // procs))
    jobs = [j + (threads, cfg.clean) for j in jobs]
    hk.progress(0, max(1, len(jobs)))
    stats = {"ok": 0, "partial": 0, "fail": 0, "restored": 0, "before": 0, "after": 0}
    if jobs:
        with ProcessPoolExecutor(max_workers=procs) as ex:
            futs = {ex.submit(C.job_compress, j): j for j in jobs}
            n = 0
            try:
                for fut in as_completed(futs):
                    if hk.cancelled():
                        raise InterruptedError
                    j = futs[fut]
                    try:
                        r = fut.result()
                    except BrokenProcessPool:
                        raise PipelineError("Một tiến trình nén bị dừng đột ngột (có thể thiếu bộ nhớ) – "
                                            "bản chép giữ nguyên, hồ sơ gốc không bị đụng.")
                    except Exception as e:
                        r = C.Result(path=j[0], status=C.ST_ERROR, message=f"Lỗi: {e}")
                    rec = recs.get(_norm(j[0]))
                    n += 1
                    hk.progress(n, len(jobs))
                    if rec is not None:
                        _apply_compress(rec, r, cfg, stats)
            except BaseException:
                for f in futs:
                    f.cancel()
                raise
    saved = max(0, stats["before"] - stats["after"])
    rep.saved_bytes = saved
    skipped_signed = sum(1 for r in rep.recs if r.comp.startswith("Giữ nguyên"))
    rep.stages[2].summary = (f"{stats['ok']:,} file đạt ≤ {cfg.limit_kb} KB/trang".replace(",", ".")
                             + (f" · {stats['partial']} chưa đạt / không nén được" if stats["partial"] else "")
                             + (f" · {stats['fail']} lỗi" if stats["fail"] else "")
                             + (f" · {stats['restored']} nén lỗi → khôi phục bản gốc" if stats["restored"] else "")
                             + (f" · {skipped_signed} file đã ký giữ nguyên" if skipped_signed else "")
                             + f" · giảm {saved / 2 ** 20:,.1f} MB".replace(",", "."))
    rep.stages[2].status = WARN if (stats["partial"] or stats["fail"] or stats["restored"]) else OK


def _apply_compress(rec: Rec, r: "C.Result", cfg: Config, stats: dict) -> None:
    rec.before, rec.after, rec.pages = r.before or rec.before, r.after or rec.after, r.pages or rec.pages
    rec.max_after_kb, rec.over_after = r.max_after_kb, r.over_after
    changed = r.after != r.before
    if r.status in (C.ST_COMPRESSED, C.ST_PARTIAL) and changed:
        why = _verify_pdf(rec.path, r.pages)
        if why:                                              # nén xong nhưng file hỏng → trả về bản gốc
            ok = _restore(rec, cfg)
            rec.after, rec.comp_level = rec.before, WARN
            rec.comp = f"⚠ Nén lỗi ({why}) → " + ("đã khôi phục bản gốc" if ok else "KHÔNG khôi phục được!")
            if not ok:
                rec.comp_level = FAIL
            stats["restored"] += 1
            stats["before"] += rec.before
            stats["after"] += rec.after
            return
    stats["before"] += r.before
    stats["after"] += r.after
    text = r.message if (r.status == C.ST_ERROR and r.message) else C.STATUS_TEXT.get(r.status, r.status)
    if r.status in (C.ST_COMPRESSED, C.ST_OK_ALREADY):
        rec.comp = "✔ " + text + (f" ({rec.before / 1024:,.0f} → {rec.after / 1024:,.0f} KB)".replace(",", ".")
                                  if changed else "")
        stats["ok"] += 1
    elif r.status in (C.ST_PARTIAL, C.ST_NO_IMAGE, C.ST_NO_GAIN):
        rec.comp = f"⚠ {text} – còn {r.over_after or r.over_before} trang vượt {cfg.limit_kb} KB"
        rec.comp_level = WARN
        stats["partial"] += 1
    else:
        rec.comp, rec.comp_level = "❌ " + text, FAIL if r.status == C.ST_ERROR else WARN
        stats["fail"] += 1


# ------------------------------------------------------------------ bước 3: gom để ký số

def _stage_gather(cfg: Config, rep: Report, hk: Hooks) -> None:
    files = scanner.scan(cfg.work).files
    recs = _by_path(rep)
    for f in files:                                           # PDF lỗi / có mật khẩu: không đem đi ký
        rec = recs.get(_norm(f.path))
        if rec is not None and f.error:
            rec.gather, rec.gather_level = f"⚠ File lỗi ({f.error}) – không gom", WARN
    plan = G.plan_gather([f for f in files if not f.error], cfg.gather, cfg.batch, cfg.batch_size)
    for it in plan:
        rec = recs.get(_norm(it.src))
        if rec is None:
            continue
        if it.status == G.G_SIGNED:
            rec.gather = "Đã có bản ký – không cần gom"
        elif it.status == G.G_NOT_DOSSIER:
            rec.gather, rec.gather_level = "⚠ Không nằm trong thư mục CCCD_HoVaTen – không gom", WARN
        elif it.status == G.G_DUPNAME:
            rec.gather, rec.gather_level = "⚠ Trùng tên hồ sơ ở nơi khác – không gom", WARN
        elif it.status == G.G_NEW:
            rec.gather, rec.gather_to = "Sẽ gom", it.rel
        elif it.status == G.G_EXISTS:
            rec.gather, rec.gather_level = "⚠ Đã có trong thư mục gom", WARN
    todo_plan = [it for it in plan if it.status == G.G_NEW]
    for it in todo_plan:
        _guard(os.path.join(cfg.gather, it.rel), cfg.gather)
    hk.progress(0, max(1, len(todo_plan)))
    j = G.gather(plan, cfg.gather, lambda a, b: hk.progress(a, b), hk.cancelled, None, cfg.work)
    # đối chiếu: file trong thư mục gom phải tồn tại và đúng kích thước
    bad = 0
    got = set(os.path.normcase(p) for p in j.copied)
    for it in todo_plan:
        rec = recs.get(_norm(it.src))
        dst = os.path.join(cfg.gather, it.rel)
        if rec is None:
            continue
        if os.path.normcase(dst) not in got:
            rec.gather, rec.gather_level = "❌ Chưa gom được (bị dừng / lỗi)", FAIL
            bad += 1
        elif os.path.getsize(G._lp(dst)) != os.path.getsize(G._lp(it.src)):
            rec.gather, rec.gather_level = "❌ Gom lỗi: kích thước không khớp", FAIL
            bad += 1
        else:
            rec.gather = "✔ Đã gom để ký"
    if hk.cancelled():
        raise InterruptedError
    rep.gathered = len(j.copied) - bad
    nw = sum(1 for r in rep.recs if r.gather_level == WARN)
    rep.stages[3].summary = (f"Đã gom {rep.gathered:,} file chưa ký vào thư mục gom".replace(",", ".")
                             + (f" · {nw} file không gom (xem cột Gom)" if nw else "") + (f" · {bad} lỗi" if bad else ""))
    rep.stages[3].status = FAIL if bad else (WARN if nw else OK)
    if bad:
        raise PipelineError(f"{bad} file gom lỗi – xem bảng kết quả.")


# ------------------------------------------------------------------ chạy cả quy trình

_STAGES = (_stage_copy, _stage_rename, _stage_compress, _stage_gather)


def _write_manifest(cfg: Config, rep: Report) -> None:
    data = {"app": "PDF-Read Pro", "created": rep.started, "source": cfg.source, "work": cfg.work,
            "gather": cfg.gather, "limit_kb": cfg.limit_kb, "rule": cfg.rule_label,
            "stages": [{"name": s.name, "status": s.status, "summary": s.summary} for s in rep.stages],
            "files": len(rep.recs), "saved_bytes": rep.saved_bytes, "gathered": rep.gathered}
    tmp = os.path.join(cfg.work, MANIFEST + ".tmp")
    with open(G._lp(tmp), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(G._lp(tmp), G._lp(os.path.join(cfg.work, MANIFEST)))


def run(cfg: Config, hk: Optional[Hooks] = None) -> Report:
    """Chạy tuần tự 4 bước. Không ném lỗi: mọi sự cố nằm trong Report (error / stage fail / cancelled)."""
    hk = hk or Hooks()
    rep = Report(cfg, started=datetime.now().isoformat(timespec="seconds"))
    t0 = time.time()
    errs = validate_dirs(cfg.source, cfg.work, cfg.gather)
    if errs:
        rep.error = "\n".join(errs)
        return rep
    cur = -1
    try:
        for i, fn in enumerate(_STAGES):
            cur = i
            st = rep.stages[i]
            hk.stage(i, STEPS[i])
            hk.log(f"▶ Bước {i}: {STEPS[i]}")
            t1 = time.time()
            st.status = OK
            fn(cfg, rep, hk)
            st.seconds = time.time() - t1
            hk.log(f"{'⚠' if st.status == WARN else '✔'} {STEPS[i]}: {st.summary}")
            hk.done(i, st)
    except InterruptedError:
        rep.cancelled = True
        rep.stages[cur].status, rep.stages[cur].summary = CANCEL, "Đã dừng theo yêu cầu"
        rep.error = "Đã dừng. Hồ sơ gốc không bị đụng; bản chép giữ nguyên để xem."
        hk.done(cur, rep.stages[cur])
    except Exception as e:
        rep.stages[cur].status = FAIL
        rep.stages[cur].summary = rep.stages[cur].summary or str(e)
        rep.error = getattr(e, "strerror", None) or str(e) or e.__class__.__name__
        hk.log(f"❌ {STEPS[cur]}: {rep.error}")
        pe = getattr(e, "partial_journal", None)
        if pe is not None and cur == 3:
            rep.gathered = len(pe.copied)
        hk.done(cur, rep.stages[cur])
    rep.seconds = time.time() - t0
    if os.path.isdir(G._lp(cfg.work)):
        try:
            _write_manifest(cfg, rep)
        except OSError:
            pass
    return rep


# ------------------------------------------------------------------ xoá kết quả (làm lại)

def removable(cfg_work: str, cfg_gather: str) -> List[str]:
    """Các thư mục do quy trình tạo (nhận ra bằng file sổ) – chỉ những thư mục này mới được xoá."""
    out = []
    if cfg_work and os.path.isfile(G._lp(os.path.join(cfg_work, MANIFEST))):
        out.append(cfg_work)
    if cfg_gather and os.path.isfile(G._lp(os.path.join(cfg_gather, G.MANIFEST))):
        out.append(cfg_gather)
    return out
