/*
 * config.h — 설정 중앙 집중
 *
 * 핀 매핑, 타이밍, MQTT 토픽 등 모든 상수를 한 곳에서 관리한다.
 * MQTT 공통(TOPIC_CONTROL, PORT)은 esp-common/esp/config_mqtt.h 에서 가져온다.
 */
#pragma once
#include <cstdint>
#include "esp/config_mqtt.h"

namespace config {

// ── 핀 매핑 ──────────────────────────────────────────────────
namespace pin {
    // DC 모터
    constexpr int DC_IN1   = 27;   // DC 모터 IN1 (방향)
    constexpr int DC_IN2   = 13;   // DC 모터 IN2 (PWM 속도)

    // 서보 모터 (각각 독립 MCPWM 채널)
    constexpr int SERVO_A  = 14;   // 1L 분류 서보
    constexpr int SERVO_B  = 15;   // 2L 분류 서보

    // 근접 센서 (ADC1 전용 핀)
    constexpr int SORT_POS_1L      = 34;   // 1L 분류위치 감지 (INPUT_ONLY)
    constexpr int SORT_POS_2L      = 35;   // 2L 분류위치 감지 (INPUT_ONLY)
    constexpr int SORT_CONFIRM_1L  = 32;   // 1L 분류 완료 확인 (통과 카운트)
    constexpr int SORT_CONFIRM_2L  = 33;   // 2L 분류 완료 확인 (통과 카운트)
    constexpr int SORT_CONFIRM_UNCL= 36;   // 미분류 확인 (말단 낙하, INPUT_ONLY)

    // RGB LED
    constexpr int LED_R    = 25;
    constexpr int LED_G    = 26;
    constexpr int LED_B    = 4;
}

// ── DC 모터 (A4950 Slow Decay) ───────────────────────────────
namespace dc {
    constexpr int LEDC_CHANNEL    = 0;
    constexpr int FREQ_HZ         = 5000;
    constexpr int RESOLUTION_BITS = 8;     // 0–255
    constexpr int DEFAULT_SPEED   = 200;
}

// ── 서보 모터 ────────────────────────────────────────────────
// 범위: -90° ~ +90°. API는 -90~+90, 내부에서 +90 오프셋으로 0~180 변환.
// CENTER_DEG(0°) = 중립(통과), SORT_DEG(+90°) = 분류 방향.
namespace servo {
    constexpr int INIT_DEG   =  0;    // 업로드/재연결 시 초기화 각도
    constexpr int CENTER_DEG =  0;    // 중립 (통과)
    constexpr int SORT_DEG   = 35;    // 분류 위치
    constexpr int MIN_US     = 544;
    constexpr int MAX_US     = 2400;
}

// ── 근접 센서 ────────────────────────────────────────────────
// analogRead + INPUT_PULLDOWN. 34,35,36은 INPUT_ONLY라 PULLDOWN 미적용.
namespace sensor {
    constexpr int           THRESHOLD   = 600;   // 이 값 이상 → 감지
    constexpr unsigned long DEBOUNCE_MS = 50;
}

// ── 분류 / 경고 타이밍 ───────────────────────────────────────
namespace timing {
    constexpr unsigned long SORT_HOLD_MS   = 1500;  // 서보 분류 위치 유지 시간
    constexpr unsigned long SORT_RETURN_MS = 600;   // 서보 중립 복귀 후 대기
    constexpr unsigned long WARNING_MS     = 3000;  // WARNING 자동 복귀 시간
}

// ── MQTT (TOPIC_CONTROL, PORT → esp/config_mqtt.h) ─────────────
namespace mqtt {
    constexpr const char* TOPIC_SENSOR  = "device/sensor";
    constexpr const char* TOPIC_STATUS  = "device/status";
}

}  // namespace config
