/*
 * Soy-DevKit — 컨베이어 FSM 제어 (서보2 + 센서6)
 *
 * 하드웨어:
 *   DC 모터(A4950) + 서보A(1L) + 서보B(2L)
 *   S1: 1L 분류위치 감지      S2: 2L 분류위치 감지
 *   S3: 1L 통과 확인          S4: 2L 통과 확인
 *   S5: 미분류 확인
 *   S6: 카메라 위치 감지 (QR 인식용 일시정지)
 *   RGB LED
 *
 * MQTT device/control 명령:
 *   SORT_START         → IDLE → RUNNING
 *   SORT_STOP          → any  → IDLE
 *   SORT_DIR:1L        → _dirQueue.push(LINE_1L)
 *   SORT_DIR:2L        → _dirQueue.push(LINE_2L)
 *
 * 분류 흐름:
 *   1. soy-pc QR 인식 → SORT_DIR:1L or 2L → _dirQueue에 추가
 *   2. S1 상승에지 → 큐 pop:
 *      - 1L → servoA.sort() + SORTING_1L 발행
 *      - 2L → _pending2L++ + DETECTED 발행 (S2에서 처리)
 *   3. S2 상승에지 → _pending2L>0이면 servoB.sort() + SORTING_2L 발행
 *   4. S3 상승에지 → servoA.center() + SORTED_1L 발행
 *      S4 상승에지 → servoB.center() + SORTED_2L 발행
 *      S5 상승에지 → SORTED_UNCLASSIFIED 발행
 *   5. Safety timeout → 확인 센서 미응답 시 강제 복귀
 *
 * FSM 상태:
 *   IDLE    — DC OFF, 서보 0° → disable, LED 빨강
 *   RUNNING — DC ON, LED 초록
 *   PAUSED  — DC OFF, LED 노랑
 */

#include <Arduino.h>
#include <queue>

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
static ProximitySensor  s1;       // 1L 분류위치 감지
static ProximitySensor  s2;       // 2L 분류위치 감지
static ProximitySensor  s3;       // 1L 통과 확인
static ProximitySensor  s4;       // 2L 통과 확인
static ProximitySensor  s5;       // 미분류 확인
static ProximitySensor  s6;       // 카메라 위치 감지 (QR 인식용)
static Fsm              fsm;
static MqttManager      mqtt;

// ── FSM 보조 상태 ──────────────────────────────────────────────
static std::queue<SortDir> _dirQueue;      // 방향 큐 (QR 인식 시 추가)
static bool _servoASorting   = false;      // servoA 분류 중 여부
static bool _servoBSorting   = false;      // servoB 분류 중 여부
static unsigned long _servoAStartMs = 0;   // safety timeout용
static unsigned long _servoBStartMs = 0;
static int _pending2L        = 0;          // S1 통과 후 S2 대기 중인 2L 항목 수

static bool _s1Prev = false;
static bool _s2Prev = false;
static bool _s3Prev = false;
static bool _s4Prev = false;
static bool _s5Prev = false;
static bool _s6Prev = false;

static int _dcSpeed  = config::dc::DEFAULT_SPEED;
static int _sortDegA = config::servo::SORT_DEG_A;
static int _sortDegB = config::servo::SORT_DEG_B;

// 카메라 감지 상태
static bool          _cameraWaitingForDir = false;  // S6 감지 후 SORT_DIR 대기 중
static unsigned long _cameraWaitStart     = 0;      // 대기 시작 시간 (safety timeout용)
static unsigned long _cameraBlankUntil    = 0;      // 홀드 후 S6 무시 종료 시각

// MQTT 재연결 감지
static bool _mqttPrevConnected = false;

