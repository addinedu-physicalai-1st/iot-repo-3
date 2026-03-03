/*
 * net/mqtt_manager.h — MQTT 연결 + 스트리밍 제어 콜백
 *
 * PubSubClient 래핑. DC_START/DC_STOP 수신 시 스트리밍 플래그를 제어한다.
 */
#pragma once
#include <PubSubClient.h>
#include <WiFi.h>

class MqttManager {
public:
    /**
     * MQTT 클라이언트 초기화.
     * @param broker       브로커 주소
     * @param port         포트
     * @param streamingFlag  스트리밍 상태 플래그 포인터 (콜백에서 직접 제어)
     */
    void begin(const char* broker, int port, volatile bool* streamingFlag);

    /** MQTT loop + 재연결 처리 */
    void loop();

private:
    void reconnect();
    static void _rawCallback(char* topic, byte* payload, unsigned int length);

    WiFiClient    _wifiClient;
    PubSubClient  _mqtt;
    const char*   _broker  = nullptr;
    int           _port    = 1883;
    unsigned long _lastRetryMs = 0;

    static MqttManager*  _instance;
    static volatile bool* _streamingFlag;
};
