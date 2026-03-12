# 변경 이력 — 2026-03-04

## 개요

일시정지 기능 추가, 카메라 영상 보정, QR 코드 인식률 개선 작업을 수행했다.

---

## 1. 일시정지/중지 버튼 분리

기존 "시작/중지" 토글 버튼 1개를 **시작**, **일시정지/재개**, **중지** 3개 버튼으로 분리했다.

### 동작 방식

| 버튼 | 동작 | ESP32 상태 | DB 상태 |
|------|------|-----------|---------|
| 시작 | DC 모터 구동, 분류 시작 | RUNNING | RUNNING |
| 일시정지 | DC 모터 정지, 분류 정지, 카메라 유지 | PAUSED | RUNNING (유지) |
| 재개 | DC 모터 재구동, 분류 재개 | RUNNING | RUNNING |
| 중지 | 공정 종료, 상태 초기화 | IDLE | COMPLETED |

### 수정 파일

#### ESP32 펌웨어 (`soy-controller/esp32-devkit/`)

| 파일 | 변경 내용 |
|------|----------|
| `src/fsm.h` | `State` enum에 `PAUSED` 추가, FSM 다이어그램 업데이트 |
| `src/fsm.cpp` | `stateName()`에 `PAUSED` → `"PAUSED"` 매핑 추가 |
| `src/command.h` | `CommandType`에 `SORT_PAUSE`, `SORT_RESUME` 추가 |
| `src/command.cpp` | `"SORT_PAUSE"`, `"SORT_RESUME"` 문자열 파싱 추가 |
| `src/main.cpp` | `enterState(PAUSED)`: DC brake + MQTT `"PAUSED"` 발행 |
| | `onCommand()`: `SORT_PAUSE` → RUNNING에서만 PAUSED 전이, `SORT_RESUME` → PAUSED에서만 RUNNING 전이 (SORTING 중 무시) |
| | `handleConfirmSensors()`: PAUSED 상태에서 센서 이벤트 무시 |
| `src/peripheral/rgb_led.h` | 헤더 주석에 PAUSED 색상(노랑) 추가 |
| `src/peripheral/rgb_led.cpp` | `forState()`에 `PAUSED → yellow()` 추가 |

#### Python PC (`soy-pc/`)

| 파일 | 변경 내용 |
|------|----------|
| `features/worker/process_controller.py` | `FsmState.PAUSED` 추가 |
| | `pause()`: MQTT `"SORT_PAUSE"` 발행 (DB 미변경) |
| | `resume()`: MQTT `"SORT_RESUME"` 발행 |
| | `ProcessCallbacks`에 `on_process_paused()`, `on_process_resumed()` 추가 |
| | `handle_status()`: PAUSED 상태에서 Watchdog SORT_START 재전송 비활성화 |
| `ui/worker_screen.ui` | `classifyToggleButton` → `classifyStartButton` + `classifyPauseButton` + `classifyStopButton` 3개로 분리 |
| `features/worker/classify_page.py` | FSM 상태 표시에 `PAUSED` (일시정지, 노랑) 추가 |
| | `_update_buttons()`: FSM 상태별 버튼 활성화 로직 구현 |
| | 시작/일시정지(재개)/중지 별도 클릭 핸들러 분리 |
| | 앱 재시작 시 DB RUNNING 공정 있으면 시작/중지 버튼 활성화 (컨트롤러 비활성 상태 대응) |

---

## 2. 카메라 영상 보정

### 변경 전 상태
- ESP32-CAM: `set_vflip(s, 1)` (수직 반전 ON)
- Python: `cv2.flip(frame, 0)` (수직 반전) — 두 번 반전이 서로 상쇄

### 변경 내용

| 파일 | 변경 |
|------|------|
| `soy-controller/esp32-cam/src/stream/camera_capture.cpp` | `set_vflip(s, 1)` 유지 (좌우 반전은 필요 시 `set_hmirror(s, 1)` 추가) |
| `soy-pc/features/worker/threads.py` | `cv2.flip(frame, 0)` 제거 — 하드웨어에서 처리하므로 소프트웨어 flip 불필요 |

### 결과
- ESP32-CAM 하드웨어 레벨에서 영상 방향 보정
- Python 측 불필요한 프레임 변환 제거로 성능 개선

---

## 3. QR 코드 인식률 개선

### 문제
- `pyzbar.decode(frame)` 1회만 호출 → 회전된 QR코드 인식 실패
- 저해상도(320x240) + JPEG 압축 아티팩트로 인식 한계

### 해결

`soy-pc/features/worker/threads.py`에 `_try_decode_qr()` 함수 추가:

```
1차: 원본 프레임 → pyzbar.decode()
2차: 90°, 180°, 270° 회전 → 각각 pyzbar.decode()
3차: 그레이스케일 + 적응적 이진화(adaptiveThreshold) → pyzbar.decode()
```

- 성공 시 즉시 반환 (오버헤드 없음)
- 최악의 경우 6회 decode — 320x240 해상도에서 충분히 빠름

---

## 4. 버그 수정

### 앱 재시작 시 버튼 비활성화 문제

**증상**: 앱 재시작 후 DB에 RUNNING 공정이 있지만, `ProcessController`가 비활성 상태라 시작/중지 버튼 모두 비활성화됨

**원인**: `_update_buttons()`가 `_controller.is_active`만 확인하여 컨트롤러 비활성 시 모든 버튼 비활성화

**수정** (`classify_page.py`):
- `_update_buttons()` else 분기에서 선택된 공정이 DB RUNNING이면 시작/중지 버튼 활성화
- `_on_stop_clicked()`에서 테이블 선택 pid를 `_controller.stop()`에 전달

---

## 참고: ESP32-CAM UDP 전송 에러

```
[E][WiFiUdp.cpp:185] endPacket(): could not send data: 12
```

- 에러 코드 12 = `ENOMEM` (ESP32 내부 lwIP 전송 버퍼 부족)
- 프레임 전송 속도 > 네트워크 처리 속도일 때 발생
- UDP 특성상 패킷 드롭되어도 다음 프레임이 즉시 전송되므로 영상에 체감 영향 없음
- 필요 시 `FRAME_INTERVAL_MS` 값을 늘려 전송 속도 조절 가능
