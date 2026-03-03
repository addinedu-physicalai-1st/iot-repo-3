# 공정 비교: "잘 짠 C++" vs Rust — 언어 본질적 차이만

> 이전 문서(`firmware-comparison-arduino-vs-rust.md`)는 "단일 파일 Arduino C++" vs "모듈화된 Rust"를 비교하여 **코드 품질 차이를 언어 차이로 오인**할 수 있다. 이 문서는 C++도 동일한 수준으로 리팩토링했다고 가정하고, **언어 자체의 차이**만 분석한다.

---

## 1. C++로도 똑같이 할 수 있는 것들

아래 항목들은 이전 문서에서 Rust의 장점으로 분류했지만, **C++도 동일하게 구현 가능**하다:

### 1.1 모듈화
```
// C++도 동일하게 분리 가능
src/
├── main.cpp
├── fsm.h / fsm.cpp
├── command.h / command.cpp
├── motor/dc.h / dc.cpp
├── motor/servo.h / servo.cpp
├── peripheral/led.h / led.cpp
├── peripheral/sensor.h / sensor.cpp
├── config.h
├── error.h
└── wifi.h / wifi.cpp
```
→ **결론: 모듈화는 언어 차이가 아니라 개발자 선택의 문제**

### 1.2 RAII (리소스 자동 관리)
```cpp
// C++이 RAII를 발명했다. 동일 패턴 가능:
class Frame {
    camera_fb_t* fb_;
public:
    explicit Frame(camera_fb_t* fb) : fb_(fb) {}
    ~Frame() { if (fb_) esp_camera_fb_return(fb_); }

    // 복사 금지, 이동만 허용
    Frame(const Frame&) = delete;
    Frame& operator=(const Frame&) = delete;
    Frame(Frame&& other) noexcept : fb_(other.fb_) { other.fb_ = nullptr; }

    const uint8_t* data() const { return fb_->buf; }
    size_t size() const { return fb_->len; }
};
```
→ **결론: RAII 자체는 C++의 핵심 기능. 소멸자로 동일하게 구현 가능**

### 1.3 강타입 래퍼 (Newtype 패턴)
```cpp
// C++도 가능:
class ServoAngle {
    uint32_t deg_;
    explicit ServoAngle(uint32_t d) : deg_(d) {}
public:
    static constexpr ServoAngle center() { return ServoAngle{90}; }
    static std::optional<ServoAngle> try_new(uint32_t d) {
        if (d <= 180) return ServoAngle{d};
        return std::nullopt;
    }
    uint32_t value() const { return deg_; }
};

class MotorSpeed {
    uint8_t speed_;
public:
    explicit MotorSpeed(uint8_t s) : speed_(s) {}
    uint8_t value() const { return speed_; }
};
```
→ **결론: Newtype 패턴은 C++에서도 가능 (다만 보일러플레이트가 더 많음)**

### 1.4 enum class + FSM
```cpp
// C++11 이후 enum class로 타입 안전 enum 가능:
enum class State : uint8_t { Idle, Running, Sorting, Warning };
enum class SortDir : uint8_t { None, Line1L, Line2L };
enum class Command { DcStart, DcStop, SortDir1L, SortDir2L, SortDirWarn };
```
→ **결론: C++ enum class는 Rust enum만큼 타입 안전** (단, 데이터를 담을 수 없음 — 아래 참조)

### 1.5 동시성 프리미티브
```cpp
// C++도 atomic, 큐 사용 가능:
#include <atomic>
std::atomic<bool> streaming{false};

// FreeRTOS 큐 (ESP32에서 표준):
QueueHandle_t cmd_queue = xQueueCreate(20, sizeof(Command));
```
→ **결론: ESP32 환경에서 C++의 FreeRTOS 큐는 Rust의 mpsc 채널과 동등**

### 1.6 의존성 관리
```ini
; platformio.ini에서 lib_deps 사용하면 벤더링 불필요:
lib_deps =
    knolleary/PubSubClient@^2.8
    bblanchon/ArduinoJson@^7.0
```
→ **결론: PlatformIO lib_deps를 쓰면 Cargo만큼은 아니어도 상당히 개선됨**

---

## 2. Rust만의 진짜 언어적 장점 (C++로는 불가능하거나 매우 어려운 것)

### 2.1 에러 무시가 불가능 (`Result<T, E>` + 컴파일러 강제)

이것이 **가장 실질적인 차이**다.

