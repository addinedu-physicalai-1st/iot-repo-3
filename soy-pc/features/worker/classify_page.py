"""분류하기 페이지 — HMI 스타일 모니터, 공정 테이블, 창고 차트, 공정 시작/중지."""

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QTableWidgetItem,
)

from api import list_processes, process_update, list_inventory
from features.worker.threads import UdpCameraThread, MqttSignalBridge
from features.worker.inbound_dialog import parse_qr_payload
from features.worker.process_controller import (
    FsmState,
    ProcessController,
)

logger = logging.getLogger(__name__)

# ── 공정 상태 색상 ────────────────────────────────────────────
_STATE_COLORS = {
    "IDLE": "#e74c3c",
    "RUNNING": "#27ae60",
    "PAUSED": "#f39c12",
}
_STATE_LABELS = {
    "IDLE": "대기",
    "RUNNING": "가동중",
    "PAUSED": "일시정지",
}

# ── 분류대 스타일 ─────────────────────────────────────────────
_STATION_IDLE_STYLE = (
    "QFrame { background: #f5f5f5; border: 2px solid #ddd; border-radius: 8px; }"
)
_STATION_ACTIVE_STYLE = (
    "QFrame { background: #e8f4fd; border: 2px solid #3498db; border-radius: 8px; }"
)
_STATION_DOT_IDLE = "color: #aaa; font-size: 16px; border: none;"
_STATION_DOT_ACTIVE = "color: #3498db; font-size: 16px; font-weight: bold; border: none;"
_STATION_LABEL_IDLE = "color: #888; font-size: 12px; border: none;"
_STATION_LABEL_ACTIVE = "color: #3498db; font-size: 12px; font-weight: bold; border: none;"

WAREHOUSE_TOTAL = 10  # 창고 현황 총량 기준


