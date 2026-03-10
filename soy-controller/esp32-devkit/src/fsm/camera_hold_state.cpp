#include "fsm/camera_hold_state.h"
#include "fsm/conveying_state.h"
#include "fsm/idle_state.h"
#include "fsm/paused_state.h"
#include "fsm/context.h"
#include "command.h"
#include "config.h"
#include "motor/dc_motor.h"
#include "peripheral/rgb_led.h"
#include "peripheral/proximity_sensor.h"
#include "net/mqtt_manager.h"

extern IdleState      idleState;
extern ConveyingState conveyingState;
extern PausedState    pausedState;

void CameraHoldState::onEnter(Context& ctx) {
    ctx.dcMotor.startSoftStop(ctx.dcSpeed, config::timing::SOFT_STOP_DURATION_MS);
    _enterMs = millis();
    if (config::dc::SOFT_STOP_DURATION_MS > 0) {
        ctx.dcSoftStopStartSpeed = ctx.dcSpeed;
        ctx.dcSoftStopStartMs = millis();
        Serial.printf("[SENSOR] S6 → CAMERA_HOLD soft stop %lums\n", config::dc::SOFT_STOP_DURATION_MS);
    } else {
        ctx.dcMotor.brake();
    }
    ctx.mqtt.publish(config::mqtt::TOPIC_SENSOR, "CAMERA_DETECT");
    Serial.println("[SENSOR] S6 → CAMERA_HOLD (soft stop + waiting SORT_DIR)");
}

void CameraHoldState::onExit(Context& ctx) {
    ctx.dcSoftStopStartSpeed = 0;
    ctx.led.stopBlink();
}

void CameraHoldState::onLoop(Context& ctx) {
    // 위치센서 감지 시 DC 모터 소프트 정지: 감속 후 brake
    if (ctx.dcSoftStopStartSpeed > 0) {
        unsigned long duration = config::dc::SOFT_STOP_DURATION_MS;
        unsigned long elapsed = millis() - ctx.dcSoftStopStartMs;
        if (elapsed >= duration) {
            ctx.dcMotor.brake();
            ctx.dcSoftStopStartSpeed = 0;
        } else {
            int speed = (int)((unsigned long)ctx.dcSoftStopStartSpeed * (duration - elapsed) / duration);
            if (speed < 0) speed = 0;
            ctx.dcMotor.drive(speed);
        }
    }

    // LED 초록 점멸
    ctx.led.updateBlink(config::timing::LED_BLINK_MS, 0, 1, 0);

    // 소프트 스톱 감속 업데이트
    ctx.dcMotor.updateSoftStop();

    // ★ 카메라 대기 중에도 이미 컨베이어를 탄 뒤의 분류기 동작은 독립 백그라운드로 수행
    ctx.processSorters(millis());

    // Safety timeout → CONVEYING 복귀
    if (millis() - _enterMs >= config::timing::CAMERA_WAIT_MAX_MS) {
        ctx.cameraBlankUntil = millis() + config::timing::CAMERA_BLANK_MS;
        ctx.s6.sync(); ctx.s6Prev = ctx.s6.isDetected();
        ctx.mqtt.publish(config::mqtt::TOPIC_SENSOR, "CAMERA_TIMEOUT");
        Serial.println("[SENSOR] Camera hold TIMEOUT → CONVEYING + blanking");
        ctx.transition(&conveyingState);
    }
}

void CameraHoldState::onCommand(Context& ctx, const Command& cmd) {
    switch (cmd.type) {
        case CommandType::SORT_DIR_1L:
        case CommandType::SORT_DIR_2L: {
            // 큐 크기 제한
            if ((int)ctx.dirQueue.size() >= config::queue::MAX_DIR_QUEUE_SIZE) {
                Serial.println("[CMD] SORT_DIR rejected: queue full");
                break;
            }
            SortDir dir = (cmd.type == CommandType::SORT_DIR_1L)
                              ? SortDir::LINE_1L : SortDir::LINE_2L;
            ctx.dirQueue.push(dir);
            Serial.printf("[CMD] queued %s → CONVEYING (q=%d)\n",
                dir == SortDir::LINE_1L ? "1L" : "2L", (int)ctx.dirQueue.size());

            // CAMERA_HOLD 해제 → CONVEYING
            ctx.cameraBlankUntil = millis() + config::timing::CAMERA_BLANK_MS;
            ctx.s6.sync(); ctx.s6Prev = ctx.s6.isDetected();
            ctx.transition(&conveyingState);
            break;
        }

        case CommandType::SORT_DIR_WARN: {
            // 미분류 상품: 큐에 넣지 않고 즉시 CONVEYING 복귀 (미분류로 통과)
            Serial.println("[CMD] SORT_DIR:WARN → CONVEYING (no queue)");
            ctx.cameraBlankUntil = millis() + config::timing::CAMERA_BLANK_MS;
            ctx.s6.sync(); ctx.s6Prev = ctx.s6.isDetected();
            ctx.transition(&conveyingState);
            break;
        }

        case CommandType::SORT_STOP:
            ctx.transition(&idleState);
            break;

        case CommandType::SORT_PAUSE:
            ctx.transition(&pausedState);
            break;

        case CommandType::DC_SPEED:
            ctx.dcSpeed = constrain(cmd.value, 150, 255);
            Serial.printf("[CMD] DC_SPEED=%d (hold)\n", ctx.dcSpeed);
            break;

        default:
            break;
    }
}
