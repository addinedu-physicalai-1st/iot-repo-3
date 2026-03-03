#include "mqtt_manager.h"
#include "config.h"
#include <Arduino.h>

// ── static 멤버 초기화 ──────────────────────────────────────
MqttManager*  MqttManager::_instance      = nullptr;
volatile bool* MqttManager::_streamingFlag = nullptr;

#ifndef MQTT_BROKER
  #error ".env file is missing or env_script.py failed to inject MQTT_BROKER"
#endif

void MqttManager::begin(const char* broker, int port, volatile bool* streamingFlag) {
    _broker        = broker;
    _port          = port;
    _instance      = this;
    _streamingFlag = streamingFlag;

    _mqtt.setClient(_wifiClient);
    _mqtt.setServer(_broker, _port);
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

void MqttManager::reconnect() {
    if (_mqtt.connected()) return;

    Serial.print("[MQTT] connecting...");
    String clientId = "SoyCam-";
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
    char msg[64];
    unsigned int copyLen = (length < sizeof(msg) - 1) ? length : sizeof(msg) - 1;
    memcpy(msg, payload, copyLen);
    msg[copyLen] = '\0';

    Serial.printf("[MQTT RX] %s : %s\n", topic, msg);

    if (strcmp(topic, config::mqtt::TOPIC_CONTROL) != 0) return;

    if (strncmp(msg, "DC_START", 8) == 0) {
        if (_streamingFlag) *_streamingFlag = true;
        Serial.println("[CAM] Streaming ON");
    } else if (strcmp(msg, "DC_STOP") == 0) {
        if (_streamingFlag) *_streamingFlag = false;
        Serial.println("[CAM] Streaming OFF");
    }
}