**C++ (잘 짜도)**:
```cpp
class DcMotor {
public:
    // 에러를 반환하도록 설계해도...
    std::optional<MotorError> drive(MotorSpeed speed) {
        if (auto err = in2_pwm_.set_duty(duty)) return err;
        return std::nullopt;
    }
};

// 호출자가 반환값을 무시해도 컴파일 통과:
dc_motor.drive(MotorSpeed(200));  // ← 에러 무시됨. 컴파일러는 아무 말 없음.
```

`[[nodiscard]]` 어트리뷰트를 붙이면 경고는 나오지만:
```cpp
[[nodiscard]] std::optional<MotorError> drive(MotorSpeed speed);
// 무시하면 컴파일 경고 (에러가 아님). -Werror 켜야 에러.
// 그리고 (void)dc_motor.drive(speed); 로 우회 가능.
```

**Rust**:
```rust
// Result를 무시하면 컴파일러 경고 (기본 설정에서도)
// #[must_use]가 Result에 이미 적용됨
dc_motor.drive(MotorSpeed::new(200));  // warning: unused Result
// ? 연산자로 에러가 자동 전파됨
dc_motor.drive(MotorSpeed::new(200))?;  // 실패 시 즉시 반환
```

**왜 중요한가**: ESP32 펌웨어에서 모터 드라이버가 에러를 반환했는데 무시하면, 모터가 이전 상태로 계속 돌거나, PWM이 잘못 설정되어 하드웨어 손상 가능. Rust는 이를 **언어 레벨에서 차단**.

> **판정: Rust 승** — C++의 `[[nodiscard]]`는 약한 보호. Rust의 `Result` + `?`는 에러 경로를 빠짐없이 강제하는 유일한 메인스트림 언어 기능.

---

### 2.2 패턴 매칭 완전성 검사 (exhaustiveness check)

**C++ (잘 짜도)**:
```cpp
// switch에서 케이스를 빠뜨려도 컴파일 통과:
switch (state) {
    case State::Idle:    /* ... */ break;
    case State::Running: /* ... */ break;
    case State::Sorting: /* ... */ break;
    // State::Warning을 깜빡해도 컴파일 OK
    // -Wswitch 경고가 나오긴 하지만, 강제는 아님
}
```

**Rust**:
```rust
// 케이스를 빠뜨리면 컴파일 에러 (경고가 아님):
match state {
    State::Idle => { /* ... */ }
    State::Running => { /* ... */ }
    State::Sorting => { /* ... */ }
    // State::Warning 빠뜨리면 → 컴파일 에러!
    // error[E0004]: non-exhaustive patterns: `Warning` not covered
}
```

**왜 중요한가**: 나중에 FSM에 `State::Emergency` 같은 새 상태를 추가할 때,
- C++: 모든 switch문을 수동으로 찾아서 업데이트해야 함 (빠뜨리면 런타임 버그)
- Rust: 모든 match문에서 컴파일 에러 발생 → 수정 강제

> **판정: Rust 승** — C++의 `-Wswitch`는 경고 수준. Rust는 에러 수준으로 강제. 특히 FSM이 핵심인 이 프로젝트에서 실질적 안전망.

---

### 2.3 데이터를 가진 enum (tagged union 안전성)

**C++ (잘 짜도)**:
```cpp
// C++에서 "DcStart에 speed를 담기":
struct Command {
    enum Type { DcStart, DcStop, SortDir1L, SortDir2L, SortDirWarn };
    Type type;
    uint8_t speed;  // DcStart일 때만 유효. 다른 타입일 때 접근하면? → 정의되지 않은 동작 아님, 단지 의미 없는 값

    // 또는 std::variant 사용:
    // std::variant<DcStartCmd, DcStopCmd, ...> — 가능하지만 문법이 극히 복잡
};
```

**Rust**:
```rust
enum Command {
    DcStart(u8),      // speed를 enum variant에 직접 포함
    DcStop,
    SortDir1L,
    SortDir2L,
    SortDirWarn,
}

// 패턴 매칭으로 데이터 추출 — speed는 DcStart일 때만 접근 가능
match cmd {
    Command::DcStart(speed) => dc_motor.drive(MotorSpeed::new(speed))?,
    Command::DcStop => dc_motor.brake()?,
    // ...
}
```

C++의 `std::variant` + `std::visit`로 유사하게 가능하지만:
```cpp
using Command = std::variant<DcStartCmd, DcStopCmd, SortDir1LCmd, SortDir2LCmd, SortDirWarnCmd>;
std::visit(overloaded {
    [](DcStartCmd& c) { /* ... */ },
    [](DcStopCmd&) { /* ... */ },
    // ...
}, cmd);
```
→ 가능은 하지만 **ESP32 Arduino 환경에서 `<variant>`가 제한적**이고, 문법이 현저히 복잡.

