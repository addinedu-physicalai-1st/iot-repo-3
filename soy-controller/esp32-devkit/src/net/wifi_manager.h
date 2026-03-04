/*
 * net/wifi_manager.h — WiFi 연결 관리 (esp32-cam / esp32-devkit 공통)
 *
 * STA 모드로 WiFi에 연결. SSID/PASS는 빌드 시 .env → env_script.py 주입.
 */
#pragma once

namespace wifi_manager {
    /** WiFi STA 모드로 연결. 블로킹 대기. TCP/IP 스택 초기화 후 연결. */
    void connect();
}
