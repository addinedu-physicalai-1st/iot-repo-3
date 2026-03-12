#include "camera_capture.h"
#include "config.h"
#include <Arduino.h>

bool CameraCapture::begin() {
    camera_config_t cameraCfg = {};
    cameraCfg.ledc_channel = LEDC_CHANNEL_0;
    cameraCfg.ledc_timer   = LEDC_TIMER_0;
    cameraCfg.pin_d0       = config::camera_pin::Y2;
    cameraCfg.pin_d1       = config::camera_pin::Y3;
    cameraCfg.pin_d2       = config::camera_pin::Y4;
    cameraCfg.pin_d3       = config::camera_pin::Y5;
    cameraCfg.pin_d4       = config::camera_pin::Y6;
    cameraCfg.pin_d5       = config::camera_pin::Y7;
    cameraCfg.pin_d6       = config::camera_pin::Y8;
    cameraCfg.pin_d7       = config::camera_pin::Y9;
    cameraCfg.pin_xclk     = config::camera_pin::XCLK;
    cameraCfg.pin_pclk     = config::camera_pin::PCLK;
    cameraCfg.pin_vsync    = config::camera_pin::VSYNC;
    cameraCfg.pin_href     = config::camera_pin::HREF;
    cameraCfg.pin_sccb_sda = config::camera_pin::SIOD;
    cameraCfg.pin_sccb_scl = config::camera_pin::SIOC;
    cameraCfg.pin_pwdn     = config::camera_pin::PWDN;
    cameraCfg.pin_reset    = config::camera_pin::RESET;
    cameraCfg.xclk_freq_hz = config::camera::XCLK_FREQ_HZ;
    cameraCfg.pixel_format = PIXFORMAT_JPEG;
    cameraCfg.grab_mode    = CAMERA_GRAB_LATEST;
    cameraCfg.fb_location  = CAMERA_FB_IN_PSRAM;
    cameraCfg.frame_size   = FRAMESIZE_QVGA;
    cameraCfg.jpeg_quality = config::camera::JPEG_QUALITY;
    cameraCfg.fb_count     = config::camera::FB_COUNT;

    esp_err_t err = esp_camera_init(&cameraCfg);
    if (err != ESP_OK) {
        Serial.printf("[FAIL] Camera init error 0x%x\n", err);
        return false;
    }
    Serial.println("[OK] Camera Initialized");

    // 수직 반전 (AI-Thinker 모듈 보정)
    sensor_t* s = esp_camera_sensor_get();
    if (s) {
        s->set_vflip(s, 1);
    }

    return true;
}

camera_fb_t* CameraCapture::capture() {
    return esp_camera_fb_get();
}

void CameraCapture::returnFrame(camera_fb_t* fb) {
    if (fb) {
        esp_camera_fb_return(fb);
    }
}
