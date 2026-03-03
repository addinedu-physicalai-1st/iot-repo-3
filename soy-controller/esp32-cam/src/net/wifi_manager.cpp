#include "wifi_manager.h"
#include <Arduino.h>
#include <WiFi.h>

// .env 파일에서 빌드 시 자동 주입 (env_script.py)
#ifndef WIFI_SSID
  #error ".env file is missing or env_script.py failed to inject WIFI_SSID"
#endif
#ifndef WIFI_PASS
  #error ".env file is missing or env_script.py failed to inject WIFI_PASS"
#endif

void wifi_manager::connect() {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    WiFi.setSleep(false);
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\n[OK] WiFi Connected! IP: %s\n", WiFi.localIP().toString().c_str());
}
