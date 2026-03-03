#include "udp_streamer.h"
#include <Arduino.h>

void UdpStreamer::begin(const char* destIp, int destPort) {
    _destIp   = destIp;
    _destPort = destPort;
    _udp.begin(_destPort);
}

void UdpStreamer::sendFrame(camera_fb_t* fb) {
    if (!fb || fb->len == 0) return;

    int totalChunks = (fb->len + MAX_UDP_PAYLOAD - 1) / MAX_UDP_PAYLOAD;
    uint16_t imageId = _imageId;
    char frameType = 'S';

    for (int i = 0; i < totalChunks; i++) {
        _udp.beginPacket(_destIp, _destPort);

        // 헤더 조립 (10바이트)
        _udp.write((const uint8_t*)"IMG", 3);
        _udp.write((const uint8_t*)&frameType, 1);
        _udp.write((const uint8_t*)&imageId, 2);
        _udp.write((const uint8_t*)&totalChunks, 2);
        _udp.write((const uint8_t*)&i, 2);

        // 페이로드
        int offset = i * MAX_UDP_PAYLOAD;
        int payloadSize = fb->len - offset;
        if (payloadSize > MAX_UDP_PAYLOAD) {
            payloadSize = MAX_UDP_PAYLOAD;
        }
        _udp.write(fb->buf + offset, payloadSize);

        if (_udp.endPacket()) {
            delay(15);
        } else {
            delay(30);
        }
    }

    _imageId++;
}
