#include "motor/dc_motor.h"
#include <Arduino.h>

void DcMotor::begin(int in1Pin, int in2Pin, int channel, int freqHz, int resolutionBits) {
    _in1Pin  = in1Pin;
    _channel = channel;

    pinMode(_in1Pin, OUTPUT);
    digitalWrite(_in1Pin, HIGH);  // IN1 항상 HIGH

    ledcSetup(_channel, freqHz, resolutionBits);
    ledcAttachPin(in2Pin, _channel);

    brake();  // 초기 상태: 정지
}

void DcMotor::drive(int speed) {
    _softStopping = false;  // 구동 시 소프트 스톱 해제
    speed = constrain(speed, 0, 255);
    // Slow Decay 역상: duty = 255 - speed
    ledcWrite(_channel, 255 - speed);
    Serial.printf("[DC] RUN speed=%d\n", speed);
}

void DcMotor::brake() {
    _softStopping = false;
    // Brake: IN1=HIGH, IN2=HIGH (duty=255)
    ledcWrite(_channel, 255);
    Serial.println("[DC] BRAKE");
}

void DcMotor::startSoftStop(int startSpeed, unsigned long durationMs) {
    _softStopping   = true;
    _softStartSpeed = constrain(startSpeed, 0, 255);
    _softDurationMs = durationMs;
    _softStartMs    = millis();
    Serial.printf("[DC] SOFT_STOP start (speed=%d, dur=%lums)\n", _softStartSpeed, durationMs);
}

bool DcMotor::updateSoftStop() {
    if (!_softStopping) return true;

    unsigned long elapsed = millis() - _softStartMs;
    if (elapsed >= _softDurationMs) {
        // 감속 완료 → 브레이크
        brake();
        return true;
    }

    // 선형 감속: startSpeed → 0
    int curSpeed = _softStartSpeed - (int)((long)_softStartSpeed * elapsed / _softDurationMs);
    curSpeed = constrain(curSpeed, 0, 255);
    ledcWrite(_channel, 255 - curSpeed);
    return false;
}
