"""
soy-server TCP 클라이언트. Worker CRUD + card_read 푸시 수신.
환경변수: SOY_SERVER_HOST(기본 127.0.0.1), SOY_SERVER_TCP_PORT(기본 9001).
TCP: 길이 프리픽스 프레임 [4바이트 BE 길이][payload UTF-8 JSON].
"""
import json
import logging
import os
import socket
import struct
import threading
from typing import Any, Callable

# 서버와 동일: 헤더 4바이트(big-endian uint32) = payload 길이. 최대 1MB.
MAX_FRAME_PAYLOAD = 1024 * 1024

logger = logging.getLogger(__name__)

# 기본값 (환경변수 SOY_SERVER_HOST, SOY_SERVER_TCP_PORT)
_HOST = os.environ.get("SOY_SERVER_HOST", "127.0.0.1")
_PORT = int(os.environ.get("SOY_SERVER_TCP_PORT", "9001"))
_TIMEOUT = 10.0


def get_server_address() -> str:
    """soy-pc가 연결하는 서버 주소(host:port). 에러 메시지 등에 사용."""
    return f"{_HOST}:{_PORT}"

_socket: socket.socket | None = None
_socket_lock = threading.Lock()
_reader_thread: threading.Thread | None = None
_request_id = 0
_id_lock = threading.Lock()
_pending: dict[int, tuple[threading.Event, list[tuple[bool, Any, str]]]] = {}
_pending_lock = threading.Lock()
_card_read_callback: Callable[[str], None] | None = None
_reader_running = threading.Event()
_auth_token: str | None = None
_auth_token_lock = threading.Lock()


class WorkerNotFound(Exception):
    """Worker not found."""


class WorkerCreateConflict(Exception):
    """Duplicate card_uid."""

    def __init__(self, message: str = "", detail: str = ""):
        self.detail = detail or message
        super().__init__(message or self.detail)


def _next_id() -> int:
    global _request_id
    with _id_lock:
        _request_id += 1
        return _request_id


def _read_exact(s: socket.socket, n: int) -> bytes | None:
    """소켓에서 정확히 n바이트 읽기. 끊김/오류 시 None."""
    buf = b""
    while len(buf) < n:
        try:
            chunk = s.recv(min(4096, n - len(buf)))
        except (ConnectionResetError, BrokenPipeError, OSError):
            return None
        if not chunk:
            return None
        buf += chunk
    return buf


def _read_frame(s: socket.socket) -> bytes | None:
    """헤더(4바이트) 읽고 payload 길이만큼 읽어 반환. 끊김/오류/초과 시 None."""
    header = _read_exact(s, 4)
    if header is None or len(header) != 4:
        return None
    (length,) = struct.unpack(">I", header)
    if length == 0 or length > MAX_FRAME_PAYLOAD:
        return None
    return _read_exact(s, length)


def _send_frame(s: socket.socket, payload: bytes) -> bool:
    """payload 앞에 4바이트 길이 헤더 붙여 전송. 실패 시 False."""
    try:
        s.sendall(struct.pack(">I", len(payload)) + payload)
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def _ensure_connected() -> socket.socket:
    global _socket, _reader_thread
    with _socket_lock:
        if _socket is not None:
            try:
                _socket.getpeername()
                return _socket
            except OSError:
                try:
                    _socket.close()
                except Exception:
                    pass
                _socket = None
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(_TIMEOUT)
        try:
            s.connect((_HOST, _PORT))
        except ConnectionRefusedError:
            s.close()
            raise ConnectionRefusedError(
                f"서버 TCP 포트에 연결할 수 없습니다 (connection refused).\n\n"
                f"연결 시도 주소: {_HOST}:{_PORT}\n"
                f"(환경변수: SOY_SERVER_HOST, SOY_SERVER_TCP_PORT)\n\n"
                f"※ HTTP(8000)가 아니라 TCP(9001) 포트입니다.\n"
                f"  - Docker: docker compose 로 띄웠다면 9001 포트가 매핑되는지 확인.\n"
                f"  - 서버 로그에 '[TCP] listening on port 9001' 이 출력되는지 확인하세요."
            ) from None
        except OSError as e:
            if getattr(e, "errno", None) == 61:  # ECONNREFUSED (macOS/Linux)
                s.close()
                raise ConnectionRefusedError(
                    f"서버 TCP 포트에 연결할 수 없습니다 (connection refused).\n\n"
                    f"연결 시도 주소: {_HOST}:{_PORT}\n"
                    f"※ TCP 9001 포트가 열려 있어야 합니다. 서버 로그에서 '[TCP] listening on port 9001' 확인."
                ) from e
            s.close()
            raise
        s.settimeout(None)
        _socket = s
        _reader_running.set()
        if _reader_thread is None or not _reader_thread.is_alive():
            _reader_thread = threading.Thread(target=_reader_loop, daemon=True)
            _reader_thread.start()
        return _socket


