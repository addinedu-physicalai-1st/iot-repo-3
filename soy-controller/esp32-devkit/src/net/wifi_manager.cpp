#include "wifi_manager.h"
#include <Arduino.h>
#include <WiFi.h>

// .env 파일에서 빌드 시 자동 주입 (env_script.py)
#ifndef WIFI_SSID
  #error "WIFI_SSID not injected. Check .env and env_script.py"
#endif
#ifndef WIFI_PASS
  #error "WIFI_PASS not injected. Check .env and env_script.py"
#endif

void wifi_manager::connect() {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("[WiFi] connecting");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\n[WiFi] OK IP=%s\n", WiFi.localIP().toString().c_str());
}
