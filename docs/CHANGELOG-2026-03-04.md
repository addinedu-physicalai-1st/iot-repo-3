# 변경 이력 — 2026-03-04

> **작성 기준**: 2026-03-04 작업 세션 전체 (soy-pc 리팩토링 + 하드웨어 FSM 확장)  
> **최종 갱신**: 2026-03-04

---

## 목차

1. [soy-pc 아키텍처 리팩토링](#1-soy-pc-아키텍처-리팩토링)
2. [ProcessController 신규 설계](#2-processcontroller-신규-설계)
3. [worker 서브패키지 분리](#3-worker-서브패키지-분리)
4. [ESP32-DevKit FSM 확장 — PAUSED 상태](#4-esp32-devkit-fsm-확장--paused-상태)
5. [ESP32-CAM — 펌웨어 명령어 동기화](#5-esp32-cam--펌웨어-명령어-동기화)
6. [QR 인식률 개선 및 카메라 영상 보정](#6-qr-인식률-개선-및-카메라-영상-보정)
7. [버그 수정](#7-버그-수정)
8. [프로젝트 구조 정비](#8-프로젝트-구조-정비)
9. [변경된 MQTT 명세](#9-변경된-mqtt-명세)

---

## 1. soy-pc 아키텍처 리팩토링

### 배경

기존 `worker_screen.py` 1개 파일(1,202줄)에 UI·비즈니스 로직·스레드·MQTT·DB 코드가 모두 혼재.  
OOP 설계 원칙에 따라 관심사를 분리하고, 파일 단위 역할을 명확화했다.

### Before / After

| | Before | After |
|---|--------|-------|
| 구조 | `features/worker_screen.py` 1파일 (1,202줄) | `features/worker/` 서브패키지 6파일 |
| 비즈니스 로직 | UI 콜백 내부 인라인 | `ProcessController` 클래스로 분리 |
| MQTT 발행 위치 | `worker_screen.py` 내 직접 발행 | `ProcessController` 내부에서만 발행 |
| DB 업데이트 | UI 이벤트 핸들러 내 직접 호출 | `ProcessController._handle_sort_result()` |
| 공정 Queue | 모듈 수준 변수 | `ProcessState.sort_queue (deque)` |

---

## 2. ProcessController 신규 설계

**파일**: `soy-pc/features/worker/process_controller.py` (신규, 332줄)

### 구조 개요

```
process_controller.py
├── FsmState(str, Enum)          — ESP32 FSM 상태 (IDLE / RUNNING / SORTING / PAUSED)
├── SortDirection(str, Enum)     — 분류 방향 (1L / 2L / WARN)
├── SensorEvent(str, Enum)       — device/sensor 이벤트 6종
├── ProcessCallbacks(Protocol)   — UI 레이어가 구현할 콜백 인터페이스 (13개 메서드)
├── ProcessState(dataclass)      — 공정 실시간 상태 (pid / order_items / sort_queue)
└── ProcessController            — 비즈니스 로직 전담 클래스
```

### ProcessController 공개 API

| 메서드 | 설명 |
|--------|------|
| `start(process_data)` | 공정 시작 — `process_start` API 호출 + `SORT_START` MQTT 발행 |
| `pause()` | 일시정지 — `SORT_PAUSE` MQTT 발행 (DB 상태 RUNNING 유지) |
| `resume()` | 재개 — `SORT_RESUME` MQTT 발행 |
| `stop(pid?)` | 중지 — `process_stop` API 호출 + `SORT_STOP` MQTT 발행 |
| `handle_status(payload)` | `device/status` 수신 → FSM 상태 콜백 + Watchdog |
| `handle_sensor(payload, processes)` | `device/sensor` 수신 → 분류 결과 DB 업데이트 + 자동 완료 판단 |
| `handle_qr(item_code)` | QR 인식 결과 → `sort_queue`에 방향 enqueue |
| `is_active` (property) | 공정 진행 중 여부 |
| `current_pid` (property) | 현재 공정 ID |

### ProcessCallbacks 인터페이스

```python
class ProcessCallbacks(Protocol):
    def on_fsm_state_changed(self, state: FsmState) -> None: ...
    def on_proximity(self, detected: bool) -> None: ...
    def on_detected(self, direction: str, queue_size: int) -> None: ...
    def on_sort_result(self, kind: str, new_qty: int, db_ok: bool) -> None: ...
    def on_unclassified(self, new_qty: int, db_ok: bool) -> None: ...
    def on_process_started(self, pid: int) -> None: ...
    def on_process_paused(self) -> None: ...
    def on_process_resumed(self) -> None: ...
    def on_process_stopped(self, pid: int) -> None: ...
    def on_process_completed(self, pid, sorted_total, order_total) -> None: ...
    def on_qr_enqueued(self, item_code, direction, queue_size) -> None: ...
    def on_qr_error(self, message: str) -> None: ...
    def on_error(self, message: str) -> None: ...
```

### SORT_DIR Queue 알고리즘

```
QR 인식 → handle_qr(item_code)
    └─ _resolve_direction() → item_code 접미사(_1l/_2l) 기반 방향 결정
    └─ sort_queue.append(direction)

ESP32 S1/S2 센서 감지 → DETECTED → handle_sensor()
    └─ _handle_detected()
        ├─ sort_queue가 있으면: popleft() → SORT_DIR:{방향} 발행
        └─ 큐가 비었으면:        SORT_DIR:WARN 발행 (경고 처리)
```

---

## 3. worker 서브패키지 분리

**경로**: `soy-pc/features/worker/`

| 파일 | 줄 수 | 역할 |
|------|-------|------|
| `__init__.py` | 5 | `setup_worker_screen` re-export |
| `screen.py` | 218 | 메뉴 라우팅 + 입고 페이지 + 페이지 조립 |
| `threads.py` | 242 | `UdpCameraThread`, `CameraQRThread`, `MqttSignalBridge` |
| `inbound_dialog.py` | 157 | `InboundScanDialog` + `parse_qr_payload()` |
| `classify_page.py` | 600+ | 분류 모니터 UI + 공정 테이블 + 창고 차트 + 버튼 상태 |
| `process_controller.py` | 332 | 비즈니스 로직 전담 |

**`main.py` import 변경:**

```python
# Before
from features.worker_screen import setup_worker_screen

# After
from features.worker import setup_worker_screen
```

---

## 4. ESP32-DevKit FSM 확장 — PAUSED 상태

### 상태 전이도

```
IDLE ──[SORT_START]──► RUNNING ──[DETECTED]──► SORTING
  ▲                       │   ◄──[완료]──────────┘
  │                       │
  │              [SORT_PAUSE]
  │                       ▼
  │                    PAUSED
  │              [SORT_RESUME]
  │                       │
  └──[SORT_STOP]──────────┘
```

### 버튼 → MQTT 명령 → ESP32 동작

| 버튼 | MQTT 명령 | ESP32 동작 | DB 상태 |
|------|-----------|-----------|---------|
| 시작 | `SORT_START` | DC 모터 구동, RUNNING 진입 | RUNNING |
| 일시정지 | `SORT_PAUSE` | DC brake, PAUSED 진입 | RUNNING (유지) |
| 재개 | `SORT_RESUME` | DC 재구동, RUNNING 복귀 | RUNNING |
| 중지 | `SORT_STOP` | DC 정지, IDLE 복귀 | COMPLETED |

### 수정 파일 목록

#### ESP32-DevKit (`soy-controller/esp32-devkit/src/`)

| 파일 | 변경 내용 |
|------|----------|
| `fsm.h` | `State` enum에 `PAUSED` 추가 |
| `fsm.cpp` | `stateName()`에 `"PAUSED"` 매핑 추가 |
| `command.h` | `CommandType`에 `SORT_PAUSE`, `SORT_RESUME` 추가 |
| `command.cpp` | `"SORT_PAUSE"`, `"SORT_RESUME"` 문자열 파싱 추가 |
| `main.cpp` | `enterState(PAUSED)`: DC brake + MQTT `"PAUSED"` 발행 |
| | `onCommand()`: RUNNING→PAUSED, PAUSED→RUNNING 전이 (SORTING 중 PAUSE 무시) |
| | `handleConfirmSensors()`: `IDLE \|\| PAUSED` 상태에서 센서 이벤트 무시 |
| `peripheral/rgb_led.cpp` | `forState()`에 `PAUSED → yellow()` 추가 |

#### soy-pc (`soy-pc/features/worker/`)

| 파일 | 변경 내용 |
|------|----------|
| `process_controller.py` | `FsmState.PAUSED` 추가 |
| | `pause()`, `resume()` 메서드 추가 |
| | `ProcessCallbacks`에 `on_process_paused()`, `on_process_resumed()` 추가 |
| | `handle_status()`: PAUSED 상태에서 Watchdog 비활성화 |
| `classify_page.py` | FSM 배지에 `PAUSED` (일시정지, 노랑) 추가 |
| | `_update_buttons()`: FSM 상태별 버튼 활성화 로직 구현 |
| | 토글 버튼 1개 → 시작 / 일시정지(재개) / 중지 3개 핸들러 분리 |
| UI (`worker_screen.ui`) | `classifyToggleButton` → `classifyStartButton` + `classifyPauseButton` + `classifyStopButton` |

---

## 5. ESP32-CAM — 펌웨어 명령어 동기화

### 문제

구 펌웨어가 `DC_START` 명령을 기다리고 있었으나, soy-pc는 `SORT_START`를 발행.  
업데이트된 소스코드(`SORT_START` 처리)가 보드에 업로드되지 않아 카메라가 스트리밍을 시작하지 않는 문제.

**수정**: `esp32-cam/src/net/mqtt_manager.cpp`는 이미 `SORT_START` / `SORT_STOP`을 처리하도록 작성되어 있음.  
**조치**: ESP32-CAM 보드에 펌웨어 재업로드 필요 (`pio run --target upload`).

---

## 6. QR 인식률 개선 및 카메라 영상 보정

### QR 인식률 개선

**파일**: `threads.py` — `_try_decode_qr()` 함수 추가

```
1차: 원본 프레임 → pyzbar.decode()
2차: 90°, 180°, 270° 회전 → 각각 pyzbar.decode()
3차: 그레이스케일 + 적응적 이진화(adaptiveThreshold) → pyzbar.decode()
```

- 성공 시 즉시 반환 (이후 단계 건너뜀)
- 최악의 경우 6회 decode — 320×240 해상도에서 성능 문제 없음

### 카메라 영상 보정

| | Before | After |
|---|--------|-------|
| ESP32-CAM 하드웨어 | `set_vflip(s, 1)` ON | 그대로 유지 |
| soy-pc Python | `cv2.flip(frame, 0)` 추가 적용 | **제거** (이중 반전 해소) |

**결과**: 하드웨어 레벨에서 방향 보정 → Python 측 불필요한 연산 제거

---

## 7. 버그 수정

### 7.1 앱 재시작 후 공정 중지 불가

**증상**: 앱 재시작 시 DB에 RUNNING 공정이 있어도 "중지" 버튼이 동작하지 않음

**원인**: `ProcessController.stop()`이 `self._state.process_id`가 `None`이면 즉시 반환.  
재시작 후 컨트롤러 내부 상태가 초기화되어 있어 pid를 알 수 없는 상태.

**수정**:
```python
# Before
def stop(self) -> None:
    pid = self._state.process_id
    if pid is None:
        return  # 재시작 후 항상 여기서 종료됨

# After
def stop(self, pid: int | None = None) -> None:
    target_pid = pid or self._state.process_id
    if target_pid is None:
        return
```

`classify_page.py`에서 테이블 선택 pid를 직접 `stop(int(pid))`로 전달.

### 7.2 앱 재시작 후 버튼 비활성화 문제

**증상**: 앱 재시작 후 DB에 RUNNING 공정이 있어도 시작/중지 버튼 모두 비활성화

**원인**: `_update_buttons()`가 `_controller.is_active`만 확인. 재시작 후 컨트롤러 비활성 상태 → 모든 버튼 비활성화

**수정** (`classify_page.py`):  
`is_active`가 False여도, 선택 공정이 DB RUNNING이면 시작·중지 버튼 활성화.

### 7.3 분류 화면 이탈 후 복귀 시 상태 초기화 문제

**증상**: 분류하기 화면에서 다른 화면으로 이동 후 돌아오면 FSM 상태가 "대기"로 리셋

**수정** (`classify_page.py`):
```python
def _restore_classify_monitor():
    if not _controller.is_active:
        return
    pid = _controller.current_pid
    p = next((x for x in _classify_processes if x.get("process_id") == pid), None)
    if p and (p.get("status") or "").upper() == "RUNNING":
        _update_fsm_display("RUNNING")
        _start_udp_camera()
```

`stack.currentChanged` 시그널에서 분류 페이지(index=3) 복귀 시 `_restore_classify_monitor()` 호출.

### 7.4 UDP 전송 에러 (참고)

```
[E][WiFiUdp.cpp:185] endPacket(): could not send data: 12
```

- 에러 코드 12 = `ENOMEM` (lwIP 전송 버퍼 부족)
- 프레임 전송 속도 > 네트워크 처리 속도일 때 발생
- UDP 특성상 다음 프레임이 즉시 전송되므로 체감 영향 없음
- 필요 시 `config.h`의 `FRAME_INTERVAL_MS` 값을 늘려 속도 조절

---

## 8. 프로젝트 구조 정비

### 8.1 esp-common 제거

**배경**: `esp-common` 공유 패키지에 `wifi_manager`와 `config_mqtt.h` 2개만 존재.  
두 보드의 역할이 완전히 달라 공유 필요성이 낮고, `lib_deps = file://` 상대경로 방식의 취약성.

**조치**:
- `wifi_manager.h/.cpp`, `esp/config_mqtt.h`를 각 프로젝트 `src/` 안으로 이동
- `esp-common/` 폴더 삭제
- 두 `platformio.ini`에서 `lib_deps = file://../esp-common`, `-I../esp-common` 제거

**변경 후 구조**:

```
soy-controller/
├── esp32-devkit/src/
│   ├── esp/config_mqtt.h      ← 이동됨
│   ├── net/wifi_manager.h     ← 이동됨
│   └── net/wifi_manager.cpp   ← 이동됨
├── esp32-cam/src/
│   ├── esp/config_mqtt.h      ← 이동됨
│   ├── net/wifi_manager.h     ← 이동됨
│   └── net/wifi_manager.cpp   ← 이동됨
└── (esp-common/ 삭제)
```

### 8.2 lib_deps 정책 변경

외부 라이브러리(PubSubClient, ESP32Servo 등)는 `lib_deps`에 선언하지 않고,  
각 프로젝트의 `lib/` 폴더에 사용자가 직접 배치.

```
esp32-devkit/
└── lib/
    ├── PubSubClient/      ← 직접 추가
    └── ESP32Servo/        ← 직접 추가
```

---

## 9. 변경된 MQTT 명세

> **기존 `protocol_specification.md`** 및 **`api_specification.md`** 에서 변경된 부분만 기술.

### 9.1 `device/control` 토픽 — 명령어 추가

| 메시지 | 포맷 | 설명 | 처리 주체 | **신규** |
|--------|------|------|-----------|------|
| `SORT_START` | 문자열 | 분류 시작 (DC·카메라 구동) | DevKit + CAM | |
| `SORT_STOP` | 문자열 | 분류 종료 (DC·카메라 정지) | DevKit + CAM | |
| `SORT_PAUSE` | 문자열 | 일시정지 (DC brake, 카메라 유지) | DevKit | ✅ 신규 |
| `SORT_RESUME` | 문자열 | 일시정지 해제 (DC 재구동) | DevKit | ✅ 신규 |
| `SORT_DIR:{방향}` | 문자열 | 분류 방향 지시 | DevKit | ✅ 신규 |

> `{방향}` 값: `1L` / `2L` / `WARN`

### 9.2 `device/status` 토픽 — 상태 추가

| 메시지 | 포맷 | 설명 | **신규** |
|--------|------|------|------|
| `{"state":"IDLE"}` | JSON | 대기 상태 | |
| `{"state":"RUNNING"}` | JSON | 공정 진행 중 | |
| `{"state":"SORTING"}` | JSON | 분류 동작 중 | |
| `{"state":"WARNING"}` | JSON | 미등록 QR 경고 | |
| `{"state":"PAUSED"}` | JSON | 일시정지 | ✅ 신규 |

> **Watchdog 동작 변경**: `PAUSED` 상태에서는 Watchdog의 `SORT_START` 재전송 비활성화

### 9.3 구독/발행 맵 (전체)

```
┌──────────────────────────────────────────────────────────────────┐
│ soy-pc (paho-mqtt, Client ID: "soy-pc")                          │
│   Pub  → device/control  (SORT_START / SORT_STOP /               │
│                            SORT_PAUSE / SORT_RESUME /            │
│                            SORT_DIR:{1L|2L|WARN})                │
│   Sub  ← device/sensor                                           │
│   Sub  ← device/status                                           │
├──────────────────────────────────────────────────────────────────┤
│ ESP32-DevKit (PubSubClient, ID: "SoyDevKit-xxxx")                │
│   Sub  ← device/control                                          │
│   Pub  → device/sensor   (PROXIMITY:* / DETECTED /               │
│                            SORTED_1L / SORTED_2L /               │
│                            SORTED_UNCLASSIFIED)                  │
│   Pub  → device/status   (IDLE / RUNNING / SORTING /             │
│                            PAUSED / WARNING)                     │
├──────────────────────────────────────────────────────────────────┤
│ ESP32-CAM (PubSubClient, ID: "SoyCam-xxxx")                      │
│   Sub  ← device/control  (SORT_START → UDP ON, SORT_STOP → OFF)  │
└──────────────────────────────────────────────────────────────────┘
```
