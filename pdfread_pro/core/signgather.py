"""GOM KÝ SỐ: gom file PDF chưa ký của nhiều hồ sơ vào 1 thư mục để ký hàng loạt, ký xong trả về đúng hồ sơ.

Bước 1 – Gom (CHÉP, file gốc giữ nguyên):
    <Chi bộ>/056123456789_TranVanThai/01.Ly_lich_nguoi_xin_vao_Dang.pdf
      → <Thư mục gom>/[Lô 01 | <Chi bộ>/]01.Ly_lich_nguoi_xin_vao_Dang_056123456789_TranVanThai.pdf
    Chỉ gom file CHƯA KÝ: bỏ file .signed và file đã có bản .signed cạnh nó. Ghi sổ `_gom_ky_so.json` (ẩn) trong
    thư mục gom: tên trong thư mục gom → thư mục hồ sơ + tên gốc + kích thước / ngày sửa bản gốc lúc gom.

Bước 2 – Trả về (phần mềm ký tạo X_<CCCD_HoVaTen>.signed.pdf / _signed / _ky / (signed), ghi ra thư mục con
`Signed/`, hoặc ký đè lên chính file – đều nhận ra):
    Bản ký phải: có CHỮ KÝ SỐ THẬT (không chỉ đổi tên), chữ ký không hỏng, mở được, CÙNG SỐ TRANG bản gốc, phần mềm
    ký đã ghi xong, bản gốc không bị đổi sau khi gom. Sai 1 điều → giữ lại, báo lý do.
    Trả về hồ sơ gốc (CHUYỂN bản ký, xoá bản sao chưa ký giống hệt) hoặc CHÉP RA THƯ MỤC MỚI (cùng cây
    <Chi bộ>/<CCCD_HoVaTen>/, hồ sơ gốc + thư mục gom giữ nguyên, tuỳ chọn kèm đủ bộ hồ sơ).

An toàn: không bao giờ ghi đè (trùng tên khác nội dung → "xung đột"); chép qua file .part rồi mới đổi tên (mất điện
không để lại file dở); kiểm tra dung lượng ổ trước khi chép; hỗ trợ đường dẫn dài > 260 ký tự; mọi thao tác ghi
nhật ký để hoàn tác (kể cả sau khi tắt app)."""
from __future__ import annotations

import filecmp
import json
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .models import FileInfo
from .renamer import _SIGNED_TAIL
from .scanner import analyze_file

MANIFEST = "_gom_ky_so.json"
REJECT_DIR = "_Bản ký lỗi"                              # bản ký lỗi / dư được tách ra (bỏ qua khi kiểm tra)
REDO_DIR = "Ký lại"                                    # file cần ký lại được tách ra (thư mục con, vẫn được quét)
DOSSIER = re.compile(r"^\d{12}_\S+$")                  # thư mục hồ sơ: 12 số CCCD + "_" + họ tên
_TAIL = re.compile(r"_(\d{12}_[^\\/]+)$")               # đuôi _CCCD_HoVaTen trong tên file đã gom
# đuôi phần mềm ký thêm vào tên: .signed _signed -signed (signed) _ky _da_ky _đã ký _ky_so …
_ANY_TAIL = re.compile(r"(?:(?:[.\s_\-]+|\s*\()(?:signed|(?:đã|da)[ _\-]?k[ýy]|k[ýy][ _\-]?s[ốo]|k[ýy])\)?)+$", re.I)

BUSY_SECONDS = 5            # file vừa đổi trong N giây → coi như phần mềm ký đang ghi
LONG_PATH = 250             # cảnh báo đường dẫn dài (giới hạn cũ của Windows / nhiều phần mềm: 260)
BATCH_NONE, BATCH_CHIBO, BATCH_SIZE = "none", "chibo", "size"

# trạng thái (tiền tố g_ / r_: 2 bước không được trùng mã – TEXT dùng chung 1 bảng)
G_NEW, G_EXISTS, G_SIGNED, G_NOT_DOSSIER, G_DUPNAME = "g_new", "g_exists", "g_signed", "g_not_dossier", "g_dupname"
R_SIGNED, R_BACK, R_DUP, R_CONFLICT, R_WAIT, R_UNKNOWN = ("r_signed", "r_back", "r_dup", "r_conflict", "r_wait",
                                                         "r_unknown")
R_COPY, R_EXTRA, R_HAVE = "r_copy", "r_extra", "r_have"          # chỉ dùng khi chép ra thư mục mới
R_NOSIG, R_BADSIG, R_BAD, R_PAGES, R_BUSY, R_CHANGED, R_SPARE = ("r_nosig", "r_badsig", "r_bad", "r_pages", "r_busy",
                                                                 "r_changed", "r_spare")
