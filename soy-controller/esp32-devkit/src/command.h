/*
 * command.h — MQTT 명령 파싱
 *
 * device/control 토픽에서 수신하는 명령을 타입 안전하게 파싱한다.
 * soy-server(PC)는 분류 시작/종료만 제어: SORT_START, SORT_STOP.
 */
#pragma once
#include <cstdint>

enum class CommandType : uint8_t {
    SORT_START,  // 분류 시작 — DC 모터 구동
    SORT_STOP,   // 분류 종료 — DC 모터 정지
    UNKNOWN,     // 알 수 없는 명령
};

struct Command {
    CommandType type = CommandType::UNKNOWN;

    /**
     * 수신 메시지 문자열을 파싱하여 Command 구조체를 생성한다.
     *
     * 지원 형식:
     *   "SORT_START"  → SORT_START
     *   "SORT_STOP"   → SORT_STOP
     *   그 외          → UNKNOWN
     */
    static Command parse(const char* msg);
};
