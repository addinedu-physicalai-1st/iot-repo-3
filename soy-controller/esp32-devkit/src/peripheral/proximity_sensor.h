/*
 * peripheral/proximity_sensor.h — 아날로그 근접 센서 드라이버
 *
 * ADC1 GPIO 34 를 사용하며, 디바운스를 적용하여 노이즈를 필터링한다.
 * 임계값 이상이면 물체를 감지한 것으로 판단.
 */
#pragma once
#include <cstdint>

class ProximitySensor {
public:
    /**
     * ADC 초기화.
     * @param pin        아날로그 입력 핀 (예: 34)
     * @param threshold  감지 임계값 (0–4095)
     * @param debounceMs 디바운스 시간 (ms)
     */
    void begin(int pin, int threshold, unsigned long debounceMs);

    /**
     * ADC 원시 값을 읽는다 (0–4095).
     */
    int readRaw() const;

    /**
     * 디바운스 적용 후 감지 상태를 반환한다.
     * 상태가 변경된 후 debounceMs 이상 유지되어야 true.
     */
    bool isDetected();

    /**
     * 현재 센서 상태로 내부 상태를 동기화한다.
     * RUNNING 진입 시 호출하여, 이미 HIGH 인 센서를 상승 에지로 오인하지 않도록 한다.
     */
    void sync();

private:
    int           _pin        = -1;
    int           _threshold  = 1000;
    unsigned long _debounceMs = 50;
    bool          _lastState  = false;
    unsigned long _lastChange = 0;
};
