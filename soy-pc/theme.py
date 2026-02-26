"""
SoyAdmin 공장 테마 — 밝은 테마 고정, 공장/간장 공장 컨셉.
Fluent Light 위에 콘텐츠 영역에만 적용하는 스타일.
"""

# 밝은 공장 팔레트 (라이트 고정)
BG_MAIN = "#f5f4f1"
BG_CARD = "#ffffff"
BG_BUTTON = "#f0eeea"
BG_BUTTON_DISABLED = "#ebeaeb"
BORDER = "#e5e2dc"
BORDER_STRONG = "#d4d0c8"
TEXT_PRIMARY = "#1c1c1c"
TEXT_SECONDARY = "#5c5c5c"
TEXT_MUTED = "#8a8a8a"
TEXT_DISABLED = "#a0a0a0"

# 악센트 — 간장 공장 (앰버/갈색)
ACCENT = "#C4902B"
ACCENT_HOVER = "#a67b22"
ACCENT_SOFT = "#e8dcc4"

# 잠금 화면 — 브랜드 강조
LOCK_TITLE = "#8B6914"
LOCK_SUBTITLE = "#5c5c5c"
LOCK_BTN_BG = "#ffffff"
LOCK_BTN_BORDER = "#d4d0c8"
LOCK_BTN_HOVER_BG = "#e8dcc4"
LOCK_BTN_HOVER_BORDER = "#C4902B"
LOCK_HINT = "#8a8a8a"
ADMIN_BTN_BG = "#f0eeea"
ADMIN_BTN_HOVER = "#e0dcd4"

