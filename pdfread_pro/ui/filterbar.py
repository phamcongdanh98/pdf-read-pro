"""Thanh LỌC + SẮP XẾP dùng chung cho các bảng file: «Hiển thị: [Tất cả ▾]  Sắp xếp: [Thứ tự gốc ▾]  🔍 tìm…  N/M».

- `arrange()` lọc + sắp xếp một danh sách bất kỳ (tab Đổi tên dựng lại bảng theo danh sách này).
- `apply()` áp vào bảng có số dòng cố định (tab Nén, Kiểm tra trang): ẩn dòng không khớp và đổi THỨ TỰ HIỂN THỊ
  bằng header dọc (`moveSection`) – chỉ số dòng logic giữ nguyên nên mọi code dùng `files[row]` vẫn đúng."""
from __future__ import annotations

from typing import Callable, Dict, Iterable, Optional, Sequence, Set, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QTableWidget, QWidget

FILTER_ALL, SORT_ORIG = "all", "orig"

Info = Tuple[Set[str], str, Dict[str, object]]      # (nhãn lọc của dòng, văn bản để tìm, {khoá sắp xếp: giá trị})


class FilterBar(QWidget):
    changed = Signal()

    def __init__(self, filters: Sequence[Tuple[str, str]], sorts: Sequence[Tuple[str, str, bool]],
                 placeholder: str = "🔍 Tìm theo tên file / thư mục…", parent: Optional[QWidget] = None):
        """filters: [(nhãn hiển thị, khoá)] – khoá đầu tiên nên là "all". sorts: [(nhãn, khoá, giảm dần?)] – đầu tiên là thứ tự gốc."""
        super().__init__(parent)
        self._sorts = list(sorts)
        self._moved = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(QLabel("Hiển thị:"))
        self.cb_show = QComboBox()
        for label, key in filters:
            self.cb_show.addItem(label, key)
        self.cb_show.setMinimumWidth(190)
        self.cb_show.setToolTip("Chỉ hiện các file thuộc nhóm này")
        lay.addWidget(self.cb_show)
        lay.addWidget(QLabel("Sắp xếp:"))
        self.cb_sort = QComboBox()
        for label, key, _ in sorts:
            self.cb_sort.addItem(label, key)
        self.cb_sort.setMinimumWidth(170)
        self.cb_sort.setToolTip("Đổi thứ tự hiển thị (không đổi file)")
        lay.addWidget(self.cb_sort)
        self.search = QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(180)
        lay.addWidget(self.search, 1)
        self.lbl = QLabel("")
        self.lbl.setObjectName("Hint")
        lay.addWidget(self.lbl)
        self.cb_show.currentIndexChanged.connect(lambda _=0: self.changed.emit())
        self.cb_sort.currentIndexChanged.connect(lambda _=0: self.changed.emit())
        self.search.textChanged.connect(lambda _=None: self.changed.emit())

    def attach_columns(self, view, key: str, protected=()) -> None:
        """Thêm nút «▦ Cột ▾» (chọn cột hiển thị của `view`) vào cuối thanh."""
        from .tablekit import column_button, install_column_chooser
        if not hasattr(view, "_column_key"):
            install_column_chooser(view, key, protected)
        self.layout().addWidget(column_button(view, key, protected))

    # ------------------------------------------------------------------ giá trị đang chọn
    @property
    def filter_key(self) -> str:
        return self.cb_show.currentData() or FILTER_ALL

    @property
    def sort_key(self) -> str:
        return self.cb_sort.currentData() or SORT_ORIG

    @property
    def text(self) -> str:
        return self.search.text().strip().lower()

    @property
    def active(self) -> bool:
        return self.filter_key != FILTER_ALL or bool(self.text) or self.sort_key != SORT_ORIG

    def set_counts(self, shown: int, total: int) -> None:
        self.lbl.setText(f"{shown:,} / {total:,}".replace(",", ".") if self.active or shown != total else "")

    def reset(self) -> None:
        for w in (self.cb_show, self.cb_sort):
            w.blockSignals(True)
            w.setCurrentIndex(0)
            w.blockSignals(False)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.changed.emit()

    # ------------------------------------------------------------------ lọc + sắp xếp
    def arrange(self, seq: Iterable, info: Callable[[object], Info]) -> list:
        """Danh sách đã lọc + sắp xếp (ổn định; không phải sắp xếp thì giữ thứ tự gốc)."""
        flt, q, sk = self.filter_key, self.text, self.sort_key
        out = []
        for x in seq:
            tags, text, keys = info(x)
            if (flt == FILTER_ALL or flt in tags) and (not q or q in text):
                out.append((x, keys))
        if sk != SORT_ORIG:
            rev = next((r for _, k, r in self._sorts if k == sk), False)
            out.sort(key=lambda p: p[1].get(sk, 0), reverse=rev)
        return [x for x, _ in out]

    def restore_order(self, table: QTableWidget) -> None:
        """Trả thứ tự hiển thị về như gốc (gọi trước khi nạp lại bảng)."""
        if self._moved:
            vh = table.verticalHeader()
            for v in range(table.rowCount()):
                cur = vh.visualIndex(v)
                if cur != v:
                    vh.moveSection(cur, v)
            self._moved = False

    def apply(self, table: QTableWidget, n: int, info: Callable[[int], Info]) -> int:
        """Áp vào bảng n dòng cố định: ẩn dòng không khớp + sắp xếp thứ tự hiển thị. Trả về số dòng đang hiện."""
        shown = self.arrange(range(n), info)
        keep = set(shown)
        table.setUpdatesEnabled(False)
        try:
            for r in range(n):
                hide = r not in keep
                if table.isRowHidden(r) != hide:
                    table.setRowHidden(r, hide)
            want = shown + [r for r in range(n) if r not in keep]
            vh = table.verticalHeader()
            if self.sort_key != SORT_ORIG or self._moved:
                if self.sort_key == SORT_ORIG:
                    want = list(range(n))
                for v, r in enumerate(want):
                    cur = vh.visualIndex(r)
                    if cur != v:
                        vh.moveSection(cur, v)
                self._moved = self.sort_key != SORT_ORIG
        finally:
            table.setUpdatesEnabled(True)
        self.set_counts(len(shown), n)
        return len(shown)
