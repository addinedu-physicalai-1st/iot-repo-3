# Soy Kit 통신 프로토콜 (Serial / TCP 공통)

키트와 PC/서버 간 메시지 포맷. NDJSON(한 줄=JSON 하나), UTF-8, LF. Baud 9600(Serial).

```ts
// card_read (Controller → PC)
{
  type: "card_read";
  source: "register_controller" | "access_controller";
  uid: string;  // 4|7 bytes hex
}
```

**예시**

```json
{"type":"card_read","source":"register_controller","uid":"A1B2C3D4"}
```

---

## 통신 예시

### soy-pc ↔ register-controller (Serial)

- **연결**: USB 시리얼 (Baud 9600). register-controller가 카드 인식 시 한 줄 전송, soy-pc가 수신.
- **방향**: register-controller → soy-pc (단방향).

| 구분 | 설명 | 예시 |
|------|------|------|
| Controller → PC | RFID 카드 인식 시 JSON 한 줄 전송 | 아래 예시 |

**Controller → PC (카드 인식 시)**

```json
{"type":"card_read","source":"register_controller","uid":"A1B2C3D4"}
```

---

## SoyServer ↔ Soy-PC (TCP)

- **연결**: Soy-PC가 SoyServer의 TCP 포트(기본 9001)에 접속. 한 연결로 요청/응답 + card_read 푸시.
- **프로토콜**: **길이 프리픽스 프레임**. 스트림에서 `\n` 스캔 없이 한 메시지 단위로 빠르게 읽기.
  - **프레임 형식**: `[4바이트 big-endian uint32 = payload 길이][payload]`
  - **payload**: UTF-8 인코딩된 JSON 한 개. (요청/응답/card_read 동일)
  - **최대 payload 크기**: 1MB. 그 이상은 무시/연결 종료.
  - **예**: payload 10바이트면 `\x00\x00\x00\x0a` + 10바이트 전송.

### PC → 서버 (요청)

**관리자 수 확인 / 최초 관리자 등록 (인증 불필요)**

```json
{"type":"request","id":0,"action":"admin_count","body":{}}
{"type":"request","id":1,"action":"register_first_admin","body":{"password":"비밀번호"}}
```

- `admin_count`: 응답 `body.count` = 관리자 수. soy-pc는 DB 직접 연결 없이 서버로만 조회.
- `register_first_admin`: admin이 0명일 때만 사용. 첫 관리자 비밀번호 등록.

**관리자 로그인 (Worker CRUD 전에 필수)**

```json
{"type":"request","id":2,"action":"admin_login","body":{"password":"비밀번호"}}
```

**Worker CRUD (body에 auth_token 필수)**

```json
{"type":"request","id":3,"action":"list_workers","body":{"auth_token":"<로그인 시 받은 토큰>"}}
{"type":"request","id":4,"action":"get_first_admin_id","body":{"auth_token":"..."}}
{"type":"request","id":5,"action":"create_worker","body":{"admin_id":1,"name":"홍길동","card_uid":"A1B2C3D4"}}
{"type":"request","id":6,"action":"update_worker","body":{"worker_id":1,"name":"김철수"}}
{"type":"request","id":7,"action":"delete_worker","body":{"auth_token":"...","worker_id":1}}
```

**로그아웃**

```json
{"type":"request","id":8,"action":"admin_logout","body":{"auth_token":"..."}}
```

### 서버 → PC (응답)

```json
{"type":"response","id":1,"ok":true,"body":[...],"error":null}
{"type":"response","id":2,"ok":false,"body":null,"error":"Worker not found"}
```

### 서버 → PC (푸시, card_read)

Register Controller에서 시리얼로 수신한 card_read를 그대로 전달.

```json
{"type":"card_read","source":"register_controller","uid":"A1B2C3D4"}
```

### 환경 변수

| 구분 | 변수명 | 설명 |
|------|--------|------|
| 서버 | SOY_PC_TCP_PORT | Soy-PC 접속용 TCP 포트 (기본 9001) |
| 서버 | SOY_REGISTER_SERIAL_PORT | Register Controller 시리얼 포트 |
| 서버 | SOY_REGISTER_BAUD | 시리얼 Baud (기본 9600) |
| PC | SOY_SERVER_HOST | SoyServer 호스트 (기본 127.0.0.1) |
| PC | SOY_SERVER_TCP_PORT | SoyServer TCP 포트 (기본 9001) |
| PC | SOY_USE_SERVER_RFID | 0이면 시리얼 직접 연결, 그 외 서버 TCP로 card_read 수신 (기본 1) |
