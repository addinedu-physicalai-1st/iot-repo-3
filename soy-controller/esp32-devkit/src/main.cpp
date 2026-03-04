/*
 * Soy-DevKit — 컨베이어 FSM 제어
 *
 * 하드웨어: DC모터(A4950) + 서보(1개) + 근접센서 + RGB LED
 * 통신    : WiFi + MQTT (PubSubClient)
 * 빌드    : .env → env_script.py 자동 주입 (WIFI_SSID, WIFI_PASS, MQTT_BROKER)
 *
 * FSM 상태:
 *   IDLE    — 대기. DC OFF, LED 빨강
 *   RUNNING — 공정 진행. DC ON, LED 초록. DC는 STOP 명령/에러 전까지 계속 동작
 *   SORTING — 근접 감지 → 서보 분류. DC 유지, LED 파랑
 *   WARNING — 미등록 QR 경고. DC 유지, LED 노랑 깜빡임, 자동 RUNNING 복귀
 */

#include <Arduino.h>

// ── 프로젝트 모듈 ──────────────────────────────────────────────
#include "config.h"
#include "command.h"
#include "fsm.h"
#include "motor/dc_motor.h"
#include "motor/servo_motor.h"
#include "peripheral/rgb_led.h"
#include "peripheral/proximity_sensor.h"
#include "net/wifi_manager.h"
#include "net/mqtt_manager.h"

// ── 전역 인스턴스 ──────────────────────────────────────────────
static DcMotor          dcMotor;
static ServoMotor       servo;
static RgbLed           led;
static ProximitySensor  prox;
static Fsm              fsm;
static MqttManager      mqtt;

// ── FSM 보조 상태 ──────────────────────────────────────────────
static SortDir _currentSortDir = SortDir::NONE;
static SortDir _activeSortDir  = SortDir::NONE;  // SORTING 진입 시 스냅샷
static bool    _sensorPrev     = false;
static int     _dcSpeed        = config::dc::DEFAULT_SPEED;

// ── FSM 상태 전이 ──────────────────────────────────────────────
static void enterState(State s) {
    Serial.printf("[FSM] %s → %s\n", fsm.stateName(),
        (s == State::IDLE ? "IDLE" :
         s == State::RUNNING ? "RUNNING" :
         s == State::SORTING ? "SORTING" : "WARNING"));

    fsm.enter(s);
    led.forState(s);

    switch (s) {
        case State::IDLE:
            dcMotor.brake();
            servo.center();
            delay(200);
            servo.disable();
            _currentSortDir = SortDir::NONE;
            mqtt.publishStatus("IDLE");
            break;

        case State::RUNNING:
            dcMotor.drive(_dcSpeed);
            prox.sync();
            _sensorPrev = prox.isDetected();
            mqtt.publishStatus("RUNNING");
            break;

        case State::SORTING:
            _activeSortDir = _currentSortDir;
            if (_activeSortDir != SortDir::NONE) {
                servo.sort();
            } else {
                servo.center();
            }
            mqtt.publish(config::mqtt::TOPIC_SENSOR, "DETECTED");
            mqtt.publishStatus("SORTING");
            Serial.println("[SORT] Servo → sort position");
            break;

        case State::WARNING:
            mqtt.publishStatus("WARNING");
            Serial.println("[WARNING] Unclassified item");
            break;
    }
}

// ── MQTT 명령 콜백 (soy-server는 SORT_START/SORT_STOP만 발행) ───
static void onCommand(const Command& cmd) {
    switch (cmd.type) {
        case CommandType::SORT_START:
            if (fsm.state() == State::SORTING) {
                Serial.println("[WARN] SORT_START ignored (SORTING in progress)");
                return;
            }
            enterState(State::RUNNING);
            break;

        case CommandType::SORT_STOP:
            if (fsm.state() == State::SORTING) {
                Serial.println("[WARN] SORT_STOP ignored (SORTING in progress)");
                return;
            }
            if (fsm.state() != State::IDLE) {
                enterState(State::IDLE);
            }
            break;

        default:
            break;
    }
}

