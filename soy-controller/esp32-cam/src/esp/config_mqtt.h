/*
 * esp/config_mqtt.h — MQTT 공통 상수 (esp32-cam / esp32-devkit)
 *
 * device/control 토픽·포트. 각 프로젝트 config.h에서 include 후
 * 필요 시 config::mqtt 네임스페이스에 TOPIC_SENSOR, TOPIC_STATUS 등 추가.
 */
#pragma once

namespace config {
namespace mqtt {
    constexpr const char* TOPIC_CONTROL = "device/control";
    constexpr int         PORT          = 1883;
}
}
