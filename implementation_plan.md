# IoT 컨베이어 벨트 분류 시스템 구현 계획 (docs 반영)

## 배경 및 현황

- DB에 [processes](file:///home/hajun/dev_ws/iot_pj/system/soy-pc/api/client.py#399-405) 1건 등록: `process_id=1`, `status='WAITING'`, `order_id=1`
- `order_id=1` 품목: 샘표 진간장 1L, 샘표 국간장 1L, 몽고 진간장 2L

---

## 📋 docs 검토 결과 — 발견된 불일치 및 추가 필요 사항

| # | 문서 | 발견 사항 | 조치 |
|---|------|-----------|------|
| 1 | [er-diagram.md](file:///home/hajun/dev_ws/iot_pj/system/docs/er-diagram.md) | `processes.status` 허용값이 `NOT_STARTED/RUNNING/PAUSED/COMPLETED/ERROR`인데 시드(013)에서 `WAITING` 사용 중 | DB 시드 수정 + 서비스 코드 상수 정렬 |
| 2 | [er-diagram.md](file:///home/hajun/dev_ws/iot_pj/system/docs/er-diagram.md) | `ITEM_SORTING_LOGS`, `ALERTS` 테이블이 설계에 있으나 마이그레이션 미구현 | 마이그레이션 014, 015 추가 |
| 3 | [soy-kit-protocol.md](file:///home/hajun/dev_ws/iot_pj/system/docs/soy-kit-protocol.md) | UDP 헤더 스펙: **고정 24바이트** (width 2B + height 2B + frame_id 4B + camera_id 16B) + JPEG — 현재 ESP32-Cam 구현(IMG 청크 분할)과 완전 불일치 | ESP32-Cam 펌웨어 UDP 포맷 수정 |
| 4 | [soy-kit-protocol.md](file:///home/hajun/dev_ws/iot_pj/system/docs/soy-kit-protocol.md) | 문서에 MQTT 프로토콜 없음 — IoT 제어용으로 **새로 추가** 필요 | 프로토콜 문서 보완 + 구현 |
| 5 | [system-requirements.md](file:///home/hajun/dev_ws/iot_pj/system/docs/system-requirements.md) | S-09(자가진단), S-15(실시간 오류 감지), S-19(경고 알림) 미구현 | ESP32 FSM + ALERTS DB + PC 알림 |

---

## 하드웨어 구성

| 장치 | 핀 | 용도 |
|------|----|------|
| DC 모터 (A4950) IN1 | GPIO 27 | HIGH 고정 |
| DC 모터 (A4950) IN2 | GPIO 13 | PWM 속도 제어 |
| 서보 모터 (1개) | GPIO 32 | 분류기 (1L/2L) |
| 근접 센서 | GPIO 34 | 물체 감지 (INPUT_ONLY) |
| RGB LED R | GPIO 25 | 상태 Red |
| RGB LED G | GPIO 26 | 상태 Green |
| RGB LED B | GPIO 4 | 상태 Blue |

> [!IMPORTANT]
> **RGB LED 핀 (R=25, G=26, B=4)** 및 **서보 핀(32)**: 실제 배선과 다르면 알려주세요.

---

## MQTT 토픽 설계 (신규 프로토콜)

| 토픽 | 방향 | 페이로드 |
|------|------|---------|
| `device/control` | PC → DevKit | `DC_START:<speed>`, `DC_STOP`, `SORT_1L`, `SORT_2L`, `SORT_UNCLASSIFIED` |
| `device/sensor` | DevKit → PC | `DETECTED`, `SORTED_1L`, `SORTED_2L`, `SORTED_UNCLASSIFIED` |
| `device/status` | DevKit → PC | `{"state":"RUNNING","process_id":1}` |

---

## FSM 설계 (ESP32-DevKit)

```
[IDLE] ─(DC_START)→ [RUNNING] ─(센서)→ [SENSOR_DETECTED]
  ↑                     ↑                      │
  └──(DC_STOP)──────────┴──(분류완료)── [SORTING]
```

**상태별 RGB LED**: IDLE=🔴, RUNNING=🟢, SENSOR_DETECTED=🟡, SORTING=🔵, ERROR=🔴 점멸

**S-09 자가진단** (setup() 마지막): DC → 서보 → LED RGB 순차 → MQTT `SELF_TEST_OK`

---

## Proposed Changes

---

### 1. DB 마이그레이션

#### [MODIFY] [013_seed_processes.py](file:///home/hajun/dev_ws/iot_pj/system/soy-server/alembic/versions/013_seed_processes.py)
- `'WAITING'` → `'NOT_STARTED'` (ER 다이어그램 스펙 준수)

#### [NEW] 014_create_item_sorting_logs.py
- `item_sorting_logs` 테이블: `log_id PK`, `process_id FK`, `box_qr_code`, `item_code FK`, `sorted_inventory`, `is_error`, `timestamp`

#### [NEW] 015_create_alerts.py
- `alerts` 테이블: `alert_id PK`, `process_id FK`, `alert_type`, `message`, `created_at`

---

### 2. soy-server — 모델 및 서비스 보완

#### [MODIFY] [models/__init__.py](file:///home/hajun/dev_ws/iot_pj/system/soy-server/app/models/__init__.py)
- `ItemSortingLog`, `Alert` ORM 모델 추가

#### [MODIFY] [processes.py (services)](file:///home/hajun/dev_ws/iot_pj/system/soy-server/app/services/processes.py)
- `WAITING` 상수 제거, `NOT_STARTED` 추가
- `log_sorting_event(process_id, item_code, sorted_inventory, is_error)`: `item_sorting_logs` 기록
- `create_alert(process_id, alert_type, message)`: `alerts` 기록

#### [MODIFY] [requests/processes.py](file:///home/hajun/dev_ws/iot_pj/system/soy-server/app/requests/processes.py)
- `log_sorting` 액션 추가 (PC → 서버 TCP로 분류 로그 저장 요청)

---

### 3. ESP32-Cam 펌웨어 — UDP 프로토콜 수정

#### [MODIFY] [esp32-cam/src/main.cpp](file:///home/hajun/dev_ws/iot_pj/system/soy-controller/esp32-cam/src/main.cpp)
- **현재**: `IMG` 헤더 + 청크 분할 (프로토콜 문서 불일치)
- **변경**: 고정 24바이트 헤더 (`width` 2B + `height` 2B + `frame_id` 4B + `camera_id` 16B, Big-Endian) + JPEG 단일 UDP 패킷
- 해상도: `FRAMESIZE_QQVGA` (160×120) — MTU 1500B 제한 고려

---

### 4. ESP32-DevKit 펌웨어 — FSM 완전 재작성

#### [MODIFY] [esp32-devkit/src/main.cpp](file:///home/hajun/dev_ws/iot_pj/system/soy-controller/esp32-devkit/src/main.cpp)

구조체/enum 아키텍처:
```cpp
struct ConveyorConfig { int dc_in1, dc_in2, servo_pin, sensor_pin, led_r, led_g, led_b; };
struct DcMotor { ... };
struct ServoCtrl { ... };       // MCPWM, 단일 서보
struct ProximitySensor { ... }; // debounce 포함
struct RgbLed { ... };
enum class ConveyorState { IDLE, SELF_TEST, RUNNING, SENSOR_DETECTED, SORTING, ERROR };
```

---

### 5. soy-pc — MQTT 클라이언트 및 GUI 연동

#### [NEW] [mqtt_client.py](file:///home/hajun/dev_ws/iot_pj/system/soy-pc/mqtt_client.py)
- `paho-mqtt` 싱글톤, `connect/disconnect/publish/subscribe`

#### [MODIFY] [worker_screen.py](file:///home/hajun/dev_ws/iot_pj/system/soy-pc/features/worker_screen.py)
- 공정 시작/중지 → TCP + MQTT `DC_START:200`/`DC_STOP` 동시 발행
- QR 스캔 완료 → MQTT `SORT_1L/2L/UNCLASSIFIED` + API [process_update](file:///home/hajun/dev_ws/iot_pj/system/soy-pc/api/client.py#423-442) + TCP `log_sorting`
- `SORT_UNCLASSIFIED` 발행 시 GUI 경고 알림 (S-19)

#### [MODIFY] [main.py](file:///home/hajun/dev_ws/iot_pj/system/soy-pc/main.py)
- 앱 시작/종료 시 MQTT 연결/해제

---

### 6. 인프라 및 문서

#### [MODIFY] [docker-compose.yml](file:///home/hajun/dev_ws/iot_pj/system/docker-compose.yml)
- `mosquitto` 서비스 추가 (포트 1883)

#### [MODIFY] [soy-kit-protocol.md](file:///home/hajun/dev_ws/iot_pj/system/docs/soy-kit-protocol.md)
- `5. MQTT 프로토콜` 섹션 추가

---

## Verification Plan

| 단계 | 동작 | 기대 결과 |
|------|------|-----------|
| 1 | `docker compose up -d` | MQTT 브로커 1883 포트 개방 |
| 2 | ESP32-DevKit 전원 | 자가진단(S-09): LED RGB 순차, MQTT `SELF_TEST_OK` |
| 3 | GUI → 공정 시작 | DB `RUNNING`, MQTT `DC_START:200`, LED 🟢 |
| 4 | 근접 센서 앞 물체 | MQTT `DETECTED`, LED 🟡, DC 정지 |
| 5 | `sampyo_jin_1l` QR 스캔 | MQTT `SORT_1L`, 서보 동작, DB `success_1l_qty`+1, `item_sorting_logs` 기록 |
| 6 | QR 없는 물체 | MQTT `SORT_UNCLASSIFIED`, `alerts` 기록, GUI 경고(S-19) |
| 7 | GUI → 공정 중지 | DB `PAUSED`, MQTT `DC_STOP`, LED 🔴 |
| 8 | ESP32-Cam UDP | 24바이트 헤더 + JPEG 1패킷 수신 확인 |
