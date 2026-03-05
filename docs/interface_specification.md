## SoyAdminUI

관리자용 PC UI(관리자 화면, SoyAdminUI)가 다른 서비스와 통신하는 인터페이스 명세입니다.

| 프로토콜 | 수신 | API 명 | 요청 (형식) | 응답 (형식) |
| :--- | :--- | :--- | :--- | :--- |
| TCP | SoyService | 관리자 로그인 | `{ "password": string }` | `{ "token": string, "admin_id": integer }` |
| TCP | SoyService | 관리자 로그아웃 | `{ "auth_token": string }` | `null` (성공 시), 또는 `{ "error": string }` |
| TCP | SoyService | 최초 관리자 등록 필요 여부 조회 | `{}` (비어 있음) | `{ "needs_password": boolean }` |
| TCP | SoyService | 최초 관리자 비밀번호 등록 | `{ "password": string }` | `null` (성공 시), 또는 `{ "error": string }` |
| TCP | SoyService | 주문 목록 조회 | `{}` (비어 있음) | `[{ "order_id": integer, "status": string, ... }, ...]` |
| TCP | SoyService | 주문 상세 조회 | `{ "order_id": integer }` | `{ "order_id": integer, "items": [ { ... }, ... ] }` |
| TCP | SoyService | 공정 목록 조회 | `{}` (비어 있음) | `[{ "process_id": integer, "order_id": integer, "status": string, "success_1l_qty": integer, "success_2l_qty": integer, "unclassified_qty": integer }, ...]` |
| TCP | SoyService | 공정 시작 | `{ "process_id": integer }` | `{ "process_id": integer, "order_id": integer, "status": string, "success_1l_qty": integer, "success_2l_qty": integer, "unclassified_qty": integer }` |
| TCP | SoyService | 공정 중지 | `{ "process_id": integer }` | `{ "process_id": integer, "order_id": integer, "status": string, "success_1l_qty": integer, "success_2l_qty": integer, "unclassified_qty": integer }` |
| TCP | SoyService | 분류 수량 갱신 | `{ "process_id": integer, "success_1l_qty"?: integer, "success_2l_qty"?: integer, "unclassified_qty"?: integer }` | `{ "process_id": integer, "order_id": integer, "status": string, "success_1l_qty": integer, "success_2l_qty": integer, "unclassified_qty": integer }` |
| TCP | SoyService | 작업자 목록 조회 | `{ "auth_token": string, "admin_id": integer }` | `[{ "worker_id": integer, "admin_id": integer, "name": string, "card_uid": string }, ...]` |
| TCP | SoyService | 작업자 등록 | `{ "auth_token": string, "admin_id": integer, "name": string, "card_uid": string }` | `{ "worker_id": integer, "admin_id": integer, "name": string, "card_uid": string }` 또는 `{ "error": string }` |
| TCP | SoyService | 작업자 정보 수정 | `{ "auth_token": string, "worker_id": integer, "name"?: string, "card_uid"?: string }` | `{ "worker_id": integer, "admin_id": integer, "name": string, "card_uid": string }` |
| TCP | SoyService | 작업자 삭제 | `{ "auth_token": string, "worker_id": integer }` | `null` (성공 시) 또는 `{ "error": string }` |
| TCP | SoyService | 출입 로그 조회 | `{ "auth_token": string, "limit"?: integer, "worker_name"?: string }` | `[{ "access_log_id": integer, "worker_id": integer, "worker_name": string, "direction": string, "checked_at": string }, ...]` |

---

## SoyWorkerUI

작업자용 PC UI(작업자 화면, SoyWorkerUI)가 다른 서비스와 통신하는 인터페이스 명세입니다.

