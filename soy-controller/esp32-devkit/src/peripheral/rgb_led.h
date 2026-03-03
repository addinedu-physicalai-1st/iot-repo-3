/*
 * peripheral/rgb_led.h — RGB LED 드라이버
 *
 * 공통 캐소드: HIGH = 점등.
 * FSM 상태별 색상:
 *   IDLE    → 빨강
 *   RUNNING → 초록
 *   SORTING → 파랑
 *   WARNING → 노랑 (R+G)
 */
#pragma once
#include "fsm.h"

class RgbLed {
public:
    void begin(int rPin, int gPin, int bPin);

    void set(bool r, bool g, bool b);
    void red();
    void green();
    void blue();
    void yellow();
    void off();

    /** FSM 상태에 맞는 색상을 설정 */
    void forState(State s);

private:
    int _rPin = -1;
    int _gPin = -1;
    int _bPin = -1;
};
