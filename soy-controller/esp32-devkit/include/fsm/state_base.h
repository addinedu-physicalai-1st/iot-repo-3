/*
 * fsm/state_base.h — 상태 기본 인터페이스
 */
#pragma once

struct Context;
class  Command;

class StateBase {
public:
    virtual ~StateBase() = default;
    virtual void onEnter(Context& ctx) = 0;
    virtual void onExit(Context& ctx) = 0;
    virtual void onLoop(Context& ctx) = 0;
    virtual void onCommand(Context& ctx, const Command& cmd) = 0;
    virtual const char* name() const = 0;
};