> **판정: Rust 소폭 승** — `std::variant`로 가능하지만 실용성 면에서 Rust enum이 압도적으로 간결. 다만 이 프로젝트의 Command는 DcStart만 데이터를 가져서 실질적 차이는 크지 않음.

---

### 2.4 소유권 시스템 — 컴파일 타임 use-after-free 방지

**C++ (잘 짜도)**:
```cpp
// RAII로 자동 해제는 가능. 하지만:
Frame frame = camera.capture();
send_frame(frame);
// frame이 여기서 소멸됨 (소멸자에서 fb_return 호출)

// 하지만 이런 실수는 컴파일 통과:
Frame frame = camera.capture();
Frame frame2 = std::move(frame);
send_frame(frame);   // ← 이동된 객체 사용. 컴파일러: OK (undefined behavior는 아니지만 빈 객체)
```

**Rust**:
```rust
let frame = camera.capture();
let frame2 = frame;        // 소유권 이전
send_frame(&frame);        // ← 컴파일 에러! "value used after move"
```

**이 프로젝트에서의 실질적 영향**: 솔직히 말하면, 카메라 프레임의 이동/복사 실수가 발생할 확률은 낮다. 단일 스레드 메인 루프에서 `capture → send → drop` 패턴이 명확하기 때문. **소유권 시스템의 가치는 코드가 복잡해질수록 증가**하며, 현재 프로젝트 규모에서는 C++ RAII로도 충분히 안전.

> **판정: Rust 소폭 승** — 이론적으로 강력하지만, 이 프로젝트 규모에서는 C++ RAII로도 충분. 프로젝트가 커지면 차이가 벌어짐.

---

### 2.5 `unsafe` 경계의 명시성

**C++**: 모든 코드가 잠재적으로 unsafe. 어디가 위험한지 코드에서 보이지 않음.

**Rust**: `unsafe` 블록이 명시적으로 위험 구간을 표시:
```rust
// 이 프로젝트의 unsafe 사용처:
// 1. 카메라 C 바인딩 (camera.rs) — esp_camera_init, esp_camera_fb_get 등
// 2. ADC FFI (sensor.rs) — adc_oneshot_new_unit, adc_oneshot_read
// 3. 로그 레벨 설정 (main.rs) — esp_log_level_set
```

**이 프로젝트에서의 실질적 영향**: Rust 버전에도 `unsafe`가 **상당히 많다**. 카메라와 ADC가 모두 C FFI이므로, 핵심 하드웨어 접근이 전부 unsafe 안에 있다. **안전한 Rust 래퍼로 감싸는 것이 가치**이지만, 그 래퍼 내부는 결국 C와 동일한 위험도.

> **판정: Rust 소폭 승** — unsafe 경계가 명시적인 것은 가치가 있으나, 이 프로젝트는 하드웨어 FFI가 많아서 unsafe 비율이 높음.

---

## 3. C++만의 진짜 장점 (Rust에서 불가능하거나 어려운 것)

### 3.1 빌드 시간

| 항목 | C++ (PlatformIO) | Rust (esp-idf-svc) |
|------|-------------------|---------------------|
| **최초 빌드** | 30초~1분 | **10분~30분** (esp-idf SDK 전체 컴파일) |
| **증분 빌드** | 2~5초 | 10~30초 |
| **클린 빌드** | 30초~1분 | 5분~15분 |

ESP32 Rust 툴체인은 esp-idf를 내부적으로 사용하며, 최초 빌드 시 전체 SDK를 소스에서 컴파일한다. 이것은 **개발 속도에 직접적 영향**.

> **판정: C++ 압승** — 개발 이터레이션 속도에서 체감 차이가 큼.

### 3.2 생태계 및 라이브러리

| 항목 | C++ (Arduino) | Rust (esp-idf-svc) |
|------|---------------|---------------------|
| ESP32 카메라 | 네이티브 지원 | C 바인딩 + unsafe 래퍼 필요 |
| MQTT | PubSubClient (성숙) | esp-idf-svc 내장 (API 불안정) |
| 서보 모터 | ESP32Servo, MCPWM 모두 | LEDC만 (MCPWM 바인딩 제한적) |
| QR 코드 | quirc, ESP32QRCodeReader 등 | 바인딩 직접 작성 필요 |
| OLED 디스플레이 | Adafruit_SSD1306, U8g2 등 | ssd1306 crate (제한적) |
| OTA 업데이트 | ArduinoOTA (5줄) | esp-ota crate (덜 성숙) |