// ── FSM 상태 전이 ──────────────────────────────────────────────
static void enterState(State s) {
    Serial.printf("[FSM] %s → %s\n", fsm.stateName(),
        s == State::IDLE    ? "IDLE" :
        s == State::RUNNING ? "RUNNING" :
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
            // 큐/pending 초기화
            while (!_dirQueue.empty()) _dirQueue.pop();
            _servoASorting = false;
            _servoBSorting = false;
            _pending2L = 0;
            _cameraWaitingForDir = false;
            _cameraBlankUntil = 0;
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
            s6.sync(); _s6Prev = s6.isDetected();
            _cameraWaitingForDir = false;
            _cameraBlankUntil = 0;
            // 서보 분류 중이면 타임아웃 타이머 리셋 (PAUSED 동안 카운트 안함)
            if (_servoASorting) _servoAStartMs = millis();
            if (_servoBSorting) _servoBStartMs = millis();
            mqtt.publishStatus("RUNNING");
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
            if (fsm.state() == State::RUNNING) {
                // 이미 RUNNING → 상태 재발행만 (재진입 방지)
                mqtt.publishStatus("RUNNING");
            } else {
                enterState(State::RUNNING);
            }
            break;

        case CommandType::SORT_STOP:
            if (fsm.state() != State::IDLE) {
                enterState(State::IDLE);
            }
            break;

        case CommandType::SORT_PAUSE:
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
            _dirQueue.push(SortDir::LINE_1L);
            Serial.printf("[CMD] SORT_DIR queued: 1L (queue=%d)\n", (int)_dirQueue.size());
            if (_cameraWaitingForDir) {
                _cameraWaitingForDir = false;
                _cameraBlankUntil = millis() + config::timing::CAMERA_BLANK_MS;
                s6.sync(); _s6Prev = s6.isDetected();
                _s1Prev = false;
                _s2Prev = false;
                if (fsm.state() == State::RUNNING) dcMotor.drive(_dcSpeed);
                Serial.println("[SENSOR] SORT_DIR → camera wait released");
            }
            break;

        case CommandType::SORT_DIR_2L:
            _dirQueue.push(SortDir::LINE_2L);
            Serial.printf("[CMD] SORT_DIR queued: 2L (queue=%d)\n", (int)_dirQueue.size());
            if (_cameraWaitingForDir) {
                _cameraWaitingForDir = false;
                _cameraBlankUntil = millis() + config::timing::CAMERA_BLANK_MS;
                s6.sync(); _s6Prev = s6.isDetected();
                _s1Prev = false;
                _s2Prev = false;
                if (fsm.state() == State::RUNNING) dcMotor.drive(_dcSpeed);
                Serial.println("[SENSOR] SORT_DIR → camera wait released");
            }
            break;

        case CommandType::DC_SPEED:
            _dcSpeed = constrain(cmd.value, 150, 255);
            if (fsm.state() == State::RUNNING) dcMotor.drive(_dcSpeed);
            Serial.printf("[CMD] DC_SPEED=%d\n", _dcSpeed);
            break;

        case CommandType::SERVO_DEG_A:
            _sortDegA = constrain(cmd.value, 0, 45);
            Serial.printf("[CMD] SERVO_A=%d\n", _sortDegA);
            break;

        case CommandType::SERVO_DEG_B:
            _sortDegB = constrain(cmd.value, 0, 45);
            Serial.printf("[CMD] SERVO_B=%d\n", _sortDegB);
            break;

        default:
            break;
    }
}

// ── 카메라 위치 센서 (S6 → QR 인식용 SORT_DIR 대기) ─────────
static void handleCameraDetect() {
    if (fsm.state() == State::IDLE) return;

    unsigned long now = millis();

    // SORT_DIR 대기 중 → safety timeout만 체크
    if (_cameraWaitingForDir) {
        if (now - _cameraWaitStart >= config::timing::CAMERA_WAIT_MAX_MS) {
            _cameraWaitingForDir = false;
            _cameraBlankUntil = now + config::timing::CAMERA_BLANK_MS;
            s6.sync(); _s6Prev = s6.isDetected();
            if (fsm.state() == State::RUNNING) dcMotor.drive(_dcSpeed);
            Serial.println("[SENSOR] Camera wait TIMEOUT → force resume + blanking");
        }
        return;
    }

    // 블랭킹 기간 → S6 추적만 하고 이벤트 무시
    if (_cameraBlankUntil > 0) {
        if (now >= _cameraBlankUntil) {
            _cameraBlankUntil = 0;
            s6.sync(); _s6Prev = s6.isDetected();
        } else {
            _s6Prev = s6.isDetected();
        }
        return;
    }

    // S6 상승에지 → DC 정지, SORT_DIR 수신 대기 시작
    bool det6 = s6.isDetected();
    if (det6 && !_s6Prev) {
        dcMotor.brake();
        _cameraWaitingForDir = true;
        _cameraWaitStart = now;
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "CAMERA_DETECT");
        Serial.println("[SENSOR] S6 → waiting for SORT_DIR");
    }
    _s6Prev = det6;
}

// ── 분류위치 센서 (S1/S2 → 서보 시작) ────────────────────────
static void handleSortTrigger() {
    if (fsm.state() == State::IDLE) return;

    // 카메라 대기 중 → 센서 추적만 (DC 정지 상태 ADC 노이즈 false trigger 방지)
    if (_cameraWaitingForDir) {
        _s1Prev = s1.isDetected();
        _s2Prev = s2.isDetected();
        return;
    }

    bool det1 = s1.isDetected();
    bool det2 = s2.isDetected();

    // S1 상승에지 → 큐에서 pop하여 방향 결정
    if (det1 && !_s1Prev) {
        if (!_dirQueue.empty()) {
            SortDir dir = _dirQueue.front();
            _dirQueue.pop();

            if (dir == SortDir::LINE_1L) {
                // 1L → servoA 즉시 동작
                servoA.sort(_sortDegA);
                _servoASorting = true;
                _servoAStartMs = millis();
                mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTING_1L");
                Serial.println("[SORT] S1 + 1L → servoA sort");
            } else if (dir == SortDir::LINE_2L) {
                // 2L → S2에서 처리하도록 pending 증가
                _pending2L++;
                mqtt.publish(config::mqtt::TOPIC_SENSOR, "DETECTED");
                Serial.printf("[SORT] S1 + 2L → pending2L=%d\n", _pending2L);
            }
        } else {
            Serial.println("[WARN] S1 감지됐지만 큐 비어있음");
            mqtt.publish(config::mqtt::TOPIC_SENSOR, "DETECTED");
        }
    }

    // S2 상승에지 → pending2L이 있으면 servoB 동작
    if (det2 && !_s2Prev) {
        if (_pending2L > 0) {
            _pending2L--;
            servoB.sort(_sortDegB);
            _servoBSorting = true;
            _servoBStartMs = millis();
            mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTING_2L");
            Serial.printf("[SORT] S2 → servoB sort (pending2L=%d)\n", _pending2L);
        }
    }

    _s1Prev = det1;
    _s2Prev = det2;
}

