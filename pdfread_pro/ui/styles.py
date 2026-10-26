"""Theme chép theo Hồ sơ 1361 v5.6.2: nền #F8FAFC, chữ #0F172A, Segoe UI 9.5pt, nút xanh #2563EB đậm,
group box tiêu đề nền xám, tab chọn gạch đỏ #B91C1C, bảng tiêu đề xanh đậm, thanh cuộn mảnh."""

C_TEXT = "#0F172A"
C_TEXT2 = "#1E293B"
C_MUTED = "#475569"
C_PRIMARY = "#2563EB"
C_PRIMARY_DARK = "#1D4ED8"
C_NAVY = "#1E3A8A"
C_BORDER = "#CBD5E1"
C_LINE = "#E2E8F0"
C_BG = "#F8FAFC"
C_BG_ALT = "#F1F5F9"
C_SOFT = "#EFF6FF"

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

MAIN_STYLE = f"""
QMainWindow {{ background-color: {C_BG}; color: {C_TEXT}; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
QWidget {{ color: {C_TEXT}; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 9.5pt; }}
QDialog, QTabWidget > QWidget, QScrollArea > QWidget > QWidget {{ background-color: {C_BG}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}

/* Header Banner */
#HeaderFrame {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1E3A8A, stop:0.6 #1E40AF, stop:1 #2563EB);
    border: none; border-radius: 8px;
}}
#HeaderFrame QLabel {{ background-color: transparent; border: none; }}
#AppTitle {{ font-size: 14pt; font-weight: 900; color: #FFFFFF; letter-spacing: 0.5px; }}
#AppSubtitle {{ font-size: 9pt; color: #DBEAFE; font-weight: 500; }}
#VersionPill {{ background-color: #2563EB; color: #FFFFFF; font-size: 9pt; font-weight: bold;
               padding: 3px 10px; border-radius: 10px; border: 1px solid #93C5FD; }}

/* GroupBox */
QGroupBox {{
    font-weight: bold; font-size: 9.5pt; border: 1px solid {C_LINE}; border-radius: 8px;
    margin-top: 10px; padding-top: 14px; background-color: #FFFFFF;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left; padding: 2px 10px;
    color: {C_NAVY}; background-color: {C_BG_ALT}; border: 1px solid {C_LINE}; border-radius: 4px; font-weight: bold;
}}
QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QRadioButton {{ font-weight: normal; }}

/* Inputs */
QLineEdit, QComboBox, QSpinBox {{
    background-color: #FFFFFF; border: 1px solid {C_BORDER}; border-radius: 5px; padding: 6px 10px;
    font-size: 9.5pt; color: {C_TEXT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1.5px solid {C_PRIMARY}; background-color: #FFFFFF; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ background-color: {C_BG_ALT}; color: #94A3B8; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background-color: #FFFFFF; color: {C_TEXT}; border: 1px solid {C_BORDER}; outline: 0; padding: 4px;
    selection-background-color: {C_SOFT}; selection-color: #1E40AF;
}}
QComboBox QAbstractItemView::item {{ min-height: 26px; padding: 2px 8px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; background: {C_BG_ALT}; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {C_LINE}; }}
QCheckBox, QRadioButton {{ font-size: 9.5pt; color: {C_TEXT2}; font-weight: 500; spacing: 8px; }}

/* Buttons – mặc định xanh như Hồ sơ 1361 */
QPushButton {{
    background-color: {C_PRIMARY}; color: #FFFFFF; border: none; border-radius: 6px;
    padding: 7px 16px; font-weight: bold; font-size: 9.5pt;
}}
QPushButton:hover {{ background-color: {C_PRIMARY_DARK}; }}
QPushButton:pressed {{ background-color: #1E40AF; }}
QPushButton:disabled {{ background-color: {C_LINE}; color: #94A3B8; border: 1px solid {C_BORDER}; }}
QPushButton[size="sm"] {{ font-size: 9pt; padding: 6px 11px; }}
QPushButton[size="lg"] {{ font-size: 10pt; padding: 9px 20px; }}
QPushButton#light {{ background-color: #FFFFFF; color: {C_TEXT2}; border: 1px solid {C_BORDER}; }}
QPushButton#light:hover {{ background-color: {C_SOFT}; border-color: {C_PRIMARY}; color: #1E40AF; }}
QPushButton#light:disabled {{ color: #94A3B8; background: {C_BG_ALT}; }}
QPushButton#flat {{ background: transparent; color: {C_PRIMARY}; padding: 4px 8px; }}
QPushButton#flat:hover {{ background: {C_SOFT}; }}
QPushButton#flat:checked {{ background: {C_SOFT}; color: #1E40AF; }}
QToolButton {{ background-color: #FFFFFF; color: {C_TEXT2}; border: 1px solid {C_BORDER}; border-radius: 6px;
               padding: 6px 10px; font-weight: bold; }}
QToolButton:hover {{ background-color: {C_SOFT}; border-color: {C_PRIMARY}; color: #1E40AF; }}
QToolButton::menu-indicator {{ image: none; }}

/* Tabs */
QTabWidget::pane {{ border: 1px solid {C_LINE}; border-radius: 8px; background-color: #FFFFFF; top: -1px; }}
QTabBar::tab {{
    background-color: {C_BG_ALT}; color: {C_MUTED}; border: 1px solid {C_LINE}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px; padding: 9px 20px;
    font-weight: bold; font-size: 9.5pt; margin-right: 4px;
}}
QTabBar::tab:selected {{ background-color: #FFFFFF; color: {C_NAVY}; border-bottom: 3px solid #B91C1C; }}
QTabBar::tab:hover:!selected {{ background-color: {C_LINE}; color: {C_TEXT2}; }}
QTabWidget#SubTabs QTabBar::tab {{ padding: 7px 16px; font-size: 9pt; }}

/* Bảng / cây / danh sách */
QTableWidget, QTreeWidget, QListWidget {{
    background-color: #FFFFFF; alternate-background-color: #F8FAFC; gridline-color: {C_BG_ALT};
    border: 1px solid {C_LINE}; border-radius: 6px; color: {C_TEXT}; font-size: 9.5pt;
    selection-background-color: {C_SOFT}; selection-color: #1E40AF; outline: 0;
}}
QTreeWidget::item, QListWidget::item {{ padding: 3px 2px; }}
QTreeWidget::item:selected, QListWidget::item:selected, QTableWidget::item:selected {{
    background-color: #DBEAFE; color: #1E40AF; }}
QHeaderView::section {{
    background-color: {C_BG_ALT}; color: {C_NAVY}; padding: 8px; font-weight: bold; font-size: 9.5pt;
    border: none; border-bottom: 2px solid {C_BORDER}; border-right: 1px solid {C_LINE};
}}
QTableCornerButton::section {{ background-color: {C_BG_ALT}; border: none; }}

/* Tiến trình & nhật ký */
QProgressBar {{
    border: 1px solid {C_BORDER}; border-radius: 6px; text-align: center; background-color: {C_BG};
    color: {C_TEXT}; font-weight: bold; min-height: 16px; max-height: 16px; font-size: 8.5pt;
}}
QProgressBar::chunk {{ background-color: #10B981; border-radius: 5px; }}
QTextEdit, QPlainTextEdit, QTextBrowser {{
    background-color: #FFFFFF; border: 1px solid {C_BORDER}; border-radius: 6px; color: {C_TEXT};
    font-family: 'Segoe UI', Tahoma, sans-serif; font-size: 9pt;
}}

/* Thanh cuộn mảnh */
QScrollBar:vertical {{ border: none; background-color: {C_BG_ALT}; width: 10px; margin: 0; border-radius: 5px; }}
QScrollBar::handle:vertical {{ background-color: {C_BORDER}; min-height: 24px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background-color: #94A3B8; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ border: none; background-color: {C_BG_ALT}; height: 10px; margin: 0; border-radius: 5px; }}
QScrollBar::handle:horizontal {{ background-color: {C_BORDER}; min-width: 24px; border-radius: 5px; }}
QScrollBar::handle:horizontal:hover {{ background-color: #94A3B8; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QToolTip {{ background-color: {C_TEXT}; color: #FFFFFF; border: 1px solid #334155; padding: 6px 10px;
            border-radius: 4px; font-size: 9pt; }}
QMenu {{ background: #FFFFFF; border: 1px solid {C_BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C_SOFT}; color: #1E40AF; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {C_BORDER}; }}

/* Thẻ thống kê, thanh phạm vi, khung xem trước */
QFrame#card {{ background: #FFFFFF; border: 1px solid {C_LINE}; border-radius: 8px; }}
QFrame#card:hover {{ border-color: {C_PRIMARY}; }}
QFrame#scopeBar {{ background: {C_SOFT}; border: 1px solid #BFDBFE; border-radius: 6px; }}
QScrollArea#PreviewArea {{ background-color: #FFFFFF; border: 1px dashed {C_BORDER}; border-radius: 4px; }}
QScrollArea#PreviewArea > QWidget > QWidget {{ background-color: #FFFFFF; }}
QPlainTextEdit#log {{ font-family: Consolas, 'Segoe UI', monospace; font-size: 9pt; color: #334155; background: #FFFFFF; }}
QLabel#StatusText {{ font-weight: bold; color: {C_PRIMARY}; font-size: 9.5pt; }}
QLabel#Hint {{ color: #64748B; font-size: 8.5pt; }}
"""

