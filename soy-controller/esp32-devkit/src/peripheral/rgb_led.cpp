#include "rgb_led.h"
#include <Arduino.h>

void RgbLed::begin(int rPin, int gPin, int bPin) {
    _rPin = rPin;
    _gPin = gPin;
    _bPin = bPin;
    pinMode(_rPin, OUTPUT);
    pinMode(_gPin, OUTPUT);
    pinMode(_bPin, OUTPUT);
    off();
}

void RgbLed::set(bool r, bool g, bool b) {
    digitalWrite(_rPin, r);
    digitalWrite(_gPin, g);
    digitalWrite(_bPin, b);
}

void RgbLed::red()    { set(1, 0, 0); }
void RgbLed::green()  { set(0, 1, 0); }
void RgbLed::blue()   { set(0, 0, 1); }
void RgbLed::yellow() { set(1, 1, 0); }
void RgbLed::off()    { set(0, 0, 0); }

void RgbLed::forState(State s) {
    switch (s) {
        case State::IDLE:    red();    break;
        case State::RUNNING: green();  break;
        case State::PAUSED:  yellow(); break;
    }
}
