#include "motor/servo_motor.h"
#include "config.h"
#include <Arduino.h>
#include "driver/mcpwm.h"

void ServoMotor::begin(int pin, mcpwm_unit_t unit, int minUs, int maxUs) {
    _unit  = unit;
    _minUs = minUs;
    _maxUs = maxUs;

    mcpwm_gpio_init(unit, MCPWM0A, pin);

    mcpwm_config_t mcpwmCfg = {};
    mcpwmCfg.frequency    = 50;  // 50Hz (서보 표준)
    mcpwmCfg.cmpr_a       = 0;
    mcpwmCfg.counter_mode = MCPWM_UP_COUNTER;
    mcpwmCfg.duty_mode    = MCPWM_DUTY_MODE_0;
    mcpwm_init(unit, MCPWM_TIMER_0, &mcpwmCfg);

    // 업로드/재연결 시 0° (중립)로 초기화
    center();
}

void ServoMotor::setAngle(int deg) {
    // -90 ~ +90 입력을 0 ~ 180으로 변환 후 PWM 적용
    deg = constrain(deg, -90, 90);
    int deg180 = deg + 90;  // 오프셋 변환
    uint32_t us = _minUs + (uint32_t)(_maxUs - _minUs) * deg180 / 180;
    mcpwm_set_duty_in_us(_unit, MCPWM_TIMER_0, MCPWM_OPR_A, us);
}

void ServoMotor::center() {
    setAngle(config::servo::CENTER_DEG);  // 0°
}

void ServoMotor::sort(int deg) {
    setAngle(-deg);  // 방향 반전
}

void ServoMotor::disable() {
    mcpwm_set_duty_in_us(_unit, MCPWM_TIMER_0, MCPWM_OPR_A, 0);
}
