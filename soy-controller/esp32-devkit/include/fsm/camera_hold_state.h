#pragma once
#include "fsm/state_base.h"

class CameraHoldState : public StateBase {
public:
    void onEnter(Context& ctx) override;
    void onExit(Context& ctx) override;
    void onLoop(Context& ctx) override;
    void onCommand(Context& ctx, const Command& cmd) override;
    const char* name() const override { return "CAMERA_HOLD"; }
private:
    unsigned long _enterMs = 0;
};
