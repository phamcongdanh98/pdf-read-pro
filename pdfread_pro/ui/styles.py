"""Theme chép theo Hồ sơ 1361 v5.6.2: nền #F8FAFC, chữ #0F172A, Segoe UI 9.5pt, nút xanh #2563EB đậm,
group box tiêu đề nền xám, tab chọn gạch đỏ #B91C1C, bảng tiêu đề xanh đậm, thanh cuộn mảnh."""

# Bộ màu (token) cho 2 giao diện. Stylesheet, bảng màu Qt và icon ô tích đều sinh từ đây.
LIGHT = {
    "name": "light", "text": "#0F172A", "text2": "#1E293B", "muted": "#475569", "hint": "#64748B",
    "primary": "#2563EB", "primary_dark": "#1D4ED8", "primary_deep": "#1E40AF", "navy": "#1E3A8A",
    "border": "#CBD5E1", "line": "#E2E8F0", "bg": "#F8FAFC", "bg_alt": "#F1F5F9", "soft": "#EFF6FF",
    "surface": "#FFFFFF", "sel_bg": "#DBEAFE", "sel_fg": "#1E40AF", "disabled_fg": "#94A3B8", "log_fg": "#334155",
    "scope_border": "#BFDBFE", "tip_bg": "#0F172A", "tip_fg": "#FFFFFF", "tip_border": "#334155",
    "header": "stop:0 #1E3A8A, stop:0.6 #1E40AF, stop:1 #2563EB", "subtitle": "#DBEAFE", "scroll": "#CBD5E1",
    "scroll_hover": "#94A3B8", "tab_sel": "#B91C1C", "chk_box": "#FFFFFF", "chk_border": "#94A3B8",
    "chk_dis": "#F1F5F9", "arrow": "#475569", "arrow_dis": "#CBD5E1",
}
DARK = {
    "name": "dark", "text": "#E2E8F0", "text2": "#CBD5E1", "muted": "#A3B1C6", "hint": "#8C9AB0",
    "primary": "#3B82F6", "primary_dark": "#2563EB", "primary_deep": "#1D4ED8", "navy": "#A5C8FD",
    "border": "#3A475C", "line": "#26324A", "bg": "#0B1220", "bg_alt": "#162036", "soft": "#172B4D",
    "surface": "#111A2C", "sel_bg": "#1E3A66", "sel_fg": "#DBEAFE", "disabled_fg": "#5B6B82", "log_fg": "#C3CDDB",
    "scope_border": "#2B4C8C", "tip_bg": "#E2E8F0", "tip_fg": "#0F172A", "tip_border": "#94A3B8",
    "header": "stop:0 #0F1F4D, stop:0.6 #142C6B, stop:1 #1D4ED8", "subtitle": "#BFD3F5", "scroll": "#3A475C",
    "scroll_hover": "#5B6B82", "tab_sel": "#F87171", "chk_box": "#0B1220", "chk_border": "#5B6B82",
    "chk_dis": "#162036", "arrow": "#A3B1C6", "arrow_dis": "#3A475C",
}
THEMES = {"light": LIGHT, "dark": DARK}
_current = LIGHT


def current() -> dict:
    return _current


# Màu nút theo đúng Hồ sơ 1361: (thường, hover, nhấn)
BUTTON_COLORS = {
    "primary": ("#2563EB", "#1D4ED8", "#1E40AF"),   # Chọn thư mục, Làm mới, Mở tệp
    "success": ("#10B981", "#059669", "#047857"),   # Bắt đầu đổi tên
    "warning": ("#D97706", "#B45309", "#92400E"),   # Hoàn tác, Nhật ký, Giảm dung lượng
    "danger": ("#EF4444", "#DC2626", "#B91C1C"),    # Clear, Xoá
    "indigo": ("#6366F1", "#4F46E5", "#4338CA"),    # Kiểm tra tổng quan
    "violet": ("#7C3AED", "#6D28D9", "#5B21B6"),    # Cắt & ghép
    "cyan": ("#0891B2", "#0E7490", "#155E75"),      # Quản lý trang, Nhập/Xuất quy tắc
    "emerald": ("#059669", "#047857", "#065F46"),   # Ảnh thẻ
    "slate": ("#475569", "#334155", "#1E293B"),     # Thùng rác
    "rose": ("#E11D48", "#BE123C", "#9F1239"),      # Thư mục CCCD
}

