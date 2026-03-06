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
private:
    int _channel = 0;
    int _in1Pin  = -1;
};
