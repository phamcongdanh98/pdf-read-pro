"""Tab QUY TRÌNH 1 CLICK: Đổi tên → Giảm dung lượng (≤ N KB/trang) → Gom file chưa ký để ký số, chạy tuần tự 1 lần bấm.
Làm việc trên BẢN CHÉP của hồ sơ (hồ sơ gốc không bị sửa). Trước khi chạy có bước kiểm tra trước (không ghi gì) để xác nhận."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Callable, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar, QSpinBox, QTableView,
                               QVBoxLayout, QWidget)

from ..core import activity, pipeline as P, pipeline_excel as PX, signgather as G, tools
from ..core.models import FileInfo
from .common import fmt, open_path, run_bg
from .file_picker import fold
from .styles import button
from .theme import tc

GREEN, AMBER, RED, GRAY, BLUE, TEXT = "#15803D", "#B45309", "#DC2626", "#64748B", "#1D4ED8", "#1E293B"
LEVEL_COLOR = {P.OK: GREEN, P.WARN: AMBER, P.FAIL: RED, P.SKIP: GRAY, P.CANCEL: AMBER}
LEVEL_ICON = {P.OK: "✔", P.WARN: "⚠", P.FAIL: "❌", P.SKIP: "○", P.CANCEL: "■"}
LEVEL_TEXT = {P.OK: "Đạt", P.WARN: "Cần xem", P.FAIL: "Lỗi"}
STEP_HELP = ("Hồ sơ gốc KHÔNG bị sửa: app chép sang một bản làm việc rồi mới đổi tên / nén / gom. Có gì sai thì xoá "
             "bản chép và làm lại.")


class PreflightThread(QThread):
    done = Signal(object, object)

    def __init__(self, cfg: P.Config, files: List[FileInfo]):
        super().__init__()
        self.cfg, self.files = cfg, files

    def run(self):
        try:
            self.done.emit(P.preflight(self.cfg, self.files), None)
        except Exception as e:
            self.done.emit(None, e)


class RunThread(QThread):
    stage = Signal(int, str)
    stage_done = Signal(int, object)
    progress = Signal(int, int)
    log = Signal(str)
    finished_run = Signal(object)

    def __init__(self, cfg: P.Config):
        super().__init__()
        self.cfg = cfg
        self.cancelled = False

    def run(self):
        hk = P.Hooks(stage=lambda i, t: self.stage.emit(i, t), done=lambda i, s: self.stage_done.emit(i, s),
                     progress=lambda a, b: self.progress.emit(a, b), log=lambda m: self.log.emit(m),
                     cancelled=lambda: self.cancelled)
        try:
            rep = P.run(self.cfg, hk)
        except Exception as e:                      # P.run không ném lỗi; phòng hờ để giao diện không treo
            rep = P.Report(self.cfg)
            rep.error = f"Lỗi không lường trước: {e}"
        self.finished_run.emit(rep)


class _Model(QAbstractTableModel):
    COLS = ["STT", "Hồ sơ", "Tên gốc", "Tên mới", "Đổi tên", "Nén", "Gom để ký", "Kết luận"]

    def __init__(self):
        super().__init__()
        self.rows: List[P.Rec] = []

    def set_rows(self, rows: List[P.Rec]):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLS)

    def headerData(self, s, o, role=Qt.DisplayRole):
        return self.COLS[s] if o == Qt.Horizontal and role == Qt.DisplayRole else None

    @staticmethod
    def _cell(r: P.Rec, c: int, row: int):
        return (row + 1, r.folder, r.old_name, r.new_name or r.old_name, r.rename, r.comp, r.gather,
                LEVEL_TEXT[r.level])[c]

    def data(self, idx, role=Qt.DisplayRole):
        r = self.rows[idx.row()]
        c = idx.column()
        if role == Qt.DisplayRole:
            return self._cell(r, c, idx.row())
        if role == Qt.ToolTipRole and c in (2, 3, 4, 5, 6):
            return str(self._cell(r, c, idx.row())) or None
        if role == Qt.ForegroundRole:
            lv = {4: r.rename_level, 5: r.comp_level, 6: r.gather_level, 7: r.level}.get(c)
            if lv and lv != P.OK or c == 7:
                return QColor(tc(LEVEL_COLOR.get(lv or P.OK, TEXT)))
        if role == Qt.TextAlignmentRole and c in (0, 7):
            return int(Qt.AlignCenter)
        return None


class _Filter(QSortFilterProxyModel):
    def __init__(self, panel: "PipelinePanel"):
        super().__init__()
        self.p = panel
        self.text = ""

    def filterAcceptsRow(self, row, parent):
        r = self.sourceModel().rows[row]
        if self.p.ck_issue.isChecked() and r.level == P.OK:
            return False
        return not self.text or self.text in fold(f"{r.folder} {r.old_name} {r.new_name} {r.rename} {r.comp} {r.gather}")


class PipelinePanel(QWidget):
    busyChanged = Signal(bool)
    openSign = Signal(str, str)                # thư mục gom, thư mục làm việc → sang tab Gom ký số để trả về sau ký
    editRules = Signal()                       # mở tab Đổi tên để đổi quy tắc

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.root = ""
        self.files: List[FileInfo] = []
        self.rep: Optional[P.Report] = None
        self.thread: Optional[QThread] = None
        self.pf_thread: Optional[PreflightThread] = None
        self.busy_check: Callable[[], bool] = lambda: False
        self.rename_cfg: Callable[[], dict] = lambda: {"mode": "1361", "rules": {}, "always_suffix": False,
                                                       "ruleset": {}, "policy": "auto", "label": ""}
        self._work_auto = self._gather_auto = True
        self._cfg: Optional[P.Config] = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 8)
        head = QGroupBox("Quy trình 1 click: Đổi tên → Giảm dung lượng → Gom để ký số")
        hl = QVBoxLayout(head)
        steps = QLabel(f"🛡 {STEP_HELP} Gom xong, bạn ký số hàng loạt rồi sang tab <b>Gom ký số</b> để trả về.")
        steps.setObjectName("Steps")
        steps.setWordWrap(True)
        hl.addWidget(steps)
        self.lbl_src = QLabel("")
        self.lbl_src.setWordWrap(True)
        hl.addWidget(self.lbl_src)
        r = QHBoxLayout()
        r.addWidget(QLabel("Bản làm việc:"))
        self.ed_work = QLineEdit()
        self.ed_work.setPlaceholderText("Thư mục MỚI chứa bản chép đã xử lý")
        self.ed_work.textEdited.connect(lambda _: setattr(self, "_work_auto", False))
        r.addWidget(self.ed_work, 1)
        r.addWidget(button("📁 Chọn…", "light", lambda: self._pick(self.ed_work, "_work_auto"), size="sm"))
        r.addWidget(button("📂 Mở", "light", lambda: self._open(self.ed_work.text()), size="sm"))
        hl.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(QLabel("Thư mục gom:"))
        self.ed_gather = QLineEdit()
        self.ed_gather.setPlaceholderText("Thư mục MỚI chứa các file chưa ký để đem đi ký số")
        self.ed_gather.textEdited.connect(lambda _: setattr(self, "_gather_auto", False))
        r.addWidget(self.ed_gather, 1)
        r.addWidget(button("📁 Chọn…", "light", lambda: self._pick(self.ed_gather, "_gather_auto"), size="sm"))
        r.addWidget(button("📂 Mở", "light", lambda: self._open(self.ed_gather.text()), size="sm"))
        hl.addLayout(r)
        r = QHBoxLayout()
        r.addWidget(QLabel("Nén tối đa mỗi trang:"))
        self.sp = QSpinBox()
        self.sp.setRange(20, 20000)
        self.sp.setValue(P.DEFAULT_LIMIT_KB)
        self.sp.setSuffix(" KB")
        self.sp.setMinimumWidth(110)
        r.addWidget(self.sp)
        self.ck_clean = QCheckBox("✨ Rõ chữ")
        self.ck_clean.setToolTip("Làm trắng nền giấy, chữ đậm và sắc hơn (như tab Giảm dung lượng)")
        self.ck_clean.setChecked(True)
        r.addWidget(self.ck_clean)
        r.addSpacing(14)
        r.addWidget(QLabel("Chia lô khi gom:"))
        self.cb_batch = QComboBox()
        for text, data in (("Không chia", G.BATCH_NONE), ("Theo chi bộ", G.BATCH_CHIBO), ("Mỗi lô N file", G.BATCH_SIZE)):
            self.cb_batch.addItem(text, data)
        r.addWidget(self.cb_batch)
        self.sp_batch = QSpinBox()
        self.sp_batch.setRange(10, 5000)
        self.sp_batch.setSingleStep(50)
        self.sp_batch.setValue(300)
        self.sp_batch.setSuffix(" file/lô")
        r.addWidget(self.sp_batch)
        self.cb_batch.currentIndexChanged.connect(lambda _: self.sp_batch.setEnabled(
            self.cb_batch.currentData() == G.BATCH_SIZE and not self.running))
        r.addSpacing(14)
        self.lbl_rule = QLabel("")
        r.addWidget(self.lbl_rule, 1)
        r.addWidget(button("✏ Đổi quy tắc", "light", lambda: self.editRules.emit(), size="sm",
                           tip="Mở tab Đổi tên để chọn bộ quy tắc / mẫu khác"))
        hl.addLayout(r)
        lay.addWidget(head)

        # ---- nút chạy + tiến độ từng bước
        r = QHBoxLayout()
        self.btn_run = button("🚀 CHẠY CẢ QUY TRÌNH", "success", self.start, size="lg",
                              tip="Kiểm tra trước (không ghi gì) → xác nhận → chạy tuần tự 4 bước")
        self.btn_stop = button("■ Dừng", "danger", self.stop)
        self.btn_stop.setEnabled(False)
        r.addWidget(self.btn_run)
        r.addWidget(self.btn_stop)
        self.prog = QProgressBar()
        self.prog.hide()
        r.addWidget(self.prog, 1)
        self.lbl_now = QLabel("")
        self.lbl_now.setStyleSheet("font-weight:700;color:#1E40AF")
        r.addWidget(self.lbl_now)
        lay.addLayout(r)
        box = QFrame()
        box.setObjectName("FileBox")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(10, 6, 10, 6)
        self.step_lbl: List[QLabel] = []
        for i, name in enumerate(P.STEPS):
            lb = QLabel("")
            lb.setWordWrap(True)
            bl.addWidget(lb)
            self.step_lbl.append(lb)
        lay.addWidget(box)
        self._reset_steps()

        # ---- bảng kết quả từng file
        r = QHBoxLayout()
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("🔎 Tìm hồ sơ / tên file / ghi chú (không cần dấu)…")
        self.ed_search.setClearButtonEnabled(True)
        r.addWidget(self.ed_search, 1)
        self.ck_issue = QCheckBox("⚠ Chỉ file cần xem")
        r.addWidget(self.ck_issue)
        self.btn_open_g = button("📂 Thư mục gom", "light", lambda: self._open(self._res_dir("gather")), size="sm")
        self.btn_open_w = button("📂 Bản làm việc", "light", lambda: self._open(self._res_dir("work")), size="sm")
        self.btn_excel = button("📊 Xuất Excel", "light", self.export_excel, size="sm")
        self.btn_sign = button("➡ Sang tab Gom ký số", "indigo", self.to_sign, size="sm",
                               tip="Sau khi ký xong: chọn trả về / chép ra thư mục mới ở tab Gom ký số")
        self.btn_del = button("🗑 Xoá kết quả (làm lại)", "light", self.delete_results, size="sm",
                              tip="Chuyển bản làm việc + thư mục gom do quy trình tạo vào Thùng rác")
        for b in (self.btn_open_g, self.btn_open_w, self.btn_excel, self.btn_sign, self.btn_del):
            r.addWidget(b)
        lay.addLayout(r)
        self.model = _Model()
        self.proxy = _Filter(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setMinimumHeight(190)               # luôn thấy được vài dòng kết quả (tab cuộn khi màn hình thấp)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, w in enumerate((50, 210, 250, 250, 260, 300, 240)):
            self.table.setColumnWidth(i, w)
        lay.addWidget(self.table, 1)
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self._apply_filter)
        self.ed_search.textChanged.connect(lambda _: self._timer.start())
        self.ck_issue.toggled.connect(self._apply_filter)

        self.lbl = QLabel("Chọn thư mục hồ sơ ở ô trên cùng, bấm Quét, rồi bấm “🚀 CHẠY CẢ QUY TRÌNH”.")
        self.lbl.setWordWrap(True)
        self.lbl.setStyleSheet("font-weight:700;color:#1E40AF")
        lay.addWidget(self.lbl)
        self._enable()

    # ------------------------------------------------------------------ dữ liệu vào
    @property
    def running(self) -> bool:
        return self.thread is not None or self.pf_thread is not None

    def set_source(self, root: str, files: List[FileInfo]):
        """Gọi mỗi lần quét xong: hồ sơ gốc = thư mục đang quét (toàn bộ, không theo bộ lọc / phạm vi)."""
        if self.running:
            return
        changed = root != self.root
        self.root, self.files = root, list(files)
        if changed:
            self._work_auto = self._gather_auto = True
            self.rep = None
            self.model.set_rows([])
            self._reset_steps()
        self._auto_dirs()
        self._refresh_info()
        self._enable()

    def _auto_dirs(self):
        if not self.root:
            return
        w, g = P.default_dirs(self.root)
        if self._work_auto:
            self.ed_work.setText(w)
        if self._gather_auto:
            if self._work_auto:
                self.ed_gather.setText(g)
            else:                                      # người dùng tự chọn bản làm việc → thư mục gom đặt theo nó
                base = self.ed_work.text().strip().rstrip("\\/")
                self.ed_gather.setText(P.unique_dir(base + " - Gom ký số") if base else g)

    def _refresh_info(self):
        n = len(self.files)
        if not self.root:
            self.lbl_src.setText("Hồ sơ gốc: <i>chưa quét</i> – chọn thư mục ở ô trên cùng rồi bấm Quét.")
        else:
            self.lbl_src.setText(f"Hồ sơ gốc: <b>{self.root}</b> · {fmt(n)} file PDF "
                                 "<span style='color:#15803D'>(chỉ đọc – không bị sửa)</span>")
        c = self.rename_cfg()
        self.lbl_rule.setText(f"Đổi tên theo: <b>{c.get('label') or '—'}</b>")

    def showEvent(self, e):
        super().showEvent(e)
        if not self.running:
            self._refresh_info()

    def _pick(self, edit: QLineEdit, flag: str):
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục MỚI", os.path.dirname(edit.text()) or "")
        if d:
            edit.setText(os.path.normpath(d))
            setattr(self, flag, False)

    def _open(self, d: str):
        d = (d or "").strip()
        if d and os.path.isdir(d):
            open_path(d)
        else:
            QMessageBox.information(self, "Thư mục", "Thư mục này chưa được tạo – chạy quy trình trước.")

    def _res_dir(self, which: str) -> str:
        if self.rep:
            return self.rep.cfg.work if which == "work" else self.rep.cfg.gather
        return (self.ed_work if which == "work" else self.ed_gather).text()

    # ------------------------------------------------------------------ trạng thái giao diện
    def _enable(self):
        run = self.running
        for w in (self.ed_work, self.ed_gather, self.sp, self.ck_clean, self.cb_batch):
            w.setEnabled(not run)
        self.sp_batch.setEnabled(not run and self.cb_batch.currentData() == G.BATCH_SIZE)
        self.btn_run.setEnabled(not run and bool(self.files))
        self.btn_stop.setEnabled(self.thread is not None)
        done = self.rep is not None and not run
        self.btn_excel.setEnabled(done and bool(self.rep.recs))
        self.btn_open_g.setEnabled(done and os.path.isdir(self.rep.cfg.gather))
        self.btn_open_w.setEnabled(done and os.path.isdir(self.rep.cfg.work))
        self.btn_sign.setEnabled(done and os.path.isfile(os.path.join(self.rep.cfg.gather, G.MANIFEST)))
        self.btn_del.setEnabled(done and bool(P.removable(self.rep.cfg.work, self.rep.cfg.gather)))
        self.prog.setVisible(run)

    def _reset_steps(self):
        for i, lb in enumerate(self.step_lbl):
            lb.setText(f"<span style='color:#64748B'>○ <b>Bước {i}</b> · {P.STEPS[i]}</span>")

    def _set_step(self, i: int, level: str, text: str, running: bool = False):
        icon = "⏳" if running else LEVEL_ICON.get(level, "○")
        color = "#1D4ED8" if running else LEVEL_COLOR.get(level, GRAY)
        self.step_lbl[i].setText(f"<span style='color:{tc(color)}'>{icon} <b>Bước {i}</b> · {P.STEPS[i]}"
                                 + (f" — {text}" if text else "") + "</span>")

    def _apply_filter(self, *_):
        self.proxy.text = fold(self.ed_search.text().strip())
        self.proxy.invalidateFilter()

    def view_rows(self) -> int:
        return self.proxy.rowCount()

    # ------------------------------------------------------------------ bấm chạy
    def _build_cfg(self) -> Optional[P.Config]:
        if not self.root:
            QMessageBox.warning(self, "Chưa có hồ sơ", "Hãy chọn thư mục hồ sơ ở ô trên cùng và bấm Quét.")
            return None
        if self._work_auto or self._gather_auto:
            self._auto_dirs()                          # tên chưa dùng (thêm (2)… nếu lần trước đã có)
        rc = self.rename_cfg()
        self._refresh_info()
        return P.Config(source=os.path.normpath(self.root), work=os.path.normpath(self.ed_work.text().strip().strip('"')),
                        gather=os.path.normpath(self.ed_gather.text().strip().strip('"')), limit_kb=self.sp.value(),
                        clean=self.ck_clean.isChecked(), batch=self.cb_batch.currentData(),
                        batch_size=self.sp_batch.value(), mode=rc["mode"], rules=rc["rules"],
                        always_suffix=rc["always_suffix"], ruleset=rc["ruleset"], policy=rc["policy"],
                        rule_label=rc["label"])

    def start(self):
        if self.running or self.busy_check():
            return
        cfg = self._build_cfg()
        if cfg is None:
            return
        self._cfg = cfg
        self.lbl.setText("⏳ Đang kiểm tra trước (không ghi gì)…")
        self.pf_thread = PreflightThread(cfg, list(self.files))
        self.pf_thread.done.connect(self._preflight_done)
        self.pf_thread.start()
        self._enable()
        self.busyChanged.emit(True)

    def _preflight_done(self, pf: Optional[P.Preflight], err):
        if self.pf_thread:
            self.pf_thread.wait()
        self.pf_thread = None
        self._enable()
        cfg = self._cfg
        if err is not None or pf is None:
            self.busyChanged.emit(False)
            self.lbl.setText(f"❌ Không kiểm tra trước được: {err}")
            QMessageBox.warning(self, "Kiểm tra trước", f"❌ {err}")
            return
        if pf.problems:
            self.busyChanged.emit(False)
            self.lbl.setText("⛔ Chưa chạy được – xem lý do trong hộp thoại.")
            QMessageBox.warning(self, "Chưa chạy được", "Cần sửa trước khi chạy:\n\n• " + "\n• ".join(pf.problems))
            return
        mb = 2 ** 20
        txt = (f"Hồ sơ gốc: {cfg.source}\n   (KHÔNG bị sửa)\nBản làm việc: {cfg.work}\nThư mục gom: {cfg.gather}\n\n"
               f"⓪ Chép {fmt(pf.files + pf.other_files)} file ({pf.total_bytes / mb:,.0f} MB)\n".replace(",", ".")
               + f"① Đổi tên theo {cfg.rule_label}: {fmt(pf.rename_ready)} file sẽ đổi · "
                 f"{fmt(pf.rename_same)} đã đúng tên · {fmt(pf.rename_norule + pf.rename_bad)} giữ tên cũ\n"
                 f"② Nén ≤ {cfg.limit_kb} KB/trang: ước tính ~{fmt(pf.est_compress)} file cần nén "
                 f"({fmt(pf.signed)} file đã ký giữ nguyên)\n"
                 f"③ Gom để ký số: {fmt(pf.gather_new)} file chưa ký\n")
        if pf.warnings:
            txt += "\n⚠ Lưu ý:\n• " + "\n• ".join(pf.warnings) + "\n"
        txt += (f"\nCần khoảng {pf.need_bytes / mb:,.0f} MB trống (còn {pf.free_bytes / mb:,.0f} MB).\n\nChạy ngay?"
                ).replace(",", ".")
        if QMessageBox.question(self, "Xác nhận chạy quy trình", txt) != QMessageBox.Yes:
            self.busyChanged.emit(False)
            self.lbl.setText("Đã huỷ – chưa ghi gì.")
            return
        self._run(cfg)

    def _run(self, cfg: P.Config):
        self.rep = None
        self.model.set_rows([])
        self._reset_steps()
        t = RunThread(cfg)
        t.stage.connect(self._on_stage)
        t.stage_done.connect(self._on_stage_done)
        t.progress.connect(self._on_progress)
        t.log.connect(lambda m: self.lbl.setText(m))
        t.finished_run.connect(self._finished)
        self.thread = t
        self.prog.setRange(0, 0)
        t.start()
        self._enable()
        self.lbl_now.setText("")

    def stop(self):
        if isinstance(self.thread, RunThread):
            self.thread.cancelled = True
            self.lbl.setText("Đang dừng… (chờ file đang xử lý xong; hồ sơ gốc không bị đụng)")

    def _on_stage(self, i: int, title: str):
        self._set_step(i, P.OK, "đang chạy…", running=True)
        self.lbl_now.setText(f"Bước {i}/3 · {title}")
        self.prog.setRange(0, 0)

    def _on_stage_done(self, i: int, st: P.StageResult):
        self._set_step(i, st.status, st.summary)

    def _on_progress(self, a: int, b: int):
        if self.prog.maximum() != b:
            self.prog.setRange(0, max(1, b))
        self.prog.setValue(a)

    def _finished(self, rep: P.Report):
        if self.thread:
            self.thread.wait()
        self.thread = None
        self.rep = rep
        for i, st in enumerate(rep.stages):
            self._set_step(i, st.status, st.summary)
        self.model.set_rows(rep.recs)
        self._apply_filter()
        self.lbl_now.setText("")
        self._enable()
        self.busyChanged.emit(False)
        mb = 2 ** 20
        if rep.ok:
            warn = sum(1 for r in rep.recs if r.level != P.OK)
            self.lbl.setText(f"✔ Xong trong {rep.seconds:.0f} giây: đã gom {fmt(rep.gathered)} file chưa ký để ký số · "
                             f"giảm {rep.saved_bytes / mb:,.0f} MB".replace(",", ".")
                             + (f" · ⚠ {fmt(warn)} file cần xem (tích “Chỉ file cần xem”)" if warn else "") + ".")
            activity.log("Quy trình 1 click", f"{len(rep.recs)} file – gom {rep.gathered}, giảm {rep.saved_bytes // mb} MB "
                                              f"– {rep.cfg.source}")
            if QMessageBox.question(
                    self, "Đã chạy xong",
                    f"Xong! Đã gom {rep.gathered} file chưa ký vào:\n{rep.cfg.gather}\n\n"
                    "Bước tiếp: ký số hàng loạt các file trong thư mục này, rồi sang tab “Gom ký số” để trả về / chép "
                    "ra thư mục mới.\n\nMở thư mục gom?") == QMessageBox.Yes:
                open_path(rep.cfg.gather)
        else:
            self.lbl.setText(("■ " if rep.cancelled else "❌ ") + (rep.error.splitlines()[0] if rep.error else "Lỗi"))
            activity.log("Quy trình 1 click", ("Đã dừng" if rep.cancelled else "Lỗi") + f": {rep.error[:120]}")
            QMessageBox.warning(self, "Quy trình dừng", (rep.error or "Có lỗi.") +
                                "\n\nHồ sơ gốc KHÔNG bị đụng. Bản chép (nếu đã tạo) giữ nguyên để xem; dùng nút "
                                "“Xoá kết quả” rồi chạy lại.")

    # ------------------------------------------------------------------ sau khi chạy
    def to_sign(self):
        if self.rep:
            self.openSign.emit(self.rep.cfg.gather, self.rep.cfg.work)

    def export_excel(self):
        if not self.rep:
            return
        base = os.path.dirname(self.rep.cfg.work)
        name = f"Ket_qua_quy_trinh_{datetime.now():%Y%m%d_%H%M}.xlsx"
        path, _ = QFileDialog.getSaveFileName(self, "Xuất Excel kết quả", os.path.join(base, name), "Excel (*.xlsx)")
        if not path:
            return
        rep = self.rep

        def done(res, err):
            if err is not None:
                QMessageBox.warning(self, "Lỗi xuất Excel", f"❌ {err}")
            elif QMessageBox.question(self, "Đã xuất", f"Đã lưu:\n{res}\n\nMở file?") == QMessageBox.Yes:
                open_path(res)
        run_bg(self, self.btn_excel, "⏳ Đang xuất…", lambda: PX.export(path, rep), done)

    def delete_results(self):
        if not self.rep or self.running:
            return
        dirs = P.removable(self.rep.cfg.work, self.rep.cfg.gather)
        if not dirs:
            return
        fixed = [d for d in dirs if tools.drive_is_fixed(d)]
        if len(fixed) != len(dirs):
            QMessageBox.information(self, "Xoá kết quả", "Thư mục nằm trên ổ mạng / USB (không có Thùng rác) – hãy tự xoá:\n"
                                    + "\n".join(dirs))
            return
        if QMessageBox.question(self, "Xoá kết quả quy trình",
                                "Chuyển vào Thùng rác (khôi phục được):\n\n" + "\n".join(dirs) +
                                "\n\nHồ sơ gốc không bị ảnh hưởng. Tiếp tục?") != QMessageBox.Yes:
            return
        bad = [d for d in dirs if not tools.delete_dir(d, permanent=False)[0]]
        activity.log("Xoá kết quả quy trình", f"{len(dirs) - len(bad)} thư mục")
        self.rep = None
        self.model.set_rows([])
        self._reset_steps()
        self._work_auto = self._gather_auto = True
        self._auto_dirs()
        self.lbl.setText("Đã xoá kết quả – sẵn sàng chạy lại." if not bad else f"⚠ Không xoá được: {'; '.join(bad)}")
        self._enable()
