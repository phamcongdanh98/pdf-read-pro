"""Hộp thoại sửa tham số một bước đổi tên."""
from __future__ import annotations

import copy

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from ..core import renamer as R


class StepDialog(QDialog):
    """Sửa tham số của một bước."""

    def __init__(self, parent, step: dict):
        super().__init__(parent)
        self.setWindowTitle(R.STEP_TYPES.get(step["type"], "Bước"))
        self.step = copy.deepcopy(step)
        t = step["type"]
        lay = QVBoxLayout(self)
        form = QFormLayout()
        lay.addLayout(form)
        self.w = {}
        if t in ("prefix", "suffix"):
            self.w["text"] = QLineEdit(step.get("text", ""))
            form.addRow("Nội dung:", self.w["text"])
        elif t == "replace":
            self.w["find"] = QLineEdit(step.get("find", ""))
            self.w["repl"] = QLineEdit(step.get("repl", ""))
            self.w["regex"] = QCheckBox("Dùng biểu thức chính quy (regex)")
            self.w["regex"].setChecked(bool(step.get("regex")))
            self.w["case"] = QCheckBox("Phân biệt chữ hoa/thường")
            self.w["case"].setChecked(bool(step.get("case")))
            form.addRow("Tìm:", self.w["find"])
            form.addRow("Thay bằng:", self.w["repl"])
            form.addRow("", self.w["regex"])
            form.addRow("", self.w["case"])
            hint = QLabel("Ví dụ regex: <code>\\.1$</code> → <code>.signed</code> (đổi đuôi .1 thành .signed). "
                          "Dùng <code>\\1</code> để lấy nhóm trong ngoặc.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#475569")
            lay.addWidget(hint)
        elif t == "spaces":
            c = QComboBox()
            for label, val in (("Gạch dưới _", "_"), ("Gạch ngang -", "-"), ("Dấu chấm .", "."),
                               ("Xoá hết khoảng trắng", "")):
                c.addItem(label, val)
            c.setCurrentIndex(max(0, c.findData(step.get("to", "_"))))
            self.w["to"] = c
            form.addRow("Khoảng trắng thành:", c)
        elif t == "case":
            c = QComboBox()
            for label, val in (("chữ thường", "lower"), ("CHỮ HOA", "upper"),
                               ("Viết Hoa Mỗi Từ", "title"), ("Viết hoa chữ đầu câu", "sentence")):
                c.addItem(label, val)
            c.setCurrentIndex(max(0, c.findData(step.get("mode", "lower"))))
            self.w["mode"] = c
            form.addRow("Đổi thành:", c)
        elif t == "code1361":
            row = QHBoxLayout()
            e = QLineEdit(step.get("rules_path") or "")
            e.setPlaceholderText("(để trống = dùng bộ quy tắc mã số 1361 của ứng dụng)")
            b = QPushButton("Chọn…")
            b.clicked.connect(lambda: self._browse(e))
            row.addWidget(e, 1)
            row.addWidget(b)
            self.w["rules_path"] = e
            form.addRow("File quy tắc (tuỳ chọn):", row)
            hint = QLabel("Lấy mã số ở đầu tên file (01, 86dh…) và đổi cả tên theo bảng quy tắc "
                          "của Hồ sơ 1361. File không có mã sẽ giữ nguyên. Phần <code>.signed</code> ở cuối được giữ lại.")
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#475569")
            lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.setMinimumWidth(460)

    def _browse(self, edit):
        p, _ = QFileDialog.getOpenFileName(self, "Chọn rules.json", edit.text(), "JSON (*.json)")
        if p:
            edit.setText(p)

    def _ok(self):
        for k, w in self.w.items():
            if isinstance(w, QLineEdit):
                self.step[k] = w.text()
            elif isinstance(w, QCheckBox):
                self.step[k] = w.isChecked()
            elif isinstance(w, QComboBox):
                self.step[k] = w.currentData()
        if self.step["type"] == "replace" and self.step.get("regex"):
            import re
            try:
                re.compile(self.step.get("find", ""))
            except re.error as e:
                QMessageBox.warning(self, "Regex lỗi", str(e))
                return
        self.accept()