MAIN_STYLE += "".join(
    f"QPushButton#{k} {{ background-color: {a}; }} QPushButton#{k}:hover {{ background-color: {b}; }} "
    f"QPushButton#{k}:pressed {{ background-color: {c}; }} "
    f"QPushButton#{k}:disabled {{ background-color: {C_LINE}; color: #94A3B8; border: 1px solid {C_BORDER}; }} "
    for k, (a, b, c) in BUTTON_COLORS.items())


def full_style() -> str:
    """Stylesheet đầy đủ (gồm icon ô tích / mũi tên). Gọi sau khi đã tạo QApplication."""
    from .icons import icon_style
    return MAIN_STYLE + icon_style()


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


def apply_light_palette(app) -> None:
    """Luôn dùng giao diện sáng, kể cả khi Windows đang ở chế độ tối (tránh combo/ô số bị nền đen)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:
        pass
    pal = QPalette()
    for role, c in ((QPalette.Window, C_BG), (QPalette.WindowText, C_TEXT), (QPalette.Base, "#FFFFFF"),
                    (QPalette.AlternateBase, C_BG), (QPalette.Text, C_TEXT), (QPalette.Button, "#FFFFFF"),
                    (QPalette.ButtonText, C_TEXT), (QPalette.Highlight, "#DBEAFE"),
                    (QPalette.HighlightedText, "#1E40AF"), (QPalette.ToolTipBase, C_TEXT),
                    (QPalette.ToolTipText, "#FFFFFF"), (QPalette.PlaceholderText, "#94A3B8"),
                    (QPalette.Light, "#FFFFFF"), (QPalette.Midlight, C_LINE), (QPalette.Mid, C_BORDER),
                    (QPalette.Dark, "#94A3B8"), (QPalette.Shadow, "#64748B"), (QPalette.BrightText, "#FFFFFF"),
                    (QPalette.Link, C_PRIMARY)):
        pal.setColor(role, QColor(c))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#94A3B8"))
    app.setPalette(pal)