> **판정: C++ 승** — 특히 ESP32 주변장치 라이브러리에서. 새로운 센서/액추에이터 추가 시 C++이 훨씬 빠름.

### 3.3 팀 접근성 & 디버깅

- ESP32 개발자 대부분이 Arduino/C++ 경험 보유
- Stack Overflow, 포럼, 예제 코드가 C++ 중심
- ESP-IDF 공식 문서가 C/C++ 기준
- 시리얼 모니터 디버깅이 C++에서 더 직관적
- Exception Decoder가 PlatformIO에 내장 (`monitor_filters = esp32_exception_decoder`)

> **판정: C++ 승** — 협업과 유지보수 면에서 현실적 장점.

### 3.4 `std::optional` vs 수동 null 체크 — 런타임 차이 없음

C++17의 `std::optional`은 Rust의 `Option`과 기능적으로 동등. ESP32 Arduino 환경에서도 사용 가능 (C++17 지원됨).

> **판정: 동률**

---

## 4. 수정된 비교 매트릭스 (잘 짠 C++ 기준)

| 평가 기준 | 잘 짠 C++ | Rust | 차이 원인 |
|----------|-----------|------|----------|
| 메모리 안전 (RAII) | 8 | 9 | Rust의 소유권이 이동 후 사용 방지 |
| 에러 처리 강제성 | 5 | **9** | **C++는 에러 무시가 쉬움. Rust는 불가능** |
| 패턴 매칭 완전성 | 6 | **9** | **C++ switch는 경고, Rust match는 에러** |
| 타입 안전 (enum) | 7 | 8 | Rust enum이 데이터를 담아 더 표현적 |
| 빌드 속도 | **9** | 3 | **Rust 최초 빌드 10-30분** |
| 라이브러리 생태계 | **9** | 5 | **ESP32 주변장치 라이브러리** |
| 팀 접근성 | **9** | 4 | **대부분 C++ 경험** |
| 동시성 안전 | 7 | 8 | C++ atomic/FreeRTOS 큐로 유사하게 가능 |
| 모듈화/구조화 | 8 | 8 | 동등 (개발자 역량 문제) |
| 의존성 관리 | 6 | 8 | Cargo가 더 우수하나 lib_deps로 상당 부분 커버 |

---

## 5. 최종 결론: 그래서 어느 게 더 나은가?

### 답: **프로젝트 상황에 따라 다르다** (이전 문서보다 균형 잡힌 결론)

#### Rust가 진짜 나은 경우
- **장기 운영 (24/7)** IoT 디바이스 — 에러 누적 방지가 중요
- **FSM 상태가 계속 늘어나는** 프로젝트 — 패턴 매칭 완전성이 안전망
- **혼자 또는 Rust를 아는 팀** — 학습 비용 없음
- 에러 하나가 **하드웨어 손상**으로 이어질 수 있는 환경

#### C++가 진짜 나은 경우
- **빠른 개발 이터레이션** 필요 — 빌드 시간 차이가 체감됨
- **새 센서/액추에이터를 자주 추가** — 라이브러리 생태계
- **팀이 C++ 경험만 있을 때** — Rust 학습 비용 > 안전성 이점
- **프로토타이핑/교육 목적** — 단순함이 중요

#### 이 프로젝트 (Soy-Controller) 한정 판단

```
현재 상태:
- FSM 4개 상태, 5개 명령 → 규모가 작아서 C++ switch 누락 위험 낮음
- 단일 스레드 메인 루프 → 소유권 시스템의 가치 제한적
- 카메라 + ADC = 핵심이 C FFI → Rust의 unsafe 비율 높음
- 팀 프로젝트 → 접근성 중요

진짜 차이를 만드는 것:
- Result 강제 에러 처리 (Rust 승) — 모터/MQTT 에러 무시 방지
- 빌드 속도 (C++ 승) — 개발 속도에 직접 영향
- 라이브러리 (C++ 승) — 기능 추가 시
```

**솔직한 결론**: 잘 짠 C++과 Rust의 차이는 이전 문서에서 제시한 것보다 **훨씬 작다**. 핵심 차이는 `Result` 에러 처리 강제와 `match` 완전성 검사 두 가지로 압축되며, 이것이 빌드 시간/생태계/접근성 비용을 정당화하는지는 **팀 상황과 프로젝트 수명**에 달려 있다.

- **교육/학습 프로젝트** → 둘 다 OK. Rust를 배우고 싶다면 좋은 기회
- **프로덕션 24/7 운영** → Rust의 에러 강제가 가치 있음
- **빠른 기능 추가 필요** → C++이 현실적