def build_style(t: dict) -> str:
    return f"""
QMainWindow {{ background-color: {t["bg"]}; color: {t["text"]}; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
QWidget {{ color: {t["text"]}; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 9.5pt; }}
QDialog, QTabWidget > QWidget, QScrollArea > QWidget > QWidget {{ background-color: {t["bg"]}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}

/* Header Banner */
#HeaderFrame {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, {t["header"]});
    border: none; border-radius: 8px;
}}
#HeaderFrame QLabel {{ background-color: transparent; border: none; }}
#AppTitle {{ font-size: 14pt; font-weight: 900; color: #FFFFFF; letter-spacing: 0.5px; }}
#AppSubtitle {{ font-size: 9pt; color: {t["subtitle"]}; font-weight: 500; }}
#ThemeBtn {{ background: rgba(255,255,255,0.14); color: #FFFFFF; border: 1px solid rgba(255,255,255,0.35);
             border-radius: 10px; padding: 3px 12px; font-size: 9pt; font-weight: bold; }}
#ThemeBtn:hover {{ background: rgba(255,255,255,0.26); }}

/* Thẻ chọn kiểu tách (có hình minh hoạ) · ô file đang chọn · dải các bước */
QToolButton#PresetCard {{ background: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["border"]};
    border-radius: 8px; padding: 5px 8px; text-align: left; font-size: 9pt; }}
QToolButton#PresetCard:hover {{ border-color: {t["primary"]}; background: {t["soft"]}; }}
QToolButton#PresetCard:checked {{ border: 2px solid {t["primary"]}; background: {t["sel_bg"]}; color: {t["sel_fg"]};
    font-weight: bold; }}
#FileBox {{ background: {t["soft"]}; border: 1px solid {t["scope_border"]}; border-radius: 6px; padding: 5px 10px;
    font-weight: 600; color: {t["primary_deep"] if t["name"] == "light" else t["navy"]}; }}
#Steps {{ color: {t["muted"]}; font-size: 9pt; }}
#VersionPill {{ background-color: #2563EB; color: #FFFFFF; font-size: 9pt; font-weight: bold;
               padding: 3px 10px; border-radius: 10px; border: 1px solid #93C5FD; }}

/* GroupBox */
QGroupBox {{
    font-weight: bold; font-size: 9.5pt; border: 1px solid {t["line"]}; border-radius: 8px;
    margin-top: 10px; padding-top: 14px; background-color: {t["surface"]};
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left; padding: 2px 10px;
    color: {t["navy"]}; background-color: {t["bg_alt"]}; border: 1px solid {t["line"]}; border-radius: 4px; font-weight: bold;
}}
QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QRadioButton {{ font-weight: normal; }}

/* Inputs */
QLineEdit, QComboBox, QSpinBox {{
    background-color: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 5px; padding: 6px 10px;
    font-size: 9.5pt; color: {t["text"]};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1.5px solid {t["primary"]}; background-color: {t["surface"]}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ background-color: {t["bg_alt"]}; color: {t["disabled_fg"]}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background-color: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["border"]}; outline: 0; padding: 4px;
    selection-background-color: {t["soft"]}; selection-color: {t["sel_fg"]};
}}
QComboBox QAbstractItemView::item {{ min-height: 26px; padding: 2px 8px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; background: {t["bg_alt"]}; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {t["line"]}; }}
QCheckBox, QRadioButton {{ font-size: 9.5pt; color: {t["text2"]}; font-weight: 500; spacing: 8px; }}

/* Buttons – mặc định xanh như Hồ sơ 1361 */
QPushButton {{
    background-color: {t["primary"]}; color: #FFFFFF; border: none; border-radius: 6px;
    padding: 7px 16px; font-weight: bold; font-size: 9.5pt;
}}
QPushButton:hover {{ background-color: {t["primary_dark"]}; }}
QPushButton:pressed {{ background-color: {t["primary_deep"]}; }}
QPushButton:disabled {{ background-color: {t["line"]}; color: {t["disabled_fg"]}; border: 1px solid {t["border"]}; }}
QPushButton[size="sm"] {{ font-size: 9pt; padding: 6px 11px; }}
QPushButton[size="lg"] {{ font-size: 10pt; padding: 9px 20px; }}
QPushButton#light {{ background-color: {t["surface"]}; color: {t["text2"]}; border: 1px solid {t["border"]}; }}
QPushButton#light:hover {{ background-color: {t["soft"]}; border-color: {t["primary"]}; color: {t["sel_fg"]}; }}
QPushButton#light:disabled {{ color: {t["disabled_fg"]}; background: {t["bg_alt"]}; }}
QPushButton#flat {{ background: transparent; color: {t["primary"]}; padding: 4px 8px; }}
QPushButton#flat:hover {{ background: {t["soft"]}; }}
QPushButton#flat:checked {{ background: {t["soft"]}; color: {t["sel_fg"]}; }}
QToolButton {{ background-color: {t["surface"]}; color: {t["text2"]}; border: 1px solid {t["border"]}; border-radius: 6px;
               padding: 6px 10px; font-weight: bold; }}
QToolButton:hover {{ background-color: {t["soft"]}; border-color: {t["primary"]}; color: {t["sel_fg"]}; }}
QToolButton::menu-indicator {{ image: none; }}

/* Tabs */
QTabWidget::pane {{ border: 1px solid {t["line"]}; border-radius: 8px; background-color: {t["surface"]}; top: -1px; }}
QTabBar::tab {{
    background-color: {t["bg_alt"]}; color: {t["muted"]}; border: 1px solid {t["line"]}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px; padding: 9px 20px;
    font-weight: bold; font-size: 9.5pt; margin-right: 4px;
}}
QTabBar::tab:selected {{ background-color: {t["surface"]}; color: {t["navy"]}; border-bottom: 3px solid {t["tab_sel"]}; }}
QTabBar::tab:hover:!selected {{ background-color: {t["line"]}; color: {t["text2"]}; }}
QTabWidget#SubTabs QTabBar::tab {{ padding: 7px 16px; font-size: 9pt; }}

/* Bảng / cây / danh sách */
QTableWidget, QTreeWidget, QListWidget {{
    background-color: {t["surface"]}; alternate-background-color: {t["bg"]}; gridline-color: {t["bg_alt"]};
    border: 1px solid {t["line"]}; border-radius: 6px; color: {t["text"]}; font-size: 9.5pt;
    selection-background-color: {t["soft"]}; selection-color: {t["sel_fg"]}; outline: 0;
}}
QTreeWidget::item, QListWidget::item {{ padding: 3px 2px; }}
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{
    background-color: {t["sel_bg"]}; color: {t["sel_fg"]}; }}
QHeaderView::section {{
    background-color: {t["bg_alt"]}; color: {t["navy"]}; padding: 8px; font-weight: bold; font-size: 9.5pt;
    border: none; border-bottom: 2px solid {t["border"]}; border-right: 1px solid {t["line"]};
}}
QTableCornerButton::section {{ background-color: {t["bg_alt"]}; border: none; }}

/* Tiến trình & nhật ký */
QProgressBar {{
    border: 1px solid {t["border"]}; border-radius: 6px; text-align: center; background-color: {t["bg"]};
    color: {t["text"]}; font-weight: bold; min-height: 16px; max-height: 16px; font-size: 8.5pt;
}}
QProgressBar::chunk {{ background-color: #10B981; border-radius: 5px; }}
QTextEdit, QPlainTextEdit, QTextBrowser {{
    background-color: {t["surface"]}; border: 1px solid {t["border"]}; border-radius: 6px; color: {t["text"]};
    font-family: 'Segoe UI', Tahoma, sans-serif; font-size: 9pt;
}}

/* Thanh cuộn mảnh */
QScrollBar:vertical {{ border: none; background-color: {t["bg_alt"]}; width: 10px; margin: 0; border-radius: 5px; }}
QScrollBar::handle:vertical {{ background-color: {t["scroll"]}; min-height: 24px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background-color: {t["scroll_hover"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ border: none; background-color: {t["bg_alt"]}; height: 10px; margin: 0; border-radius: 5px; }}
QScrollBar::handle:horizontal {{ background-color: {t["scroll"]}; min-width: 24px; border-radius: 5px; }}
QScrollBar::handle:horizontal:hover {{ background-color: {t["scroll_hover"]}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QToolTip {{ background-color: {t["tip_bg"]}; color: {t["tip_fg"]}; border: 1px solid {t["tip_border"]}; padding: 6px 10px;
            border-radius: 4px; font-size: 9pt; }}
QMenu {{ background: {t["surface"]}; color: {t["text"]}; border: 1px solid {t["border"]}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t["soft"]}; color: {t["sel_fg"]}; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {t["border"]}; }}

/* Thẻ thống kê, thanh phạm vi, khung xem trước */
QFrame#card {{ background: {t["surface"]}; border: 1px solid {t["line"]}; border-radius: 8px; }}
QFrame#card:hover {{ border-color: {t["primary"]}; }}
QFrame#scopeBar {{ background: {t["soft"]}; border: 1px solid {t["scope_border"]}; border-radius: 6px; }}
QScrollArea#PreviewArea {{ background-color: {t["surface"]}; border: 1px dashed {t["border"]}; border-radius: 4px; }}
QScrollArea#PreviewArea > QWidget > QWidget {{ background-color: {t["surface"]}; }}
QPlainTextEdit#log {{ font-family: Consolas, 'Segoe UI', monospace; font-size: 9pt; color: {t["log_fg"]}; background: {t["surface"]}; }}
QLabel#StatusText {{ font-weight: bold; color: {t["primary"]}; font-size: 9.5pt; }}
QLabel#Hint {{ color: {t["hint"]}; font-size: 8.5pt; }}
""" + "".join(
        f"QPushButton#{k} {{ background-color: {a}; }} QPushButton#{k}:hover {{ background-color: {b}; }} "
        f"QPushButton#{k}:pressed {{ background-color: {c}; }} "
        f"QPushButton#{k}:disabled {{ background-color: {t['line']}; color: {t['disabled_fg']}; "
        f"border: 1px solid {t['border']}; }} "
        for k, (a, b, c) in BUTTON_COLORS.items())


