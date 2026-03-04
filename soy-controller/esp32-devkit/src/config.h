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
    constexpr int DC_IN1  = 27;   // DC 모터 IN1 (HIGH 고정)
    constexpr int DC_IN2  = 13;   // DC 모터 IN2 (PWM 속도 제어)
    constexpr int SERVO   = 14;   // 서보 (MCPWM, ADC1 간섭 방지)
    constexpr int SENSOR  = 34;   // 근접 센서 (ADC1, INPUT_ONLY)
    constexpr int LED_R   = 25;   // RGB LED — Red
    constexpr int LED_G   = 26;   // RGB LED — Green
    constexpr int LED_B   = 4;    // RGB LED — Blue
}

// ── DC 모터 (A4950 Slow Decay) ───────────────────────────────
namespace dc {
    constexpr int LEDC_CHANNEL    = 0;
    constexpr int FREQ_HZ         = 5000;
    constexpr int RESOLUTION_BITS = 8;     // 0–255
    constexpr int DEFAULT_SPEED   = 200;
}

// ── 서보 (MCPWM Unit0/Timer0/OprA) ──────────────────────────
namespace servo {
    constexpr int CENTER_DEG = 90;   // 중립(통과) 위치
    constexpr int SORT_DEG   = 45;   // 분류 위치
    constexpr int MIN_US     = 544;
    constexpr int MAX_US     = 2400;
}

// ── 근접 센서 (아날로그 ADC) ─────────────────────────────────
namespace sensor {
    constexpr int           THRESHOLD   = 1000;  // 이 값 이상 → 감지
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