FACTORY_STYLESHEET = f"""
/* 공통 — 밝은 공장 배경 */
QWidget {{
  background-color: {BG_MAIN};
  color: {TEXT_PRIMARY};
}}
QDialog {{
  background-color: {BG_CARD};
  color: {TEXT_PRIMARY};
  border-radius: 12px;
  padding: 24px;
}}
QDialog QWidget {{
  background-color: transparent;
}}
QDialog QLabel {{
  background-color: transparent;
}}
QPushButton {{
  background-color: {BG_BUTTON};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  padding: 5px 12px;
  min-height: 18px;
  border-radius: 6px;
  font-weight: 500;
}}
QPushButton:hover {{
  background-color: {BORDER};
  border-color: {BORDER_STRONG};
}}
QPushButton:pressed {{
  background-color: {BORDER_STRONG};
}}
QPushButton:disabled {{
  background-color: {BG_BUTTON_DISABLED};
  color: {TEXT_DISABLED};
  border-color: {BORDER};
}}
QLabel {{
  color: {TEXT_PRIMARY};
}}
QLineEdit {{
  background-color: {BG_CARD};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  padding: 10px 12px;
  border-radius: 6px;
  selection-background-color: {ACCENT_SOFT};
}}
QLineEdit:focus {{
  border-color: {ACCENT};
}}
QLineEdit:disabled {{
  background-color: {BG_BUTTON_DISABLED};
  color: {TEXT_DISABLED};
  border-color: {BORDER};
}}

/* ========== 팝업(다이얼로그) 공통 ========== */
QDialog QLabel#label_title {{
  font-size: 16px;
  font-weight: bold;
  color: {TEXT_PRIMARY};
  padding: 4px 0;
}}
QDialog QLabel#label_prompt {{
  font-size: 13px;
  color: {TEXT_PRIMARY};
  padding: 2px 0;
}}
QDialog QLabel#statusLabel {{
  font-size: 12px;
  color: {TEXT_SECONDARY};
  padding: 6px 0;
  min-height: 1.2em;
}}
QDialog QLabel#label_name,
QDialog QLabel#label_password,
QDialog QLabel#label_confirm {{
  color: {TEXT_SECONDARY};
  min-width: 100px;
}}
QDialog QLineEdit {{
  min-height: 20px;
}}
QDialog QPushButton#button_ok {{
  background-color: {ACCENT};
  color: white;
  border: none;
  min-width: 72px;
  min-height: 28px;
}}
QDialog QPushButton#button_ok:hover {{
  background-color: {ACCENT_HOVER};
}}
QDialog QPushButton#button_ok:disabled {{
  background-color: {BG_BUTTON_DISABLED};
  color: {TEXT_DISABLED};
  border: 1px solid {BORDER};
}}
QDialog QPushButton#button_cancel {{
  background-color: {BG_BUTTON};
  color: {TEXT_SECONDARY};
  min-width: 64px;
  min-height: 28px;
}}
QDialog QPushButton#button_edit {{
  background-color: {ACCENT};
  color: white;
  border: none;
  min-width: 56px;
  min-height: 28px;
  border-radius: 6px;
}}
QDialog QPushButton#button_edit:hover {{
  background-color: {ACCENT_HOVER};
}}
QDialog QPushButton#button_delete {{
  background-color: {BG_BUTTON};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  min-width: 56px;
  min-height: 28px;
  border-radius: 6px;
}}
QDialog QPushButton#button_delete:hover {{
  background-color: {BORDER};
}}
QDialog QPushButton#button_close {{
  background-color: {BG_BUTTON};
  color: {TEXT_SECONDARY};
  min-width: 56px;
  min-height: 28px;
  border-radius: 6px;
}}
QDialog QPushButton#button_close:hover {{
  background-color: {BORDER};
}}

/* ========== 잠금 화면 (스마트 간장 공장) ========== */
QWidget#LockScreen {{
  background-color: {BG_MAIN};
}}
QWidget#LockScreen QLabel#label_lockTitle {{
  color: {LOCK_TITLE};
  font-size: 28px;
  font-weight: bold;
  letter-spacing: 0.5px;
}}
QWidget#LockScreen QLabel#label_lockSubtitle {{
  color: {LOCK_SUBTITLE};
  font-size: 13px;
}}
QWidget#LockScreen QPushButton#touchToEnterButton {{
  background-color: {LOCK_BTN_BG};
  color: {TEXT_PRIMARY};
  border: 2px solid {LOCK_BTN_BORDER};
  border-radius: 12px;
  font-size: 22px;
  font-weight: bold;
  padding: 24px;
}}
QWidget#LockScreen QPushButton#touchToEnterButton:hover {{
  background-color: {LOCK_BTN_HOVER_BG};
  border-color: {LOCK_BTN_HOVER_BORDER};
  color: {ACCENT_HOVER};
}}
QWidget#LockScreen QLabel#label_touchHint {{
  color: {LOCK_HINT};
  font-size: 12px;
}}
QWidget#LockScreen QPushButton#adminModeButton {{
  background-color: {ADMIN_BTN_BG};
  color: {TEXT_SECONDARY};
  border: 1px solid {BORDER};
}}
QWidget#LockScreen QPushButton#adminModeButton:hover {{
  background-color: {ADMIN_BTN_HOVER};
  color: {ACCENT};
  border-color: {ACCENT_SOFT};
}}

/* ========== 작업자 화면 ========== */
QWidget#WorkerScreen {{
  background-color: {BG_MAIN};
}}
QWidget#WorkerScreen QFrame#worker_sidebar {{
  background-color: {BG_CARD};
  border-right: 1px solid {BORDER};
}}
QWidget#WorkerScreen QFrame#worker_sidebar QLabel#label_worker_menuTitle {{
  color: {TEXT_SECONDARY};
  font-size: 11px;
  font-weight: bold;
}}
QWidget#WorkerScreen QFrame#worker_sidebar QPushButton#menu_inbound {{
  background-color: transparent;
  color: {TEXT_PRIMARY};
  border: none;
  border-radius: 6px;
  text-align: left;
  padding: 8px 12px;
}}
QWidget#WorkerScreen QFrame#worker_sidebar QPushButton#menu_inbound:hover {{
  background-color: {BG_BUTTON};
}}
QWidget#WorkerScreen QFrame#worker_sidebar QPushButton#menu_inbound:checked {{
  background-color: {ACCENT_SOFT};
  color: {ACCENT_HOVER};
  font-weight: 600;
}}
QWidget#WorkerScreen QFrame#worker_sidebar QPushButton#backButton {{
  background-color: {BG_BUTTON};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  border-radius: 6px;
}}
QWidget#WorkerScreen QFrame#worker_sidebar QPushButton#backButton:hover {{
  background-color: {BORDER};
}}

/* ========== 관리자 화면 (사이드바 + 콘텐츠) ========== */
QWidget#AdminScreen {{
  background-color: {BG_MAIN};
}}
/* 사이드바 */
QWidget#AdminScreen QFrame#admin_sidebar {{
  background-color: {BG_CARD};
  border-right: 1px solid {BORDER};
}}
QWidget#AdminScreen QFrame#admin_sidebar QLabel#label_menuTitle {{
  color: {TEXT_SECONDARY};
  font-size: 11px;
  font-weight: bold;
}}
QWidget#AdminScreen QFrame#admin_sidebar QPushButton#menu_worker_management {{
  background-color: transparent;
  color: {TEXT_PRIMARY};
  border: none;
  border-radius: 6px;
  text-align: left;
  padding: 8px 12px;
}}
QWidget#AdminScreen QFrame#admin_sidebar QPushButton#menu_worker_management:hover {{
  background-color: {BG_BUTTON};
}}
QWidget#AdminScreen QFrame#admin_sidebar QPushButton#menu_worker_management:checked {{
  background-color: {ACCENT_SOFT};
  color: {ACCENT_HOVER};
  font-weight: 600;
}}
QWidget#AdminScreen QFrame#admin_sidebar QPushButton#backButton {{
  background-color: {BG_BUTTON};
  color: {TEXT_PRIMARY};
  border: 1px solid {BORDER};
  border-radius: 6px;
}}
QWidget#AdminScreen QFrame#admin_sidebar QPushButton#backButton:hover {{
  background-color: {BORDER};
}}
/* 작업자 관리 콘텐츠 */
QWidget#AdminScreen QLabel#label_worker_management_title {{
  color: {TEXT_PRIMARY};
  font-size: 18px;
  font-weight: bold;
}}
QWidget#AdminScreen QPushButton#addWorkerButton {{
  background-color: {ACCENT};
  color: white;
  border: none;
  min-height: 30px;
  padding: 5px 12px;
  border-radius: 8px;
  font-size: 13px;
}}
QWidget#AdminScreen QPushButton#addWorkerButton:hover {{
  background-color: {ACCENT_HOVER};
}}
QWidget#AdminScreen QTableWidget {{
  background-color: {BG_CARD};
  border: 1px solid {BORDER};
  border-radius: 8px;
  gridline-color: {BORDER};
}}
QWidget#AdminScreen QTableWidget::item {{
  padding: 8px 12px;
  color: {TEXT_PRIMARY};
}}
QWidget#AdminScreen QTableWidget::item:selected {{
  background-color: {ACCENT_SOFT};
  color: {TEXT_PRIMARY};
}}
QWidget#AdminScreen QHeaderView::section {{
  background-color: {BG_BUTTON};
  color: {TEXT_SECONDARY};
  padding: 10px 12px;
  border: none;
  border-bottom: 2px solid {BORDER};
  border-right: 1px solid {BORDER};
  font-weight: 600;
}}
QWidget#AdminScreen QHeaderView::section:last {{
  border-right: none;
}}
"""
