/*
 * command.h — MQTT 명령 파싱
 *
 * device/control 토픽에서 수신하는 명령을 타입 안전하게 파싱한다.
 * SORT_START/STOP: soy-pc 버튼 제어.
 * SORT_DIR_*: soy-pc QR 인식 결과 (분류 방향 예약).
 */
#pragma once
#include <cstdint>

enum class CommandType : uint8_t {
    SORT_START,    // 분류 시작 — DC 모터 구동
    SORT_STOP,     // 분류 종료 — DC 모터 정지
    SORT_PAUSE,    // 일시정지 — DC 모터 정지, 상태 보존
    SORT_RESUME,   // 재개 — DC 모터 재구동
    SORT_DIR_1L,   // QR 인식 결과: 1L 방향 예약
    SORT_DIR_2L,   // QR 인식 결과: 2L 방향 예약
    DC_SPEED,      // DC 모터 속도 변경 — "DC_SPEED:180"
    SERVO_DEG_A,   // 서보A 분류 각도 변경 — "SERVO_A:35"
    SERVO_DEG_B,   // 서보B 분류 각도 변경 — "SERVO_B:35"
    UNKNOWN,       // 알 수 없는 명령
};

struct Command {
    CommandType type = CommandType::UNKNOWN;
    int value = 0;

    /**
     * 수신 메시지 문자열을 파싱하여 Command 구조체를 생성한다.
     */
    static Command parse(const char* msg);
};