| 프로토콜 | 수신 | API 명 | 요청 (형식) | 응답 (형식) |
| :--- | :--- | :--- | :--- | :--- |
| TCP | SoyService | 창고 재고 목록 조회 | `{}` (비어 있음) | `[{ "inventory_id": integer, "inventory_name": string, "current_qty": integer, "updated_at": string \| null }, ...]` |
| TCP | SoyService | 창고 재고 현황 통계 조회 | `{}` (비어 있음) | `[{ "brand": string, "category": string, "inventory_id": integer, "count": integer }, ...]` |
| TCP | SoyService | 주문 목록 조회 | `{}` (비어 있음) | `[{ "order_id": integer, "status": string, ... }, ...]` |
| TCP | SoyService | 주문 상세 조회 | `{ "order_id": integer }` | `{ "order_id": integer, "items": [ { ... }, ... ] }` |
| TCP | SoyService | 주문 입고 처리 | `{ "order_id": integer }` 또는 `{ "order_item_id": integer }` | `{ "order_id": integer, "process_id": integer }` |
| TCP | SoyService | 공정 목록 조회 | `{}` (비어 있음) | `[{ "process_id": integer, "order_id": integer, "status": string, "success_1l_qty": integer, "success_2l_qty": integer, "unclassified_qty": integer }, ...]` |
| TCP | SoyService | 공정 시작 | `{ "process_id": integer }` | `{ "process_id": integer, "order_id": integer, "status": string, "success_1l_qty": integer, "success_2l_qty": integer, "unclassified_qty": integer }` |
| TCP | SoyService | 공정 중지 | `{ "process_id": integer }` | `{ "process_id": integer, "order_id": integer, "status": string, "success_1l_qty": integer, "success_2l_qty": integer, "unclassified_qty": integer }` |
| TCP | SoyService | 분류 수량 갱신 | `{ "process_id": integer, "success_1l_qty"?: integer, "success_2l_qty"?: integer, "unclassified_qty"?: integer }` | `{ "process_id": integer, "order_id": integer, "status": string, "success_1l_qty": integer, "success_2l_qty": integer, "unclassified_qty": integer }` |

---

## Register Controller (RFID 키트)

작업자 카드 등록/인식을 담당하는 Arduino + RFID 키트입니다. SoyAdminUI로 카드 인식 이벤트를 전송합니다.

| 프로토콜 | 수신 | API 명 | 요청 (형식) | 응답 (형식) |
| :--- | :--- | :--- | :--- | :--- |
| Serial | SoyAdminUI | RFID 카드 인식 전송 | NDJSON 한 줄: `{ "type": "card_read", "source": "register_controller", "uid": string }` | 응답 없음 (SoyAdminUI에서 UID를 UI 상태로 반영) |

---

## Access Controller (출입제어 ESP32)

출입문에 부착된 RFID 리더에서 카드 인식 시, UID를 ManageService(출입제어 서버)로 전달하는 ESP32 기기입니다. ROS 토픽으로 발행합니다.

| 프로토콜 | 수신 | API 명 | 요청 (형식) | 응답 (형식) |
| :--- | :--- | :--- | :--- | :--- |
| ROS (토픽) | ManageService | 입구 카드 인식 발행 | 토픽 `/rfid_entrance_door`, payload `std_msgs/String` (UID 문자열) | 응답 없음 (ManageService가 구독 후 SoyService에 TCP 요청) |
| ROS (토픽) | ManageService | 출구 카드 인식 발행 | 토픽 `/rfid_exit_door`, payload `std_msgs/String` (UID 문자열) | 응답 없음 (ManageService가 구독 후 SoyService에 TCP 요청) |

---

## ManageService (출입제어 서버)

Access Controller(ESP32)가 ROS 토픽으로 보낸 RFID UID를 구독한 뒤, SoyService에 출입 검증·출입 로그 등록을 요청하는 ROS 노드(서버)입니다.