// ── 확인 센서 + 서보 복귀 (S3/S4 → 서보 center + SORTED 발행) ──
static void handleServoConfirm() {
    if (fsm.state() == State::IDLE) {
        _s3Prev = s3.isDetected();
        _s4Prev = s4.isDetected();
        return;
    }

    // PAUSED 상태 → 센서 추적만 (서보 복귀/타임아웃 정지)
    if (fsm.state() == State::PAUSED) {
        _s3Prev = s3.isDetected();
        _s4Prev = s4.isDetected();
        return;
    }

    bool det3 = s3.isDetected();
    bool det4 = s4.isDetected();

    // S3 상승에지 → servoA 복귀 + SORTED_1L 발행
    if (det3 && !_s3Prev && _servoASorting) {
        servoA.center();
        _servoASorting = false;
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTED_1L");
        Serial.println("[CONFIRM] S3 → servoA center + SORTED_1L");
    }

    // S4 상승에지 → servoB 복귀 + SORTED_2L 발행
    if (det4 && !_s4Prev && _servoBSorting) {
        servoB.center();
        _servoBSorting = false;
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTED_2L");
        Serial.println("[CONFIRM] S4 → servoB center + SORTED_2L");
    }

    _s3Prev = det3;
    _s4Prev = det4;

    // Safety timeout: RUNNING 상태에서만 2초 후 강제 복귀
    unsigned long now = millis();
    if (_servoASorting && (now - _servoAStartMs) >= config::timing::SORT_SAFETY_TIMEOUT_MS) {
        servoA.center();
        _servoASorting = false;
        Serial.println("[TIMEOUT] servoA safety return");
    }
    if (_servoBSorting && (now - _servoBStartMs) >= config::timing::SORT_SAFETY_TIMEOUT_MS) {
        servoB.center();
        _servoBSorting = false;
        Serial.println("[TIMEOUT] servoB safety return");
    }
}

// ── 미분류 센서 (S5 → SORTED_UNCLASSIFIED 발행) ────────────────
static void handleUnclassified() {
    if (fsm.state() == State::IDLE) {
        _s5Prev = s5.isDetected();
        return;
    }

    bool det5 = s5.isDetected();
    if (det5 && !_s5Prev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTED_UNCLASSIFIED");
        Serial.println("[CONFIRM] S5 → SORTED_UNCLASSIFIED");
    }
    _s5Prev = det5;
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

    // 근접 센서 6개
    s1.begin(config::pin::SORT_POS_1L, config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s2.begin(config::pin::SORT_POS_2L, config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s3.begin(config::pin::SORT_CONFIRM_1L, config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s4.begin(config::pin::SORT_CONFIRM_2L, config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s5.begin(config::pin::SORT_CONFIRM_UNCL, config::sensor::THRESHOLD, config::sensor::DEBOUNCE_MS);
    s6.begin(config::pin::CAMERA_DETECT, 0, config::sensor::DEBOUNCE_S6_MS, true, true);  // 디지털 모드, Active-Low, 빠른 디바운스

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

    // MQTT 재연결 감지 → 현재 FSM 상태 재발행
    {
        bool nowConn = mqtt.connected();
        if (nowConn && !_mqttPrevConnected) {
            mqtt.publishStatus(fsm.stateName());
            Serial.println("[MQTT] Reconnected → re-publish state");
        }
        _mqttPrevConnected = nowConn;
    }

    // ADC 주기 디버그 (1000ms마다)
    {
        static unsigned long lastDbg = 0;
        unsigned long now = millis();
        if (now - lastDbg >= 1000) {
            Serial.printf("[DBG] S1=%d S2=%d S3=%d S4=%d S5=%d S6=%d  q=%d  state=%s  sA=%d sB=%d p2L=%d\n",
                s1.readRaw(), s2.readRaw(), s3.readRaw(), s4.readRaw(), s5.readRaw(), s6.readRaw(),
                (int)_dirQueue.size(), fsm.stateName(),
                _servoASorting, _servoBSorting, _pending2L);
            lastDbg = now;
        }
    }

    handleCameraDetect();    // S6 → QR용 일시정지
    handleSortTrigger();     // S1/S2 → 서보 시작
    handleServoConfirm();    // S3/S4 → 서보 복귀 + SORTED 발행 + timeout
    handleUnclassified();    // S5 → SORTED_UNCLASSIFIED
}
