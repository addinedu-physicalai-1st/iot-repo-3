#include "fsm/paused_state.h"
#include "fsm/conveying_state.h"
#include "fsm/idle_state.h"
#include "fsm/context.h"
#include "command.h"
#include "config.h"
#include "motor/dc_motor.h"
#include "motor/servo_motor.h"
#include "peripheral/rgb_led.h"
#include "peripheral/proximity_sensor.h"
#include "net/mqtt_manager.h"

extern IdleState      idleState;
extern ConveyingState conveyingState;

void PausedState::onEnter(Context& ctx) {
    ctx.dcMotor.brake();
    ctx.led.yellow();
    ctx.mqtt.publishStatus("PAUSED");
}

void PausedState::onExit(Context& ctx) {
    // 큐/서보 상태 보존 (초기화하지 않음)
}

void PausedState::onLoop(Context& ctx) {
    // PAUSED에서는 센서 추적 대신 백그라운드 분류기 동작 수행
    // 일시정지(모터정지)라도 서보 타임아웃/근접 센서 감지는 독립 처리
    ctx.processSorters(millis());
}

void PausedState::onCommand(Context& ctx, const Command& cmd) {
    switch (cmd.type) {
        case CommandType::SORT_RESUME:
            ctx.transition(&conveyingState);  // PAUSED → CONVEYING
            break;

        case CommandType::SORT_DIR_1L:
        case CommandType::SORT_DIR_2L:
            // 로직·큐는 PC가 관장.
            break;

        case CommandType::SORT_STOP:
            ctx.transition(&idleState);
            break;

        case CommandType::DC_SPEED:
            ctx.dcSpeed = constrain(cmd.value, 150, 255);
            Serial.printf("[CMD] DC_SPEED=%d (paused)\n", ctx.dcSpeed);
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
