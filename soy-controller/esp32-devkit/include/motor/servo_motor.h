/*
 * motor/servo_motor.h — 서보 모터 드라이버 (MCPWM)
 */
#pragma once
#include <cstdint>
#include "driver/mcpwm.h"

class ServoMotor {
public:
    void begin(int pin, mcpwm_unit_t unit, int minUs, int maxUs);
    void setAngle(int deg);
    void center();
    void sort(int deg);
    void disable();
private:
    mcpwm_unit_t _unit  = MCPWM_UNIT_0;
    int          _minUs = 544;
    int          _maxUs = 2400;
};
