# soy-controller 리팩토링 계획

> Rust 레퍼런스(`hajun_dev_rust/firmware`) 아키텍처를 분석하여, 동일한 **모듈화·구조체화·책임 분리** 원칙을 현재 C++/Arduino PlatformIO 코드에 적용합니다.

## 1. Rust 레퍼런스 아키텍처 분석

### esp32-devkit (컨베이어 FSM)

```
firmware/esp32-devkit/src/
├── main.rs          ← 엔트리포인트: 초기화 + 메인 루프만 담당
├── config.rs        ← 타입 안전 설정 구조체 (컴파일 타임 상수)
├── command.rs       ← MQTT 명령 파싱 (enum + TryFrom)
├── error.rs         ← 계층적 에러 타입 (MotorError, AppError)
├── fsm.rs           ← FSM 상태/방향/페이즈 enum + Fsm 구조체
├── motor/
│   ├── mod.rs       ← 모듈 re-export
│   ├── dc.rs        ← DcMotor RAII 구조체 (뉴타입 MotorSpeed)
│   └── servo.rs     ← ServoMotor 구조체 (뉴타입 ServoAngle)
├── peripheral/
│   ├── mod.rs       ← 모듈 re-export
│   ├── led.rs       ← RgbLed 구조체 (상태별 색상)
│   └── sensor.rs    ← ProximitySensor 구조체 (ADC + 디바운스)
└── wifi.rs          ← WiFi 연결 함수
```

### esp32-cam (UDP 스트리머)

```
firmware/esp32-cam/src/
├── main.rs          ← 엔트리포인트: 초기화 + 스트리밍 루프
├── config.rs        ← 설정 구조체
├── error.rs         ← 에러 타입 (Camera, Udp, Wifi 등)
├── stream/
│   ├── mod.rs       ← 모듈 re-export
│   ├── camera.rs    ← CameraCapture RAII (Frame 자동 해제)
│   └── udp.rs       ← UdpStreamer (청크 프로토콜 + 드롭 통계)
└── wifi.rs          ← WiFi 연결 (esp32-devkit과 공유)
```

### 핵심 설계 원칙

| 원칙 | Rust 구현 | 현재 C++ 문제점 |
|------|-----------|----------------|
| **단일 책임** | 파일 1개 = 역할 1개 | `main.cpp` 1개에 모든 것이 혼재 |
| **구조체화** | DcMotor, ServoMotor 등 RAII 구조체 | struct 있지만 `cfg` 전역에 의존 |
| **설정 분리** | `config.rs` 정적 상수 집합 | 설정이 구조체에 하드코딩 |
| **명령 파싱** | `Command` enum + `TryFrom` | 콜백 내 문자열 비교 스파게티 |
| **에러 처리** | 계층적 enum (Wifi/Mqtt/Motor/Sensor) | 에러 처리 없이 시리얼 출력만 |
| **FSM 캡슐화** | `Fsm` 구조체 + `SortPhase` enum | 전역 변수 + 함수로 산재 |
| **모듈 re-export** | `mod.rs`로 깔끔한 public API | N/A (파일 하나) |

---

## 2. C++ 리팩토링 후 목표 구조

### esp32-devkit

```
soy-controller/esp32-devkit/
├── platformio.ini
├── partitions.csv
└── src/
    ├── main.cpp              ← setup()/loop()만 담당
    ├── config.h              ← 핀 맵 + 타이밍 + 토픽 상수
    ├── command.h / .cpp      ← Command enum + parse 함수
    ├── fsm.h / .cpp          ← State/SortDir/SortPhase enum + Fsm 클래스
    ├── motor/
    │   ├── dc_motor.h / .cpp     ← DcMotor 클래스
    │   └── servo_motor.h / .cpp  ← ServoMotor 클래스 (MCPWM)
    ├── peripheral/
    │   ├── rgb_led.h / .cpp      ← RgbLed 클래스
    │   └── proximity_sensor.h / .cpp ← ProximitySensor 클래스
    └── net/
        ├── wifi_manager.h / .cpp ← WiFi 연결
        └── mqtt_manager.h / .cpp ← MQTT 연결 + 발행/구독
```

### esp32-cam

