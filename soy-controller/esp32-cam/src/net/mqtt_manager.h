/*
 * net/mqtt_manager.h — MQTT 연결 + 스트리밍 제어 콜백
 *
 * PubSubClient 래핑. SORT_START/SORT_STOP 수신 시 스트리밍 상태를 제어한다.
 */
#pragma once
#include <PubSubClient.h>
#include <WiFi.h>

#include "esp_camera.h"
#include "stream_state.h"

class MqttManager {
public:
    /**
     * MQTT 클라이언트 초기화.
     * @param broker        브로커 주소
     * @param port          포트
     * @param streamingState  스트리밍 상태 포인터 (콜백에서 SORT_START/STOP 시 설정)
     */
    void begin(const char* broker, int port, volatile StreamingState* streamingState);

    /** MQTT loop + 재연결 처리 */
    void loop();

private:
    void reconnect();
    static void _rawCallback(char* topic, byte* payload, unsigned int length);
    static void _handleCameraCommand(const char* cmd);

    WiFiClient    _wifiClient;
    PubSubClient  _mqtt;
    const char*   _broker  = nullptr;
    int           _port    = 1883;
    unsigned long _lastRetryMs = 0;

    static MqttManager*  _instance;
    static volatile StreamingState* _streamingState;
};