def setup_classify_page(worker, window, stacked, stack) -> tuple:
    """분류 페이지 UI + 이벤트 구성. (controller, refresh_list, refresh_chart, restore_monitor) 반환."""

    _classify_processes: list[dict[str, Any]] = []

    # ── 모니터 프레임 생성 ────────────────────────────────────────
    classify_layout = worker.verticalLayout_classify

    monitor_frame = QFrame()
    monitor_frame.setFrameShape(QFrame.Shape.StyledPanel)
    monitor_frame.setStyleSheet(
        "QFrame { background: #fafafa; border: 1px solid #ddd; border-radius: 6px; }"
    )
    monitor_layout = QHBoxLayout(monitor_frame)
    monitor_layout.setContentsMargins(12, 12, 12, 12)
    monitor_layout.setSpacing(16)

    # 좌측: 카메라 프리뷰
    cam_preview = QLabel("카메라 대기")
    cam_preview.setFixedSize(320, 240)
    cam_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cam_preview.setStyleSheet(
        "background: #222; color: #888; border: 1px solid #555; font-size: 13px;"
    )
    monitor_layout.addWidget(cam_preview)

    # 우측: HMI 스타일 공정 상태
    info_layout = QVBoxLayout()
    info_layout.setSpacing(8)

    # ── 공정 상태 표시 ────────────────────────────────────────
    process_state_label = QLabel()
    process_state_label.setStyleSheet(
        "font-weight: bold; font-size: 14px; border: none;"
    )
    info_layout.addWidget(process_state_label)

    # ── 분류대 패널 (1L / 2L) ─────────────────────────────────
    stations_row = QHBoxLayout()
    stations_row.setSpacing(12)

    # 1L 분류대
    station_1l_frame = QFrame()
    station_1l_frame.setFixedSize(130, 70)
    station_1l_frame.setStyleSheet(_STATION_IDLE_STYLE)
    station_1l_layout = QVBoxLayout(station_1l_frame)
    station_1l_layout.setContentsMargins(8, 6, 8, 6)
    station_1l_layout.setSpacing(2)
    station_1l_title = QLabel("분류대 1L")
    station_1l_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    station_1l_title.setStyleSheet(
        "font-weight: bold; font-size: 12px; color: #555; border: none;"
    )
    station_1l_status = QLabel("\u25cf 대기")
    station_1l_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    station_1l_status.setStyleSheet(_STATION_DOT_IDLE)
    station_1l_layout.addWidget(station_1l_title)
    station_1l_layout.addWidget(station_1l_status)

    # 2L 분류대
    station_2l_frame = QFrame()
    station_2l_frame.setFixedSize(130, 70)
    station_2l_frame.setStyleSheet(_STATION_IDLE_STYLE)
    station_2l_layout = QVBoxLayout(station_2l_frame)
    station_2l_layout.setContentsMargins(8, 6, 8, 6)
    station_2l_layout.setSpacing(2)
    station_2l_title = QLabel("분류대 2L")
    station_2l_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    station_2l_title.setStyleSheet(
        "font-weight: bold; font-size: 12px; color: #555; border: none;"
    )
    station_2l_status = QLabel("\u25cf 대기")
    station_2l_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    station_2l_status.setStyleSheet(_STATION_DOT_IDLE)
    station_2l_layout.addWidget(station_2l_title)
    station_2l_layout.addWidget(station_2l_status)

    stations_row.addWidget(station_1l_frame)
    stations_row.addWidget(station_2l_frame)
    stations_row.addStretch()
    info_layout.addLayout(stations_row)

    # ── 컨베이어 흐름 표시 ─────────────────────────────────────
    flow_label = QLabel("\u25b6QR \u2550\u2550\u25b6 S1 \u2550\u2550\u25b6 S2 \u2550\u2550\u25b6 \ubbf8\ubd84\ub958")
    flow_label.setStyleSheet(
        "font-size: 12px; color: #777; font-family: monospace; border: none;"
    )
    info_layout.addWidget(flow_label)

    # ── 대기 목록 ──────────────────────────────────────────────
    pending_title = QLabel("대기 목록:")
    pending_title.setStyleSheet(
        "font-weight: bold; font-size: 12px; color: #555; border: none;"
    )
    info_layout.addWidget(pending_title)

    pending_list = QListWidget()
    pending_list.setMaximumHeight(80)
    pending_list.setStyleSheet(
        "QListWidget { background: #fff; border: 1px solid #ddd; border-radius: 4px; "
        "font-size: 12px; } "
        "QListWidget::item { padding: 2px 6px; }"
    )
    pending_list.addItem("(비어있음)")
    info_layout.addWidget(pending_list)

    # ── 경고 라벨 ──────────────────────────────────────────────
    warning_label = QLabel("경고: (없음)")
    warning_label.setStyleSheet("font-size: 12px; color: #8a8a8a; border: none;")
    warning_label.setWordWrap(True)
    info_layout.addWidget(warning_label)

    info_layout.addStretch()
    monitor_layout.addLayout(info_layout)
    monitor_layout.setStretch(0, 0)
    monitor_layout.setStretch(1, 1)

    classify_layout.insertWidget(1, monitor_frame)

    # ── HMI 상태 업데이트 헬퍼 ─────────────────────────────────
    def _update_process_state(state_name: str):
        color = _STATE_COLORS.get(state_name, "#888")
        label = _STATE_LABELS.get(state_name, state_name)
        process_state_label.setText(f"\u25a0 {label}")
        process_state_label.setStyleSheet(
            f"font-weight: bold; font-size: 14px; color: {color}; border: none;"
        )

    def _update_station(station: str, active: bool):
        if station == "1L":
            frame, status_lbl = station_1l_frame, station_1l_status
        else:
            frame, status_lbl = station_2l_frame, station_2l_status
        if active:
            frame.setStyleSheet(_STATION_ACTIVE_STYLE)
            status_lbl.setText("\u25cf \ubd84\ub958\uc911")
            status_lbl.setStyleSheet(_STATION_DOT_ACTIVE)
        else:
            frame.setStyleSheet(_STATION_IDLE_STYLE)
            status_lbl.setText("\u25cf \ub300\uae30")
            status_lbl.setStyleSheet(_STATION_DOT_IDLE)

    def _update_pending_list(items: list[tuple[str, str]]):
        pending_list.clear()
        if not items:
            pending_list.addItem("(\ube44\uc5b4\uc788\uc74c)")
        else:
            for item_code, direction in items:
                pending_list.addItem(f"{item_code}  \u2192  {direction}")

    _update_process_state("IDLE")

    # ── ProcessController + UI 콜백 ──────────────────────────────
    class _UiCallbacks:
        def on_fsm_state_changed(self, state: FsmState) -> None:
            _update_process_state(state.value)
            _update_buttons(state.value)

        def on_proximity(self, detected: bool) -> None:
            pass

        def on_detected(self, direction: str, queue_size: int) -> None:
            pass

        def on_sort_result(self, kind: str, new_qty: int, db_ok: bool) -> None:
            suffix = "" if db_ok else " (DB 오류)"
            worker.classifyResultLabel.setText(f"분류 완료: {kind} {new_qty}개{suffix}")
            _refresh_classify_list()
            _refresh_warehouse_chart()

        def on_unclassified(self, new_qty: int, db_ok: bool) -> None:
            worker.classifyResultLabel.setText(f"미분류 감지 ({new_qty}건)")
            warning_label.setText(f"경고: 미분류 물품 감지 ({new_qty}건)")
            warning_label.setStyleSheet(
                "font-size: 12px; color: #f39c12; font-weight: bold; border: none;"
            )
            _refresh_classify_list()
            _refresh_warehouse_chart()

        def on_process_started(self, pid: int) -> None:
            worker.classifyResultLabel.setText("공정을 시작했습니다.")
            _update_buttons("RUNNING")

        def on_process_paused(self) -> None:
            worker.classifyResultLabel.setText("공정을 일시정지했습니다.")
            _update_buttons("PAUSED")

        def on_process_resumed(self) -> None:
            worker.classifyResultLabel.setText("공정을 재개했습니다.")
            _update_buttons("RUNNING")

        def on_process_stopped(self, pid: int) -> None:
            _stop_udp_camera()
            _reset_monitor()
            _update_buttons("IDLE")
            worker.classifyResultLabel.setText("공정을 중지했습니다.")

        def on_process_completed(
            self, pid: int, sorted_total: int, order_total: int
        ) -> None:
            _stop_udp_camera()
            _reset_monitor()
            _refresh_classify_list()
            _refresh_warehouse_chart()
            worker.classifyResultLabel.setText(
                f"공정 #{pid} 완료! (분류 {sorted_total}/{order_total})"
            )

        def on_qr_enqueued(
            self, item_code: str, direction: str, queue_size: int
        ) -> None:
            pass  # pending_updated로 대체

        def on_qr_error(self, message: str) -> None:
            warning_label.setText(f"경고: {message}")
            warning_label.setStyleSheet(
                "font-size: 12px; color: #f39c12; border: none;"
            )

        def on_error(self, message: str) -> None:
            worker.classifyResultLabel.setText(message)

        def on_sorting_started(self, station: str) -> None:
            _update_station(station, True)

        def on_sorting_ended(self, station: str) -> None:
            _update_station(station, False)

        def on_pending_updated(self, items: list[tuple[str, str]]) -> None:
            _update_pending_list(items)

    _controller = ProcessController(_UiCallbacks())

    # ── MQTT 브릿지 ──────────────────────────────────────────────
    mqtt_bridge = MqttSignalBridge(parent=window)
    mqtt_bridge.status_received.connect(lambda p: _controller.handle_status(p))
    mqtt_bridge.sensor_received.connect(
        lambda p: _controller.handle_sensor(p, _classify_processes)
    )

    def _on_camera_detect_reset(payload: str):
        """CAMERA_DETECT 수신 시 UdpCameraThread 쿨다운 초기화."""
        if payload == "CAMERA_DETECT":
            thread = _udp_cam_thread[0]
            if thread:
                thread.reset_cooldown()

    mqtt_bridge.sensor_received.connect(_on_camera_detect_reset)

    # ── UDP 카메라 ───────────────────────────────────────────────
    _udp_cam_thread: list[UdpCameraThread | None] = [None]

    def _start_udp_camera():
        if _udp_cam_thread[0] and _udp_cam_thread[0].isRunning():
            return
        thread = UdpCameraThread(parent=window)

        def on_frame(qimg: QImage):
            pix = QPixmap.fromImage(qimg)
            cam_preview.setPixmap(
                pix.scaled(
                    cam_preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        thread.frame_ready.connect(on_frame)
        thread.qr_decoded.connect(_on_classify_qr_decoded)
        thread.start()
        _udp_cam_thread[0] = thread

    def _stop_udp_camera():
        thread = _udp_cam_thread[0]
        if thread and thread.isRunning():
            thread.stop()
            thread.wait(3000)
        _udp_cam_thread[0] = None
        cam_preview.clear()
        cam_preview.setText("카메라 대기")
        cam_preview.setStyleSheet(
            "background: #222; color: #888; border: 1px solid #555; font-size: 13px;"
        )

    # ── QR → 컨트롤러 ───────────────────────────────────────────
    def _on_classify_qr_decoded(data: str):
        payload = parse_qr_payload(data)
        if not payload:
            warning_label.setText("경고: QR 인식 형식 오류")
            warning_label.setStyleSheet(
                "font-size: 12px; color: #f39c12; border: none;"
            )
            logger.warning("[QR] 파싱 실패: %s", data)
            return
        item_code = payload.get("item_code", "")
        _controller.handle_qr(item_code if item_code else None)

    # ── 모니터 초기화 ────────────────────────────────────────────
    def _reset_monitor():
        _update_process_state("IDLE")
        _update_station("1L", False)
        _update_station("2L", False)
        _update_pending_list([])
        warning_label.setText("경고: (없음)")
        warning_label.setStyleSheet("font-size: 12px; color: #8a8a8a; border: none;")

    # ── 공정 목록 갱신 ───────────────────────────────────────────
    def _refresh_classify_list():
        nonlocal _classify_processes
        try:
            _classify_processes = list_processes()
        except (TimeoutError, OSError, ConnectionError) as e:
            worker.classifyResultLabel.setText(f"서버 연결 실패.\n{e!s}")
            worker.processTable.setRowCount(0)
            worker.label_running_status.setText("현재 진행 중: (목록 불러오기 실패)")
            worker.classifyStartButton.setEnabled(False)
            return
        except RuntimeError as e:
            worker.classifyResultLabel.setText(str(e))
            worker.processTable.setRowCount(0)
            worker.label_running_status.setText("현재 진행 중: (오류)")
            worker.classifyStartButton.setEnabled(False)
            return
        worker.classifyResultLabel.setText("")
        running = next(
            (
                p
                for p in _classify_processes
                if (p.get("status") or "").upper() == "RUNNING"
            ),
            None,
        )
        worker.processTable.setHorizontalHeaderLabels(
            [
                "공정 ID",
                "주문 ID",
                "상태",
                "시작 시각",
                "종료 시각",
                "1L",
                "2L",
                "미분류",
            ]
        )
        worker.processTable.setRowCount(0)
        worker.processTable.blockSignals(True)
        try:
            for p in _classify_processes:
                row = worker.processTable.rowCount()
                worker.processTable.insertRow(row)
                pid = p.get("process_id")
                oid = p.get("order_id")
                st = (p.get("status") or "").upper()

                def _fmt_dt(s: str | None) -> str:
                    if not s:
                        return "\u2014"
                    return s.replace("T", " ")[:16]

                start_str = _fmt_dt(p.get("start_time"))
                end_str = _fmt_dt(p.get("end_time"))
                s1l = p.get("success_1l_qty", 0)
                s2l = p.get("success_2l_qty", 0)
                uncl = p.get("unclassified_qty", 0)
                flags_ro = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                flags_ed = flags_ro | Qt.ItemFlag.ItemIsEditable
                item0 = QTableWidgetItem(str(pid))
                item0.setData(Qt.ItemDataRole.UserRole, pid)
                item0.setFlags(flags_ro)
                worker.processTable.setItem(row, 0, item0)
                for col, val in [(1, str(oid)), (2, st), (3, start_str), (4, end_str)]:
                    it = QTableWidgetItem(val)
                    it.setFlags(flags_ro)
                    worker.processTable.setItem(row, col, it)
                it5 = QTableWidgetItem(str(s1l))
                it5.setFlags(flags_ed)
                worker.processTable.setItem(row, 5, it5)
                it6 = QTableWidgetItem(str(s2l))
                it6.setFlags(flags_ed)
                worker.processTable.setItem(row, 6, it6)
                it7 = QTableWidgetItem(str(uncl))
                it7.setFlags(flags_ed)
                worker.processTable.setItem(row, 7, it7)
                worker.processTable.setRowHeight(row, 52)
        finally:
            worker.processTable.blockSignals(False)
        worker.processTable.setColumnWidth(3, 150)
        worker.processTable.setColumnWidth(4, 150)
        worker.processTable.setColumnWidth(5, 50)
        worker.processTable.setColumnWidth(6, 50)
        worker.processTable.setColumnWidth(7, 55)
        worker.processTable.verticalHeader().setDefaultSectionSize(52)
        if running:
            worker.label_running_status.setText(
                f"현재 진행 중: 공정 #{running['process_id']} (주문 #{running['order_id']})"
            )
        else:
            worker.label_running_status.setText("현재 진행 중: 없음")
        _classify_update_toggle_button()

    # ── 창고 현황 ────────────────────────────────────────────────
    def _refresh_warehouse_chart():
        try:
            inventory = list_inventory()
        except (TimeoutError, OSError, ConnectionError, RuntimeError):
            worker.label_warehouse_1l_count.setText("\u2014")
            worker.label_warehouse_2l_count.setText("\u2014")
            worker.label_warehouse_unclassified_count.setText("\u2014")
            for bar in (
                worker.progressBar_1l,
                worker.progressBar_2l,
                worker.progressBar_unclassified,
            ):
                bar.setMaximum(WAREHOUSE_TOTAL)
                bar.setValue(0)
            return
        # inventory_id 기준: 1 = 1L 창고, 2 = 2L 창고, 3 = 미분류 창고
        total_1l = 0
        total_2l = 0
        total_uncl = 0
        for inv in inventory:
            inv_id = inv.get("inventory_id")
            qty = inv.get("current_qty") or 0
            if inv_id == 1:
                total_1l = qty
            elif inv_id == 2:
                total_2l = qty
            elif inv_id == 3:
                total_uncl = qty
        worker.label_warehouse_1l_count.setText(f"{total_1l}/{WAREHOUSE_TOTAL}")
        worker.label_warehouse_2l_count.setText(f"{total_2l}/{WAREHOUSE_TOTAL}")
        worker.label_warehouse_unclassified_count.setText(
            f"{total_uncl}/{WAREHOUSE_TOTAL}"
        )
        worker.progressBar_1l.setMaximum(WAREHOUSE_TOTAL)
        worker.progressBar_1l.setValue(min(total_1l, WAREHOUSE_TOTAL))
        worker.progressBar_2l.setMaximum(WAREHOUSE_TOTAL)
        worker.progressBar_2l.setValue(min(total_2l, WAREHOUSE_TOTAL))
        worker.progressBar_unclassified.setMaximum(WAREHOUSE_TOTAL)
        worker.progressBar_unclassified.setValue(min(total_uncl, WAREHOUSE_TOTAL))

    worker.warehouseRefreshButton.clicked.connect(_refresh_warehouse_chart)
    for bar in (
        worker.progressBar_1l,
        worker.progressBar_2l,
        worker.progressBar_unclassified,
    ):
        bar.setTextVisible(False)

    # ── 버튼 상태 관리 ─────────────────────────────────────────────
    _current_fsm_state: list[str] = ["IDLE"]

    def _update_buttons(fsm_state: str | None = None):
        """FSM 상태에 따라 시작/일시정지/중지 버튼 활성화."""
        if fsm_state is not None:
            _current_fsm_state[0] = fsm_state

        state = _current_fsm_state[0]
        is_active = _controller.is_active

        if is_active and state == "RUNNING":
            worker.classifyStartButton.setEnabled(False)
            worker.classifyPauseButton.setEnabled(True)
            worker.classifyPauseButton.setText("일시정지")
            worker.classifyStopButton.setEnabled(True)
        elif is_active and state == "PAUSED":
            worker.classifyStartButton.setEnabled(False)
            worker.classifyPauseButton.setEnabled(True)
            worker.classifyPauseButton.setText("재개")
            worker.classifyStopButton.setEnabled(True)
        else:
            # IDLE 또는 공정 미활성
            row = worker.processTable.currentRow()
            item0 = worker.processTable.item(row, 0) if row >= 0 else None
            pid = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
            running = next(
                (p for p in _classify_processes if (p.get("status") or "").upper() == "RUNNING"),
                None,
            )
            is_selected_running = (
                pid is not None and running is not None
                and running.get("process_id") == pid
            )
            if is_selected_running:
                # 앱 재시작 등으로 컨트롤러는 비활성이지만 DB에 RUNNING 공정 존재
                worker.classifyStartButton.setEnabled(True)
                worker.classifyStopButton.setEnabled(True)
            else:
                can_start = pid is not None and not running
                worker.classifyStartButton.setEnabled(can_start)
                worker.classifyStopButton.setEnabled(False)
            worker.classifyPauseButton.setEnabled(False)
            worker.classifyPauseButton.setText("일시정지")

    def _classify_update_toggle_button():
        _update_buttons()

    worker.processTable.itemSelectionChanged.connect(_classify_update_toggle_button)

    # ── 공정 시작/일시정지/중지 ──────────────────────────────────
    def _on_start_clicked():
        row = worker.processTable.currentRow()
        if row < 0:
            worker.classifyResultLabel.setText("공정을 선택하세요.")
            return
        item0 = worker.processTable.item(row, 0)
        pid = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        if pid is None:
            return
        p = next((x for x in _classify_processes if x.get("process_id") == pid), None)
        try:
            if p:
                _controller.start(p)
                _start_udp_camera()
                _reset_monitor()
            _refresh_classify_list()
        except RuntimeError as e:
            worker.classifyResultLabel.setText(f"처리 실패: {e}")
        except (TimeoutError, OSError, ConnectionError) as e:
            worker.classifyResultLabel.setText(f"서버 연결 실패.\n{e!s}")

    def _on_pause_clicked():
        if _current_fsm_state[0] == "PAUSED":
            _controller.resume()
        else:
            _controller.pause()

    def _on_stop_clicked():
        row = worker.processTable.currentRow()
        item0 = worker.processTable.item(row, 0) if row >= 0 else None
        pid = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        try:
            _controller.stop(int(pid) if pid is not None else None)
            _refresh_classify_list()
        except RuntimeError as e:
            worker.classifyResultLabel.setText(f"처리 실패: {e}")
        except (TimeoutError, OSError, ConnectionError) as e:
            worker.classifyResultLabel.setText(f"서버 연결 실패.\n{e!s}")

    worker.classifyStartButton.clicked.connect(_on_start_clicked)
    worker.classifyPauseButton.clicked.connect(_on_pause_clicked)
    worker.classifyStopButton.clicked.connect(_on_stop_clicked)
    worker.classifyRefreshButton.clicked.connect(_refresh_classify_list)

    # ── 셀 직접 편집 ─────────────────────────────────────────────
    def on_classify_cell_changed(row: int, col: int):
        if col not in (5, 6, 7):
            return
        item0 = worker.processTable.item(row, 0)
        pid = item0.data(Qt.ItemDataRole.UserRole) if item0 else None
        if pid is None:
            return
        item = worker.processTable.item(row, col)
        if not item:
            return
        raw = item.text().strip()
        try:
            val = int(raw)
            if val < 0:
                raise ValueError("0 이상이어야 합니다")
        except ValueError:
            worker.processTable.blockSignals(True)
            p = next(
                (x for x in _classify_processes if x.get("process_id") == pid), None
            )
            old = (
                p.get("success_1l_qty", 0)
                if col == 5
                else (
                    p.get("success_2l_qty", 0)
                    if col == 6
                    else p.get("unclassified_qty", 0)
                )
            )
            item.setText(str(old))
            worker.processTable.blockSignals(False)
            worker.classifyResultLabel.setText(
                "1L, 2L, 미분류에는 0 이상의 숫자만 입력하세요."
            )
            return
        p = next((x for x in _classify_processes if x.get("process_id") == pid), None)
        if not p:
            return

        def _cell_int(r: int, c: int) -> int:
            it = worker.processTable.item(r, c)
            if not it:
                return 0
            try:
                return int((it.text() or "0").strip())
            except ValueError:
                return 0

        new_1l = val if col == 5 else _cell_int(row, 5)
        new_2l = val if col == 6 else _cell_int(row, 6)
        new_uncl = val if col == 7 else _cell_int(row, 7)
        order_total = p.get("order_total_qty")
        if order_total is not None and (new_1l + new_2l + new_uncl) > order_total:
            worker.processTable.blockSignals(True)
            old = (
                p.get("success_1l_qty", 0)
                if col == 5
                else (
                    p.get("success_2l_qty", 0)
                    if col == 6
                    else p.get("unclassified_qty", 0)
                )
            )
            item.setText(str(old))
            worker.processTable.blockSignals(False)
            worker.classifyResultLabel.setText(
                f"1L+2L+미분류 합계({new_1l + new_2l + new_uncl})가 해당 주문 총 수량({order_total})을 초과할 수 없습니다."
            )
            return

        field = {5: "success_1l_qty", 6: "success_2l_qty", 7: "unclassified_qty"}[col]
        try:
            process_update(int(pid), **{field: val})
            for x in _classify_processes:
                if x.get("process_id") == pid:
                    x[field] = val
                    break
            worker.classifyResultLabel.setText("수량이 저장되었습니다.")
        except (RuntimeError, TimeoutError, OSError, ConnectionError) as e:
            worker.processTable.blockSignals(True)
            p = next(
                (x for x in _classify_processes if x.get("process_id") == pid), None
            )
            old = (
                p.get("success_1l_qty", 0)
                if col == 5
                else (
                    p.get("success_2l_qty", 0)
                    if col == 6
                    else p.get("unclassified_qty", 0)
                )
            )
            item.setText(str(old))
            worker.processTable.blockSignals(False)
            msg = (
                f"저장 실패: {e}"
                if isinstance(e, RuntimeError)
                else f"서버 연결 실패.\n{e!s}"
            )
            worker.classifyResultLabel.setText(msg)

    worker.processTable.itemChanged.connect(
        lambda item: on_classify_cell_changed(item.row(), item.column())
    )

    # ── 화면 복원 ────────────────────────────────────────────────
    def _restore_classify_monitor():
        if not _controller.is_active:
            return
        pid = _controller.current_pid
        p = next((x for x in _classify_processes if x.get("process_id") == pid), None)
        if p and (p.get("status") or "").upper() == "RUNNING":
            _update_process_state("RUNNING")
            _start_udp_camera()
            logger.info("[복원] 분류 화면 복귀 → 공정 #%s RUNNING 상태 복원", pid)

    return (
        _controller,
        _refresh_classify_list,
        _refresh_warehouse_chart,
        _restore_classify_monitor,
        _stop_udp_camera,
    )
