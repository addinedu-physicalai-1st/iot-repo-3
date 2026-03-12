# Soy Kit 통신 프로토콜

키트·PC·서버 간 통신은 **Serial**, **TCP**, **UDP** 세 가지 프로토콜을 사용한다. 각 프로토콜별로 연결, 포맷, 메시지 타입을 정리한다.

---

## 1. Serial 프로토콜 (register-controller ↔ soy-pc)

작업자 등록용 Register Controller와 soy-pc 간 **USB 시리얼** 통신.

### 연결·포맷

| 항목 | 내용 |
|------|------|
| 연결 | USB 시리얼 |
| Baud | 9600 (환경 변수로 변경 가능) |
| 포맷 | NDJSON — 한 줄에 JSON 하나, UTF-8, 줄 구분 LF |
| 방향 | register-controller → soy-pc (단방향. 카드 인식 시에만 전송) |

### 메시지 타입

이 프로토콜에서는 **card_read** 한 종류만 사용한다.

```ts
{
  type: "card_read";
  source: "register_controller" | "access_controller";
  uid: string;  // 4|7 bytes hex
}
```

### 예시

**Controller → PC (RFID 카드 인식 시)**

```json
{"type":"card_read","source":"register_controller","uid":"A1B2C3D4"}
```

---

## 2. TCP 프로토콜 (Soy-PC ↔ SoyServer)

Soy-PC(관리자/작업자 클라이언트)와 SoyServer 간 **TCP** 통신. 한 연결로 요청/응답과 card_read 푸시를 모두 처리한다.

### 연결

| 항목 | 내용 |
|------|------|
| 연결 | Soy-PC가 SoyServer TCP 포트에 접속 (기본 9001) |
| 동시 사용 | 요청(request) / 응답(response) / 푸시(card_read) 모두 같은 연결 |

### 프레임 형식

**길이 프리픽스 프레임** — LF로 줄 나누지 않고, 4바이트 헤더로 메시지 경계를 구분한다.

| 오프셋 | 길이 | 설명 |
|-------|------|------|
| 0 | 4바이트 | **헤더**: payload 길이. big-endian 부호 없는 32비트 정수(uint32). 단위는 바이트. |
| 4 | N바이트 | **payload**: UTF-8 인코딩된 JSON 한 개. N = 헤더에 적힌 값. |

- **최대 payload 크기**: 1MB (1,048,576). 초과 시 프레임 무시 또는 연결 종료.
- **예**: payload 10바이트 → 헤더 `00 00 00 0a` + payload 10바이트. payload 0바이트 또는 1MB 초과는 무효 프레임.

### 메시지 타입

**PC → 서버 요청**

```ts
{
  type: "request";
  id: number;    // 응답과 매칭용
  action: string;
  body: object;
}
```

**서버 → PC 응답**

```ts
{
  type: "response";
  id: number;    // 요청 id와 동일
  ok: boolean;
  body: object | null;
  error: string | null;
}
```

**서버 → PC 푸시 (card_read)** — Serial에서 받은 card_read를 그대로 TCP로 전달할 때 사용.

```ts
{
  type: "card_read";
  source: "register_controller" | "access_controller";
  uid: string;
}
```

### PC → 서버 (요청)

**관리자 수 확인 / 최초 관리자 등록 (인증 불필요)**

```json
{"type":"request","id":0,"action":"admin_count","body":{}}
{"type":"request","id":1,"action":"register_first_admin","body":{"password":"비밀번호"}}
```

- `admin_count`: 응답 `body.count` = 관리자 수.
- `register_first_admin`: admin이 0명일 때만 사용. 첫 관리자 비밀번호 등록.

**관리자 로그인 (Worker CRUD 전에 필수)**

```json
{"type":"request","id":2,"action":"admin_login","body":{"password":"비밀번호"}}
```

**Worker CRUD (body에 auth_token 필수)**

```json
{"type":"request","id":3,"action":"list_workers","body":{"auth_token":"<로그인 시 받은 토큰>"}}
{"type":"request","id":4,"action":"get_first_admin_id","body":{"auth_token":"..."}}
{"type":"request","id":5,"action":"create_worker","body":{"auth_token":"...","admin_id":1,"name":"홍길동","card_uid":"A1B2C3D4"}}
{"type":"request","id":6,"action":"update_worker","body":{"auth_token":"...","worker_id":1,"name":"김철수"}}
{"type":"request","id":7,"action":"delete_worker","body":{"auth_token":"...","worker_id":1}}
```

**로그아웃**

```json
{"type":"request","id":8,"action":"admin_logout","body":{"auth_token":"..."}}
```

**주문 (인증 불필요)**

- `get_order`: `body.order_id` 필수. 응답 `body` = `{ order_id, order_date, status }`.
- `get_order_id_by_order_item_id`: `body.order_item_id` 필수. 응답 `body` = `{ order_id }`.
- `order_mark_delivered`: `body.order_id` 또는 `body.order_item_id` 중 하나 필수. 응답 `body` = `{ order_id, process_id }`.

```json
{"type":"request","id":10,"action":"get_order","body":{"order_id":1}}
{"type":"request","id":11,"action":"get_order_id_by_order_item_id","body":{"order_item_id":5}}
{"type":"request","id":12,"action":"order_mark_delivered","body":{"order_id":1}}
{"type":"request","id":13,"action":"order_mark_delivered","body":{"order_item_id":5}}
```

