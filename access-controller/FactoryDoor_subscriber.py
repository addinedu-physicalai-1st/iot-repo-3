import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import SetBool
import socket
import json
import struct

class RfidAuthManager(Node):
    def __init__(self):
        super().__init__('rfid_auth_manager_node')
        
        # TCP 서버 설정 (브릿지 서버)
        self.tcp_host = '127.0.0.1' 
        self.tcp_port = 9001

        # 1. ESP32에서 보내는 UID 구독 (입구/출구)
        self.create_subscription(String, '/rfid_entrance_door', self.handle_entrance, 10)
        self.create_subscription(String, '/rfid_exit_door', self.handle_exit, 10)

        # 2. ESP32의 문을 열기 위한 서비스 클라이언트 생성
        self.door_client = self.create_client(SetBool, '/set_door_state')
        
        self.get_logger().info('--- [Manager] RFID 통합 인증 시스템 가동 ---')

    # 🌟 모든 함수는 이 클래스(RfidAuthManager) 안에 들여쓰기 되어야 합니다.

    def request_tcp_server(self, card_uid, direction):
        """TCP 서버에 접속하여 응답 전체를 로그로 출력"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0)
                sock.connect((self.tcp_host, self.tcp_port))

                request_body = {
                    "id": 1,
                    "type": "request",
                    "action": "get_worker_by_uid",
                    "body": {
                        "card_uid": card_uid,
                        "direction": direction
                    }
                }
                
                payload = json.dumps(request_body).encode('utf-8')
                sock.sendall(struct.pack(">I", len(payload)) + payload)

                resp_header = sock.recv(4)
                if not resp_header: 
                    self.get_logger().error("❌ 서버로부터 헤더를 받지 못했습니다.")
                    return None
                
                resp_len = struct.unpack(">I", resp_header)[0]
                raw_response = sock.recv(resp_len).decode('utf-8')
                
                # 서버 응답 디버깅 로그
                self.get_logger().info(f'🔍 [서버 응답 원본]: {raw_response}')
                
                return json.loads(raw_response)
        except Exception as e:
            self.get_logger().error(f'❌ TCP 서버 통신 에러: {e}')
            return None
    
    def call_door_service(self, should_open):
        if not self.door_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().warn('ESP32 도어 서비스를 찾을 수 없습니다!')
            return

        req = SetBool.Request()
        req.data = should_open
        
        # 비동기 호출 및 콜백 등록
        future = self.door_client.call_async(req)
        future.add_done_callback(self.door_service_callback)
        self.get_logger().info(f'🚀 ESP32로 명령 전송 완료: {should_open}')
        
    def door_service_callback(self, future):
        try:
            response = future.result()
            self.get_logger().info(f'📩 ESP32 응답 수신: {response.success}, 메시지: {response.message}')
        except Exception as e:
            self.get_logger().error(f'❌ 서비스 호출 실패: {e}')   
            
    def handle_entrance(self, msg):
        uid = msg.data
        self.get_logger().info(f'입구 인식: {uid}')
        res = self.request_tcp_server(uid, "enter")
        
        self.get_logger().warn(f'handle_entrance(self, msg): {res.get("ok")}')
        if res and res.get("ok"):
            worker = res.get("body")
            # worker가 dict 형태인지 확인 후 이름 출력
            name = worker.get("name", "Unknown") if isinstance(worker, dict) else "Unknown"
            self.get_logger().info(f'✅ 승인: {name}')
            self.call_door_service(True) 
        else:
            err_msg = res.get("error") if res else "Timeout/No Response"
            self.get_logger().error(f'❌ 입구 거부: {err_msg}')

    def handle_exit(self, msg):
        uid = msg.data
        self.get_logger().info(f'출구 인식: {uid}')
        res = self.request_tcp_server(uid, "exit")
        
        if res and res.get("ok"):
            self.get_logger().info(f'✅ 퇴실 확인 완료')
            self.call_door_service(True) 
        else:
            err_msg = res.get("error") if res else "Timeout/No Response"
            self.get_logger().error(f'❌ 퇴실 거부: {err_msg}')

def main(args=None):
    rclpy.init(args=args)
    node = RfidAuthManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"치명적 오류 발생: {e}")
    finally:
        # rclpy.ok() 체크를 통해 중복 shutdown 에러 방지
        if rclpy.ok():
            node.destroy_node()
            rclpy.shutdown()

if __name__ == '__main__':
    main()