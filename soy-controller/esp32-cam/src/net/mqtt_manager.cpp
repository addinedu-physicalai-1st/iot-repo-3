#include "mqtt_manager.h"
#include "config.h"
#include <Arduino.h>

// ── static 멤버 초기화 ──────────────────────────────────────
MqttManager*  MqttManager::_instance       = nullptr;
volatile StreamingState* MqttManager::_streamingState = nullptr;

#ifndef MQTT_BROKER
  #error ".env file is missing or env_script.py failed to inject MQTT_BROKER"
#endif

void MqttManager::begin(const char* broker, int port, volatile StreamingState* streamingState) {
    _broker         = broker;
    _port           = port;
    _instance       = this;
    _streamingState = streamingState;

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

    if (strcmp(msg, "SORT_START") == 0) {
        if (_streamingState) *_streamingState = StreamingState::STREAMING;
        Serial.println("[CAM] Streaming ON (SORT_START)");
    } else if (strcmp(msg, "SORT_STOP") == 0) {
        if (_streamingState) *_streamingState = StreamingState::IDLE;
        Serial.println("[CAM] Streaming OFF (SORT_STOP)");
    } else if (strncmp(msg, "CAM:", 4) == 0) {
        _handleCameraCommand(msg + 4);
    }
}

void MqttManager::_handleCameraCommand(const char* cmd) {
    sensor_t* s = esp_camera_sensor_get();
    if (!s) {
        Serial.println("[CAM] sensor_t is NULL");
        return;
    }

    // "KEY:VALUE" 파싱
    char key[32] = {};
    int val = 0;
    const char* colon = strchr(cmd, ':');
    if (!colon) return;
    size_t keyLen = colon - cmd;
    if (keyLen >= sizeof(key)) return;
    memcpy(key, cmd, keyLen);
    key[keyLen] = '\0';
    val = atoi(colon + 1);

    if      (strcmp(key, "quality")      == 0) s->set_quality(s, val);
    else if (strcmp(key, "framesize")    == 0) s->set_framesize(s, (framesize_t)val);
    else if (strcmp(key, "brightness")   == 0) s->set_brightness(s, val);
    else if (strcmp(key, "contrast")     == 0) s->set_contrast(s, val);
    else if (strcmp(key, "saturation")   == 0) s->set_saturation(s, val);
    else if (strcmp(key, "sharpness")    == 0) s->set_sharpness(s, val);
    else if (strcmp(key, "special_effect") == 0) s->set_special_effect(s, val);
    else if (strcmp(key, "whitebal")     == 0) s->set_whitebal(s, val);
    else if (strcmp(key, "awb_gain")     == 0) s->set_awb_gain(s, val);
    else if (strcmp(key, "wb_mode")      == 0) s->set_wb_mode(s, val);
    else if (strcmp(key, "exposure_ctrl") == 0) s->set_exposure_ctrl(s, val);
    else if (strcmp(key, "aec2")         == 0) s->set_aec2(s, val);
    else if (strcmp(key, "ae_level")     == 0) s->set_ae_level(s, val);
    else if (strcmp(key, "aec_value")    == 0) s->set_aec_value(s, val);
    else if (strcmp(key, "gain_ctrl")    == 0) s->set_gain_ctrl(s, val);
    else if (strcmp(key, "agc_gain")     == 0) s->set_agc_gain(s, val);
    else if (strcmp(key, "gainceiling")  == 0) s->set_gainceiling(s, (gainceiling_t)val);
    else if (strcmp(key, "bpc")          == 0) s->set_bpc(s, val);
    else if (strcmp(key, "wpc")          == 0) s->set_wpc(s, val);
    else if (strcmp(key, "raw_gma")      == 0) s->set_raw_gma(s, val);
    else if (strcmp(key, "lenc")         == 0) s->set_lenc(s, val);
    else if (strcmp(key, "hmirror")      == 0) s->set_hmirror(s, val);
    else if (strcmp(key, "vflip")        == 0) s->set_vflip(s, val);
    else if (strcmp(key, "dcw")          == 0) s->set_dcw(s, val);
    else {
        Serial.printf("[CAM] unknown key: %s\n", key);
        return;
    }

    Serial.printf("[CAM] %s = %d\n", key, val);
}
