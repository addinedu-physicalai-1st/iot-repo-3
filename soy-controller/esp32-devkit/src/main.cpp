/*
 * Soy-DevKit — 컨베이어 HFSM 제어 (State 디자인패턴)
 *
 * 아키텍처:
 *   Context(공유 데이터) + StateBase(인터페이스) + 5개 상태 클래스
 *   전역 플래그 제거, 모든 로직이 상태 클래스 내부로 캡슐화됨.
 *   (단, 분류기 서보/센서 제어는 상태에 종속되지 않고 백그라운드로 처리)
 *
 * 상태: IDLE / CONVEYING / CAMERA_HOLD / PAUSED / ERROR
 *
 * main.cpp는 하드웨어 초기화 + Context 생성 + loop() 위임만 담당.
 */

#include <Arduino.h>

// ── 하드웨어 드라이버 ──────────────────────────────────────────
#include "config.h"
#include "command.h"
#include "motor/dc_motor.h"
#include "motor/servo_motor.h"
#include "peripheral/rgb_led.h"
#include "peripheral/proximity_sensor.h"
#include "net/wifi_manager.h"
#include "net/mqtt_manager.h"

// ── FSM State 패턴 ──────────────────────────────────────────────
#include "fsm/context.h"
#include "fsm/state_base.h"
#include "fsm/idle_state.h"
#include "fsm/conveying_state.h"
#include "fsm/camera_hold_state.h"
#include "fsm/paused_state.h"
#include "fsm/error_state.h"

// ── 하드웨어 인스턴스 (정적) ────────────────────────────────────
static DcMotor          dcMotor;
static ServoMotor       servoA;
static ServoMotor       servoB;
static RgbLed           led;
static ProximitySensor  s1, s2, s3, s4, s5, s6;
static MqttManager      mqtt;

// ── 상태 인스턴스 (정적 — 힙 할당 없음) ─────────────────────────
IdleState       idleState;
ConveyingState  conveyingState;
CameraHoldState cameraHoldState;
PausedState     pausedState;
ErrorState      errorState;

// ── Context (모든 상태가 공유) ───────────────────────────────────
static Context ctx(
    dcMotor, servoA, servoB, led,
    s1, s2, s3, s4, s5, s6,
    mqtt
);

// MQTT 재연결 감지
static bool _mqttPrevConnected = false;

// ── MQTT 명령 콜백 → 현재 상태에 위임 ─────────────────────────
static void onCommand(const Command& cmd) {
    if (ctx.currentState && cmd.type != CommandType::UNKNOWN) {
        ctx.currentState->onCommand(ctx, cmd);
    }
}

// ══════════════════════════════════════════════════════════════
// Setup
// ══════════════════════════════════════════════════════════════
void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== Soy DevKit (State Pattern HFSM) ===");

    // DC 모터
    dcMotor.begin(config::pin::DC_IN1, config::pin::DC_IN2,
                  config::dc::LEDC_CHANNEL, config::dc::FREQ_HZ,
                  config::dc::RESOLUTION_BITS);

    // 서보 A (1L) → MCPWM_UNIT_0, 서보 B (2L) → MCPWM_UNIT_1
    servoA.begin(config::pin::SERVO_A, MCPWM_UNIT_0,
                 config::servo::MIN_US, config::servo::MAX_US);
    servoB.begin(config::pin::SERVO_B, MCPWM_UNIT_1,
                 config::servo::MIN_US, config::servo::MAX_US);

    // RGB LED
    led.begin(config::pin::LED_R, config::pin::LED_G, config::pin::LED_B);

    // 근접 센서 6개
    s1.begin(config::pin::SORT_POS_1L, 0, config::sensor::DEBOUNCE_S1_MS, true, true);  // S6와 동일 종류, 더 민감(디바운스 짧음)
    s2.begin(config::pin::SORT_POS_2L,      config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s3.begin(config::pin::SORT_CONFIRM_1L,  config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s4.begin(config::pin::SORT_CONFIRM_2L,  config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s5.begin(config::pin::SORT_CONFIRM_UNCL,config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s6.begin(config::pin::CAMERA_DETECT, 0, config::sensor::DEBOUNCE_S6_MS, true, true);

    // WiFi
    wifi_manager::connect();

    // MQTT
    mqtt.begin(MQTT_BROKER, config::mqtt::PORT, onCommand);

    // 부팅 → IDLE (CleanShutdown: 모든 상태 초기화)
    ctx.transition(&idleState);

    Serial.println("=== Boot complete. State: IDLE ===");
}

// ══════════════════════════════════════════════════════════════
// Loop — 현재 상태에 위임
// ══════════════════════════════════════════════════════════════
void loop() {
    mqtt.loop();

    // MQTT 재연결 → 현재 상태 재발행
    {
        bool nowConn = mqtt.connected();
        if (nowConn && !_mqttPrevConnected && ctx.currentState) {
            mqtt.publishStatus(ctx.currentState->name());
            Serial.println("[MQTT] Reconnected → re-publish state");
        }
        _mqttPrevConnected = nowConn;
    }

    // 디버그 출력 (1초마다)
    {
        static unsigned long lastDbg = 0;
        unsigned long now = millis();
        if (now - lastDbg >= 1000) {
            Serial.printf("[DBG] S1=%d S2=%d S3=%d S4=%d S5=%d S6=%d  state=%s\n",
                s1.readRaw(), s2.readRaw(), s3.readRaw(), s4.readRaw(), s5.readRaw(), s6.readRaw(),
                ctx.currentState ? ctx.currentState->name() : "NULL");
            lastDbg = now;
        }
    }

    // 현재 상태의 onLoop() 호출
    if (ctx.currentState) {
        ctx.currentState->onLoop(ctx);
    }
}
