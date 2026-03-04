/*
 * config.h — ESP32-CAM 설정 중앙 집중
 *
 * 카메라 핀 매핑, 네트워크 설정, 스트리밍 파라미터를 한 곳에서 관리한다.
 * MQTT 상수는 esp-common/esp/config_mqtt.h 에서 가져온다.
 */
#pragma once
#include <cstdint>
#include "esp/config_mqtt.h"

namespace config {

// ── 카메라 핀 (AI-Thinker ESP32-CAM 고정 배치) ──────────────
namespace camera_pin {
    constexpr int PWDN  = 32;
    constexpr int RESET = -1;    // 소프트웨어 리셋 사용
    constexpr int XCLK  = 0;
    constexpr int SIOD  = 26;    // SDA
    constexpr int SIOC  = 27;    // SCL
    constexpr int Y9    = 35;
    constexpr int Y8    = 34;
    constexpr int Y7    = 39;
    constexpr int Y6    = 36;
    constexpr int Y5    = 21;
    constexpr int Y4    = 19;
    constexpr int Y3    = 18;
    constexpr int Y2    = 5;
    constexpr int VSYNC = 25;
    constexpr int HREF  = 23;
    constexpr int PCLK  = 22;
}

// ── UDP 스트리밍 ─────────────────────────────────────────────
namespace udp {
    constexpr int PORT = 8021;
}

// ── 카메라 ───────────────────────────────────────────────────
namespace camera {
    constexpr int  JPEG_QUALITY      = 12;   // 0-63, 낮을수록 고품질
    constexpr int  XCLK_FREQ_HZ     = 20000000;
    constexpr int  FB_COUNT          = 1;
    constexpr unsigned long FRAME_INTERVAL_MS = 200;  // ~5 FPS
}

// mqtt (TOPIC_CONTROL, PORT) → esp/config_mqtt.h

}  // namespace config
