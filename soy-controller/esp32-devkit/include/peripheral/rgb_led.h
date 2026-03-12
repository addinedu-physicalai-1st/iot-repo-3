/*
 * peripheral/rgb_led.h — RGB LED 드라이버 (점멸 지원)
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
    void forState(State s);
    void updateBlink(unsigned long blinkMs, bool r, bool g, bool b);
    void stopBlink();
private:
    int  _rPin = -1, _gPin = -1, _bPin = -1;
    bool _blinking = false, _blinkOn = false;
    unsigned long _lastBlinkMs = 0;
};
