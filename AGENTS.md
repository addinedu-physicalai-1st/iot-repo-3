# Agent 가이드 — Smart Soy Sauce Factory (스마트 간장공장)

AI 에이전트가 이 저장소에서 작업할 때 참고할 프로젝트 컨텍스트와 규칙입니다. 상세 개요·실행 방법은 [README.md](./README.md)를 참고하세요.

---

## 1. 프로젝트 요약

- **목적**: 제품 상자 QR 코드의 주소를 읽어 **국내/해외**로 자동 분류하는 스마트 간장공장 소프트웨어.
- **흐름**: 컨베이어 → ESP32CAM(QR 인식) → SoyServer(주소 해석·분류 지시) → 서보모터로 창고 분류.
- **통신**: 출입제어키트·분류키트·관리자 PC는 **중앙서버(SoyServer)** 를 통해 **SoyDB(MySQL)** 와 연동.

---

## 2. 저장소 구조 및 모듈별 가이드

| 경로 | 역할 | 스택 | 에이전트 작업 시 참고 |
|------|------|------|------------------------|
| `soy-server/` | 중앙서버 | Python 3.12, FastAPI, Alembic·SQLAlchemy | REST API·비동기·DB 연동. **Alembic은 soy-server/ 내부(soy-server/alembic/)에서 관리.** 스키마 변경 시 마이그레이션과 정합성 유지. |
| `soy-pc/` | 관리자/작업자 UI (SoyAdmin) | PyQt6 | `main.py`, `theme.py`, `ui/`(`.ui` 파일), `db/`(연결·admin·worker), `features/`(잠금·작업자·관리자 화면·관리자 등록). 루트의 `designer.py`로 UI 편집, `soy_pc.py`로 실행. SoyServer·카메라 UDP 연동. |
| `soy-db/` | DB·인프라 | MySQL, Docker | 스키마·Docker 설정. 테이블 변경은 SoyServer 쪽 마이그레이션과 맞출 것. |
| `soy-controller/` | 분류키트 | Arduino, ESP32CAM | QR 인식, 근접·서보·DC모터. **TCP**(분류 지시)·**UDP**(카메라). |
| `access-controller/` | 출입제어키트 | Arduino, ESP32, RFID | 중앙서버와 **TCP** 통신. |

**루트 주요 파일**

- `pyproject.toml`, `uv.lock` — Python 의존성 (서버·PyQt6 등). 패키지 추가 시 `uv add [패키지]`.
- `docker-compose.yml` — MySQL + SoyServer 한 번에 기동. `docker compose up -d`. 각 서비스 이미지는 `soy-db/Dockerfile`, `soy-server/Dockerfile` 에서 빌드.
- `designer.py` — Qt Designer 실행, `soy-pc/ui/main_window.ui` 열기 (다른 화면은 `soy-pc/ui/` 내 `*_screen.ui`, `password_dialog.ui`).
- `soy_pc.py` — SoyAdmin 앱 실행 (`soy-pc/main.py` 호출).

---

## 3. 자주 쓰는 명령 (루트 기준)

```bash
uv venv && uv sync                    # 프로젝트 세팅
docker compose up -d                  # 서버·DB 기동 (시리얼 미연결 시 실패하면 ./scripts/compose-up.sh up -d 사용)
uv run uvicorn app.main:app --app-dir soy-server --reload   # 서버 로컬 실행 (HTTP 8000, TCP 9001)
uv run python designer.py             # Qt Designer (soy-pc/ui/*.ui 편집)
uv run python soy_pc.py               # SoyAdmin 실행
cd soy-server && uv run alembic upgrade head   # DB 마이그레이션 적용
```

펌웨어(access-controller, soy-controller)는 VSCode + PlatformIO IDE로 해당 폴더를 열어 빌드·업로드.

---

## 4. soy-server app 구조 (AI 참고용)

`soy-server/` 실행 시 `--app-dir soy-server` 로 `app` 패키지가 로드된다. 아래는 **MVC + 도메인 서비스** 구조 요약.

### 4.1 디렉터리 개요

| 경로 | 역할 (MVC) | 설명 |
|------|-------------|------|
| `app/main.py` | 진입점 | FastAPI 앱·TCP·시리얼 기동. |
| `app/database.py` | 인프라 | DB 세션(`get_session`). |
| `app/models/` | Model | ORM 엔티티(Order, Process, Worker, Admin 등). |
| `app/auth.py` | Model/서비스 | 관리자 비밀번호 검증·최초 등록. |
| `app/services/` | Model (도메인) | **주문·공정·작업자** DB 로직. TCP/HTTP를 모름. |
| `app/requests/` | Controller | PC 브릿지 TCP 요청: `action`+`body` → `(ok, body, err)`. `app.services` 호출. |
| `app/views/` | View | Controller 결과 → TCP 응답 JSON 구조(`format_response`). |
| `app/pc_bridge.py` | 전송 계층 | TCP 프레임 수신/송신, 세션, `_handle_request`로 라우팅 후 View로 응답. |

### 4.2 서비스·요청·뷰 매핑

- **`app/services/orders.py`** — `get_order`, `get_order_id_by_order_item_id`, `set_order_delivered_and_create_process`. 예외: `OrderNotFound`.
- **`app/services/processes.py`** — `list_processes`, `start_process`, `stop_process`, `update_process`. 예외: `ProcessNotFound`.
- **`app/services/workers.py`** — `count_admins`, `get_first_admin_id`, `list_workers`, `create_worker`, `update_worker`, `delete_worker`. 예외: `WorkerNotFound`, `WorkerCreateConflict`.
- **`app/requests/auth.py`** — 인증 불필요: `admin_login`, `admin_logout`, `admin_count`, `register_first_admin`. 세션은 `pc_bridge`에서 주입.
- **`app/requests/orders.py`** — 인증 불필요: `get_order`, `get_order_id_by_order_item_id`, `order_mark_delivered`.
- **`app/requests/processes.py`** — 인증 불필요: `list_processes`, `process_start`, `process_stop`, `process_update`.
- **`app/requests/workers.py`** — **admin 로그인 필수**: `get_first_admin_id`, `list_workers`, `create_worker`, `update_worker`, `delete_worker`.
- **`app/views/tcp_response.py`** — `format_response(req_id, ok, body, error)` → `{ type, id, ok, body, error }` dict.

### 4.3 의존 방향 (에이전트 작업 시 참고)

- **Model**: `models`, `database`, `auth`, `services/*` — 프로토콜/전송 계층을 import 하지 않음.
- **Controller**: `app/requests/*` → `app.services`, `app.auth` 만 사용.
- **View**: `app/views/*` — 순수 응답 포맷만.
- **전송**: `pc_bridge` → `app.requests`, `app.views`, `app.services`(예외 타입용). 세션(`_sessions`)은 `pc_bridge` 소유.

새 액션 추가 시: 도메인 로직은 `app/services/` 또는 `app/auth`, 라우팅·파라미터 해석은 `app/requests/` 해당 파일, 응답 형식 변경은 `app/views/` 에서 처리하면 됨.
