#include "net/wifi_manager.h"
#include <Arduino.h>
#include <WiFi.h>

// .env → env_script.py 로 빌드 시 주입
#ifndef WIFI_SSID
  #error ".env file is missing or env_script.py failed to inject WIFI_SSID"
#endif
#ifndef WIFI_PASS
  #error ".env file is missing or env_script.py failed to inject WIFI_PASS"
#endif

void wifi_manager::connect() {
    WiFi.mode(WIFI_STA);  // TCP/IP 스택 초기화 (lwIP mbox 준비)
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    WiFi.setSleep(false);

    Serial.print("[WiFi] connecting");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\n[WiFi] OK IP=%s\n", WiFi.localIP().toString().c_str());
}
