"""최초 관리자 등록 — 첫 admin에 비밀번호가 없으면 비밀번호 등록 팝업 (서버 API 사용)."""
import os

from PyQt6 import uic
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QDialog, QWidget

from qfluentwidgets import MessageBox

from api.client import first_admin_needs_password, get_server_address, register_first_admin


def ensure_admin_registered(ui_dir: str, parent: QWidget | None = None) -> bool:
    """
    서버를 통해 첫 admin 비밀번호 필요 여부 확인. 필요하면 최초 설정(비밀번호 등록) 팝업을 띄움.
    등록 성공 또는 이미 비밀번호가 설정되어 있으면 True, 서버 연결 실패 시 False.
    """
    try:
        needs_password = first_admin_needs_password()
    except (ConnectionRefusedError, TimeoutError, OSError) as e:
        addr = get_server_address()
        w = MessageBox(
            "서버 연결 실패",
            "soy-server TCP에 연결할 수 없습니다.\n\n"
            f"연결 주소: {addr}\n"
            f"(HTTP 8000이 아닌 TCP 9001 포트입니다.)\n\n"
            "서버가 떠 있어도 TCP 9001이 열려 있어야 합니다.\n"
            "서버 로그에 '[TCP] listening on port 9001' 이 있는지 확인하세요.\n\n"
            f"상세: {e!s}",
            parent,
        )
        w.cancelButton.hide()
        w.yesButton.setText("확인")
        w.exec()
        return False
    except Exception as e:
        w = MessageBox(
            "오류",
            f"관리자 설정 확인 중 오류가 발생했습니다.\n{e!s}",
            parent,
        )
        w.cancelButton.hide()
        w.yesButton.setText("확인")
        w.exec()
        return False
    if not needs_password:
        return True

    # 첫 admin에 비밀번호 없음 → 등록 팝업
    while True:
        dialog = QDialog(parent)
        uic.loadUi(
            os.path.join(ui_dir, "admin_registration_dialog.ui"),
            dialog,
        )
        dialog.setWindowTitle("최초 설정 — 관리자 등록")

        def try_register() -> None:
            QGuiApplication.inputMethod().commit()
            pw = dialog.lineEdit_password.text().strip()
            cf = dialog.lineEdit_confirm.text().strip()
            if not pw:
                box = MessageBox("입력 오류", "비밀번호를 입력하세요.", dialog)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                dialog.lineEdit_password.setFocus()
                return
            if len(pw) < 4:
                box = MessageBox("입력 오류", "비밀번호는 4자 이상으로 설정하세요.", dialog)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                dialog.lineEdit_password.setFocus()
                return
            if pw != cf:
                box = MessageBox("입력 오류", "비밀번호가 일치하지 않습니다.", dialog)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                dialog.lineEdit_confirm.selectAll()
                dialog.lineEdit_confirm.setFocus()
                return
            try:
                register_first_admin(pw)
                box = MessageBox("등록 완료", "관리자 비밀번호가 등록되었습니다.", dialog)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()
                dialog.accept()
            except Exception as e:
                box = MessageBox("등록 실패", f"서버 등록 중 오류가 발생했습니다.\n{e!s}", dialog)
                box.cancelButton.hide()
                box.yesButton.setText("확인")
                box.exec()

        dialog.button_ok.clicked.connect(try_register)
        dialog.button_cancel.hide()
        dialog.button_cancel.clicked.connect(dialog.reject)
        dialog.lineEdit_confirm.returnPressed.connect(try_register)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        break
    return True
