#include "fsm/idle_state.h"
#include "fsm/conveying_state.h"
#include "fsm/context.h"
#include "command.h"
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

        case CommandType::DC_SPEED:
            ctx.dcSpeed = constrain(cmd.value, 150, 255);
            Serial.printf("[CMD] DC_SPEED=%d\n", ctx.dcSpeed);
            break;

        case CommandType::SERVO_DEG_A:
            ctx.sortDegA = constrain(cmd.value, 0, 45);
            Serial.printf("[CMD] SERVO_A=%d\n", ctx.sortDegA);
            break;

        case CommandType::SERVO_DEG_B:
            ctx.sortDegB = constrain(cmd.value, 0, 45);
            Serial.printf("[CMD] SERVO_B=%d\n", ctx.sortDegB);
            break;

        default:
            break;
    }
}
