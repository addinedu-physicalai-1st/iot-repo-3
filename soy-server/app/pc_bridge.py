"""
Soy-PC 브릿지: 시리얼 수신(Register Controller) + TCP 서버(요청/응답 + card_read 푸시).
Worker CRUD는 admin 로그인(세션 토큰) 후에만 허용.
NDJSON 한 줄 = JSON, UTF-8, LF.
"""
import json
import logging
import os
import socket
import threading
import uuid
from typing import Any

logger = logging.getLogger(__name__)

from app import workers
from app.auth import create_first_admin, verify_admin_password

# 환경변수
TCP_PORT = int(os.environ.get("SOY_PC_TCP_PORT", "9001"))
SERIAL_PORT = os.environ.get("SOY_REGISTER_SERIAL_PORT", "").strip()
SERIAL_BAUD = int(os.environ.get("SOY_REGISTER_BAUD", "9600"))

_clients: set[socket.socket] = set()
_clients_lock = threading.Lock()
_serial_thread: threading.Thread | None = None
_tcp_thread: threading.Thread | None = None
_tcp_server_socket: socket.socket | None = None
_stop = threading.Event()

# admin 세션: token -> admin_id (Worker CRUD는 유효한 토큰 필요)
_sessions: dict[str, int] = {}
_sessions_lock = threading.Lock()


def _broadcast_card_read(line: str) -> None:
    """card_read NDJSON 한 줄을 모든 연결된 클라이언트에 전송."""
    data = (line.strip() + "\n").encode("utf-8")
    with _clients_lock:
        n = len(_clients)
        dead = []
        for sock in _clients:
            try:
                sock.sendall(data)
            except (BrokenPipeError, ConnectionResetError, OSError):
                dead.append(sock)
        for sock in dead:
            _clients.discard(sock)
            try:
                sock.close()
            except Exception:
                pass
    try:
        obj = json.loads(line)
        uid = obj.get("uid", "") if isinstance(obj, dict) else ""
        msg = f"[RFID] card_read broadcast uid={uid!r} -> {n} client(s)"
        logger.info(msg)
        print(msg, flush=True)
    except Exception:
        msg = f"[RFID] card_read broadcast -> {n} client(s)"
        logger.info(msg)
        print(msg, flush=True)


def _require_admin(body: dict[str, Any]) -> tuple[bool, str]:
    """auth_token 검사. (유효 여부, 에러 메시지)."""
    token = body.get("auth_token")
    if not token or not isinstance(token, str):
        return (False, "Admin login required")
    with _sessions_lock:
        if token not in _sessions:
            return (False, "Admin login required")
    return (True, "")


def _handle_request(action: str, body: dict[str, Any]) -> tuple[bool, Any, str]:
    """CRUD 또는 admin_login 실행. (ok, body_or_none, error_message)."""
    try:
        if action == "admin_login":
            password = (body.get("password") or "").strip()
            if not password:
                return (False, None, "Password required")
            if not verify_admin_password(password):
                return (False, None, "비밀번호가 올바르지 않습니다.")
            aid = workers.get_first_admin_id()
            if aid is None:
                return (False, None, "No admin registered")
            token = str(uuid.uuid4())
            with _sessions_lock:
                _sessions[token] = aid
            return (True, {"token": token, "admin_id": aid}, "")
        if action == "admin_logout":
            token = body.get("auth_token")
            if token:
                with _sessions_lock:
                    _sessions.pop(token, None)
            return (True, None, "")
        if action == "admin_count":
            n = workers.count_admins()
            return (True, {"count": n}, "")
        if action == "register_first_admin":
            password = (body.get("password") or "").strip()
            if not password:
                return (False, None, "비밀번호를 입력하세요.")
            if len(password) < 4:
                return (False, None, "비밀번호는 4자 이상으로 설정하세요.")
            try:
                create_first_admin(password)
                return (True, None, "")
            except ValueError as e:
                return (False, None, str(e))
        # Worker CRUD는 admin 로그인 필수
        ok, err = _require_admin(body)
        if not ok:
            return (False, None, err)
        if action == "get_first_admin_id":
            aid = workers.get_first_admin_id()
            return (True, {"admin_id": aid} if aid is not None else None, "")
        if action == "list_workers":
            return (True, workers.list_workers(), "")
        if action == "create_worker":
            aid = body.get("admin_id")
            name = body.get("name", "")
            uid = body.get("card_uid", "")
            if aid is None:
                return (False, None, "admin_id required")
            out = workers.create_worker(int(aid), name, uid)
            return (True, out, "")
        if action == "update_worker":
            wid = body.get("worker_id")
            if wid is None:
                return (False, None, "worker_id required")
            out = workers.update_worker(
                int(wid),
                name=body.get("name"),
                card_uid=body.get("card_uid"),
            )
            return (True, out, "")
        if action == "delete_worker":
            wid = body.get("worker_id")
            if wid is None:
                return (False, None, "worker_id required")
            workers.delete_worker(int(wid))
            return (True, None, "")
        return (False, None, f"Unknown action: {action}")
    except workers.WorkerNotFound:
        return (False, None, "Worker not found")
    except workers.WorkerCreateConflict as e:
        return (False, None, e.detail)
    except Exception as e:
        return (False, None, str(e))


