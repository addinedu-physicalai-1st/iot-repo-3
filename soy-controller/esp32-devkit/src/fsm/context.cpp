#include "fsm/context.h"
#include "fsm/state_base.h"
#include "peripheral/proximity_sensor.h"
#include "motor/servo_motor.h"
#include "net/mqtt_manager.h"

void Context::transition(StateBase* newState) {
    if (currentState) {
        Serial.printf("[FSM] %s → %s\n",
            currentState->name(), newState ? newState->name() : "NULL");
        currentState->onExit(*this);
    }
    currentState = newState;
    if (currentState) {
        currentState->onEnter(*this);
    }
}

void Context::flushAll() {
    cameraBlankUntil = 0;
    dcSoftStopStartSpeed = 0;
}

void Context::syncAllSensors() {
    s1.sync(); s1Prev = s1.isDetected();
    s2.sync(); s2Prev = s2.isDetected();
    s3.sync(); s3Prev = s3.isDetected();
    s4.sync(); s4Prev = s4.isDetected();
    s5.sync(); s5Prev = s5.isDetected();
    s6.sync(); s6Prev = s6.isDetected();
}

void Context::processSorters(unsigned long now) {
    (void)now;
    // 센서 감지만 PC에 알림. 서보 동작은 PC가 판단 후 SERVO_A/SERVO_B 명령으로 지시.

    // S1: 1L 분기 직전 — PC에만 알림 (PC가 current_item 기준으로 서보 명령 전송)
    bool det1 = s1.isDetected();
    if (det1 && !s1Prev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "S1_DETECTED");
        Serial.println("[SENSOR] S1_DETECTED");
    }
    s1Prev = det1;

    // S2: 2L 분기 직전
    bool det2 = s2.isDetected();
    if (det2 && !s2Prev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "S2_DETECTED");
        Serial.println("[SENSOR] S2_DETECTED");
    }
    s2Prev = det2;

    // S3/S4/S5: 카운팅 센서 감지 — PC에만 알림 (PC가 1L/2L/미분류 카운팅)
    bool det3 = s3.isDetected();
    if (det3 && !s3Prev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "S3_DETECTED");
        Serial.println("[SENSOR] S3_DETECTED");
    }
    s3Prev = det3;

    bool det4 = s4.isDetected();
    if (det4 && !s4Prev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "S4_DETECTED");
        Serial.println("[SENSOR] S4_DETECTED");
    }
    s4Prev = det4;

    bool det5 = s5.isDetected();
    if (det5 && !s5Prev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "S5_DETECTED");
        Serial.println("[SENSOR] S5_DETECTED");
    }
    s5Prev = det5;
}