TEXT = {G_NEW: "Sẽ gom", G_EXISTS: "Đã có trong thư mục gom", G_SIGNED: "Đã có bản ký – bỏ qua",
        G_NOT_DOSSIER: "Không nằm trong thư mục CCCD_HoVaTen – bỏ qua",
        G_DUPNAME: "Trùng tên hồ sơ ở thư mục khác – bỏ qua",
        R_SIGNED: "Trả bản đã ký về hồ sơ", R_BACK: "Trả bản chưa ký về hồ sơ (hồ sơ không còn bản gốc)",
        R_DUP: "Bản chưa ký giống bản gốc – xoá bản sao",
        R_CONFLICT: "Đích đã có file cùng tên nhưng khác nội dung – giữ lại", R_WAIT: "Chưa ký – giữ lại",
        R_UNKNOWN: "Không rõ thuộc hồ sơ nào – giữ lại",
        R_COPY: "Chép bản chưa ký", R_EXTRA: "Chép kèm file khác của hồ sơ", R_HAVE: "Đã có ở thư mục mới – bỏ qua",
        R_NOSIG: "Tên đã ký nhưng KHÔNG có chữ ký số – giữ lại", R_BADSIG: "Chữ ký số bị hỏng – giữ lại",
        R_BAD: "Bản ký lỗi / không mở được – giữ lại", R_PAGES: "Bản ký khác số trang bản gốc – giữ lại",
        R_BUSY: "Phần mềm đang ghi / mở file – chờ", R_CHANGED: "Bản gốc đã đổi sau khi gom – cần gom & ký lại",
        R_SPARE: "Bản ký dư (đã dùng bản ký khác) – giữ lại"}
assert len(TEXT) == 21, "mã trạng thái bị trùng"
COPY_ACTIONS = (R_SIGNED, R_COPY, R_EXTRA)
BACK_ACTIONS = (R_SIGNED, R_BACK, R_DUP)
ISSUES = {G_DUPNAME, R_CONFLICT, R_UNKNOWN, R_NOSIG, R_BADSIG, R_BAD, R_PAGES, R_BUSY, R_CHANGED, R_SPARE}
REJECTS = {R_NOSIG, R_BADSIG, R_BAD, R_PAGES, R_SPARE, R_CHANGED}  # tách ra _Bản ký lỗi


@dataclass
class GatherItem:
    src: str                 # file gốc
    folder: str              # tên thư mục hồ sơ (CCCD_HoVaTen)
    new_name: str            # tên trong thư mục gom
    status: str
    sub: str = ""            # thư mục con trong thư mục gom (chia lô)
    note: str = ""

    @property
    def rel(self) -> str:
        return os.path.join(self.sub, self.new_name) if self.sub else self.new_name


@dataclass
class ReturnItem:
    path: str                # file nguồn (trong thư mục gom; bản chưa ký / file kèm có thể ở hồ sơ gốc)
    dest: str                # đích ('' nếu không rõ)
    status: str
    folder: str = ""
    note: str = ""
    signed: bool = False     # dòng này là bản đã ký


@dataclass
class Journal:
    """Nhật ký thao tác vừa làm (để hoàn tác): copied = file đã chép mới; moved = (từ, tới);
    removed = (bản sao đã xoá, file gốc giống hệt)."""
    copied: List[str] = field(default_factory=list)
    moved: List[tuple] = field(default_factory=list)
    removed: List[tuple] = field(default_factory=list)
    kind: str = ""           # gather | return | copy | regroup
    info: str = ""
    time: str = ""

    def __len__(self):
        return len(self.copied) + len(self.moved) + len(self.removed)


@dataclass
class Check:
    """Kết quả đọc 1 file PDF: trạng thái chữ ký (none | ok | modified | broken | unreadable), người ký, số trang."""
    sig: str = "none"
    signer: str = ""
    pages: Optional[int] = None
    error: str = ""


# ------------------------------------------------------------------ tiện ích file (đường dẫn dài, không ghi đè)

def _lp(p: str) -> str:
    """Đường dẫn dạng \\\\?\\ cho Windows khi dài (vượt giới hạn 260 ký tự cũ)."""
    if os.name != "nt" or not p:
        return p
    p = os.path.abspath(p)
    if len(p) < 240 or p.startswith("\\\\?\\"):
        return p
    return "\\\\?\\UNC\\" + p[2:] if p.startswith("\\\\") else "\\\\?\\" + p


def _exists(p: str) -> bool:
    return os.path.exists(_lp(p))


def _same(a: str, b: str) -> bool:
    try:
        sa, sb = os.stat(_lp(a)), os.stat(_lp(b))
        if sa.st_size != sb.st_size:
            return False
        if abs(sa.st_mtime - sb.st_mtime) < 2:           # bản chép (copy2) giữ nguyên ngày sửa → khỏi đọc lại từng byte
            return True
        return filecmp.cmp(_lp(a), _lp(b), shallow=False)
    except OSError:
        return False