def _handle_client(sock: socket.socket) -> None:
    """한 클라이언트의 요청 루프."""
    try:
        buf = b""
        while not _stop.is_set():
            try:
                chunk = sock.recv(4096)
            except (ConnectionResetError, BrokenPipeError, OSError):
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line_str = line.decode("utf-8", errors="ignore").strip()
                if not line_str:
                    continue
                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict) or msg.get("type") != "request":
                    continue
                req_id = msg.get("id")
                action = msg.get("action", "")
                body = msg.get("body") or {}
                ok, res_body, err = _handle_request(action, body)
                resp = {
                    "type": "response",
                    "id": req_id,
                    "ok": ok,
                    "body": res_body,
                    "error": err if not ok else None,
                }
                try:
                    sock.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break
    finally:
        with _clients_lock:
            _clients.discard(sock)
        try:
            sock.close()
        except Exception:
            pass


def _serial_loop() -> None:
    """시리얼 포트에서 NDJSON 한 줄씩 읽고, card_read면 브로드캐스트."""
    if not SERIAL_PORT:
        msg = "[Serial] SOY_REGISTER_SERIAL_PORT not set — serial RFID disabled"
        logger.warning(msg)
        print(msg, flush=True)
        return
    try:
        import serial
    except ImportError:
        msg = "[Serial] pyserial not installed — serial RFID disabled"
        logger.warning(msg)
        print(msg, flush=True)
        return
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=0.5)
        msg = f"[Serial] opened {SERIAL_PORT} @ {SERIAL_BAUD} baud"
        logger.info(msg)
        print(msg, flush=True)
    except Exception as e:
        msg = f"[Serial] port unavailable (worker registration disabled): {SERIAL_PORT} — {e}"
        logger.warning(msg)
        print(msg, flush=True)
        return
    try:
        while not _stop.is_set():
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
            except Exception as e:
                logger.debug("[Serial] read error: %s", e)
                continue
            if not line:
                continue
            logger.debug("[Serial] raw line: %r", line)
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("[Serial] invalid JSON: %r", line[:80])
                continue
            if isinstance(obj, dict) and obj.get("type") == "card_read":
                uid = obj.get("uid", "")
                msg = f"[Serial] card_read received uid={uid!r} -> broadcasting"
                logger.info(msg)
                print(msg, flush=True)
                _broadcast_card_read(line)
            else:
                logger.debug("[Serial] ignored (not card_read): %r", line[:60])
    finally:
        try:
            ser.close()
        except Exception:
            pass
        logger.info("[Serial] closed %s", SERIAL_PORT)


def _tcp_accept_loop(server: socket.socket) -> None:
    """TCP accept 루프 (서버 소켓은 메인 스레드에서 이미 bind/listen 완료)."""
    try:
        while not _stop.is_set():
            try:
                client, addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with _clients_lock:
                _clients.add(client)
            n = len(_clients)
            msg = f"[TCP] Soy-PC connected from {addr} (total {n} client(s))"
            logger.info(msg)
            print(msg, flush=True)
            t = threading.Thread(target=_handle_client, args=(client,), daemon=True)
            t.start()
    finally:
        pass


def start() -> None:
    """브릿지 시작. TCP 포트는 메인 스레드에서 즉시 bind하여 기동 직후부터 접속 가능하게 함."""
    global _serial_thread, _tcp_thread, _tcp_server_socket
    _stop.clear()
    # TCP 서버 소켓을 메인 스레드에서 bind/listen (기동 완료 전에 9001 포트 확실히 개방)
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", TCP_PORT))
        server.listen(8)
        server.settimeout(1.0)
        _tcp_server_socket = server
        msg = f"[TCP] listening on port {TCP_PORT} (Soy-PC)"
        logger.info(msg)
        print(msg, flush=True)
    except Exception as e:
        msg = f"[TCP] failed to bind port {TCP_PORT}: {e}"
        logger.error(msg)
        print(msg, flush=True)
        return
    _tcp_thread = threading.Thread(target=_tcp_accept_loop, args=(server,), daemon=True)
    _tcp_thread.start()
    if SERIAL_PORT:
        _serial_thread = threading.Thread(target=_serial_loop, daemon=True)
        _serial_thread.start()
        msg = f"[pc_bridge] started (TCP port {TCP_PORT}, Serial {SERIAL_PORT})"
    else:
        msg = f"[pc_bridge] started (TCP port {TCP_PORT}, Serial disabled)"
    logger.info(msg)
    print(msg, flush=True)


def stop() -> None:
    """브릿지 정지."""
    global _tcp_server_socket
    _stop.set()
    if _tcp_server_socket is not None:
        try:
            _tcp_server_socket.close()
        except Exception:
            pass
        _tcp_server_socket = None
    with _clients_lock:
        for sock in list(_clients):
            try:
                sock.close()
            except Exception:
                pass
        _clients.clear()