```
soy-controller/esp32-cam/
├── platformio.ini
├── partitions.csv
└── src/
    ├── main.cpp              ← setup()/loop()만 담당
    ├── config.h              ← 핀 맵 + 네트워크 설정 상수
    ├── stream/
    │   ├── camera.h / .cpp       ← CameraCapture 클래스 (RAII)
    │   └── udp_streamer.h / .cpp ← UdpStreamer 클래스 (청크 프로토콜)
    └── net/
        ├── wifi_manager.h / .cpp ← WiFi 연결
        └── mqtt_manager.h / .cpp ← MQTT 연결 + 콜백
```

---

## 3. 각 모듈 상세 변경사항

### 3.1 `config.h` — 설정 중앙 집중

**변경 이유:** 현재 `ConveyorConfig` 구조체에 핀번호·타이밍이 혼재되어 있고, MQTT 토픽은 `static const char*` 전역으로 분산되어 있음. Rust의 `Config` 구조체처럼 모든 설정을 한 곳에 모음.

```cpp
#pragma once
#include <cstdint>

namespace config {
    // ── 핀 매핑 ──
    namespace pin {
        constexpr int DC_IN1  = 27;
        constexpr int DC_IN2  = 13;
        constexpr int SERVO   = 14;
        constexpr int SENSOR  = 34;
        constexpr int LED_R   = 25;
        constexpr int LED_G   = 26;
        constexpr int LED_B   = 4;
    }
    // ── DC 모터 ──
    namespace dc {
        constexpr int    LEDC_CHANNEL = 0;
        constexpr int    FREQ_HZ      = 5000;
        constexpr int    RESOLUTION   = 8;  // 0-255
        constexpr int    DEFAULT_SPEED = 200;
    }
    // ── 서보 ──
    namespace servo {
        constexpr int CENTER_DEG = 90;
        constexpr int SORT_DEG   = 45;
        constexpr int MIN_US     = 544;
        constexpr int MAX_US     = 2400;
    }
    // ── 센서 ──
    namespace sensor {
        constexpr int           THRESHOLD    = 1000;
        constexpr unsigned long DEBOUNCE_MS  = 50;
    }
    // ── 타이밍 ──
    namespace timing {
        constexpr unsigned long SORT_HOLD_MS   = 1500;
        constexpr unsigned long SORT_RETURN_MS = 600;
        constexpr unsigned long WARNING_MS     = 3000;
    }
    // ── MQTT 토픽 ──
    namespace mqtt {
        constexpr const char* TOPIC_CONTROL = "device/control";
        constexpr const char* TOPIC_SENSOR  = "device/sensor";
        constexpr const char* TOPIC_STATUS  = "device/status";
        constexpr int         PORT          = 1883;
    }
}
```

### 3.2 `command.h/.cpp` — 명령 파싱 분리

**변경 이유:** Rust의 `Command` enum + `TryFrom` 패턴을 그대로 적용. MQTT 콜백에서 문자열 비교 로직을 완전히 분리.

```cpp
// command.h
#pragma once
#include <cstdint>

enum class CommandType : uint8_t {
    DC_START, DC_STOP,
    SORT_DIR_1L, SORT_DIR_2L, SORT_DIR_WARN,
    UNKNOWN,
};

struct Command {
    CommandType type;
    int speed;  // DC_START 시에만 유효

    static Command parse(const char* msg);
};
```

### 3.3 `fsm.h/.cpp` — FSM 캡슐화

**변경 이유:** 현재 `ConveyorFSM`은 `state`와 `entered_at`만 갖고, `SortPhase`가 전역 bool 변수(`_servo_returned`)로 관리됨. Rust처럼 `SortPhase`를 FSM 내부로 통합.

```cpp
// fsm.h
#pragma once
#include <cstdint>

enum class State : uint8_t { IDLE, RUNNING, SORTING, WARNING };
enum class SortDir : uint8_t { NONE, LINE_1L, LINE_2L };
enum class SortPhase : uint8_t { HOLDING, RETURNING };

class Fsm {
public:
    State state() const;
    const char* stateName() const;
    unsigned long elapsed() const;
    SortPhase sortPhase() const;

    void enter(State s);
    void advanceSortPhase();

private:
    State         _state      = State::IDLE;
    unsigned long _entered_at = 0;
    SortPhase     _sort_phase = SortPhase::HOLDING;
};
```

### 3.4 `motor/dc_motor.h/.cpp` — DC 모터 클래스

**변경 이유:** `cfg` 전역 의존을 제거하고, 생성자에서 핀을 초기화하는 자족적 클래스로.

