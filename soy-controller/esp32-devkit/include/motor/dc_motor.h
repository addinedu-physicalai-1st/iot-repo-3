/*
 * motor/dc_motor.h — DC 모터 드라이버 (A4950 Slow Decay)
 */
#pragma once
#include <cstdint>

class DcMotor {
public:
    void begin(int in1Pin, int in2Pin, int channel, int freqHz, int resolutionBits);
    void drive(int speed);
    void brake();

    /**
     * 소프트 스톱 시작 — 현재 속도에서 0까지 감속.
     * startSpeed: 감속 시작 속도 (보통 ctx.dcSpeed)
     * durationMs: 감속에 걸리는 시간 (ms)
     */
    void startSoftStop(int startSpeed, unsigned long durationMs);

    /**
     * 소프트 스톱 업데이트 — onLoop()에서 매 틱마다 호출.
     * @return true: 감속 완료 (정지 상태), false: 아직 감속 중
     */
    bool updateSoftStop();

    bool isSoftStopping() const { return _softStopping; }

private:
    int _channel = 0;
    int _in1Pin  = -1;

    // 소프트 스톱 상태
    bool          _softStopping  = false;
    int           _softStartSpeed = 0;
    unsigned long _softDurationMs = 0;
    unsigned long _softStartMs    = 0;
};
