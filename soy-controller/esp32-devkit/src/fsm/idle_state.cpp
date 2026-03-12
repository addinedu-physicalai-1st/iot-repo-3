#include "fsm/idle_state.h"
#include "fsm/conveying_state.h"
#include "fsm/context.h"
#include "command.h"
#include "config.h"
#include "motor/dc_motor.h"
#include "motor/servo_motor.h"
#include "peripheral/rgb_led.h"
#include "peripheral/proximity_sensor.h"
#include "net/mqtt_manager.h"

// 전방 선언 — 전이 대상 상태 (states.cpp에서 정의)
extern ConveyingState conveyingState;

void IdleState::onEnter(Context& ctx) {
    ctx.dcMotor.brake();
    ctx.servoA.center();
    ctx.servoB.center();
    delay(200);
    ctx.servoA.disable();
    ctx.servoB.disable();
    ctx.led.red();

    // CleanShutdown: 큐/pending/플래그 전부 초기화
    ctx.flushAll();
    ctx.mqtt.publishStatus("IDLE");
}

void IdleState::onExit(Context& ctx) {
    // IDLE 이탈 시 특별히 할 것 없음
}

void IdleState::onLoop(Context& ctx) {
    // IDLE에서는 센서 추적만 (이벤트 처리 없음)
    ctx.s5Prev = ctx.s5.isDetected();
    ctx.s3Prev = ctx.s3.isDetected();
    ctx.s4Prev = ctx.s4.isDetected();
}

void IdleState::onCommand(Context& ctx, const Command& cmd) {
    switch (cmd.type) {
        case CommandType::SORT_START:
            ctx.transition(&conveyingState);  // IDLE → CONVEYING
            break;

        case CommandType::SORT_DIR_1L:
        case CommandType::SORT_DIR_2L:
            // 로직·큐는 PC가 관장. 디바이스는 센서만 보고, SERVO_A/B 명령만 수행.
            break;

        case CommandType::DC_SPEED:
            ctx.dcSpeed = constrain(cmd.value, 150, 255);
            Serial.printf("[CMD] DC_SPEED=%d\n", ctx.dcSpeed);
            break;

        case CommandType::SERVO_DEG_A: {
            int deg = constrain(cmd.value, 0, 45);
            ctx.sortDegA = deg;
            if (deg == 0)
                ctx.servoA.center();
            else
                ctx.servoA.sort(deg);
            Serial.printf("[CMD] SERVO_A=%d\n", deg);
            break;
        }
        case CommandType::SERVO_DEG_B: {
            int deg = constrain(cmd.value, 0, 45);
            ctx.sortDegB = deg;
            if (deg == 0)
                ctx.servoB.center();
            else
                ctx.servoB.sort(deg);
            Serial.printf("[CMD] SERVO_B=%d\n", deg);
            break;
        }

        default:
            break;
    }
}
