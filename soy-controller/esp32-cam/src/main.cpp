/*
 * ESP32-CAM — MQTT 제어 UDP JPEG 스트리밍
 *
 * 동작:
 *   부팅 → WiFi + MQTT 연결 → 대기
 *   SORT_START 수신 → UDP JPEG 스트리밍 시작
 *   SORT_STOP  수신 → 스트리밍 중지
 *
 * .env 주입: WIFI_SSID, WIFI_PASS, MQTT_BROKER, UDP_IP
 */

#include <Arduino.h>

// 브라운아웃(전압 강하에 의한 재부팅 루프) 방지용 헤더
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"

// ── 프로젝트 모듈 ──────────────────────────────────────────────
#include "config.h"
#include "stream_state.h"
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

// 스트리밍 상태 (MQTT 콜백에서 설정, runFsm()에서 switch로 분기)
static volatile StreamingState _streamingState = StreamingState::IDLE;

// ── FSM 핸들러 ─────────────────────────────────────────────────
static void handleStreaming() {
    camera_fb_t* fb = camera.capture();
    if (fb) {
        streamer.sendFrame(fb);
        camera.returnFrame(fb);
    }
    delay(config::camera::FRAME_INTERVAL_MS);
}

/** FSM 디스패치 (esp32-devkit과 동일 패턴: loop에서 mqtt.loop() 후 runFsm 호출) */
static void runFsm() {
    switch (_streamingState) {
        case StreamingState::STREAMING:
            handleStreaming();
            break;
        case StreamingState::IDLE:
        default:
            break;
    }
}

// ══════════════════════════════════════════════════════════════
// Setup
// ══════════════════════════════════════════════════════════════
void setup() {
    // 브라운아웃 방지: 카메라/WiFi 초기화 전에 반드시 먼저 실행 (전압 강하 시 리부팅 루프 방지)
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    Serial.begin(115200);
    delay(1000);  // 전원·시리얼 안정화
    Serial.println("\n=== Soy CAM Booting ===");

    // 하드웨어 초기화 (카메라만; UDP/MQTT는 WiFi 이후)
    if (!camera.begin()) {
        while (true) delay(1000);  // 카메라 실패 시 정지
    }

    // WiFi (TCP/IP 스택 초기화 — 반드시 streamer/MQTT보다 먼저)
    wifi_manager::connect();

    streamer.begin(UDP_IP, config::udp::PORT);

    // MQTT
    mqtt.begin(MQTT_BROKER, config::mqtt::PORT, &_streamingState);

    // 부팅 완료
    Serial.println("=== Boot complete. Waiting for SORT_START ===");
}

// ══════════════════════════════════════════════════════════════
// Loop
// ══════════════════════════════════════════════════════════════
void loop() {
    mqtt.loop();
    runFsm();
}