def _copy_new(src: str, dst: str) -> bool:
    """Chép src → dst qua file .part (mất điện không để lại file dở); dst đã có → không ghi đè, trả False."""
    if _exists(dst):
        return False
    os.makedirs(_lp(os.path.dirname(dst)), exist_ok=True)
    part = dst + ".part"
    shutil.copy2(_lp(src), _lp(part))
    try:
        os.rename(_lp(part), _lp(dst))            # Windows: rename không ghi đè
    except FileExistsError:
        os.remove(_lp(part))
        return False
    return True


def _move_new(src: str, dst: str) -> None:
    os.makedirs(_lp(os.path.dirname(dst)), exist_ok=True)
    if _exists(dst):
        raise FileExistsError(dst)
    shutil.move(_lp(src), _lp(dst))


def _drive(p: str) -> str:
    return os.path.splitdrive(os.path.abspath(p))[0].lower()


def check_space(pairs: Iterable[Tuple[str, str]]) -> None:
    """Ném OSError nếu ổ đích không đủ chỗ cho các file sẽ chép (src, dst)."""
    need: Dict[str, int] = {}
    where: Dict[str, str] = {}
    for src, dst in pairs:
        try:
            n = os.path.getsize(_lp(src))
        except OSError:
            continue
        d = _drive(dst)
        need[d] = need.get(d, 0) + n
        where.setdefault(d, dst)
    for d, n in need.items():
        p = os.path.dirname(os.path.abspath(where[d]))
        while p and not os.path.isdir(_lp(p)) and os.path.dirname(p) != p:
            p = os.path.dirname(p)
        try:
            free = shutil.disk_usage(_lp(p)).free
        except OSError:
            continue
        if free < n * 1.02 + 50 * 2 ** 20:
            raise OSError(f"Ổ {d.upper() or p} không đủ chỗ: cần khoảng {n / 2 ** 20:,.0f} MB, "
                          f"chỉ còn {free / 2 ** 20:,.0f} MB. Hãy giải phóng ổ đĩa hoặc chọn ổ khác.")


def _walk_pdfs(top: str) -> List[str]:
    """Mọi PDF trong thư mục gom kể cả thư mục con (lô, Signed/…); bỏ thư mục bắt đầu bằng '_' và file .part."""
    out, stack = [], [top]
    while stack:
        cur = stack.pop()
        try:
            entries = list(os.scandir(_lp(cur)))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    if not e.name.startswith("_"):
                        stack.append(os.path.join(cur, e.name))
                elif e.name.lower().endswith(".pdf"):
                    out.append(os.path.join(cur, e.name))
            except OSError:
                continue
    return sorted(out, key=lambda p: (os.path.dirname(p).lower(), os.path.basename(p).lower()))


def long_note(path: str) -> str:
    return f"⚠ đường dẫn dài {len(path)} ký tự – phần mềm khác có thể không mở được" if len(path) > LONG_PATH else ""


def _join_note(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


# ------------------------------------------------------------------ đọc PDF (chữ ký thật + số trang), có bộ nhớ đệm

_CACHE: Dict[str, Tuple[int, int, Check]] = {}


def inspect(path: str) -> Check:
    """Chữ ký số thật (băm lại vùng ký) + số trang. Đệm theo (kích thước, ngày sửa) → lần kiểm tra sau gần như tức thì."""
    try:
        st = os.stat(_lp(path))
    except OSError as e:
        return Check(error=f"Không đọc được: {e.strerror or e}")
    key = os.path.normcase(os.path.abspath(path))
    hit = _CACHE.get(key)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        return hit[2]
    if st.st_size == 0:
        chk = Check(error="File rỗng (0 byte)")
    else:
        fi = analyze_file(FileInfo(path=_lp(path), rel="", name=os.path.basename(path)))
        chk = Check(fi.sig_status, ", ".join(fi.signers), fi.pages, fi.error)
    _CACHE[key] = (st.st_size, st.st_mtime_ns, chk)
    return chk


def inspect_many(paths: List[str], progress: Optional[Callable[[int, int], None]] = None) -> Dict[str, Check]:
    out: Dict[str, Check] = {}
    uniq = list(dict.fromkeys(paths))
    with ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 2) * 2)) as ex:
        for i, (p, c) in enumerate(zip(uniq, ex.map(inspect, uniq)), 1):
            out[p] = c
            if progress and (i % 50 == 0 or i == len(uniq)):
                progress(i, len(uniq))
    return out


def _busy(path: str, now: float) -> bool:
    """Phần mềm ký còn đang ghi: file vừa đổi trong BUSY_SECONDS giây hoặc đang bị khoá ghi."""
    try:
        st = os.stat(_lp(path))
    except OSError:
        return False
    if now - st.st_mtime < BUSY_SECONDS:
        return True
    if os.access(_lp(path), os.W_OK):
        try:
            with open(_lp(path), "r+b"):
                pass
        except PermissionError:
            return True
        except OSError:
            pass
    return False


