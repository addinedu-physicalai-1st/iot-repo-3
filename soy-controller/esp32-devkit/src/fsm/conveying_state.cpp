#include "fsm/conveying_state.h"
#include "fsm/idle_state.h"
#include "fsm/camera_hold_state.h"
#include "fsm/paused_state.h"
#include "fsm/context.h"
#include "command.h"
#include "config.h"
#include "motor/dc_motor.h"
#include "motor/servo_motor.h"
#include "peripheral/rgb_led.h"
#include "peripheral/proximity_sensor.h"
#include "net/mqtt_manager.h"

// 전방 선언 — 전이 대상 상태
extern IdleState       idleState;
extern CameraHoldState cameraHoldState;
extern PausedState     pausedState;

void ConveyingState::onEnter(Context& ctx) {
    ctx.dcMotor.drive(ctx.dcSpeed);
    ctx.led.green();
    ctx.syncAllSensors();
    ctx.cameraBlankUntil = 0;
    // 서보 분류 중이면 타임아웃 타이머 리셋 (PAUSED 복귀 후)
    if (ctx.servoASorting) ctx.servoAStartMs = millis();
    if (ctx.servoBSorting) ctx.servoBStartMs = millis();
    ctx.mqtt.publishStatus("RUNNING");
}

void ConveyingState::onExit(Context& ctx) {
    // 이탈 시 특별히 할 것 없음
}

void ConveyingState::onLoop(Context& ctx) {
    unsigned long now = millis();

    // FSM 외부 분류기 백그라운드 동작 수행 (conveying 중에도 동작)
    ctx.processSorters(now);

    // ── S6 카메라 감지 → CAMERA_HOLD ──────────────────────────
    // 블랭킹 기간이면 추적만
    if (ctx.cameraBlankUntil > 0) {
        if (now >= ctx.cameraBlankUntil) {
            ctx.cameraBlankUntil = 0;
            ctx.s6.sync(); ctx.s6Prev = ctx.s6.isDetected();
        } else {
            ctx.s6Prev = ctx.s6.isDetected();
        }
    } else {
        bool det6 = ctx.s6.isDetected();
        if (det6 && !ctx.s6Prev) {
            ctx.s6Prev = det6;
            ctx.transition(&cameraHoldState);
            return;  // 상태 전이됨
        }
        ctx.s6Prev = det6;
    }
}

void ConveyingState::onCommand(Context& ctx, const Command& cmd) {
    switch (cmd.type) {
        case CommandType::SORT_START:
            ctx.mqtt.publishStatus("RUNNING");  // 이미 RUNNING
            break;

        case CommandType::SORT_STOP:
            ctx.transition(&idleState);
            break;

        case CommandType::SORT_PAUSE:
            ctx.transition(&pausedState);
            break;

        case CommandType::SORT_DIR_1L:
            if ((int)ctx.dirQueue.size() >= config::queue::MAX_DIR_QUEUE_SIZE) {
                Serial.println("[CMD] SORT_DIR rejected: queue full");
                break;
            }
            ctx.dirQueue.push(SortDir::LINE_1L);
            Serial.printf("[CMD] queued 1L (q=%d)\n", (int)ctx.dirQueue.size());
            break;

        case CommandType::SORT_DIR_2L:
            if ((int)ctx.dirQueue.size() >= config::queue::MAX_DIR_QUEUE_SIZE) {
                Serial.println("[CMD] SORT_DIR rejected: queue full");
                break;
            }
            ctx.dirQueue.push(SortDir::LINE_2L);
            Serial.printf("[CMD] queued 2L (q=%d)\n", (int)ctx.dirQueue.size());
            break;

        case CommandType::SORT_DIR_WARN:
            // 미분류 상품: 큐에 넣지 않음 (서보 동작 없이 통과)
            Serial.println("[CMD] SORT_DIR:WARN (no queue)");
            break;

        case CommandType::DC_SPEED:
            ctx.dcSpeed = constrain(cmd.value, 150, 255);
            ctx.dcMotor.drive(ctx.dcSpeed);
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
