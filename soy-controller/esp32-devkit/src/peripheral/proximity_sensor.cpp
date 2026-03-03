#include "proximity_sensor.h"
#include <Arduino.h>

void ProximitySensor::begin(int pin, int threshold, unsigned long debounceMs) {
    _pin        = pin;
    _threshold  = threshold;
    _debounceMs = debounceMs;

    // GPIO 34 는 INPUT_ONLY 핀 → 내부 풀다운/풀업 불가 (하드웨어 제약)
    // 전체 ADC1 감쇄를 11dB(0~3.3V) 로 설정해야 올바른 값이 나옴
    analogSetAttenuation(ADC_11db);  // 모든 ADC 채널에 적용
    analogReadResolution(12);        // 0~4095
}

int ProximitySensor::readRaw() const {
    return analogRead(_pin);
}

bool ProximitySensor::isDetected() {
    int raw = readRaw();
    bool detected = (raw >= _threshold);
    unsigned long now = millis();

    if (detected != _lastState) {
        _lastState  = detected;
        _lastChange = now;
    }

    return _lastState && (now - _lastChange >= _debounceMs);
}

void ProximitySensor::sync() {
    int raw = readRaw();
    _lastState  = (raw >= _threshold);
    // _lastChange = 0 → debounce 조건 (millis() - 0 >= 50)이 항상 통과
    _lastChange = 0;
}
