#include "fsm/camera_hold_state.h"
#include "fsm/conveying_state.h"
#include "fsm/idle_state.h"
#include "fsm/paused_state.h"
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
        case CommandType::SORT_DIR_2L:
            // 로직은 PC가 관장. 디바이스는 CAMERA_HOLD 해제만 수행.
            Serial.println("[CMD] SORT_DIR → CONVEYING");
            ctx.cameraBlankUntil = millis() + config::timing::CAMERA_BLANK_MS;
            ctx.s6.sync(); ctx.s6Prev = ctx.s6.isDetected();
            ctx.transition(&conveyingState);
            break;

        case CommandType::SORT_DIR_WARN: {
            Serial.println("[CMD] SORT_DIR:WARN → CONVEYING");
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
