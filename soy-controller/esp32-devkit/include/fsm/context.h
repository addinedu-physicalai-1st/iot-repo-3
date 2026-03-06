/*
 * fsm/context.h — 공유 컨텍스트
 */
#pragma once

#include <Arduino.h>
#include <queue>
#include "fsm.h"
#include "config.h"

class StateBase;
class DcMotor;
class ServoMotor;
class RgbLed;
class ProximitySensor;
class MqttManager;

struct Context {
    DcMotor&         dcMotor;
    ServoMotor&      servoA;
    ServoMotor&      servoB;
    RgbLed&          led;
    ProximitySensor& s1;
    ProximitySensor& s2;
    ProximitySensor& s3;
    ProximitySensor& s4;
    ProximitySensor& s5;
    ProximitySensor& s6;
    MqttManager&     mqtt;

    Context(DcMotor& m, ServoMotor& sa, ServoMotor& sb, RgbLed& l,
            ProximitySensor& ps1, ProximitySensor& ps2, ProximitySensor& ps3,
            ProximitySensor& ps4, ProximitySensor& ps5, ProximitySensor& ps6,
            MqttManager& mq)
        : dcMotor(m), servoA(sa), servoB(sb), led(l),
          s1(ps1), s2(ps2), s3(ps3), s4(ps4), s5(ps5), s6(ps6), mqtt(mq) {}

    std::queue<SortDir> dirQueue;
    int  dcSpeed    = config::dc::DEFAULT_SPEED;
    int  sortDegA   = config::servo::SORT_DEG_A;
    int  sortDegB   = config::servo::SORT_DEG_B;
    int  pending2L  = 0;
    bool servoASorting = false;
    bool servoBSorting = false;
    unsigned long servoAStartMs = 0;
    unsigned long servoBStartMs = 0;
    unsigned long cameraBlankUntil = 0;

    bool s1Prev = false, s2Prev = false;
    bool s3Prev = false, s4Prev = false;
    bool s5Prev = false, s6Prev = false;

    StateBase* currentState = nullptr;

    void transition(StateBase* newState);
    void flushAll();
    void syncAllSensors();

    // 분류기 전담 백그라운드 태스크
    void processSorters(unsigned long now);
};
