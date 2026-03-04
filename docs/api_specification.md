# 인터페이스 및 통신 명세서 (API Specification)

## 1. TCP 커스텀 API (soy-pc ↔ soy-server)
> - **프레임 구조**: [4 Byte Payload 길이] + [JSON 형식 페이로드]
> - **기본 JSON 구조**: 
>   - **Request**: `{ "type": "request", "id": 정수, "action": "액션명", "body": {입력 데이터} }`
>   - **Response**: `{ "type": "response", "id": 정수, "ok": Boolean, "body": {반환 데이터}, "error": "에러 내용" }`
> - 아래 표의 입력 데이터는 `body` 파트 기준입니다. (성공은 `ok: true`, 실패는 `ok: false`)

### 1-1. 인증 불필요 API (일반 작업자 / 시스템 용)

| 기능 | 설명 | 프로토콜 | 액션 (Action) | 입력 데이터(Request `body`) | 반환 데이터(Response `body`) | 기타 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **관리자 로그인** | 어드민 로그인 및 토큰 발급 | TCP | `admin_login` | `{`<br>&nbsp;&nbsp;`"password": "String"`<br>`}` | **성공 (ok:true)**<br>`{`<br>&nbsp;&nbsp;`"token": "String",`<br>&nbsp;&nbsp;`"admin_id": Integer`<br>`}`<br>**실패 (ok:false)**<br>`error` 필드에 실패 사유 (비번틀림 등) | 세션 토큰은<br>관리자 권한 API에 필요 |
| **관리자 로그아웃** | 발급된 토큰 폐기 | TCP | `admin_logout` | `{`<br>&nbsp;&nbsp;`"auth_token": "String"`<br>`}` | **성공**<br>`null` | |
| **최초 관리자 등록 확인** | 초기 비번 등록 필요 여부 | TCP | `first_admin_needs_password` |없음 (Empty) | **성공**<br>`{`<br>&nbsp;&nbsp;`"needs_password": Boolean`<br>`}` | |
| **최초 관리자 등록** | 관리자 비밀번호 세팅 | TCP | `register_first_admin`| `{`<br>&nbsp;&nbsp;`"password": "String"`<br>`}` | **성공**<br>`null` | 비밀번호 4자 이상 |
| **주문 목록 조회** | 전체 주문 내역 가져오기 | TCP | `list_orders` | 없음 (Empty) | **성공**<br>`[`<br>&nbsp;&nbsp;`{`<br>&nbsp;&nbsp;&nbsp;&nbsp;`"order_id": Integer,`<br>&nbsp;&nbsp;&nbsp;&nbsp;`"status": "String",`<br>&nbsp;&nbsp;&nbsp;&nbsp;`...`<br>&nbsp;&nbsp;`}`<br>`]` | |
| **주문 상세 조회** | 특정 주문 상세 정보 | TCP | `get_order` | `{`<br>&nbsp;&nbsp;`"order_id": Integer`<br>`}` | **성공**<br>`{`<br>&nbsp;&nbsp;`"order_id": Integer,`<br>&nbsp;&nbsp;`"items": [ {...} ]`<br>`}` | |
| **주문 입고 처리** | 송장 스캔 시 입고 상태 변경 | TCP | `order_mark_delivered`| `{`<br>&nbsp;&nbsp;`"order_id": Integer`<br>`}` *또는*<br>`{`<br>&nbsp;&nbsp;`"order_item_id": Int`<br>`}` | **성공**<br>`{`<br>&nbsp;&nbsp;`"order_id": Integer,`<br>&nbsp;&nbsp;`"process_id": Integer`<br>`}` | 성공 시 자동으로<br>새 Process 생성됨 |
| **공정 목록 조회** | 생성된 공정 이력 반환 | TCP | `list_processes`| 없음 (Empty) | **성공**<br>`[`<br>&nbsp;&nbsp;`{ "process_id": Integer, ... }`<br>`]` | |
| **공정 시작** | 공정을 가동 상태로 변환 | TCP | `process_start` | `{`<br>&nbsp;&nbsp;`"process_id": Integer`<br>`}` | **성공**<br>`{ process 상세 객체 }` | |
| **공정 중지** | 공정을 정지(완료) 처리 | TCP | `process_stop` | `{`<br>&nbsp;&nbsp;`"process_id": Integer`<br>`}` | **성공**<br>`{ process 상세 객체 }` | |
| **분류 수량 갱신** | 센서 알림 후 DB 수량 + 1 | TCP | `process_update`| `{`<br>&nbsp;&nbsp;`"process_id": Integer,`<br>&nbsp;&nbsp;`"success_1l_qty": Int(opt),`<br>&nbsp;&nbsp;`"success_2l_qty": Int(opt),`<br>&nbsp;&nbsp;`"unclassified_qty": Int(opt)`<br>`}` | **성공**<br>`{ process 상세 객체 }`<br>**실패**<br>주문 수량 초과 시 에러 | |

<br>

### 1-2. 관리자 권한 API (Admin Only)
> - 모든 입력 데이터(`body`)에 `"auth_token": "String"` 이 반드시 포함되어야 합니다.