MAIN_STYLE = build_style(LIGHT)          # tương thích ngược


def full_style(t: dict | None = None) -> str:
    """Stylesheet đầy đủ (gồm icon ô tích / mũi tên) theo giao diện `t` (mặc định: đang dùng).
    Gọi sau khi đã tạo QApplication."""
    from .icons import icon_style
    t = t or _current
    return build_style(t) + icon_style(t)


def button(text: str, color: str = "primary", slot=None, tip: str = "", size: str = ""):
    """Tạo nút theo phong cách Hồ sơ 1361. color: primary/success/warning/danger/indigo/violet/cyan/emerald/slate/light."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton
    b = QPushButton(text)
    b.setObjectName(color)
    b.setCursor(Qt.PointingHandCursor)
    if size:
        b.setProperty("size", size)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


def apply_palette(app, t: dict) -> None:
    """Bảng màu Qt theo giao diện (không theo Windows sáng/tối – tránh combo/ô số lệch màu)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Dark if t["name"] == "dark" else Qt.ColorScheme.Light)
    except AttributeError:
        pass
    pal = QPalette()
    for role, c in ((QPalette.Window, t["bg"]), (QPalette.WindowText, t["text"]), (QPalette.Base, t["surface"]),
                    (QPalette.AlternateBase, t["bg"]), (QPalette.Text, t["text"]), (QPalette.Button, t["surface"]),
                    (QPalette.ButtonText, t["text"]), (QPalette.Highlight, t["sel_bg"]),
                    (QPalette.HighlightedText, t["sel_fg"]), (QPalette.ToolTipBase, t["tip_bg"]),
                    (QPalette.ToolTipText, t["tip_fg"]), (QPalette.PlaceholderText, t["disabled_fg"]),
                    (QPalette.Light, t["surface"]), (QPalette.Midlight, t["line"]), (QPalette.Mid, t["border"]),
                    (QPalette.Dark, t["disabled_fg"]), (QPalette.Shadow, t["hint"]), (QPalette.BrightText, "#FFFFFF"),
                    (QPalette.Link, t["primary"])):
        pal.setColor(role, QColor(c))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(t["disabled_fg"]))
    app.setPalette(pal)


def apply_light_palette(app) -> None:
    apply_palette(app, LIGHT)


def set_theme(app, name: str) -> None:
    """Đổi giao diện sáng / tối ngay khi đang chạy (stylesheet + bảng màu + màu viết trong từng tab)."""
    global _current
    _current = THEMES.get(name, LIGHT)
    from . import theme
    theme.set_dark(_current is DARK)
    apply_palette(app, _current)
    app.setStyleSheet(full_style(_current))
    theme.recolor_all(app)
