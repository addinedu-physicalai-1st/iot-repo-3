/*
 * stream/udp_streamer.h — UDP 청크 프로토콜 스트리머
 *
 * JPEG 프레임을 청크로 나눠 UDP 패킷으로 전송한다.
 * Python GUI가 기대하는 IMG 패킷 프로토콜 준수.
 *
 * 패킷 포맷:
 *   Offset  Size  Field
 *    0-2     3    "IMG" magic
 *    3       1    frame_type ('S'=standard)
 *    4-5     2    image_id   (u16 LE, wrapping)
 *    6-7     2    total_chunks (u16 LE)
 *    8-9     2    chunk_index  (u16 LE, 0-based)
 *    10+    ≤1024 JPEG payload
 *
 * Rust의 stream/udp.rs (UdpStreamer)에 대응.
 */
#pragma once
#include <WiFiUdp.h>
#include "esp_camera.h"

class UdpStreamer {
public:
    /**
     * UDP 소켓 초기화.
     * @param destIp   전송 대상 IP (빌드 시 .env에서 주입)
     * @param destPort 전송 대상 포트
     */
    void begin(const char* destIp, int destPort);

    /**
     * 프레임을 청크로 나눠 UDP로 전송한다.
     * 전송 실패 시 해당 청크를 스킵하고 다음 프레임으로 넘어간다.
     */
    void sendFrame(camera_fb_t* fb);

private:
    WiFiUDP  _udp;
    const char* _destIp   = nullptr;
    int         _destPort = 8021;
    uint16_t    _imageId  = 0;

    static constexpr int MAX_UDP_PAYLOAD = 1024;
    static constexpr int HEADER_SIZE     = 10;  // IMG(3)+type(1)+id(2)+total(2)+idx(2)
};