| 프로토콜 | 수신 | API 명 | 요청 (형식) | 응답 (형식) |
| :--- | :--- | :--- | :--- | :--- |
| TCP | SoyService | 출입구 작업자 UID 조회 및 출입 로그 등록 | `{ "card_uid": string, "direction": string }` | `{ "worker_id": integer, "admin_id": integer, "name": string, "card_uid": string }` (성공 시 출입 로그 생성) 또는 `{ "error": string }` |

---

## ESP32-DevKit

분류 라인의 DC 모터·센서·상태 관리를 담당하는 컨트롤러입니다. MQTT 브로커를 통해 SoyWorkerUI와 통신합니다.

| 프로토콜 | 수신 | API 명 | 요청 (형식) | 응답 (형식) |
| :--- | :--- | :--- | :--- | :--- |
| MQTT | MQTT Broker | 센서 이벤트 발행 | 토픽 `device/sensor`, payload 문자열 (`"PROXIMITY:1"`, `"PROXIMITY:0"`, `"DETECTED"`, `"SORTED_1L"`, `"SORTED_2L"`, `"SORTED_UNCLASSIFIED"`) | MQTT 프로토콜 상 응답 없음 (브로커가 구독자들에게 재전송) |
| MQTT | MQTT Broker | 상태 이벤트 발행 | 토픽 `device/status`, payload JSON `{ "state": string }` (`"IDLE"`, `"RUNNING"`, `"SORTING"`, `"PAUSED"`, `"WARNING"` 등) | MQTT 프로토콜 상 응답 없음 (브로커가 구독자들에게 재전송) |

---

## ESP32-CAM

분류 라인의 카메라 및 QR 인식을 담당하는 컨트롤러입니다. UDP로 영상 스트림을 전송합니다.

| 프로토콜 | 수신 | API 명 | 요청 (형식) | 응답 (형식) |
| :--- | :--- | :--- | :--- | :--- |
| UDP | SoyWorkerUI | 카메라 영상 스트림 발행 | UDP 패킷 payload: `b"IMG"` + 7바이트 헤더 + JPEG 청크 바이트 | 응답 없음 (SoyWorkerUI에서 수신·표시·QR 디코딩) |


---

## 공통 프로토콜 프레이밍 규칙

각 서비스가 TCP / UDP / Serial로 송신·수신할 때 **헤더를 어떻게 해석해서 어디까지를 하나의 메시지로 읽는지**를 정리합니다.

### TCP (SoyAdminUI / SoyWorkerUI ↔ SoyService, ManageService ↔ SoyService)

- **프레임 구조**:  
  \[4바이트 길이 헤더\] + \[payload (UTF-8 JSON)\]
- **길이 헤더**
  - 4바이트 **big-endian 부호 없는 정수(uint32)**.
  - 값 = **뒤에 따라오는 JSON payload의 바이트 수**.
- **송신 규칙**
  - 클라이언트/서버는 JSON 문자열을 UTF-8로 인코딩한 뒤, 길이를 계산해 4바이트 BE로 붙이고 `sendall` 합니다.
  - 하나의 TCP 프레임 = 하나의 JSON 메시지(`type: "request"` 또는 `type: "response"` 혹은 `type: "card_read"`).
- **수신 규칙**
  - 먼저 **정확히 4바이트**를 읽어 길이 헤더를 복원합니다.
  - 헤더에서 구한 길이 `N`만큼 **payload를 정확히 N바이트** 읽습니다.
  - 읽은 payload 바이트를 UTF-8로 디코딩 후 JSON으로 파싱합니다.
  - 길이가 0이거나, 미리 정한 최대 크기(예: 1MB)를 넘으면 해당 프레임은 무시/에러 처리합니다.

이 규칙을 통해 **바이트 스트림인 TCP 연결 위에서 메시지 경계를 명확히 구분**합니다.

### UDP (ESP32-CAM ↔ SoyWorkerUI 카메라 스트림)

