/*
 * net/mqtt_manager.h — MQTT 연결 + 발행/구독 관리
 */
#pragma once
#include <PubSubClient.h>
#include <WiFi.h>
#include "command.h"

using CommandCallback = void(*)(const Command& cmd);

class MqttManager {
public:
    void begin(const char* broker, int port, CommandCallback onCommand);
    void loop();
    void publish(const char* topic, const char* payload);
    void publishStatus(const char* stateName);
    bool connected() { return _mqtt.connected(); }
private:
    void reconnect();
    static void _rawCallback(char* topic, byte* payload, unsigned int length);
    WiFiClient    _wifiClient;
    PubSubClient  _mqtt;
    const char*   _broker  = nullptr;
    int           _port    = 1883;
    unsigned long _lastRetryMs = 0;
    static MqttManager*   _instance;
    static CommandCallback _onCommand;
};