| 기능 | 설명 | 프로토콜 | 액션 (Action) | 부가 입력 데이터 | 반환 데이터(Response `body`) | 기타 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **작업자 조회** | 시스템에 등록된 작업자 반환 | TCP | `list_workers` | 없음 | **성공**<br>`[ { "worker_id": Int, "name": "Str", "card_uid": "Str" } ]` | |
| **작업자 등록** | 신규 작업자 및 사원증 추가 | TCP | `create_worker`| `{`<br>&nbsp;&nbsp;`"admin_id": Integer,`<br>&nbsp;&nbsp;`"name": "String",`<br>&nbsp;&nbsp;`"card_uid": "String"`<br>`}` | **성공**<br>`{ 추가된 worker 객체 }` | |
| **작업자 수정** | 기존 작업자 이름/사원증 변경 | TCP | `update_worker`| `{`<br>&nbsp;&nbsp;`"worker_id": Integer,`<br>&nbsp;&nbsp;`"name": "Str"(선택),`<br>&nbsp;&nbsp;`"card_uid": "Str"(선택)`<br>`}` | **성공**<br>`{ 변경된 worker 객체 }` | |
| **작업자 삭제** | 작업자 DB 삭제 | TCP | `delete_worker`| `{`<br>&nbsp;&nbsp;`"worker_id": Integer`<br>`}` | **성공**<br>`null` | |

---

## 2. IoT 제어 및 센서 이벤트 (MQTT 통신)
> - **중계**: `soy-pc` ↔ `MQTT 브로커` ↔ `ESP32 기기`
> - 요청(Request)/응답(Response) 구조가 아닌 **발행(Publish)/구독(Subscribe)** 형태입니다.

| 기능 | 설명 | 방향 | 토픽 (Topic) | 데이터 (Payload) | 기타 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **분류 시작** | DC 모터·카메라 구동 | `PC → ESP32` | `device/control` | `"SORT_START"` | DevKit: DC 구동, CAM: UDP 스트리밍 시작 |
| **분류 종료** | DC 모터·카메라 정지 | `PC → ESP32` | `device/control` | `"SORT_STOP"` | DevKit: DC 정지, CAM: UDP 스트리밍 중지 |
| **일시정지** | DC 모터 정지, 카메라 유지 | `PC → ESP32` | `device/control` | `"SORT_PAUSE"` | DevKit: DC brake, PAUSED 상태 진입. DB 상태는 RUNNING 유지 |
| **재개** | DC 모터 재구동 | `PC → ESP32` | `device/control` | `"SORT_RESUME"` | DevKit: DC 재구동, RUNNING 복귀 |
| **분류 방향 지시** | QR 스캔 결과에 따른 분류 방향 | `PC → ESP32` | `device/control` | `"SORT_DIR:1L"`<br>`"SORT_DIR:2L"`<br>`"SORT_DIR:WARN"` | DETECTED 이벤트 수신 시 QR Queue에서 꺼내 발행 |
| **근접 센서 상태** | 센서 감지 상태의 변화 알림 | `ESP32 → PC` | `device/sensor` | `"PROXIMITY:1"` (감지)<br>`"PROXIMITY:0"` (미감지) | GUI 화면 표시용 업데이트 |
| **분류 진입 알림** | 컨베이어 끝에서 물체 확인 | `ESP32 → PC` | `device/sensor` | `"DETECTED"` | 이 시점에 물체가 멈추고 분류 진행됨 |
| **분류 완료 알림** | 물리적인 분류 처리가 끝남 | `ESP32 → PC` | `device/sensor` | `"SORTED_1L"`<br>`"SORTED_2L"`<br>`"SORTED_UNCLASSIFIED"`| PC는 이 값을 받고<br>서버로 `process_update` 요청 |
| **FSM 상태 변경** | 기기의 시스템 상태 | `ESP32 → PC` | `device/status` | `{"state": "IDLE"}`<br>`{"state": "RUNNING"}`<br>`{"state": "SORTING"}`<br>`{"state": "PAUSED"}`<br>`{"state": "WARNING"}`| JSON 포맷. 화면의 공정 단계 컬러 배지를 바꿈. PAUSED 상태에서는 Watchdog 비활성화 |

---

## 3. 이벤트 푸시 통신 (단방향)

| 기능 | 설명 | 프로토콜 | 식별 / 라우팅 | 전송 데이터 (Payload) | 기타 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **카메라 영상 스트림** | ESP32-CAM에서 PC로<br>실시간 JPEG 영상 프레임 전송 | UDP | 포트 **8021**<br>(`ESP32 → PC`) | `IMG(3B) + 헤더(7B) + JPEG 청크(최대 1024B)` | QR 스캔을 위한 비디오 스트리밍 프로토콜 |
| **RFID 인식 이벤트** | 아두이노 RFID 인식 시 서버를<br>통해 해당 이벤트를 PC로 쏴줌 | TCP | 푸시 이벤트<br>(`SVR → PC`) | `{`<br>&nbsp;&nbsp;`"type": "card_read",`<br>&nbsp;&nbsp;`"uid": "String"`<br>`}` | PC 클라이언트 측에서 자동으로<br>사원증 로그인 처리가 됨 |