// ── SORTING 단계 처리 ─────────────────────────────────────────
static void handleSorting() {
    unsigned long el = fsm.elapsed();

    switch (fsm.sortPhase()) {
        case SortPhase::HOLDING:
            // Phase 1: 분류 위치 유지
            if (el >= config::timing::SORT_HOLD_MS) {
                servo.center();
                fsm.advanceSortPhase();
                Serial.println("[SORT] Servo → center");
            }
            break;

        case SortPhase::RETURNING:
            // Phase 2: 복귀 후 대기 완료 → RUNNING
            if (el >= config::timing::SORT_HOLD_MS + config::timing::SORT_RETURN_MS) {
                servo.disable();

                // 분류 결과 발행
                const char* result = nullptr;
                switch (_activeSortDir) {
                    case SortDir::LINE_1L:
                        result = "SORTED_1L";
                        break;
                    case SortDir::LINE_2L:
                        result = "SORTED_2L";
                        break;
                    case SortDir::NONE:
                        result = "SORTED_UNCLASSIFIED";
                        break;
                }
                mqtt.publish(config::mqtt::TOPIC_SENSOR, result);
                Serial.printf("[SORT] Complete → %s\n", result);

                enterState(State::RUNNING);
            }
            break;
    }
}

// ── WARNING 상태 처리 ─────────────────────────────────────────
static void handleWarning() {
    unsigned long el = fsm.elapsed();

    // 노랑 LED 깜빡임 (250ms 주기)
    if ((el / 250) % 2 == 0) {
        led.yellow();
    } else {
        led.off();
    }

    // 자동 RUNNING 복귀
    if (el >= config::timing::WARNING_MS) {
        Serial.println("[WARNING] Timeout → RUNNING");
        enterState(State::RUNNING);
    }
}

// ── 근접 감지 폴링 ───────────────────────────────────────────
static void handleProximity() {
    if (fsm.state() != State::RUNNING) return;

    bool det = prox.isDetected();

    // 상태 변경 시 MQTT 발행
    if (det != _sensorPrev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, det ? "PROXIMITY:1" : "PROXIMITY:0");
        Serial.printf("[SENSOR] Proximity: %d\n", det);
    }

    // 상승 에지 (false→true) + sort_dir 설정 시 → SORTING
    if (det && !_sensorPrev) {
        if (_currentSortDir != SortDir::NONE) {
            Serial.println("[SENSOR] Object detected → SORTING");
            enterState(State::SORTING);
        } else {
            Serial.println("[SENSOR] Object detected but no sort_dir set → skip");
        }
    }

    _sensorPrev = det;
}

// ── FSM 디스패치 ─────────────────────────────────────────────
/** esp32-cam과 동일 패턴: loop에서 mqtt.loop() 후 runFsm() 호출 */
static void runFsm() {
    switch (fsm.state()) {
        case State::SORTING:
            handleSorting();
            break;
        case State::WARNING:
            handleWarning();
            break;
        default:
            handleProximity();
            break;
    }
}

// ══════════════════════════════════════════════════════════════
// Setup
// ══════════════════════════════════════════════════════════════
void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== Soy DevKit Booting ===");

    // 하드웨어 초기화
    dcMotor.begin(config::pin::DC_IN1, config::pin::DC_IN2,
                  config::dc::LEDC_CHANNEL, config::dc::FREQ_HZ,
                  config::dc::RESOLUTION_BITS);

    servo.begin(config::pin::SERVO,
                config::servo::MIN_US, config::servo::MAX_US);

    led.begin(config::pin::LED_R, config::pin::LED_G, config::pin::LED_B);

    prox.begin(config::pin::SENSOR,
               config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);

    // WiFi
    wifi_manager::connect();

    // MQTT
    mqtt.begin(MQTT_BROKER, config::mqtt::PORT, onCommand);

    // 부팅 완료 → IDLE
    led.red();
    mqtt.publishStatus("IDLE");

    Serial.println("=== Boot complete. State: IDLE ===");
}

// ══════════════════════════════════════════════════════════════
// Loop
// ══════════════════════════════════════════════════════════════
void loop() {
    mqtt.loop();

    // 근접센서 ADC 실시간 디버그 (500ms마다)
    {
        static unsigned long lastAdcDbg = 0;
        unsigned long now = millis();
        if (now - lastAdcDbg >= 500) {
            int raw = prox.readRaw();
            Serial.printf("[DBG] ADC=%4d  det=%d  prev=%d  dir=%d  state=%s\n",
                raw,
                (raw >= config::sensor::THRESHOLD) ? 1 : 0,
                _sensorPrev ? 1 : 0,
                (int)_currentSortDir,
                fsm.stateName());
            lastAdcDbg = now;
        }
    }

    runFsm();
}
