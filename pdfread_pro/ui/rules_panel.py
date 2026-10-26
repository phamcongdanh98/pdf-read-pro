"""Tab QUẢN LÝ BỘ QUY TẮC: danh sách bộ quy tắc + trình soạn quy tắc + ví dụ trực tiếp."""
from __future__ import annotations

import copy
import json
import os
from typing import List, Optional

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QPushButton, QSpinBox, QSplitter, QToolButton, QVBoxLayout, QWidget)

from ..core import renamer as R
from ..core.models import FileInfo
from .step_dialog import StepDialog

NEW_NAME = "Bộ quy tắc mới (chưa lưu)"


def _builtin_names() -> set:
    return {p["name"] for p in R.default_presets()}


class RulesPanel(QWidget):
    """Nguồn duy nhất của bộ quy tắc đang dùng; tab Đổi tên đọc từ đây."""
    rulesChanged = Signal()
    presetsChanged = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.presets: List[dict] = []
        self.ruleset = R.new_ruleset(NEW_NAME)
        self.sample_files: List[FileInfo] = []
        self._loading = False
        self.dirty = False

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split)

        # ---------------- trái: danh sách bộ quy tắc
        left = QGroupBox("Danh sách mẫu đổi tên")
        ll = QVBoxLayout(left)
        self.lst_presets = QListWidget()
        self.lst_presets.itemClicked.connect(self._preset_clicked)
        ll.addWidget(self.lst_presets, 1)
        tip = QLabel("🔒 = mẫu có sẵn (không sửa trực tiếp, hãy “Lưu thành mẫu mới”). Đổi tên theo mã số 1361 nằm ở tab con bên cạnh.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#64748B;font-size:9pt")
        ll.addWidget(tip)
        g = QGridLayout()
        btns = [("＋ Mẫu mới", "primary", self.new_preset), ("💾 Lưu", "success", self.save_preset),
                ("📄 Lưu thành mẫu mới", "primary", self.save_as_preset), ("🗑 Xoá", "danger", self.delete_preset),
                ("📥 Nhập JSON", "cyan", self.import_preset), ("📤 Xuất JSON", "cyan", self.export_preset)]
        for i, (text, obj, slot) in enumerate(btns):
            b = QPushButton(text)
            b.setObjectName(obj)
            b.setProperty("size", "sm")
            b.clicked.connect(slot)
            g.addWidget(b, i // 2, i % 2)
        ll.addLayout(g)
        split.addWidget(left)

        # ---------------- phải: trình soạn
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        self.lbl_name = QLabel("")
        self.lbl_name.setStyleSheet("font-size:12pt;font-weight:800;color:#1E40AF")
        rl.addWidget(self.lbl_name)

        g2 = QGroupBox("1. Mẫu tên mới (có biến)")
        g2l = QVBoxLayout(g2)
        r = QHBoxLayout()
        self.ed_tpl = QLineEdit("{stem}")
        self.ed_tpl.textChanged.connect(self._changed)
        r.addWidget(self.ed_tpl, 1)
        vb = QToolButton()
        vb.setText("＋ Chèn biến")
        vb.setPopupMode(QToolButton.InstantPopup)
        vm = QMenu(vb)
        for k, desc in R.VARIABLES.items():
            vm.addAction(f"{{{k}}}  –  {desc}", lambda _=False, k=k: self._insert_var(k))
        vb.setMenu(vm)
        r.addWidget(vb)
        g2l.addLayout(r)
        h = QLabel("Đuôi file (.pdf) luôn giữ nguyên. Ví dụ: <b>{n}.{stem}</b> → <b>01.Tên cũ</b>  ·  "
                   "<b>{folder}_{stem}</b> → <b>NguyenVanA_Tên cũ</b>  ·  <b>{stem}_{date:%d%m%Y}</b> → <b>Tên cũ_21102026</b>")
        h.setWordWrap(True)
        h.setStyleSheet("color:#475569;font-size:9pt")
        g2l.addWidget(h)
        rl.addWidget(g2)

        g3 = QGroupBox("2. Đánh số  {n}")
        f3 = QHBoxLayout(g3)
        self.sp_start, self.sp_step, self.sp_pad = QSpinBox(), QSpinBox(), QSpinBox()
        self.sp_start.setRange(0, 999999)
        self.sp_start.setValue(1)
        self.sp_step.setRange(1, 1000)
        self.sp_pad.setRange(0, 8)
        self.ck_folder = QCheckBox("Đánh lại từ đầu ở mỗi thư mục")
        self.ck_folder.setChecked(True)
        for lbl, w in (("Bắt đầu", self.sp_start), ("Bước", self.sp_step), ("Số chữ số", self.sp_pad)):
            f3.addWidget(QLabel(lbl))
            w.setMinimumWidth(70)
            f3.addWidget(w)
            w.valueChanged.connect(self._changed)
        f3.addSpacing(10)
        f3.addWidget(self.ck_folder, 1)
        self.ck_folder.toggled.connect(self._changed)
        rl.addWidget(g3)

        g4 = QGroupBox("3. Các bước biến đổi (chạy lần lượt từ trên xuống)")
        g4l = QHBoxLayout(g4)
        self.lst = QListWidget()
        self.lst.setMinimumHeight(120)
        self.lst.itemDoubleClicked.connect(lambda *_: self.edit_step())
        g4l.addWidget(self.lst, 1)
        col = QVBoxLayout()
        ab = QToolButton()
        ab.setText("＋ Thêm bước ▾")
        ab.setPopupMode(QToolButton.InstantPopup)
        am = QMenu(ab)
        for k, desc in R.STEP_TYPES.items():
            am.addAction(desc, lambda _=False, k=k: self.add_step(k))
        ab.setMenu(am)
        ab.setToolButtonStyle(Qt.ToolButtonTextOnly)
        col.addWidget(ab)
        for text, slot in (("✎ Sửa", self.edit_step), ("▲ Lên", lambda: self.move_step(-1)),
                           ("▼ Xuống", lambda: self.move_step(1)), ("✖ Xoá bước", self.del_step)):
            b = QPushButton(text)
            b.setObjectName("danger" if "Xoá" in text else "light")
            b.setProperty("size", "sm")
            b.clicked.connect(slot)
            col.addWidget(b)
        col.addStretch(1)
        g4l.addLayout(col)
        rl.addWidget(g4, 1)

        g5 = QGroupBox("4. Khi tên mới bị trùng")
        g5l = QHBoxLayout(g5)
        self.cb_policy = QComboBox()
        self.cb_policy.addItem("Tự thêm số  (2), (3)…", "auto")
        self.cb_policy.addItem("Bỏ qua file bị trùng", "skip")
        self.cb_policy.currentIndexChanged.connect(self._changed)
        g5l.addWidget(self.cb_policy)
        g5l.addWidget(QLabel("· Không bao giờ ghi đè file đã có."), 1)
        rl.addWidget(g5)

        g6 = QGroupBox("Ví dụ với file trong thư mục đang quét")
        g6l = QVBoxLayout(g6)
        self.lbl_example = QLabel("Quét thư mục để xem ví dụ.")
        self.lbl_example.setTextFormat(Qt.RichText)
        self.lbl_example.setWordWrap(True)
        g6l.addWidget(self.lbl_example)
        rl.addWidget(g6)

        split.addWidget(right)
        split.setSizes([300, 800])

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._emit)
        self.reload_presets()
        self.load_ruleset(self.ruleset)

    # ------------------------------------------------------------- API cho tab Đổi tên
    def current_ruleset(self) -> dict:
        return {
            "name": self.ruleset.get("name", NEW_NAME),
            "template": self.ed_tpl.text() or "{stem}",
            "numbering": {"start": self.sp_start.value(), "step": self.sp_step.value(),
                          "pad": self.sp_pad.value(), "per_folder": self.ck_folder.isChecked()},
            "steps": copy.deepcopy(self.ruleset.get("steps", [])),
        }

    def policy(self) -> str:
        return self.cb_policy.currentData()

    def summary(self) -> str:
        rs = self.current_ruleset()
        steps = " → ".join(R.step_summary(s) for s in rs["steps"]) or "không có bước biến đổi"
        return f"Mẫu: {rs['template']} · {steps}"

    def select_preset(self, name: str) -> None:
        for p in self.presets:
            if p["name"] == name:
                self.load_ruleset(p)
                return

    def set_sample_files(self, files: List[FileInfo]) -> None:
        self.sample_files = files[:6]
        self._update_example()

    # ------------------------------------------------------------- nội bộ
    def _changed(self, *_):
        if self._loading:
            return
        self.dirty = True
        self._update_title()
        self._timer.start()

    def _emit(self):
        self._update_example()
        self.rulesChanged.emit()

    def _update_title(self):
        name = self.ruleset.get("name", NEW_NAME)
        lock = " 🔒" if name in _builtin_names() else ""
        dirty = "  <span style='color:#B45309;font-size:9pt'>● đã sửa, chưa lưu</span>" if self.dirty else ""
        self.lbl_name.setText(f"⚙ {name}{lock}{dirty}")

    def _update_example(self):
        if not self.sample_files:
            self.lbl_example.setText("<span style='color:#64748B'>Quét thư mục để xem ví dụ.</span>")
            return
        items = R.build_preview(self.sample_files, self.current_ruleset(), self.policy())
        rows = []
        for it in items:
            color = "#15803D" if it.status in (R.ST_READY, R.ST_RENAMED_AUTO) else (
                "#B91C1C" if it.status == R.ST_INVALID else "#64748B")
            new = it.new_name if it.status != R.ST_INVALID else f"⚠ {it.note}"
            rows.append(f"<tr><td style='color:#475569;padding-right:10px'>{it.fi.name}</td>"
                        f"<td style='padding-right:10px'>→</td><td style='color:{color};font-weight:600'>{new}</td></tr>")
        self.lbl_example.setText("<table>" + "".join(rows) + "</table>")

    def _insert_var(self, key: str):
        self.ed_tpl.insert("{" + key + "}")
        self.ed_tpl.setFocus()

    def load_ruleset(self, rs: dict):
        self._loading = True
        self.ruleset = copy.deepcopy(rs)
        self.ruleset.setdefault("steps", [])
        self.ed_tpl.setText(rs.get("template", "{stem}"))
        n = rs.get("numbering", {})
        self.sp_start.setValue(int(n.get("start", 1)))
        self.sp_step.setValue(int(n.get("step", 1)))
        self.sp_pad.setValue(int(n.get("pad", 0)))
        self.ck_folder.setChecked(bool(n.get("per_folder", True)))
        self._loading = False
        self.dirty = False
        self.refresh_steps()
        self._update_title()
        self._mark_selected()
        self._emit()

    def reload_presets(self):
        self.presets = R.load_presets()
        self.lst_presets.clear()
        builtin = _builtin_names()
        for p in self.presets:
            it = QListWidgetItem(("🔒 " if p["name"] in builtin else "📝 ") + p["name"])
            it.setData(Qt.UserRole, p["name"])
            self.lst_presets.addItem(it)
        self._mark_selected()
        self.presetsChanged.emit()

    def _mark_selected(self):
        name = self.ruleset.get("name")
        for i in range(self.lst_presets.count()):
            it = self.lst_presets.item(i)
            sel = it.data(Qt.UserRole) == name
            it.setSelected(sel)
            f = it.font()
            f.setBold(sel)
            it.setFont(f)

    def _preset_clicked(self, item: QListWidgetItem):
        if self.dirty and QMessageBox.question(self, "Đổi bộ quy tắc",
                                               "Bộ quy tắc hiện tại đã sửa nhưng chưa lưu. Bỏ thay đổi?") != QMessageBox.Yes:
            self._mark_selected()
            return
        self.select_preset(item.data(Qt.UserRole))

    # ------------------------------------------------------------- lưu / xoá / nhập / xuất
    def _user_presets(self, exclude: str = "") -> List[dict]:
        b = _builtin_names()
        return [p for p in self.presets if p["name"] not in b and p["name"] != exclude]

    def _store(self, name: str):
        rs = self.current_ruleset()
        rs["name"] = name
        R.save_user_presets(self._user_presets(exclude=name) + [rs])
        self.ruleset["name"] = name
        self.dirty = False
        self.reload_presets()
        self._update_title()

    def new_preset(self):
        self.load_ruleset(R.new_ruleset(NEW_NAME))

    def save_preset(self):
        name = self.ruleset.get("name", "")
        if not name or name == NEW_NAME or name in _builtin_names():
            self.save_as_preset()
            return
        self._store(name)

    def save_as_preset(self):
        cur = self.ruleset.get("name", "")
        name, ok = QInputDialog.getText(self, "Lưu thành bộ mới", "Tên bộ quy tắc:",
                                        text="" if cur in _builtin_names() or cur == NEW_NAME else cur)
        name = name.strip()
        if not ok or not name:
            return
        if name in _builtin_names() or name == NEW_NAME:
            QMessageBox.warning(self, "Lưu", "Tên này trùng bộ quy tắc có sẵn, hãy đặt tên khác.")
            return
        if any(p["name"] == name for p in self.presets) and QMessageBox.question(
                self, "Ghi đè", f"Đã có bộ “{name}”. Ghi đè?") != QMessageBox.Yes:
            return
        self._store(name)

    def delete_preset(self):
        name = self.ruleset.get("name", "")
        if name in _builtin_names() or not any(p["name"] == name for p in self.presets):
            QMessageBox.information(self, "Xoá", "Chỉ xoá được bộ quy tắc do bạn tự lưu (📝).")
            return
        if QMessageBox.question(self, "Xoá", f"Xoá bộ quy tắc “{name}”?") != QMessageBox.Yes:
            return
        R.save_user_presets(self._user_presets(exclude=name))
        self.reload_presets()
        self.new_preset()

    def import_preset(self):
        p, _ = QFileDialog.getOpenFileName(self, "Nhập bộ quy tắc", "", "JSON (*.json)")
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8") as fh:
                rs = json.load(fh)
            if not isinstance(rs, dict) or "template" not in rs:
                raise ValueError("File không đúng định dạng bộ quy tắc.")
            rs.setdefault("name", os.path.splitext(os.path.basename(p))[0])
            self.load_ruleset(rs)
            self.dirty = True
            self._update_title()
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Nhập bộ quy tắc", str(e))

    def export_preset(self):
        p, _ = QFileDialog.getSaveFileName(self, "Xuất bộ quy tắc", f"{self.ruleset.get('name', 'quy-tac')}.json",
                                           "JSON (*.json)")
        if p:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(self.current_ruleset(), fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------- các bước
    def refresh_steps(self):
        self.lst.clear()
        for i, s in enumerate(self.ruleset["steps"], 1):
            self.lst.addItem(f"{i}. {R.step_summary(s)}")
        if not self.ruleset["steps"]:
            it = QListWidgetItem("(Chưa có bước nào – bấm “＋ Thêm bước”)")
            it.setForeground(QColor("#94A3B8"))
            it.setFlags(Qt.NoItemFlags)
            self.lst.addItem(it)

    def add_step(self, kind: str):
        step = {"type": kind}
        if kind == "replace":
            step.update(find="", repl="", regex=False, case=False)
        elif kind == "spaces":
            step["to"] = "_"
        elif kind == "case":
            step["mode"] = "lower"
        elif kind == "code1361":
            step["rules_path"] = R.DEFAULT_RULES_1361
        if kind not in ("remove_accents", "trim"):
            d = StepDialog(self, step)
            if d.exec() != StepDialog.Accepted:
                return
            step = d.step
        self.ruleset["steps"].append(step)
        self.refresh_steps()
        self._changed()

    def edit_step(self):
        i = self.lst.currentRow()
        if not 0 <= i < len(self.ruleset["steps"]):
            return
        s = self.ruleset["steps"][i]
        if s["type"] in ("remove_accents", "trim"):
            return
        d = StepDialog(self, s)
        if d.exec() == StepDialog.Accepted:
            self.ruleset["steps"][i] = d.step
            self.refresh_steps()
            self.lst.setCurrentRow(i)
            self._changed()

    def move_step(self, delta: int):
        i, steps = self.lst.currentRow(), self.ruleset["steps"]
        j = i + delta
        if not 0 <= i < len(steps) or not 0 <= j < len(steps):
            return
        steps[i], steps[j] = steps[j], steps[i]
        self.refresh_steps()
        self.lst.setCurrentRow(j)
        self._changed()

    def del_step(self):
        i = self.lst.currentRow()
        if 0 <= i < len(self.ruleset["steps"]):
            del self.ruleset["steps"][i]
            self.refresh_steps()
            self._changed()
