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
    speed = constrain(speed, 0, 255);
    // Slow Decay 역상: duty = 255 - speed
    ledcWrite(_channel, 255 - speed);
    Serial.printf("[DC] RUN speed=%d\n", speed);
}

void DcMotor::brake() {
    // Brake: IN1=HIGH, IN2=HIGH (duty=255)
    ledcWrite(_channel, 255);
    Serial.println("[DC] BRAKE");
}
