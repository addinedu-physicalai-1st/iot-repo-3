#include "proximity_sensor.h"
#include <Arduino.h>

void ProximitySensor::begin(int pin, int threshold, unsigned long debounceMs, bool isDigital, bool activeLow) {
    _pin        = pin;
    _threshold  = threshold;
    _debounceMs = debounceMs;
    _isDigital  = isDigital;
    _activeLow  = activeLow;

    // GPIO 34, 35, 36, 39는 INPUT_ONLY 핀 — 내부 풀다운/풀업 불가 (하드웨어 제약)
    // 그 외 핀(S3=32, S4=33)은 INPUT_PULLDOWN 설정
    if (pin != 34 && pin != 35 && pin != 36 && pin != 39) {
        pinMode(pin, INPUT_PULLDOWN);
    } else {
        pinMode(pin, INPUT);
    }

    if (!_isDigital) {
        // 전체 ADC1 감쇄를 11dB(0~3.3V)로 설정
        analogSetAttenuation(ADC_11db);
        analogReadResolution(12);  // 0~4095
    }
}

int ProximitySensor::readRaw() const {
    if (_isDigital) {
        return digitalRead(_pin);
    } else {
        return analogRead(_pin);
    }
}

bool ProximitySensor::isDetected() {
    int raw = readRaw();
    bool detected = false;
    
    if (_isDigital) {
        detected = _activeLow ? (raw == LOW) : (raw == HIGH);
    } else {
        detected = (raw >= _threshold);
    }

    unsigned long now = millis();

    if (detected != _lastState) {
        _lastState  = detected;
        _lastChange = now;
    }

    return _lastState && (now - _lastChange >= _debounceMs);
}

void ProximitySensor::sync() {
    int raw = readRaw();
    if (_isDigital) {
        _lastState = _activeLow ? (raw == LOW) : (raw == HIGH);
    } else {
        _lastState = (raw >= _threshold);
    }
    // _lastChange = 0 → debounce 조건 (millis() - 0 >= 50)이 항상 통과
    _lastChange = 0;
}
