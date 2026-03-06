/*
 * peripheral/proximity_sensor.h — 아날로그/디지털 근접 센서 드라이버
 */
#pragma once
#include <cstdint>

class ProximitySensor {
public:
    void begin(int pin, int threshold, unsigned long debounceMs, bool isDigital = false, bool activeLow = false);
    int readRaw() const;
    bool isDetected();
    void sync();
private:
    int           _pin        = -1;
    int           _threshold  = 1000;
    unsigned long _debounceMs = 50;
    bool          _lastState  = false;
    bool          _stableState = false;
    unsigned long _lastChange = 0;
    bool          _isDigital  = false;
    bool          _activeLow  = false;
};
