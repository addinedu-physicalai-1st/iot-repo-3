/*
 * stream_state.h — 스트리밍 상태 (FSM)
 *
 * MQTT SORT_START/SORT_STOP 수신 시 main loop의 switch에서
 * 각 상태별 핸들러로 분기한다.
 */
#pragma once
#include <cstdint>

enum class StreamingState : uint8_t {
    IDLE,       // 대기. UDP 전송 안 함.
    STREAMING,  // JPEG 캡처 → UDP 전송
};
