"""
Soy-PC 브릿지: 시리얼 수신(Register Controller) + TCP 서버(요청/응답 + card_read 푸시).
Worker CRUD는 admin 로그인(세션 토큰) 후에만 허용.
TCP: 길이 프리픽스 프레임 [4바이트 BE 길이][payload UTF-8 JSON]. Serial은 NDJSON(LF).
"""
import json
import logging
import os
import socket
import struct
import threading
import uuid
from typing import Any

# TCP 프레임: 헤더 4바이트(big-endian uint32) = payload 바이트 수, 이후 payload. 최대 1MB.
MAX_FRAME_PAYLOAD = 1024 * 1024

logger = logging.getLogger(__name__)

from app import orders, processes as processes_module, workers
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


def _read_exact(sock: socket.socket, n: int) -> bytes | None:
    """소켓에서 정확히 n바이트 읽기. 연결 끊김/오류 시 None."""
    buf = b""
    while len(buf) < n:
        try:
            chunk = sock.recv(min(4096, n - len(buf)))
        except (ConnectionResetError, BrokenPipeError, OSError):
            return None
        if not chunk:
            return None
        buf += chunk
    return buf


def _read_frame(sock: socket.socket) -> bytes | None:
    """헤더(4바이트) 읽고 payload 길이만큼 읽어 반환. 끊김/오류/초과 시 None."""
    header = _read_exact(sock, 4)
    if header is None or len(header) != 4:
        return None
    (length,) = struct.unpack(">I", header)
    if length == 0 or length > MAX_FRAME_PAYLOAD:
        return None
    return _read_exact(sock, length)


def _send_frame(sock: socket.socket, payload: bytes) -> bool:
    """payload 앞에 4바이트 길이 헤더 붙여 전송. 실패 시 False."""
    try:
        sock.sendall(struct.pack(">I", len(payload)) + payload)
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def _broadcast_card_read(line: str) -> None:
    """card_read JSON을 길이 프리픽스 프레임으로 모든 TCP 클라이언트에 전송."""
    payload = line.strip().encode("utf-8")
    with _clients_lock:
        n = len(_clients)
        dead = []
        for sock in _clients:
            if not _send_frame(sock, payload):
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
        # 주문/입고 (작업자 화면 입고관리, 인증 불필요)
        if action == "get_order":
            oid = body.get("order_id")
            if oid is None:
                return (False, None, "order_id required")
            order = orders.get_order(int(oid))
            if order is None:
                return (False, None, "주문을 찾을 수 없습니다.")
            return (True, order, "")
        if action == "get_order_id_by_order_item_id":
            oiid = body.get("order_item_id")
            if oiid is None:
                return (False, None, "order_item_id required")
            oid = orders.get_order_id_by_order_item_id(int(oiid))
            if oid is None:
                return (False, None, "주문 상세를 찾을 수 없습니다.")
            return (True, {"order_id": oid}, "")
        if action == "order_mark_delivered":
            oid = body.get("order_id")
            oiid = body.get("order_item_id")
            if oid is None and oiid is None:
                return (False, None, "order_id 또는 order_item_id가 필요합니다.")
            if oid is None:
                oid = orders.get_order_id_by_order_item_id(int(oiid))
                if oid is None:
                    return (False, None, "주문 상세를 찾을 수 없습니다.")
            else:
                oid = int(oid)
            try:
                err, process_id = orders.set_order_delivered_and_create_process(oid)
            except orders.OrderNotFound:
                return (False, None, "주문을 찾을 수 없습니다.")
            except Exception as e:
                logger.warning("order_mark_delivered: 트랜잭션 실패 order_id=%s: %s", oid, e)
                return (False, None, f"입고 등록 실패. 주문은 변경되지 않았습니다. ({e})")
            if err:
                return (False, None, err)
            return (True, {"order_id": oid, "process_id": process_id}, "")
        # 공정 목록/시작/중지 (작업자 화면 분류하기, 인증 불필요)
        if action == "list_processes":
            lst = processes_module.list_processes()
            return (True, lst, "")
        if action == "process_start":
            pid = body.get("process_id")
            if pid is None:
                return (False, None, "process_id required")
            try:
                out = processes_module.start_process(int(pid))
                return (True, out, "")
            except processes_module.ProcessNotFound:
                return (False, None, "공정을 찾을 수 없습니다.")
        if action == "process_stop":
            pid = body.get("process_id")
            if pid is None:
                return (False, None, "process_id required")
            try:
                out = processes_module.stop_process(int(pid))
                return (True, out, "")
            except processes_module.ProcessNotFound:
                return (False, None, "공정을 찾을 수 없습니다.")
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
    except processes_module.ProcessNotFound:
        return (False, None, "공정을 찾을 수 없습니다.")
    except orders.OrderNotFound:
        return (False, None, "주문을 찾을 수 없습니다.")
    except Exception as e:
        return (False, None, str(e))


def _handle_client(sock: socket.socket) -> None:
    """한 클라이언트의 요청 루프. 길이 프리픽스 프레임으로 수신/송신."""
    try:
        while not _stop.is_set():
            payload = _read_frame(sock)
            if payload is None:
                break
            try:
                msg = json.loads(payload.decode("utf-8", errors="strict"))
            except (json.JSONDecodeError, UnicodeDecodeError):
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
            resp_bytes = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            if not _send_frame(sock, resp_bytes):
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
