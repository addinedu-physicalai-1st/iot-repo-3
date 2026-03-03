/*
 * command.h — MQTT 명령 파싱
 *
 * device/control 토픽에서 수신하는 명령을 타입 안전하게 파싱한다.
 * Rust의 Command enum + TryFrom 패턴에 대응.
 */
#pragma once
#include <cstdint>

enum class CommandType : uint8_t {
    DC_START,        // DC 모터 시작 (speed 필드 유효)
    DC_STOP,         // DC 모터 정지
    SORT_DIR_1L,     // 분류 방향: 1L 라인
    SORT_DIR_2L,     // 분류 방향: 2L 라인
    SORT_DIR_WARN,   // 분류 방향: 경고 (미등록 QR)
    UNKNOWN,         // 알 수 없는 명령
};

struct Command {
    CommandType type  = CommandType::UNKNOWN;
    int         speed = -1;  // DC_START 시에만 유효 (-1 = 기본 속도 사용)

    /**
     * 수신 메시지 문자열을 파싱하여 Command 구조체를 생성한다.
     *
     * 지원 형식:
     *   "DC_START"       → DC_START (기본 속도)
     *   "DC_START:200"   → DC_START (speed=200)
     *   "DC_STOP"        → DC_STOP
     *   "SORT_DIR:1L"    → SORT_DIR_1L
     *   "SORT_DIR:2L"    → SORT_DIR_2L
     *   "SORT_DIR:WARN"  → SORT_DIR_WARN
     *   그 외             → UNKNOWN
     */
    static Command parse(const char* msg);
};
