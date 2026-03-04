#include "fsm.h"

const char* Fsm::stateName() const {
    switch (_state) {
        case State::IDLE:    return "IDLE";
        case State::RUNNING: return "RUNNING";
        case State::SORTING: return "SORTING";
        case State::WARNING: return "WARNING";
        case State::PAUSED:  return "PAUSED";
        default:             return "UNKNOWN";
    }
}

void Fsm::enter(State s) {
    _state      = s;
    _entered_at = millis();
    if (s == State::SORTING) {
        _sort_phase = SortPhase::HOLDING;
    }
}
