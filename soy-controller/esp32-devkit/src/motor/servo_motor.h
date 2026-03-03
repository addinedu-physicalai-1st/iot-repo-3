/*
 * motor/servo_motor.h — 서보 모터 드라이버 (MCPWM)
 *
 * ESP32 MCPWM Unit0/Timer0/OprA 를 사용하여 50Hz PWM 제어.
 * 펄스 폭(μs) = minUs + (maxUs - minUs) × angle / 180
 */
#pragma once
#include <cstdint>

class ServoMotor {
public:
    /**
     * MCPWM 초기화. 50Hz PWM 출력 시작.
     */
    void begin(int pin, int minUs, int maxUs);

    /**
     * 각도 설정 (0–180°). 해당 펄스 폭으로 PWM 출력.
     */
    void setAngle(int deg);

    /** 중립 위치 (config::servo::CENTER_DEG)로 설정 */
    void center();

    /** 분류 위치 (config::servo::SORT_DEG)로 설정 */
    void sort();

    /**
     * PWM 출력 차단 (duty=0). 서보 잔떨림 방지.
     */
    void disable();

private:
    int _minUs = 544;
    int _maxUs = 2400;
};
