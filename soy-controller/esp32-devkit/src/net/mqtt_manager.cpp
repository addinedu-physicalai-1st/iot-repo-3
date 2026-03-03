#include "mqtt_manager.h"
#include "config.h"
#include <Arduino.h>

// ── static 멤버 초기화 ──────────────────────────────────────
MqttManager*   MqttManager::_instance  = nullptr;
CommandCallback MqttManager::_onCommand = nullptr;

// .env 파일에서 빌드 시 자동 주입 (env_script.py)
#ifndef MQTT_BROKER
  #error "MQTT_BROKER not injected. Check .env and env_script.py"
#endif

void MqttManager::begin(const char* broker, int port, CommandCallback onCommand) {
    _broker    = broker;
    _port      = port;
    _instance  = this;
    _onCommand = onCommand;

    _mqtt.setClient(_wifiClient);
    _mqtt.setServer(_broker, _port);
    _mqtt.setSocketTimeout(15);
    _mqtt.setCallback(_rawCallback);

    reconnect();
}

void MqttManager::loop() {
    if (!_mqtt.connected()) {
        unsigned long now = millis();
        if (now - _lastRetryMs > 5000) {
            reconnect();
            _lastRetryMs = now;
        }
    } else {
        _mqtt.loop();
    }
}

void MqttManager::publish(const char* topic, const char* payload) {
    _mqtt.publish(topic, payload);
}

void MqttManager::publishStatus(const char* stateName) {
    char buf[64];
    snprintf(buf, sizeof(buf), "{\"state\":\"%s\"}", stateName);
    _mqtt.publish(config::mqtt::TOPIC_STATUS, buf);
    Serial.printf("[STATUS] %s\n", buf);
}

void MqttManager::reconnect() {
    if (_mqtt.connected()) return;

    Serial.print("[MQTT] connecting...");
    String clientId = "SoyDevKit-";
    clientId += String(random(0xffff), HEX);

    if (_mqtt.connect(clientId.c_str())) {
        Serial.println("OK");
        _mqtt.subscribe(config::mqtt::TOPIC_CONTROL);
    } else {
        Serial.printf("failed, rc=%d (retry in 5s)\n", _mqtt.state());
    }
}

void MqttManager::_rawCallback(char* topic, byte* payload, unsigned int length) {
    // 페이로드를 null-terminated 문자열로 변환
    char msg[128];
    unsigned int copyLen = (length < sizeof(msg) - 1) ? length : sizeof(msg) - 1;
    memcpy(msg, payload, copyLen);
    msg[copyLen] = '\0';

    Serial.printf("[MQTT RX] %s : %s\n", topic, msg);

    // control 토픽만 처리
    if (strcmp(topic, config::mqtt::TOPIC_CONTROL) != 0) return;

    // 명령 파싱 후 콜백 전달
    Command cmd = Command::parse(msg);
    if (_onCommand && cmd.type != CommandType::UNKNOWN) {
        _onCommand(cmd);
    }
}
