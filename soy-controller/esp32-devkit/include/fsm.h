/*
 * fsm.h — 컨베이어 HFSM 열거형 정의
 * State 패턴 클래스는 fsm/ 디렉토리 참조.
 */
#pragma once
#include <cstdint>

enum class State : uint8_t {
    IDLE,    RUNNING,  PAUSED,  ERROR,
};

enum class SubState : uint8_t {
    NONE,  CONVEYING,  CAMERA_HOLD,  SORTING_A,  SORTING_B,
};

enum class SortDir : uint8_t {
    NONE,  LINE_1L,  LINE_2L,
};