- **소켓 레벨**
  - 한 번의 `recvfrom` 호출로 **하나의 UDP 패킷 전체**를 받습니다.  
    (UDP는 패킷 단위라서 TCP처럼 “조각나서” 오지 않습니다.)
- **패킷 payload 구조 (UDP datagram)**
  - `IMG` 매직(3바이트) + **헤더 7바이트** + **JPEG 청크 데이터**
  - 총 최소 길이: 10바이트 (`IMG` + 헤더)
- **헤더 상세 (7바이트, Little-endian)**
  - `frame_type` (1바이트): 프레임 타입 식별용
  - `image_id` (2바이트, LE `uint16`): 같은 프레임(이미지)을 구성하는 청크의 ID
  - `total_chunks` (2바이트, LE `uint16`): 이 이미지가 몇 개의 청크로 나뉘어 오는지
  - `chunk_index` (2바이트, LE `uint16`): 현재 청크의 인덱스 (0부터 시작)
- **수신 측 파싱 규칙 (SoyWorkerUI)**
  1. `data = recvfrom(...)` 결과의 길이가 **10바이트 미만**이거나, `data[:3] != b"IMG"` 이면 **무시**.
  2. `frame_type = data[3]`  
     `image_id = struct.unpack_from("<H", data, 4)[0]`  
     `total_chunks = struct.unpack_from("<H", data, 6)[0]`  
     `chunk_index = struct.unpack_from("<H", data, 8)[0]`
  3. JPEG 조각은 `jpeg_part = data[10:]` 로 잘라냅니다.
  4. `image_id`별로 `total_chunks` 개수가 쌓일 때까지 `chunk_index` 순서대로 버퍼링한 뒤, 모든 청크가 모이면 **순서대로 이어붙여 하나의 JPEG 바이너리**로 재조립합니다.

이렇게 하면 **여러 UDP 패킷에 나뉘어서 온 한 프레임의 JPEG 이미지**를 정확하게 복구할 수 있습니다.

### Serial (Register Controller → SoyAdminUI)

- **라인 단위 프로토콜** (NDJSON)
  - 각 메시지는 **하나의 JSON 객체 + 개행(LF)** 로 전송됩니다.
  - 예시:  
    `{"type":"card_read","source":"register_controller","uid":"A1B2C3D4"}\n`
- **송신 규칙**
  - Register Controller는 카드 인식 시, 위와 같은 JSON 문자열을 보내고, 끝에 `\n`을 붙여 전송합니다.
- **수신 규칙 (SoyAdminUI)**
  - 시리얼 포트에서 **한 줄 단위**(`readline`)로 읽어들입니다.
  - 개행 문자 제거 후 전체 문자열을 JSON으로 파싱합니다.
  - `type == "card_read"` 인 경우에만 UID를 추출하여 UI에 반영합니다.

### MQTT (SoyWorkerUI ↔ 분류키트)

- **프레이밍**
  - MQTT는 프로토콜 자체에서 **고정 헤더 + 가변 헤더 + payload** 구조를 가지며, paho-mqtt / PubSubClient 라이브러리가 모두 처리합니다.
  - 애플리케이션 레벨에서는 **“토픽 + 문자열 payload”** 만 다룹니다.
- **애플리케이션 규칙**
  - 제어 명령: `device/control` 토픽에 `"SORT_START"`, `"SORT_STOP"`, `"SORT_PAUSE"`, `"SORT_RESUME"`, `"SORT_DIR:1L"` 등 **단순 텍스트**를 발행합니다.
  - 센서/상태: `device/sensor` 에 `"PROXIMITY:1"`, `"DETECTED"`, `"SORTED_1L"` 등, `device/status` 에 `{"state":"RUNNING"}` 같은 **문자열/JSON 텍스트**를 발행합니다.
  - 수신 측은 라이브러리 콜백으로 **이미 잘린 한 메시지 단위 payload**를 받기 때문에 추가적인 길이 헤더 파싱은 필요 없습니다.
