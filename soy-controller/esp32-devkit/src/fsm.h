/*
 * fsm.h — 컨베이어 유한 상태 기계
 *
 * State(상태), SortDir(분류 방향) enum과 Fsm 클래스를 정의한다.
 *
 * FSM 다이어그램:
 *   IDLE ──SORT_START──▶ RUNNING ◀──SORT_RESUME── PAUSED
 *                        │  ▲                       ▲
 *                        │  └───────────────────────┘
 *                        └──SORT_PAUSE──────────────┘
 */
#pragma once
#include <Arduino.h>
#include <cstdint>

// ── 컨베이어 FSM 상태 ────────────────────────────────────────
enum class State : uint8_t {
    IDLE,       // 대기. DC OFF, LED 빨강.
    RUNNING,    // 공정 진행. DC ON, LED 초록.
    PAUSED,     // 일시정지. DC OFF, LED 노랑 고정.
};

// ── 분류 서보 방향 ───────────────────────────────────────────
enum class SortDir : uint8_t {
    NONE,       // 방향 미설정 (QR 미인식)
    LINE_1L,    // 1L 라인
    LINE_2L,    // 2L 라인
};

// ── 컨베이어 유한 상태 기계 ──────────────────────────────────
class Fsm {
public:
    /** 현재 상태 */
    State state() const { return _state; }

    /** 현재 상태의 이름 문자열 (MQTT 발행용) */
    const char* stateName() const;

    /** 현재 상태에 머문 시간 (ms) */
    unsigned long elapsed() const { return millis() - _entered_at; }

    /** 상태 전이. 진입 시각을 기록한다. */
    void enter(State s);

private:
    State         _state      = State::IDLE;
    unsigned long _entered_at = 0;
};
