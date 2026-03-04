/*
 * motor/servo_motor.h — 서보 모터 드라이버 (MCPWM)
 *
 * 서보 2개를 독립적으로 제어한다.
 *   ServoA → MCPWM_UNIT_0 (1L 분류)
 *   ServoB → MCPWM_UNIT_1 (2L 분류)
 *
 * 각도 범위: -90° ~ +90°
 *   - 0°  = 중립(통과)
 *   - +90° = 분류 방향
 * 내부에서 +90 오프셋으로 0~180으로 변환 후 PWM 적용.
 * begin() 호출 시 0°(중립)로 자동 초기화.
 */
#pragma once
#include <cstdint>
#include "driver/mcpwm.h"

class ServoMotor {
public:
    /**
     * MCPWM 초기화. 50Hz PWM 출력 시작 후 즉시 0°(중립)로 이동.
     * @param pin    서보 신호 핀
     * @param unit   MCPWM_UNIT_0 (ServoA) or MCPWM_UNIT_1 (ServoB)
     * @param minUs  최소 펄스폭 μs (예: 544)
     * @param maxUs  최대 펄스폭 μs (예: 2400)
     */
    void begin(int pin, mcpwm_unit_t unit, int minUs, int maxUs);

    /**
     * 각도 설정. 범위: -90 ~ +90°.
     * 내부에서 +90 오프셋으로 0~180으로 변환.
     */
    void setAngle(int deg);

    /** 0° (중립/통과) */
    void center();

    /** +90° (분류 위치) */
    void sort();

    /** PWM 출력 차단 (duty=0). 서보 잔떨림 방지. */
    void disable();

private:
    mcpwm_unit_t _unit  = MCPWM_UNIT_0;
    int          _minUs = 544;
    int          _maxUs = 2400;
};
