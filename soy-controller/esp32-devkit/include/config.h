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
    constexpr int DC_IN1   = 27;
    constexpr int DC_IN2   = 13;
    constexpr int SERVO_A  = 14;
    constexpr int SERVO_B  = 15;
    constexpr int SORT_POS_1L      = 34;
    constexpr int SORT_POS_2L      = 35;
    constexpr int SORT_CONFIRM_1L  = 32;
    constexpr int SORT_CONFIRM_2L  = 33;
    constexpr int SORT_CONFIRM_UNCL= 36;
    constexpr int CAMERA_DETECT    = 39;
    constexpr int LED_R    = 25;
    constexpr int LED_G    = 26;
    constexpr int LED_B    = 4;
}

namespace dc {
    constexpr int LEDC_CHANNEL    = 0;
    constexpr int FREQ_HZ         = 5000;
    constexpr int RESOLUTION_BITS = 8;
    constexpr int DEFAULT_SPEED   = 175;
    /** 위치센서(S6) 감지 시 DC 모터 소프트 정지 시간(ms). 클수록 천천히 정지. 0이면 즉시 정지. */
    constexpr unsigned long SOFT_STOP_DURATION_MS = 450;
}

namespace servo {
    constexpr int INIT_DEG   =  0;
    constexpr int CENTER_DEG =  0;
    constexpr int SORT_DEG_A = 43;
    constexpr int SORT_DEG_B = 35;
    constexpr int MIN_US     = 544;
    constexpr int MAX_US     = 2400;
}

namespace sensor {
    constexpr int           THRESHOLD    = 800;
    constexpr int           THRESHOLD_S6 = 3600;
    constexpr unsigned long DEBOUNCE_MS  = 50;
    constexpr unsigned long DEBOUNCE_S6_MS = 10;
    /** S1: 디바운스 해제(0). 센서 감지 즉시 PC에 전달. */
    constexpr unsigned long DEBOUNCE_S1_MS = 0;
}

namespace timing {
    constexpr unsigned long SORT_SAFETY_TIMEOUT_MS = 3000;
    /** 카메라 위치(S6) 정지 후 QR 미인식 대기시간. 초과 시 CAMERA_TIMEOUT 발행. */
    constexpr unsigned long CAMERA_WAIT_MAX_MS     = 1000;
    constexpr unsigned long CAMERA_BLANK_MS        = 3000;
    constexpr unsigned long LED_BLINK_MS           = 500;
    constexpr unsigned long SOFT_STOP_DURATION_MS  = 250;  // S6 감지 시 감속 정지 시간
}

namespace queue {
    constexpr int MAX_DIR_QUEUE_SIZE = 1;  // PC가 로직 관장, 디바이스는 미사용
}

namespace mqtt {
    constexpr const char* TOPIC_SENSOR  = "device/sensor";
    constexpr const char* TOPIC_STATUS  = "device/status";
}

}  // namespace config
