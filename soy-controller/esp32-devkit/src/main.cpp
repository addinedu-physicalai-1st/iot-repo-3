/*
 * Soy-DevKit — 컨베이어 FSM 제어 (서보2 + 센서5)
 *
 * 하드웨어:
 *   DC 모터(A4950) + 서보A(1L) + 서보B(2L)
 *   S1: 분류위치 감지/1L  S2: 분류위치 감지/2L
 *   S3: 1L 통과 확인      S4: 2L 통과 확인
 *   S5: 미분류 확인
 *   RGB LED
 *
 * MQTT device/control 명령:
 *   SORT_START         → IDLE → RUNNING
 *   SORT_STOP          → RUNNING → IDLE
 *   SORT_DIR:1L        → _nextSortDir = LINE_1L (S1 감지 시 사용)
 *   SORT_DIR:2L        → _nextSortDir = LINE_2L (S2 감지 시 사용)
 *
 * 분류 흐름:
 *   1. soy-pc QR 인식 → SORT_DIR:1L or 2L 발행 (S1/S2 감지 전 예약)
 *   2. S1 상승에지  → servoA 동작 (1L 분류)
 *      S2 상승에지  → servoB 동작 (2L 분류)
 *   3. S3 상승에지  → SORTED_1L 발행
 *      S4 상승에지  → SORTED_2L 발행
 *      S5 상승에지  → SORTED_UNCLASSIFIED 발행
 *
 * FSM 상태:
 *   IDLE    — DC OFF, 서보 0° → disable, LED 빨강
 *   RUNNING — DC ON, LED 초록
 *   SORTING — S1 or S2 감지 후 서보 분류 중, LED 파랑
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
static ServoMotor       servoA;   // 1L 분류
static ServoMotor       servoB;   // 2L 분류
static RgbLed           led;
static ProximitySensor  s1;       // 분류위치 / 1L
static ProximitySensor  s2;       // 분류위치 / 2L
static ProximitySensor  s3;       // 1L 통과 확인
static ProximitySensor  s4;       // 2L 통과 확인
static ProximitySensor  s5;       // 미분류 확인
static Fsm              fsm;
static MqttManager      mqtt;

// ── FSM 보조 상태 ──────────────────────────────────────────────
// SORTING 진입 시 어느 서보를 동작시킬지 기록
static SortDir _activeSortDir  = SortDir::NONE;
// S1/S2 감지 직전 soy-pc가 예약한 방향 (SORT_DIR 명령으로 설정)
static SortDir _nextSortDir    = SortDir::NONE;

static bool _s1Prev = false;
static bool _s2Prev = false;
static bool _s3Prev = false;
static bool _s4Prev = false;
static bool _s5Prev = false;

static int _dcSpeed = config::dc::DEFAULT_SPEED;

// ── 활성 서보 헬퍼 ────────────────────────────────────────────
static ServoMotor& activeServo() {
    return (_activeSortDir == SortDir::LINE_2L) ? servoB : servoA;
}

// ── FSM 상태 전이 ──────────────────────────────────────────────
static void enterState(State s) {
    Serial.printf("[FSM] %s → %s\n", fsm.stateName(),
        s == State::IDLE    ? "IDLE" :
        s == State::RUNNING ? "RUNNING" :
        s == State::SORTING ? "SORTING" :
        s == State::PAUSED  ? "PAUSED" : "?");

    fsm.enter(s);
    led.forState(s);

    switch (s) {
        case State::IDLE:
            dcMotor.brake();
            servoA.center();
            servoB.center();
            delay(200);
            servoA.disable();
            servoB.disable();
            _nextSortDir   = SortDir::NONE;
            _activeSortDir = SortDir::NONE;
            mqtt.publishStatus("IDLE");
            break;

        case State::RUNNING:
            dcMotor.drive(_dcSpeed);
            // 센서 이전 상태 동기화 (상승에지 오인 방지)
            s1.sync(); _s1Prev = s1.isDetected();
            s2.sync(); _s2Prev = s2.isDetected();
            s3.sync(); _s3Prev = s3.isDetected();
            s4.sync(); _s4Prev = s4.isDetected();
            s5.sync(); _s5Prev = s5.isDetected();
            mqtt.publishStatus("RUNNING");
            break;

        case State::SORTING:
            // 예약된 방향 스냅샷 적용
            _activeSortDir = _nextSortDir;
            // 해당 서보 동작
            if (_activeSortDir != SortDir::NONE) {
                activeServo().sort();
            }
            mqtt.publish(config::mqtt::TOPIC_SENSOR, "DETECTED");
            mqtt.publishStatus("SORTING");
            Serial.printf("[SORT] ServoActive=%s\n",
                _activeSortDir == SortDir::LINE_1L ? "A(1L)" :
                _activeSortDir == SortDir::LINE_2L ? "B(2L)" : "NONE");
            break;

        case State::PAUSED:
            dcMotor.brake();
            mqtt.publishStatus("PAUSED");
            break;

        default:
            break;
    }
}

// ── MQTT 명령 콜백 ─────────────────────────────────────────────
static void onCommand(const Command& cmd) {
    switch (cmd.type) {
        case CommandType::SORT_START:
            if (fsm.state() == State::SORTING) {
                Serial.println("[WARN] SORT_START ignored (SORTING)");
                return;
            }
            enterState(State::RUNNING);
            break;

        case CommandType::SORT_STOP:
            if (fsm.state() == State::SORTING) {
                Serial.println("[WARN] SORT_STOP ignored (SORTING)");
                return;
            }
            if (fsm.state() != State::IDLE) {
                enterState(State::IDLE);
            }
            break;

        case CommandType::SORT_PAUSE:
            if (fsm.state() == State::SORTING) {
                Serial.println("[WARN] SORT_PAUSE ignored (SORTING)");
                return;
            }
            if (fsm.state() == State::RUNNING) {
                enterState(State::PAUSED);
            }
            break;

        case CommandType::SORT_RESUME:
            if (fsm.state() == State::PAUSED) {
                enterState(State::RUNNING);
            }
            break;

        case CommandType::SORT_DIR_1L:
            _nextSortDir = SortDir::LINE_1L;
            Serial.println("[CMD] SORT_DIR reserved: 1L");
            break;

        case CommandType::SORT_DIR_2L:
            _nextSortDir = SortDir::LINE_2L;
            Serial.println("[CMD] SORT_DIR reserved: 2L");
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
            if (el >= config::timing::SORT_HOLD_MS) {
                activeServo().center();
                fsm.advanceSortPhase();
                Serial.println("[SORT] Servo → center");
            }
            break;

        case SortPhase::RETURNING:
            if (el >= config::timing::SORT_HOLD_MS + config::timing::SORT_RETURN_MS) {
                activeServo().disable();
                // nextSortDir를 소비했으므로 초기화
                _nextSortDir = SortDir::NONE;
                Serial.println("[SORT] Servo disabled → RUNNING");
                enterState(State::RUNNING);
            }
            break;
    }
}

// ── 분류위치 센서 폴링 (S1/S2 → SORTING 전이) ────────────────
static void handleSortTrigger() {
    if (fsm.state() != State::RUNNING) return;

    bool det1 = s1.isDetected();
    bool det2 = s2.isDetected();

    // S1 상승에지
    if (det1 && !_s1Prev) {
        Serial.println("[SENSOR] S1 detected → SORTING (1L)");
        if (_nextSortDir == SortDir::NONE) {
            Serial.println("[WARN] S1 감지됐지만 SORT_DIR 미예약 → SORTING(NONE)");
        }
        enterState(State::SORTING);
    }
    // S2 상승에지 (S1 동시 처리 방지: SORTING 미진입 시만)
    else if (det2 && !_s2Prev && fsm.state() == State::RUNNING) {
        Serial.println("[SENSOR] S2 detected → SORTING (2L)");
        if (_nextSortDir == SortDir::NONE) {
            Serial.println("[WARN] S2 감지됐지만 SORT_DIR 미예약 → SORTING(NONE)");
        }
        enterState(State::SORTING);
    }

    _s1Prev = det1;
    _s2Prev = det2;
}

// ── 확인 센서 폴링 (S3/S4/S5 → SORTED_* 발행) ────────────────
// FSM 상태에 무관하게 항상 폴링 (단, IDLE에서는 카운트 무시)
static void handleConfirmSensors() {
    if (fsm.state() == State::IDLE || fsm.state() == State::PAUSED) {
        // IDLE/PAUSED 중에는 이전 상태만 업데이트해 상승에지 오인 방지
        _s3Prev = s3.isDetected();
        _s4Prev = s4.isDetected();
        _s5Prev = s5.isDetected();
        return;
    }

    bool det3 = s3.isDetected();
    bool det4 = s4.isDetected();
    bool det5 = s5.isDetected();

    if (det3 && !_s3Prev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTED_1L");
        Serial.println("[CONFIRM] S3 → SORTED_1L");
    }
    if (det4 && !_s4Prev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTED_2L");
        Serial.println("[CONFIRM] S4 → SORTED_2L");
    }
    if (det5 && !_s5Prev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTED_UNCLASSIFIED");
        Serial.println("[CONFIRM] S5 → SORTED_UNCLASSIFIED");
    }

    _s3Prev = det3;
    _s4Prev = det4;
    _s5Prev = det5;
}

// ── FSM 디스패치 ─────────────────────────────────────────────
static void runFsm() {
    switch (fsm.state()) {
        case State::SORTING:
            handleSorting();
            break;
        default:
            handleSortTrigger();
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

    // 근접 센서 5개
    s1.begin(config::pin::SORT_POS_1L, config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s2.begin(config::pin::SORT_POS_2L, config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s3.begin(config::pin::SORT_CONFIRM_1L, config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s4.begin(config::pin::SORT_CONFIRM_2L, config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s5.begin(config::pin::SORT_CONFIRM_UNCL, config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);

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

    // ADC 주기 디버그 (1000ms마다)
    {
        static unsigned long lastDbg = 0;
        unsigned long now = millis();
        if (now - lastDbg >= 1000) {
            Serial.printf("[DBG] S1=%d S2=%d S3=%d S4=%d S5=%d  dir=%d  state=%s\n",
                s1.readRaw(), s2.readRaw(), s3.readRaw(), s4.readRaw(), s5.readRaw(),
                (int)_nextSortDir, fsm.stateName());
            lastDbg = now;
        }
    }

    runFsm();
    handleConfirmSensors();
}
