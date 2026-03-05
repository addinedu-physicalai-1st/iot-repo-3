#include "fsm.h"

const char* Fsm::stateName() const {
    switch (_state) {
        case State::IDLE:    return "IDLE";
        case State::RUNNING: return "RUNNING";
        case State::PAUSED:  return "PAUSED";
        default:             return "UNKNOWN";
    }
}

void Fsm::enter(State s) {
    _state      = s;
    _entered_at = millis();
}