**공정 (인증 불필요)**

- `list_processes`: `body` = `{}`. 응답 `body` = 배열. 각 항목: `process_id`, `order_id`, `start_time`, `end_time`, `status`, `total_qty`, `success_1l_qty`, `success_2l_qty`, `unclassified_qty`.
- `process_start`: `body.process_id` 필수. 응답 `body` = `{ process_id, order_id, start_time, status }`.
- `process_stop`: `body.process_id` 필수. 응답 `body` = `{ process_id, end_time, status }`.
- `process_update`: `body.process_id` 필수. 수량만 갱신 시 `success_1l_qty`, `success_2l_qty`, `unclassified_qty` 중 전달할 것만 포함. 응답 `body` = `{ process_id, success_1l_qty, success_2l_qty, unclassified_qty }`.

```json
{"type":"request","id":20,"action":"list_processes","body":{}}
{"type":"request","id":21,"action":"process_start","body":{"process_id":1}}
{"type":"request","id":22,"action":"process_stop","body":{"process_id":1}}
{"type":"request","id":23,"action":"process_update","body":{"process_id":1,"success_1l_qty":10,"success_2l_qty":5,"unclassified_qty":0}}
```

### 서버 → PC (응답)

- `id`: 요청의 `id`와 동일. `ok`가 `true`면 `body`에 결과, `false`면 `error`에 메시지.

```json
{"type":"response","id":1,"ok":true,"body":[...],"error":null}
{"type":"response","id":2,"ok":false,"body":null,"error":"Worker not found"}
```

**에러 메시지 예**: `"Admin login required"`, `"Worker not found"`, `"주문을 찾을 수 없습니다."`, `"주문 상세를 찾을 수 없습니다."`, `"이미 입고한 주문입니다."`, `"공정을 찾을 수 없습니다."`, `"order_id required"`, `"process_id required"` 등.

### 서버 → PC (푸시, card_read)

Register Controller에서 시리얼로 수신한 card_read를 TCP 클라이언트들에게 그대로 전달한다. 프레임 형식은 동일(4바이트 헤더 + JSON payload).

```json
{"type":"card_read","source":"register_controller","uid":"A1B2C3D4"}
```

---

## 3. UDP 프로토콜 (카메라 ↔ SoyServer)

컨베이어벨트 상단 카메라(예: ESP32CAM)가 **이미지 프레임(JPEG)** 을 SoyServer로 전송하고, 서버에서 QR을 읽는 용도. **아직 구현 전이며, 예상 스펙**이다.

### 연결

| 항목 | 내용 |
|------|------|
| 방향 | 카메라(soy-controller) → SoyServer (단방향) |
| 전송 | UDP. 한 패킷 = 한 프레임(헤더 + JPEG). |
| 포트 | 서버가 리슨 (환경 변수 `SOY_CAMERA_UDP_PORT`) |

### 프레임 형식 (바이너리)

UDP payload는 **고정 길이 바이너리 헤더 + JPEG 바이너리**이다. 숫자 필드는 모두 **big-endian**이다.

**헤더 (고정 24바이트)**

| 오프셋 | 길이 | 타입 | 설명 |
|--------|------|------|------|
| 0 | 2바이트 | uint16 | **width** — 이미지 가로 픽셀 |
| 2 | 2바이트 | uint16 | **height** — 이미지 세로 픽셀 |
| 4 | 4바이트 | uint32 | **frame_id** — 프레임 시퀀스 번호 (0부터 증가) |
| 8 | 16바이트 | byte[16] | **camera_id** — 카메라/라인 식별자. ASCII, 부족분은 0x00 패딩. |

**헤더 직후**

| 오프셋 | 길이 | 설명 |
|--------|------|------|
| 24 | (패킷 길이 − 24)바이트 | **이미지**: JPEG 바이너리. |

- UDP datagram 길이에서 24를 빼면 JPEG 길이.
- MTU(약 1500바이트)를 넘지 않도록 JPEG 해상도/품질을 조절하는 것이 좋다.

### 예시 (헤더만)

- width=320, height=240, frame_id=1, camera_id="line1_cam" (나머지 0 패딩)  
  → `00 01 40` `00 00 F0` `00 00 00 01` `6C 69 6E 65 31 5F 63 61 6D 00 00 00 00 00 00 00` (2+2+4+16 = 24바이트) + JPEG 바이너리.

---

## 4. 환경 변수

| 프로토콜 | 구분 | 변수명 | 설명 |
|----------|------|--------|------|
| Serial | 서버 | SOY_REGISTER_SERIAL_PORT | Register Controller 시리얼 포트 |
| Serial | 서버 | SOY_REGISTER_BAUD | 시리얼 Baud (기본 9600) |
| TCP | 서버 | SOY_PC_TCP_PORT | Soy-PC 접속용 TCP 포트 (기본 9001) |
| TCP | PC | SOY_SERVER_HOST | SoyServer 호스트 (기본 127.0.0.1) |
| TCP | PC | SOY_SERVER_TCP_PORT | SoyServer TCP 포트 (기본 9001) |
| TCP | PC | SOY_USE_SERVER_RFID | 0이면 시리얼 직접 연결, 그 외 서버 TCP로 card_read 수신 (기본 1) |
| UDP | 서버 | SOY_CAMERA_UDP_PORT | 카메라 이미지 수신용 UDP 포트 (예: 9100) |