# ------------------------------------------------------------------ tiện ích tên

def split_signed(stem: str):
    """('01.X_0561..._Tran', '.signed') – phần lõi và đuôi ký số (nếu có)."""
    m = _SIGNED_TAIL.search(stem)
    return (stem[:m.start()], stem[m.start():]) if m else (stem, "")


def gathered_name(fi_name: str, folder: str) -> str:
    stem = os.path.splitext(fi_name)[0]
    return f"{stem}_{folder}.pdf"


def _signed_sibling(path: str, names_lower: set) -> bool:
    """X.pdf đã có bản ký cạnh nó (X.signed.pdf, X_signed.pdf…)?"""
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    for n in names_lower:
        if n.endswith(".pdf"):
            core, tail = split_signed(n[:-4])
            if tail and core == stem:
                return True
    return False


# ------------------------------------------------------------------ bước 1: gom

def plan_gather(files: List[FileInfo], gather_dir: str, batch: str = BATCH_NONE, batch_size: int = 300) -> List[GatherItem]:
    gdir = os.path.normcase(os.path.abspath(gather_dir)) if gather_dir else ""
    have = {os.path.basename(p).lower() for p in _walk_pdfs(gather_dir)} if gather_dir and os.path.isdir(gather_dir) \
        else set()
    # cùng tên thư mục hồ sơ ở 2 nơi → tên gom trùng nhau → không gom (báo để sửa)
    places: Dict[str, Dict[str, str]] = {}               # tên hồ sơ → {đường dẫn chuẩn hoá: đường dẫn hiển thị}
    for f in files:
        d = os.path.dirname(f.path)
        if DOSSIER.match(os.path.basename(d)):
            places.setdefault(os.path.basename(d).lower(), {})[os.path.normcase(os.path.abspath(d))] = d
    listing: Dict[str, set] = {}
    out = []
    n_new = 0
    for f in files:
        d = os.path.dirname(f.path)
        if gdir and (os.path.normcase(os.path.abspath(d)) + os.sep).startswith(gdir + os.sep):
            continue                                       # file nằm sẵn trong thư mục gom
        folder = os.path.basename(d)
        if not DOSSIER.match(folder):
            out.append(GatherItem(f.path, folder, "", G_NOT_DOSSIER))
            continue
        if f.name_signed:
            continue                                       # bản đã ký: không gom, không cần liệt kê
        if d not in listing:
            try:
                listing[d] = {n.lower() for n in os.listdir(_lp(d))}
            except OSError:
                listing[d] = set()
        new = gathered_name(f.name, folder)
        note, sub = "", ""
        me = os.path.normcase(os.path.abspath(d))
        others = [v for k, v in places.get(folder.lower(), {}).items() if k != me]
        if others:
            st, note = G_DUPNAME, "Trùng với: " + "; ".join(sorted(others))
        elif _signed_sibling(f.path, listing[d]):
            st = G_SIGNED
        elif new.lower() in have:
            st = G_EXISTS
        else:
            st = G_NEW
            if batch == BATCH_CHIBO:
                sub = os.path.basename(os.path.dirname(d)) or "Khác"
            elif batch == BATCH_SIZE:
                sub = f"Lô {n_new // max(1, batch_size) + 1:02d}"
            n_new += 1
            if gather_dir:
                note = long_note(os.path.join(gather_dir, sub, new))
        out.append(GatherItem(f.path, folder, new, st, sub, note))
    return out


def _load_manifest(gather_dir: str) -> dict:
    try:
        with open(_lp(os.path.join(gather_dir, MANIFEST)), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) and isinstance(data.get("items"), dict) else {"items": {}}
    except (OSError, ValueError):
        return {"items": {}}


def _hide(path: str) -> None:
    if os.name == "nt":            # ẩn: Ctrl+A trong Explorer / phần mềm ký không chọn nhầm file .json
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(_lp(path), 0x2)      # FILE_ATTRIBUTE_HIDDEN
        except (OSError, AttributeError):
            pass


