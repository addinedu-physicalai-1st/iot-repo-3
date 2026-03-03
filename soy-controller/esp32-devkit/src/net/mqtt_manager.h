/*
 * net/mqtt_manager.h — MQTT 연결 + 발행/구독 관리
 *
 * PubSubClient 래핑. 명령 수신 시 Command 구조체로 파싱하여 콜백 전달.
 */
#pragma once
#include <PubSubClient.h>
#include <WiFi.h>
#include "command.h"

// MQTT 콜백 함수 포인터 타입 (Command 구조체를 전달)
using CommandCallback = void(*)(const Command& cmd);

class MqttManager {
public:
    /**
     * MQTT 클라이언트 초기화.
     * @param broker    브로커 주소 (빌드 시 .env에서 주입)
     * @param port      포트 (기본 1883)
     * @param onCommand 명령 수신 콜백
     */
    void begin(const char* broker, int port, CommandCallback onCommand);

    /** MQTT loop 호출 + 재연결 처리. loop() 에서 매 틱 호출. */
    void loop();

    /** 토픽에 페이로드 발행 */
    void publish(const char* topic, const char* payload);

    /** FSM 상태를 JSON 형식으로 발행: {"state":"XXX"} */
    void publishStatus(const char* stateName);

    /** 연결 여부 */
    bool connected() { return _mqtt.connected(); }

private:
    void reconnect();

    // PubSubClient 원본 콜백 → Command 파싱 → 사용자 콜백 호출
    static void _rawCallback(char* topic, byte* payload, unsigned int length);

    WiFiClient    _wifiClient;
    PubSubClient  _mqtt;
    const char*   _broker  = nullptr;
    int           _port    = 1883;
    unsigned long _lastRetryMs = 0;

    // static 콜백에서 접근하기 위한 싱글톤 포인터
    static MqttManager*   _instance;
    static CommandCallback _onCommand;
};
