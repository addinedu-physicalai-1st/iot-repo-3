/*
 * motor/dc_motor.h — DC 모터 드라이버
 *
 * A4950 Slow Decay 모드:
 *   IN1 = HIGH 고정
 *   IN2 = PWM (역상: duty 높을수록 느림)
 *
 * | speed | duty(IN2)   | 효과     |
 * |-------|-------------|----------|
 * | 0     | 255 (100%)  | Brake    |
 * | 255   | 0   (0%)    | 최대속도 |
 */
#pragma once
#include <cstdint>

class DcMotor {
public:
    /**
     * 핀 + LEDC 채널 초기화. IN1=HIGH, IN2=Brake 상태로 시작.
     */
    void begin(int in1Pin, int in2Pin, int channel, int freqHz, int resolutionBits);

    /**
     * 지정 속도로 구동 (0–255). Slow Decay 역상 관계.
     */
    void drive(int speed);

    /**
     * 전기적 제동 (IN1=HIGH, IN2=HIGH → duty=255).
     */
    void brake();

private:
    int _channel    = 0;
    int _in1Pin     = -1;
};
