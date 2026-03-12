#include "peripheral/rgb_led.h"
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

void RgbLed::red()    { stopBlink(); set(1, 0, 0); }
void RgbLed::green()  { stopBlink(); set(0, 1, 0); }
void RgbLed::blue()   { stopBlink(); set(0, 0, 1); }
void RgbLed::yellow() { stopBlink(); set(1, 1, 0); }
void RgbLed::off()    { stopBlink(); set(0, 0, 0); }

void RgbLed::forState(State s) {
    switch (s) {
        case State::IDLE:    red();    break;
        case State::RUNNING: green();  break;
        case State::PAUSED:  yellow(); break;
        case State::ERROR:   // ERROR는 updateBlink()로 처리
            _blinking = true;
            break;
    }
}

void RgbLed::updateBlink(unsigned long blinkMs, bool r, bool g, bool b) {
    _blinking = true;
    unsigned long now = millis();
    if (now - _lastBlinkMs >= blinkMs) {
        _lastBlinkMs = now;
        _blinkOn = !_blinkOn;
        if (_blinkOn) {
            set(r, g, b);
        } else {
            set(0, 0, 0);
        }
    }
}

void RgbLed::stopBlink() {
    _blinking = false;
    _blinkOn  = false;
    _lastBlinkMs = 0;
}
