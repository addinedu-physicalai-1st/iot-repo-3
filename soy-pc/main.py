import logging
import os
import sys
import traceback

from PyQt6 import uic
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QStackedLayout, QVBoxLayout, QWidget

from qfluentwidgets import FluentWidget, setTheme, setThemeColor, Theme

from features.admin_registration import ensure_admin_registered
from features.admin_screen import setup_admin_screen
from features.lock_screen import setup_lock_screen
from features.worker_screen import setup_worker_screen
from theme import BG_MAIN, FACTORY_STYLESHEET


def _setup_global_ime(app: QApplication) -> None:
    """모든 QLineEdit/QPlainTextEdit에 포커스 시 한글 IME 조합 허용(ImhNone)."""

    def on_focus_changed(_old: QWidget | None, new: QWidget | None) -> None:
        if new is None:
            return
        if isinstance(new, (QLineEdit, QPlainTextEdit)):
            new.setInputMethodHints(Qt.InputMethodHint.ImhNone)

    app.focusChanged.connect(on_focus_changed)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
    logging.getLogger("api").setLevel(logging.INFO)

    app = QApplication(sys.argv)
    base = os.path.dirname(__file__)
    ui_dir = os.path.join(base, "ui")

    _setup_global_ime(app)
    setTheme(Theme.LIGHT)
    setThemeColor(QColor("#C4902B"))  # 공장/간장 악센트 (앰버)
    app.setStyleSheet(FACTORY_STYLESHEET)  # 메인·팝업 공통 테마

    window = FluentWidget()
    window.setWindowTitle("Soy-PC")
    window.resize(1100, 750)
    window.setMicaEffectEnabled(False)
    window.setCustomBackgroundColor(QColor(BG_MAIN), QColor(BG_MAIN))

    central = QWidget()
    stacked = QStackedLayout(central)
    stacked.setContentsMargins(0, 0, 0, 0)

    page_lock = QWidget()
    uic.loadUi(os.path.join(ui_dir, "lock_screen.ui"), page_lock)
    stacked.addWidget(page_lock)

    page_worker = QWidget()
    uic.loadUi(os.path.join(ui_dir, "worker_screen.ui"), page_worker)
    stacked.addWidget(page_worker)

    page_admin = QWidget()
    uic.loadUi(os.path.join(ui_dir, "admin_screen.ui"), page_admin)
    stacked.addWidget(page_admin)

    window.page_lock = page_lock
    window.page_worker = page_worker
    window.page_admin = page_admin

    main_layout = QVBoxLayout(window)
    main_layout.setContentsMargins(0, window.titleBar.height(), 0, 0)
    main_layout.setSpacing(0)
    main_layout.addWidget(central)

    stacked.setCurrentIndex(0)

    setup_lock_screen(window, stacked, ui_dir)
    setup_worker_screen(window, stacked)
    setup_admin_screen(window, stacked, ui_dir)

    window.show()

    while not ensure_admin_registered(ui_dir, window):
        pass

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        print("Soy-PC 시작 실패:", e, file=sys.stderr, flush=True)
        sys.exit(1)