```cpp
// dc_motor.h
#pragma once

class DcMotor {
public:
    void begin(int in1Pin, int in2Pin, int channel, int freq, int resolution);
    void drive(int speed);
    void brake();
private:
    int _channel = 0;
};
```

### 3.5 `motor/servo_motor.h/.cpp` — 서보 모터 클래스

```cpp
// servo_motor.h
#pragma once

class ServoMotor {
public:
    void begin(int pin);
    void setAngle(int deg);
    void center();
    void sort();
    void disable();
};
```

### 3.6 `peripheral/rgb_led.h/.cpp` — LED 클래스

```cpp
// rgb_led.h
#pragma once
#include "fsm.h"  // State enum

class RgbLed {
public:
    void begin(int rPin, int gPin, int bPin);
    void set(bool r, bool g, bool b);
    void red();
    void green();
    void blue();
    void yellow();
    void off();
    void forState(State s);
private:
    int _r, _g, _b;
};
```

### 3.7 `peripheral/proximity_sensor.h/.cpp` — 센서 클래스

```cpp
// proximity_sensor.h
#pragma once

class ProximitySensor {
public:
    void begin(int pin, int threshold, unsigned long debounceMs);
    bool isDetected();
    void sync();
    int readRaw();
private:
    int           _pin;
    int           _threshold;
    unsigned long _debounceMs;
    bool          _lastState    = false;
    unsigned long _lastChange   = 0;
};
```

### 3.8 `net/wifi_manager.h/.cpp` — WiFi 연결

```cpp
// wifi_manager.h
#pragma once

namespace wifi_manager {
    void connect();  // 블로킹 연결, WIFI_SSID/WIFI_PASS 빌드 시 주입
}
```

### 3.9 `net/mqtt_manager.h/.cpp` — MQTT 관리

```cpp
// mqtt_manager.h
#pragma once
#include <PubSubClient.h>
#include "command.h"
#include <functional>

class MqttManager {
public:
    using CommandCallback = std::function<void(const Command&)>;

    void begin(const char* broker, int port, CommandCallback onCommand);
    void loop();
    void publish(const char* topic, const char* payload);
    void publishStatus(const char* stateName);

private:
    void reconnect();
    static void mqttCallback(char* topic, byte* payload, unsigned int length);
};
```

---

## 4. 변경 순서 (단계별)

> [!IMPORTANT]
> 각 단계마다 PlatformIO 빌드 성공을 확인하면서 진행합니다.

### Phase 1: esp32-devkit (컨베이어 FSM)
1. `config.h` 생성 → 기존 상수/핀 정의 이동
2. `fsm.h/.cpp` 생성 → `ConveyorFSM` + `SortPhase` 통합
3. `command.h/.cpp` 생성 → MQTT 명령 파싱 분리
4. `motor/dc_motor.h/.cpp` 생성 → DcMotor 구조체 이동
5. `motor/servo_motor.h/.cpp` 생성 → ServoCtrl → ServoMotor
6. `peripheral/rgb_led.h/.cpp` 생성 → RgbLed 이동
7. `peripheral/proximity_sensor.h/.cpp` 생성 → ProximitySensor 이동
8. `net/wifi_manager.h/.cpp` 생성 → WiFi 코드 분리
9. `net/mqtt_manager.h/.cpp` 생성 → MQTT 코드 분리
10. `main.cpp` 리팩토링 → setup()/loop()만 남기기

### Phase 2: esp32-cam (UDP 스트리머)
1. `config.h` 생성 → 카메라 핀 + 네트워크 설정
2. `stream/camera.h/.cpp` 생성 → 카메라 초기화 + 캡처
3. `stream/udp_streamer.h/.cpp` 생성 → UDP 청크 프로토콜
4. `net/wifi_manager.h/.cpp` 생성 → WiFi 코드 분리
5. `net/mqtt_manager.h/.cpp` 생성 → MQTT 콜백 분리
6. `main.cpp` 리팩토링 → setup()/loop()만 남기기

---

## 5. 변경하지 않는 것

- **`platformio.ini`**: 빌드 설정은 그대로 유지
- **`env_script.py`**: `.env` 주입 메커니즘 유지
- **`partitions.csv`**: 파티션 테이블 유지
- **`lib/` 외부 라이브러리**: PubSubClient 등 유지
- **기능/동작 로직**: FSM 전이, MQTT 메시지 내용, UDP 프로토콜 등 동작은 100% 동일 유지