def _save_manifest(gather_dir: str, data: dict) -> None:
    data["updated"] = datetime.now().isoformat(timespec="seconds")
    tmp = os.path.join(gather_dir, MANIFEST + ".tmp")
    with open(_lp(tmp), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    path = os.path.join(gather_dir, MANIFEST)
    os.replace(_lp(tmp), _lp(path))
    _hide(path)


def gather(items: List[GatherItem], gather_dir: str, progress: Optional[Callable[[int, int], None]] = None,
           cancel: Optional[Callable[[], bool]] = None,
           checkpoint: Optional[Callable[[Journal], None]] = None, root: str = "") -> Journal:
    """Chép các file 'Sẽ gom' vào thư mục gom (không ghi đè) và ghi sổ để trả về.
    root: thư mục hồ sơ gốc lúc gom – ghi vào sổ để chép ra thư mục mới giữ đúng cây thư mục (kể cả khi chỉ có 1 chi bộ)."""
    todo = [it for it in items if it.status == G_NEW]
    check_space((it.src, os.path.join(gather_dir, it.rel)) for it in todo)
    os.makedirs(_lp(gather_dir), exist_ok=True)
    data = _load_manifest(gather_dir)
    if root:
        data["root"] = os.path.abspath(root)
    j = Journal(kind="gather", info=gather_dir, time=datetime.now().isoformat(timespec="seconds"))
    try:
        for i, it in enumerate(todo, 1):
            if cancel and cancel():
                break
            if _copy_new(it.src, os.path.join(gather_dir, it.rel)):
                j.copied.append(os.path.join(gather_dir, it.rel))
                st = os.stat(_lp(it.src))
                data["items"][it.new_name] = {"dir": os.path.dirname(it.src), "name": os.path.basename(it.src),
                                              "size": st.st_size, "mtime": st.st_mtime_ns}
            if i % 100 == 0:                               # mất điện giữa chừng vẫn còn sổ + nhật ký hoàn tác
                _save_manifest(gather_dir, data)
                if checkpoint:
                    checkpoint(j)
            if progress:
                progress(i, len(todo))
    except Exception as e:                                 # lỗi giữa chừng: phần đã làm vẫn hoàn tác được
        e.partial_journal = j
        raise
    finally:
        _save_manifest(gather_dir, data)
    return j


# ------------------------------------------------------------------ bước 2: trả về

def _find_dossier(folder: str, roots: List[str], index: Dict[str, str]) -> str:
    """Thư mục hồ sơ theo tên (khi không có sổ ghi): tìm trong cây thư mục đã quét."""
    if not index:
        for r in roots:
            for dp, dns, _ in os.walk(r):
                for d in dns:
                    if DOSSIER.match(d):
                        index.setdefault(d.lower(), os.path.join(dp, d))
        index.setdefault("", "")                           # đã dựng (kể cả rỗng) → không đi lại
    return index.get(folder.lower(), "")


def looks_like_gather(gather_dir: str) -> bool:
    """Thư mục này đã được gom rồi? (có sổ ghi, hoặc có PDF tên đuôi _CCCD_HoVaTen) → tab hiện luôn bảng ② Trả về."""
    if not gather_dir or not os.path.isdir(_lp(gather_dir)):
        return False
    if os.path.isfile(_lp(os.path.join(gather_dir, MANIFEST))):
        return True
    for p in _walk_pdfs(gather_dir)[:50]:
        m = _ANY_TAIL.search(os.path.basename(p)[:-4])
        if _TAIL.search(os.path.basename(p)[:-4][:m.start()] if m else os.path.basename(p)[:-4]):
            return True
    return False


def count_dossiers(folder: str, depth: int = 3) -> int:
    """Số thư mục hồ sơ CCCD_HoVaTen trong cây (tối đa `depth` cấp) – nhận ra thư mục HỒ SƠ / chi bộ."""
    n, level = 0, [folder]
    for _ in range(depth):
        nxt = []
        for d in level:
            try:
                for e in os.scandir(_lp(d)):
                    if e.is_dir(follow_symlinks=False):
                        if DOSSIER.match(e.name):
                            n += 1
                        else:
                            nxt.append(os.path.join(d, e.name))
            except OSError:
                continue
        if n:
            break
        level = nxt[:200]
    return n


def guess_root(gather_dir: str) -> str:
    """Thư mục hồ sơ gốc theo sổ ghi (thư mục gốc lúc gom; sổ cũ thì suy ra thư mục chung chứa các thư mục hồ sơ) –
    dùng được cả khi CHƯA quét."""
    man = _load_manifest(gather_dir)
    root = man.get("root")
    if isinstance(root, str) and root and os.path.isdir(_lp(root)):
        return root
    parents = {os.path.dirname(os.path.abspath(r["dir"])) for r in man["items"].values()
               if isinstance(r, dict) and isinstance(r.get("dir"), str) and r["dir"]}
    if not parents:
        return ""
    try:
        return os.path.commonpath(sorted(parents))
    except ValueError:                                     # khác ổ đĩa
        return ""


def _out_dir_of(dossier: str, roots: List[str], out_dir: str) -> str:
    """Thư mục hồ sơ tương ứng trong thư mục mới: giữ cây thư mục tính từ thư mục đang quét."""
    d = os.path.normcase(os.path.abspath(dossier))
    for r in roots:
        rr = os.path.normcase(os.path.abspath(r))
        if d.startswith(rr + os.sep):
            return os.path.join(out_dir, os.path.relpath(os.path.abspath(dossier), os.path.abspath(r)))
    return os.path.join(out_dir, os.path.basename(dossier))


def _record(core: str, data_l: Dict[str, dict], roots: List[str], index: Dict[str, str]) -> Optional[dict]:
    rec = data_l.get(core.lower() + ".pdf")
    if isinstance(rec, dict) and isinstance(rec.get("dir"), str) and isinstance(rec.get("name"), str):
        return rec
    m = _TAIL.search(core)                                 # không có trong sổ: đoán theo đuôi _CCCD_HoVaTen
    if m:
        d = _find_dossier(m.group(1), roots, index)
        if d:
            return {"dir": d, "name": core[:m.start()] + ".pdf"}
    return None


def _orig_changed(rec: dict, orig: str) -> bool:
    if "size" not in rec or not _exists(orig):
        return False
    try:
        st = os.stat(_lp(orig))
    except OSError:
        return False
    return st.st_size != rec.get("size") or st.st_mtime_ns != rec.get("mtime")


def plan_return(gather_dir: str, roots: List[str], out_dir: str = "", full: bool = True, verify: bool = True,
                progress: Optional[Callable[[int, int], None]] = None) -> List[ReturnItem]:
    """out_dir rỗng: trả về hồ sơ gốc. out_dir có giá trị: chép ra thư mục mới (full = kèm file khác của hồ sơ).
    verify: chỉ nhận bản ký có chữ ký số thật, không hỏng, cùng số trang bản gốc."""
    data_l = {k.lower(): v for k, v in _load_manifest(gather_dir)["items"].items()}
    paths = _walk_pdfs(gather_dir)
    index: Dict[str, str] = {}
    groups: Dict[tuple, dict] = {}
    out: List[ReturnItem] = []
    for p in paths:                                        # 1) nhận diện file thuộc hồ sơ nào, bản ký hay chưa
        stem = os.path.basename(p)[:-4]
        core, tail, rec = stem, "", _record(stem, data_l, roots, index)
        if rec is None:
            m = _ANY_TAIL.search(stem)
            if m:
                core, tail = stem[:m.start()], m.group()
                rec = _record(core, data_l, roots, index)
        if rec is None:
            out.append(ReturnItem(p, "", R_UNKNOWN, note=long_note(p)))
            continue
        g = groups.setdefault((os.path.normcase(rec["dir"]), rec["name"].lower()),
                              {"rec": rec, "signed": [], "plain": []})
        (g["signed"] if tail else g["plain"]).append((p, tail))
    checks: Dict[str, Check] = {}
    if verify and groups:                                  # 2) đọc chữ ký thật + số trang (song song, có đệm)
        want = [p for g in groups.values() for p, _ in g["signed"] + g["plain"]]
        want += [os.path.join(g["rec"]["dir"], g["rec"]["name"]) for g in groups.values()]
        checks = inspect_many([p for p in want if _exists(p)], progress)
    now = time.time()
    dossiers: Dict[str, set] = {}                         # hồ sơ có file chép ra → tên đã có (chép kèm đủ bộ)
    for _, g in sorted(groups.items(), key=lambda kv: (os.path.basename(kv[1]["rec"]["dir"]).lower(), kv[0][1])):
        rec = g["rec"]
        folder = os.path.basename(rec["dir"])
        orig = os.path.join(rec["dir"], rec["name"])
        orig_stem = os.path.splitext(rec["name"])[0]
        signed, plain = list(g["signed"]), list(g["plain"])
        if verify:                                         # ký đè lên chính file / ghi ra Signed/ cùng tên
            for p, t in list(plain):
                if checks.get(p, Check()).sig != "none":
                    plain.remove((p, t))
                    signed.append((p, ""))
        # ưu tiên bản có đuôi .signed / nằm thẳng trong thư mục gom
        signed.sort(key=lambda x: (not x[1], len(os.path.dirname(x[0]))))
        changed = _orig_changed(rec, orig)
        ref = checks.get(orig) if orig in checks else (checks.get(plain[0][0]) if plain else None)
        ref_pages = ref.pages if ref else None
        valid: Optional[Tuple[str, str, str]] = None
        busy = False
        rows: List[ReturnItem] = []
        for p, tail in signed:
            note, st = "", ""
            c = checks.get(p)
            if _busy(p, now):
                st, busy = R_BUSY, True
            elif changed:
                st = R_CHANGED
            elif verify and c is not None:
                if c.pages is None and c.error:
                    st, note = R_BAD, c.error
                elif c.sig == "none":
                    st = R_NOSIG
                elif c.sig == "broken":
                    st, note = R_BADSIG, "nội dung đã bị sửa sau khi ký"
                elif ref_pages and c.pages and c.pages != ref_pages:
                    st, note = R_PAGES, f"bản ký {c.pages} trang ≠ bản gốc {ref_pages} trang"
                else:
                    note = _join_note(f"✔ ký bởi {c.signer}" if c.signer else "✔ có chữ ký số",
                                      {"modified": "⚠ có sửa thêm sau khi ký",
                                       "unreadable": "⚠ không đọc được chi tiết chữ ký"}.get(c.sig, ""))
            if not st:
                if valid is None:
                    valid = (p, tail, note)
                    continue
                st = R_SPARE
            rows.append(ReturnItem(p, "", st, folder, note, True))
        if valid:
            p, tail, note = valid
            dtail = tail if tail and _SIGNED_TAIL.fullmatch(tail) else ".signed"
            base = _out_dir_of(rec["dir"], roots, out_dir) if out_dir else rec["dir"]
            dest = os.path.join(base, orig_stem + dtail + ".pdf")
            if _exists(dest):
                st = (R_HAVE if out_dir else R_SIGNED) if _same(p, dest) else R_CONFLICT
            else:
                st = R_SIGNED
            rows.insert(0, ReturnItem(p, dest, st, folder, _join_note(note, long_note(dest)), True))
        # bản chưa ký
        if out_dir:
            src = plain[0][0] if plain else (orig if _exists(orig) else "")
            for k, (p, _) in enumerate(plain or ([(src, "")] if src and valid else [])):
                dest = os.path.join(_out_dir_of(rec["dir"], roots, out_dir), rec["name"])
                if not valid:
                    st = R_CHANGED if changed else (R_BUSY if busy else R_WAIT)
                elif k:
                    st = R_SPARE
                elif _exists(dest):
                    st = R_HAVE if _same(p, dest) else R_CONFLICT
                else:
                    st = R_COPY
                rows.append(ReturnItem(p, dest if valid else "", st, folder,
                                       long_note(dest) if valid else ("bản ký bị lỗi – xem dòng trên" if signed
                                                                      and not busy else "")))
            if valid:
                taken = dossiers.setdefault(rec["dir"], set())
                taken.add(rec["name"].lower())
                taken.update(os.path.basename(r.dest).lower() for r in rows if r.dest)
        else:
            for p, _ in plain:
                if not valid:
                    st = R_CHANGED if changed else (R_BUSY if busy else R_WAIT)
                    rows.append(ReturnItem(p, "", st, folder, "bản ký bị lỗi – xem dòng trên" if signed and not busy
                                           else ""))
                    continue
                if _exists(orig):
                    st = R_DUP if _same(p, orig) else R_CONFLICT
                else:
                    st = R_BACK                            # hồ sơ không còn bản chưa ký → trả cả bản này về
                rows.append(ReturnItem(p, orig, st, folder))
        out.extend(rows)
    if out_dir and full:                                  # kèm các file khác của hồ sơ → bộ hồ sơ đầy đủ
        for d, taken in sorted(dossiers.items()):
            try:
                names_d = sorted(os.listdir(_lp(d)))
            except OSError:
                continue
            target = _out_dir_of(d, roots, out_dir)
            for n in names_d:
                src = os.path.join(d, n)
                if n.lower() in taken or not os.path.isfile(_lp(src)):
                    continue
                dest = os.path.join(target, n)
                st = (R_HAVE if _same(src, dest) else R_CONFLICT) if _exists(dest) else R_EXTRA
                out.append(ReturnItem(src, dest, st, os.path.basename(d), long_note(dest)))
    return out


def do_return(items: List[ReturnItem], progress: Optional[Callable[[int, int], None]] = None,
              copy: bool = False, cancel: Optional[Callable[[], bool]] = None,
              checkpoint: Optional[Callable[[Journal], None]] = None) -> Journal:
    """copy=False: chuyển bản ký về hồ sơ gốc. copy=True: chép ra thư mục mới (không đụng hồ sơ gốc / thư mục gom)."""
    j = Journal(kind="copy" if copy else "return", time=datetime.now().isoformat(timespec="seconds"))
    todo = [it for it in items if it.status in (COPY_ACTIONS if copy else BACK_ACTIONS)]
    if copy:
        check_space((it.path, it.dest) for it in todo)
    else:                                                  # chuyển khác ổ = chép + xoá → cũng cần chỗ trống
        check_space((it.path, it.dest) for it in todo if it.status != R_DUP and _drive(it.path) != _drive(it.dest))
    try:
        for i, it in enumerate(todo, 1):
            if cancel and cancel():
                break
            if copy:
                if _copy_new(it.path, it.dest):            # không ghi đè
                    j.copied.append(it.dest)
            elif it.status == R_DUP:
                os.remove(_lp(it.path))
                j.removed.append((it.path, it.dest))
            elif _exists(it.dest):
                if _same(it.path, it.dest):                # đã trả trước đó (giống hệt) → bỏ bản thừa
                    os.remove(_lp(it.path))
                    j.removed.append((it.path, it.dest))
            else:
                _move_new(it.path, it.dest)
                j.moved.append((it.path, it.dest))
            if checkpoint and i % 100 == 0:
                checkpoint(j)
            if progress:
                progress(i, len(todo))
    except Exception as e:                                 # lỗi giữa chừng: phần đã làm vẫn hoàn tác được
        e.partial_journal = j
        raise
    return j


def verify_copy(items: List[ReturnItem]) -> Tuple[int, List[str]]:
    """Đối chiếu sau khi chép: mỗi file đích phải có mặt và đúng dung lượng bản nguồn. Trả (số đúng, danh sách lỗi)."""
    ok, bad = 0, []
    for it in items:
        try:
            good = os.path.getsize(_lp(it.dest)) == os.path.getsize(_lp(it.path))
        except OSError:
            good = False
        if good:
            ok += 1
        else:
            bad.append(it.dest)
    return ok, bad


def describe(items: List[ReturnItem]) -> Tuple[int, int]:
    """(số hồ sơ, tổng dung lượng byte) của các file sẽ chép / trả về – để hiện trong hộp xác nhận."""
    folders, size = set(), 0
    for it in items:
        folders.add(it.folder)
        try:
            size += os.path.getsize(_lp(it.path))
        except OSError:
            pass
    return len(folders), size


# ------------------------------------------------------------------ tách file cần ký lại / bản ký lỗi

def plan_regroup(items: List[ReturnItem], gather_dir: str) -> List[Tuple[str, str]]:
    """File chưa ký (chờ) → <gom>/Ký lại <ngày giờ>/ (ký riêng phần còn thiếu); bản ký lỗi / dư / bản gốc đã đổi →
    <gom>/_Bản ký lỗi/ (không bị kiểm tra lại). Chỉ file nằm trong thư mục gom."""
    g = os.path.normcase(os.path.abspath(gather_dir)) + os.sep
    redo = os.path.join(gather_dir, f"{REDO_DIR} {datetime.now():%Y-%m-%d %H%M}")
    rej = os.path.join(gather_dir, REJECT_DIR)
    out, used = [], set()
    for it in items:
        if not os.path.normcase(os.path.abspath(it.path)).startswith(g):
            continue
        if it.status in REJECTS:
            base = rej
        elif it.status == R_WAIT and not os.path.basename(os.path.dirname(it.path)).startswith(REDO_DIR):
            base = redo
        else:
            continue
        stem, ext = os.path.splitext(os.path.basename(it.path))
        dst, k = os.path.join(base, stem + ext), 2
        while _exists(dst) or dst.lower() in used:
            dst, k = os.path.join(base, f"{stem} ({k}){ext}"), k + 1
        used.add(dst.lower())
        out.append((it.path, dst))
    return out


def regroup(pairs: List[Tuple[str, str]], progress: Optional[Callable[[int, int], None]] = None) -> Journal:
    j = Journal(kind="regroup", time=datetime.now().isoformat(timespec="seconds"))
    try:
        for i, (src, dst) in enumerate(pairs, 1):
            if _exists(src):
                _move_new(src, dst)
                j.moved.append((src, dst))
            if progress:
                progress(i, len(pairs))
    except Exception as e:
        e.partial_journal = j
        raise
    return j


# ------------------------------------------------------------------ hoàn tác (nhớ cả sau khi tắt app)

def undo(j: Journal, progress: Optional[Callable[[int, int], None]] = None) -> int:
    """Hoàn tác: chuyển file đã trả về lại thư mục gom, chép lại bản sao đã xoá, xoá bản đã chép."""
    n, total, k = 0, len(j), 0

    def step():
        nonlocal k
        k += 1
        if progress and (k % 50 == 0 or k == total):
            progress(k, total)
    for src, dst in reversed(j.moved):
        if _exists(dst) and not _exists(src):
            os.makedirs(_lp(os.path.dirname(src)), exist_ok=True)
            shutil.move(_lp(dst), _lp(src))
            n += 1
        step()
    for copy_path, orig in j.removed:
        if _exists(orig) and not _exists(copy_path):
            shutil.copy2(_lp(orig), _lp(copy_path))
            n += 1
        step()
    for p in j.copied:
        if _exists(p):
            os.remove(_lp(p))
            n += 1
        step()
    return n


def save_journal(path: str, j: Journal) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(asdict(j), fh, ensure_ascii=False)
    os.replace(tmp, path)


def load_journal(path: str) -> Optional[Journal]:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        j = Journal(copied=[str(x) for x in d.get("copied", [])],
                    moved=[tuple(x) for x in d.get("moved", []) if len(x) == 2],
                    removed=[tuple(x) for x in d.get("removed", []) if len(x) == 2],
                    kind=str(d.get("kind", "")), info=str(d.get("info", "")), time=str(d.get("time", "")))
        return j if len(j) else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None
