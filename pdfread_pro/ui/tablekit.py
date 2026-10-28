"""Tiện ích dùng chung cho mọi bảng / danh sách file:
- CHỌN CỘT HIỂN THỊ: chuột phải vào tiêu đề cột hoặc nút «▦ Cột» → tích / bỏ tích từng cột (nhớ cho lần sau);
- MENU CHUỘT PHẢI THEO DÒNG: các việc riêng của từng tab (cập nhật / kiểm tra lại / sửa riêng dòng này…) + việc chung
  (mở file, mở thư mục, sao chép đường dẫn / tên / nội dung dòng)."""
from __future__ import annotations

import os
from typing import Callable, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QAbstractItemView, QMenu, QPushButton, QTreeView, QWidget

from ..paths import make_settings
from .common import open_path, reveal

Item = Optional[tuple]          # (nhãn, hàm) hoặc None = đường kẻ ngăn


def _header(view):
    return view.header() if isinstance(view, QTreeView) else view.horizontalHeader()


def _titles(view) -> List[str]:
    m = view.model()
    return [str(m.headerData(i, Qt.Horizontal) or f"Cột {i + 1}").strip() or f"Cột {i + 1}" for i in range(m.columnCount())]


def load_hidden(key: str) -> set:
    try:
        raw = str(make_settings().value(f"cols/{key}", "") or "")
        return {int(x) for x in raw.split(",") if x.strip().isdigit()}
    except Exception:
        return set()


def save_hidden(key: str, hidden: set) -> None:
    try:
        make_settings().setValue(f"cols/{key}", ",".join(str(i) for i in sorted(hidden)))
    except Exception:
        pass


def _hidden_now(view) -> set:
    return {i for i in range(view.model().columnCount()) if view.isColumnHidden(i)}


def build_column_menu(view, key: str, protected: Sequence[int], parent: Optional[QWidget] = None) -> QMenu:
    m = QMenu(parent or view)
    titles = _titles(view)
    for i, t in enumerate(titles):
        a = m.addAction(t)
        a.setCheckable(True)
        a.setChecked(not view.isColumnHidden(i))
        a.setEnabled(i not in protected)

        def toggle(on, col=i):
            hidden = _hidden_now(view)
            (hidden.discard if on else hidden.add)(col)
            if len(hidden) >= len(titles):               # luôn chừa ít nhất 1 cột
                return
            view.setColumnHidden(col, not on)
            save_hidden(key, hidden)
        a.triggered.connect(toggle)
    m.addSeparator()

    def show_all():
        for c in range(len(titles)):
            view.setColumnHidden(c, False)
        save_hidden(key, set())
    m.addAction("👁 Hiện tất cả cột").triggered.connect(show_all)
    return m


def install_column_chooser(view, key: str, protected: Sequence[int] = ()) -> None:
    """Áp cột đã ẩn từ lần trước + menu chuột phải ở tiêu đề cột."""
    for c in load_hidden(key):
        if c < view.model().columnCount() and c not in protected:
            view.setColumnHidden(c, True)
    h = _header(view)
    h.setContextMenuPolicy(Qt.CustomContextMenu)
    h.customContextMenuRequested.connect(
        lambda pos: build_column_menu(view, key, protected).exec(h.mapToGlobal(pos)))
    view._column_key, view._column_protected = key, tuple(protected)


def column_button(view, key: Optional[str] = None, protected: Sequence[int] = ()) -> QPushButton:
    """Nút «▦ Cột ▾» mở menu chọn cột (menu dựng lại mỗi lần mở)."""
    key = key or getattr(view, "_column_key", "cols")
    protected = protected or getattr(view, "_column_protected", ())
    b = QPushButton("▦ Cột ▾")
    b.setProperty("size", "sm")
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip("Chọn cột nào hiển thị (cũng có thể chuột phải vào tiêu đề cột)")
    b.clicked.connect(lambda: build_column_menu(view, key, protected).exec(b.mapToGlobal(b.rect().bottomLeft())))
    return b


# ------------------------------------------------------------------ menu chuột phải theo dòng
def _row_at(view, pos) -> int:
    if isinstance(view, QTreeView):
        ix = view.indexAt(pos)
        return ix.row() if ix.isValid() else -1
    return view.rowAt(pos.y())


def selected_rows(view) -> List[int]:
    sm = view.selectionModel()
    return sorted({ix.row() for ix in sm.selectedRows()}) if sm else []


def row_text(view, row: int) -> str:
    m = view.model()
    return "\t".join(str(m.index(row, c).data() or "") for c in range(m.columnCount()) if not view.isColumnHidden(c))


def install_row_menu(view, paths_of: Callable[[List[int]], List[str]],
                     extras: Optional[Callable[[List[int]], List[Item]]] = None) -> None:
    """Chuột phải vào dòng: `extras(rows)` = các việc riêng của tab; sau đó là việc chung theo `paths_of(rows)` (đường dẫn file)."""
    view.setContextMenuPolicy(Qt.CustomContextMenu)

    def handler(pos):
        row = _row_at(view, pos)
        if row < 0:
            return
        rows = selected_rows(view)
        if row not in rows:
            view.setCurrentIndex(view.model().index(row, 0))
            if isinstance(view, QAbstractItemView) and hasattr(view, "selectRow"):
                view.selectRow(row)
            rows = [row]
        m = QMenu(view)
        n = 0
        for it in (extras(rows) if extras else []):
            if it is None:
                m.addSeparator()
            else:
                a = m.addAction(it[0])
                a.triggered.connect(lambda _=False, fn=it[1]: fn())
                if len(it) > 2 and it[2] is False:
                    a.setEnabled(False)
                n += 1
        if n:
            m.addSeparator()
        paths = [p for p in paths_of(rows) if p]
        first = paths[0] if paths else ""
        a = m.addAction("📄 Mở file")
        a.setEnabled(bool(first) and os.path.isfile(first))
        a.triggered.connect(lambda: open_path(first))
        a = m.addAction("📂 Mở thư mục chứa file")
        a.setEnabled(bool(first))
        a.triggered.connect(lambda: reveal(first))
        cb = QGuiApplication.clipboard()
        m.addAction("📋 Sao chép đường dẫn" + (f" ({len(paths)} file)" if len(paths) > 1 else "")).triggered.connect(
            lambda: cb.setText("\n".join(paths)))
        m.addAction("📋 Sao chép tên file").triggered.connect(lambda: cb.setText("\n".join(os.path.basename(p) for p in paths)))
        m.addAction("📋 Sao chép nội dung dòng").triggered.connect(lambda: cb.setText("\n".join(row_text(view, r) for r in rows)))
        m.addSeparator()
        m.addAction("▦ Chọn cột hiển thị…").triggered.connect(
            lambda: build_column_menu(view, getattr(view, "_column_key", "cols"), getattr(view, "_column_protected", ())).exec(
                view.viewport().mapToGlobal(pos)))
        m.exec(view.viewport().mapToGlobal(pos))

    view.customContextMenuRequested.connect(handler)
