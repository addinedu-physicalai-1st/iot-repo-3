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
    while (!dirQueue.empty()) dirQueue.pop();
    servoASorting = false;
    servoBSorting = false;
    pending2L = 0;
    cameraBlankUntil = 0;
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
    // S1: 1L 분류기 동작
    bool det1 = s1.isDetected();
    if (det1 && !s1Prev) {
        if (!dirQueue.empty()) {
            SortDir dir = dirQueue.front();
            dirQueue.pop();
            if (dir == SortDir::LINE_1L) {
                servoA.sort(sortDegA);
                servoASorting = true;
                servoAStartMs = now;
                mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTING_1L");
                Serial.println("[SORT] S1+1L → servoA");
            } else if (dir == SortDir::LINE_2L) {
                pending2L++;
                mqtt.publish(config::mqtt::TOPIC_SENSOR, "DETECTED");
                Serial.printf("[SORT] S1+2L → pending2L=%d\n", pending2L);
            }
        } else {
            Serial.println("[WARN] S1 감지 but queue empty");
            mqtt.publish(config::mqtt::TOPIC_SENSOR, "DETECTED");
        }
    }
    s1Prev = det1;

    // S2: 2L 분류기 동작
    bool det2 = s2.isDetected();
    if (det2 && !s2Prev) {
        if (pending2L > 0) {
            pending2L--;
            servoB.sort(sortDegB);
            servoBSorting = true;
            servoBStartMs = now;
            mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTING_2L");
            Serial.printf("[SORT] S2 → servoB (p2L=%d)\n", pending2L);
        }
    }
    s2Prev = det2;

    // S3: 서보A 복귀 및 확인
    bool det3 = s3.isDetected();
    if (det3 && !s3Prev && servoASorting) {
        servoA.center();
        servoASorting = false;
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTED_1L");
        Serial.println("[CONFIRM] S3 → SORTED_1L");
    }
    s3Prev = det3;

    // S4: 서보B 복귀 및 확인
    bool det4 = s4.isDetected();
    if (det4 && !s4Prev && servoBSorting) {
        servoB.center();
        servoBSorting = false;
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTED_2L");
        Serial.println("[CONFIRM] S4 → SORTED_2L");
    }
    s4Prev = det4;

    // S5: 미분류 감지
    bool det5 = s5.isDetected();
    if (det5 && !s5Prev) {
        mqtt.publish(config::mqtt::TOPIC_SENSOR, "SORTED_UNCLASSIFIED");
        Serial.println("[CONFIRM] S5 → SORTED_UNCLASSIFIED");
    }
    s5Prev = det5;

    // Safety timeout: 서보A (2s 초과 시 원위치)
    if (servoASorting && (now - servoAStartMs) >= config::timing::SORT_SAFETY_TIMEOUT_MS) {
        servoA.center();
        servoASorting = false;
        Serial.println("[TIMEOUT] servoA safety return");
    }
    // Safety timeout: 서보B (2s 초과 시 원위치)
    if (servoBSorting && (now - servoBStartMs) >= config::timing::SORT_SAFETY_TIMEOUT_MS) {
        servoB.center();
        servoBSorting = false;
        Serial.println("[TIMEOUT] servoB safety return");
    }
}
