#include "servo_motor.h"
#include "config.h"
#include <Arduino.h>
#include "driver/mcpwm.h"

void ServoMotor::begin(int pin, int minUs, int maxUs) {
    _minUs = minUs;
    _maxUs = maxUs;

    mcpwm_gpio_init(MCPWM_UNIT_0, MCPWM0A, pin);

    mcpwm_config_t mcpwmCfg = {};
    mcpwmCfg.frequency    = 50;  // 50Hz
    mcpwmCfg.cmpr_a       = 0;
    mcpwmCfg.counter_mode = MCPWM_UP_COUNTER;
    mcpwmCfg.duty_mode    = MCPWM_DUTY_MODE_0;
    mcpwm_init(MCPWM_UNIT_0, MCPWM_TIMER_0, &mcpwmCfg);
}

void ServoMotor::setAngle(int deg) {
    deg = constrain(deg, 0, 180);
    uint32_t us = _minUs + (uint32_t)(_maxUs - _minUs) * deg / 180;
    mcpwm_set_duty_in_us(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A, us);
}

void ServoMotor::center() {
    setAngle(config::servo::CENTER_DEG);
}

void ServoMotor::sort() {
    setAngle(config::servo::SORT_DEG);
}

void ServoMotor::disable() {
    mcpwm_set_duty_in_us(MCPWM_UNIT_0, MCPWM_TIMER_0, MCPWM_OPR_A, 0);
}