def _reader_loop() -> None:
    """길이 프리픽스 프레임으로 한 메시지씩 읽어 response면 pending에, card_read면 콜백."""
    global _socket
    while _reader_running.is_set():
        try:
            s = _socket
            if s is None:
                break
            payload = _read_frame(s)
            if payload is None:
                break
            try:
                msg = json.loads(payload.decode("utf-8", errors="strict"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "response":
                rid = msg.get("id")
                ok = msg.get("ok", False)
                body = msg.get("body")
                err = msg.get("error") or ""
                with _pending_lock:
                    if rid in _pending:
                        ev, res = _pending.pop(rid)
                        res.append((ok, body, err))
                        ev.set()
            elif msg.get("type") == "card_read":
                uid = msg.get("uid") or ""
                logger.info("[RFID] card_read received from server uid=%r callback=%s", uid, _card_read_callback is not None)
                if uid and _card_read_callback:
                    try:
                        _card_read_callback(uid)
                        logger.info("[RFID] card_read callback done uid=%r", uid)
                    except Exception as e:
                        logger.warning("[RFID] card_read callback error: %s", e)
                elif not uid:
                    logger.warning("[RFID] card_read ignored: uid empty")
                else:
                    logger.warning("[RFID] card_read ignored: no callback registered")
        except Exception:
            break
    with _socket_lock:
        if _socket:
            try:
                _socket.close()
            except Exception:
                pass
            _socket = None


def set_auth_token(token: str | None) -> None:
    """관리자 로그인 후 받은 토큰 설정. None이면 로그아웃."""
    global _auth_token
    with _auth_token_lock:
        _auth_token = token


def admin_login(password: str) -> str:
    """관리자 로그인. 성공 시 토큰 반환. 실패 시 RuntimeError."""
    ok, body, err = _request("admin_login", {"password": password.strip()})
    if not ok:
        raise RuntimeError(err or "Login failed")
    if body and isinstance(body, dict) and body.get("token"):
        return body["token"]
    raise RuntimeError(err or "No token returned")


def admin_logout() -> None:
    """관리자 로그아웃. 서버 세션 무효화 후 토큰 제거."""
    with _auth_token_lock:
        tok = _auth_token
    if tok:
        try:
            _request("admin_logout", {"auth_token": tok})
        except Exception:
            pass
        set_auth_token(None)


def _request(action: str, body: dict[str, Any]) -> tuple[bool, Any, str]:
    """요청 한 번 보내고 응답 대기. (ok, body, error)."""
    body = dict(body)
    with _auth_token_lock:
        tok = _auth_token
    if tok and action != "admin_login":
        body["auth_token"] = tok
    req_id = _next_id()
    ev = threading.Event()
    res: list[tuple[bool, Any, str]] = []
    with _pending_lock:
        _pending[req_id] = (ev, res)
    try:
        sock = _ensure_connected()
        req = {"type": "request", "id": req_id, "action": action, "body": body}
        payload = json.dumps(req, ensure_ascii=False).encode("utf-8")
        if not _send_frame(sock, payload):
            raise ConnectionError("Send failed")
    except Exception as e:
        with _pending_lock:
            _pending.pop(req_id, None)
        raise
    if not ev.wait(timeout=_TIMEOUT):
        with _pending_lock:
            _pending.pop(req_id, None)
        raise TimeoutError("Server did not respond")
    if not res:
        return (False, None, "No response")
    ok, body, err = res[0]
    return (ok, body, err)


def set_card_read_callback(cb: Callable[[str], None] | None) -> None:
    """card_read 푸시 수신 시 호출할 콜백."""
    global _card_read_callback
    _card_read_callback = cb


def admin_count() -> int:
    """관리자 수. 서버 연결 실패 시 예외."""
    ok, body, err = _request("admin_count", {})
    if not ok:
        raise RuntimeError(err or "admin_count failed")
    if body is not None and isinstance(body, dict) and "count" in body:
        return int(body["count"])
    return 0


def register_first_admin(password: str) -> None:
    """최초 관리자 등록(비밀번호). 이미 있거나 실패 시 예외."""
    ok, _, err = _request("register_first_admin", {"password": password.strip()})
    if not ok:
        raise RuntimeError(err or "등록 실패")


def get_first_admin_id() -> int | None:
    """첫 번째 admin의 admin_id. 없거나 오류 시 None."""
    try:
        ok, body, err = _request("get_first_admin_id", {})
        if not ok:
            return None
        if body and isinstance(body, dict) and "admin_id" in body:
            return body["admin_id"]
        return None
    except Exception:
        return None


def list_workers() -> list[dict]:
    """작업자 목록."""
    ok, body, err = _request("list_workers", {})
    if not ok:
        raise RuntimeError(err or "list_workers failed")
    if body is None:
        return []
    return body if isinstance(body, list) else []


def create_worker(admin_id: int, name: str, card_uid: str) -> dict:
    """작업자 등록. card_uid 중복 시 WorkerCreateConflict."""
    ok, body, err = _request(
        "create_worker",
        {"admin_id": admin_id, "name": name.strip(), "card_uid": card_uid.strip()},
    )
    if not ok:
        if "이미 등록된" in (err or "") or "Duplicate" in (err or ""):
            raise WorkerCreateConflict(detail=err or "Duplicate card_uid")
        raise RuntimeError(err or "create_worker failed")
    return body or {}


def update_worker(
    worker_id: int, *, name: str | None = None, card_uid: str | None = None
) -> dict:
    """작업자 수정. WorkerNotFound / WorkerCreateConflict 시 예외."""
    body: dict[str, Any] = {"worker_id": worker_id}
    if name is not None:
        body["name"] = name.strip()
    if card_uid is not None:
        body["card_uid"] = card_uid.strip()
    ok, res, err = _request("update_worker", body)
    if not ok:
        if "not found" in (err or "").lower() or "찾을 수 없" in (err or ""):
            raise WorkerNotFound()
        if "이미" in (err or "") or "Duplicate" in (err or ""):
            raise WorkerCreateConflict(detail=err or "Duplicate card_uid")
        raise RuntimeError(err or "update_worker failed")
    return res or {}


def delete_worker(worker_id: int) -> None:
    """작업자 삭제. 없으면 WorkerNotFound."""
    ok, _, err = _request("delete_worker", {"worker_id": worker_id})
    if not ok:
        if "not found" in (err or "").lower() or "찾을 수 없" in (err or ""):
            raise WorkerNotFound()
        raise RuntimeError(err or "delete_worker failed")


# ----- 주문/입고 (작업자 화면 입고관리, 인증 불필요) -----


def get_order(order_id: int) -> dict:
    """주문 조회. 없으면 RuntimeError."""
    ok, body, err = _request("get_order", {"order_id": order_id})
    if not ok:
        raise RuntimeError(err or "주문 조회 실패")
    return body or {}


def get_order_id_by_order_item_id(order_item_id: int) -> int:
    """order_item_id로 order_id 조회. 없으면 RuntimeError."""
    ok, body, err = _request("get_order_id_by_order_item_id", {"order_item_id": order_item_id})
    if not ok:
        raise RuntimeError(err or "주문 상세 조회 실패")
    if body and isinstance(body, dict) and "order_id" in body:
        return int(body["order_id"])
    raise RuntimeError("order_id not in response")


def order_mark_delivered(*, order_id: int | None = None, order_item_id: int | None = None) -> dict:
    """주문을 입고 처리(pending → delivered). order_id 또는 order_item_id 중 하나 지정.
    이미 delivered면 RuntimeError(메시지에 '이미 입고한 주문')."""
    body: dict[str, Any] = {}
    if order_id is not None:
        body["order_id"] = order_id
    if order_item_id is not None:
        body["order_item_id"] = order_item_id
    if not body:
        raise ValueError("order_id 또는 order_item_id 필요")
    ok, res, err = _request("order_mark_delivered", body)
    if not ok:
        raise RuntimeError(err or "입고 처리 실패")
    return res or {}
