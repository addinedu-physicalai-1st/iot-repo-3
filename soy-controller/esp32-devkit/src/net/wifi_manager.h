/*
 * net/wifi_manager.h — WiFi 연결 관리
 *
 * STA 모드로 WiFi에 연결한다. SSID/PASS는 빌드 시 주입 (.env → env_script.py).
 */
#pragma once

namespace wifi_manager {
    /** WiFi STA 모드로 연결. 블로킹 대기. */
    void connect();
}
