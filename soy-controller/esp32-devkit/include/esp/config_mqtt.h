/*
 * esp/config_mqtt.h — MQTT 공통 상수 (esp32-cam / esp32-devkit)
 */
#pragma once

namespace config {
namespace mqtt {
    constexpr const char* TOPIC_CONTROL = "device/control";
    constexpr int         PORT          = 1883;
}
}
