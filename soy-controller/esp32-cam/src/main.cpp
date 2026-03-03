/*
 * ESP32-CAM — MQTT 제어 UDP JPEG 스트리밍
 *
 * 동작:
 *   부팅 → WiFi + MQTT 연결 → 대기
 *   DC_START 수신 → UDP JPEG 스트리밍 시작
 *   DC_STOP  수신 → 스트리밍 중지
 *
 * .env 주입: WIFI_SSID, WIFI_PASS, MQTT_BROKER, UDP_IP
 */

#include <Arduino.h>

// 브라운아웃(전압 강하에 의한 재부팅 루프) 방지용 헤더
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ── 프로젝트 모듈 ──────────────────────────────────────────────
#include "config.h"
#include "stream/camera_capture.h"
#include "stream/udp_streamer.h"
#include "net/wifi_manager.h"
#include "net/mqtt_manager.h"

// .env 주입 검증 (UDP_IP)
#ifndef UDP_IP
  #error ".env file is missing or env_script.py failed to inject UDP_IP"
#endif

// ── 전역 인스턴스 ──────────────────────────────────────────────
static CameraCapture camera;
static UdpStreamer    streamer;
static MqttManager   mqtt;

// 스트리밍 상태 플래그
static volatile bool _streaming = false;

// ══════════════════════════════════════════════════════════════
// Setup
// ══════════════════════════════════════════════════════════════
void setup() {
    // 브라운아웃 방지
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    Serial.begin(115200);
    delay(1000);

    // 카메라 초기화
    if (!camera.begin()) {
        while (true) delay(1000);  // 카메라 실패 시 정지
    }

    // WiFi
    wifi_manager::connect();

    // UDP 스트리머
    streamer.begin(UDP_IP, config::udp::PORT);

    // MQTT
    mqtt.begin(MQTT_BROKER, config::mqtt::PORT, &_streaming);

    Serial.println("[READY] Waiting for DC_START command...");
}

// ══════════════════════════════════════════════════════════════
// Loop
// ══════════════════════════════════════════════════════════════
void loop() {
    // MQTT 유지
    mqtt.loop();

    // DC_START 수신 시에만 스트리밍
    if (_streaming) {
        camera_fb_t* fb = camera.capture();
        if (fb) {
            streamer.sendFrame(fb);
            camera.returnFrame(fb);
        }
        delay(config::camera::FRAME_INTERVAL_MS);
    }
}
