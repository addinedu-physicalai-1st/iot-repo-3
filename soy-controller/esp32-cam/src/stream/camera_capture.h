/*
 * stream/camera_capture.h — 카메라 초기화 및 프레임 캡처
 *
 * AI-Thinker ESP32-CAM (OV2640 + PSRAM) 에 맞춰 초기화하고,
 * JPEG 프레임을 캡처·반환한다.
 * Rust의 stream/camera.rs (CameraCapture + Frame RAII)에 대응.
 */
#pragma once
#include "esp_camera.h"

class CameraCapture {
public:
    /**
     * 카메라 초기화 (QVGA JPEG, PSRAM, GRAB_LATEST, vflip).
     * @return true: 성공, false: 실패
     */
    bool begin();

    /**
     * 프레임 캡처. 호출자가 사용 후 반드시 returnFrame()을 호출해야 한다.
     * @return 프레임 버퍼 포인터. 실패 시 nullptr.
     */
    camera_fb_t* capture();

    /**
     * 프레임 버퍼 반환. 메모리 누수 방지.
     */
    void returnFrame(camera_fb_t* fb);
};
