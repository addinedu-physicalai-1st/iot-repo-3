#include "fsm/error_state.h"
#include "fsm/idle_state.h"
#include "fsm/context.h"
#include "command.h"
#include "config.h"
#include "motor/dc_motor.h"
#include "motor/servo_motor.h"
#include "peripheral/rgb_led.h"
#include "net/mqtt_manager.h"

extern IdleState idleState;

void ErrorState::onEnter(Context& ctx) {
    ctx.dcMotor.brake();
    ctx.servoA.center();
    ctx.servoB.center();
    ctx.flushAll();
    ctx.mqtt.publishStatus("ERROR");
    Serial.println("[ERROR] 에러 상태 진입 — SORT_STOP으로 복구");
}

void ErrorState::onExit(Context& ctx) {
    ctx.led.stopBlink();
}

void ErrorState::onLoop(Context& ctx) {
    // LED 빨강 점멸
    ctx.led.updateBlink(config::timing::LED_BLINK_MS, 1, 0, 0);
}

void ErrorState::onCommand(Context& ctx, const Command& cmd) {
    // ERROR에서는 SORT_STOP만 수용 (수동 복구)
    if (cmd.type == CommandType::SORT_STOP) {
        ctx.transition(&idleState);
    }
}
