# 펌웨어 비교 분석: Arduino(PlatformIO) vs Rust(esp-idf-svc)

> **대상 프로젝트**: [iot-repo-3](https://github.com/addinedu-physicalai-1st/iot-repo-3)
> **비교 브랜치**: `hajun_dev` (Arduino) vs `hajun_dev_rust` (Rust)
> **작성일**: 2026-03-03

---

## 1. 프로젝트 개요

**Soy-Controller**는 컨베이어 벨트 기반 물류 분류 시스템의 펌웨어로, 두 개의 ESP32 보드로 구성된다:

| 보드 | 역할 | 핵심 기능 |
|------|------|----------|
| **ESP32-CAM** | 영상 스트리밍 | OV2640 카메라 → UDP JPEG 청크 전송 |
| **ESP32-DevKit** | 컨베이어 FSM 제어 | DC 모터 + 서보 + 근접센서 + RGB LED, MQTT 명령 수신 |

두 브랜치는 **동일한 하드웨어, 동일한 프로토콜, 동일한 동작**을 구현하며, 언어/프레임워크만 다르다.

---

## 2. 구조 비교

### 2.1 디렉토리 구조

**Arduino (`hajun_dev`)**
```
soy-controller/
├── .env
├── env_script.py              # PlatformIO .env 주입 스크립트
├── esp32-cam/
│   ├── platformio.ini
│   ├── src/main.cpp           # 221줄 (전체 로직 단일 파일)
│   └── lib/                   # 벤더 라이브러리 (ArduinoJson, PubSubClient)
│       ├── ArduinoJson-7.x/   # ~300+ 파일
│       └── pubsubclient-master/
└── esp32-devkit/
    ├── platformio.ini
    ├── src/main.cpp           # 516줄 (전체 로직 단일 파일)
    └── lib/
        └── pubsubclient-master/
```

**Rust (`hajun_dev_rust`)**
```
firmware/
├── .env.example
├── Cargo.toml                 # 워크스페이스
├── esp32-cam/
│   ├── Cargo.toml
│   ├── build.rs
│   └── src/
│       ├── main.rs            # 138줄
│       ├── config.rs
│       ├── error.rs
│       ├── wifi.rs
│       └── stream/
│           ├── mod.rs
│           ├── camera.rs      # RAII 래퍼
│           └── udp.rs         # 청크 프로토콜
└── esp32-devkit/
    ├── Cargo.toml
    ├── build.rs
    └── src/
        ├── main.rs            # 378줄
        ├── command.rs         # MQTT 명령 파서
        ├── config.rs
        ├── error.rs
        ├── fsm.rs             # 상태 기계
        ├── wifi.rs
        ├── motor/
        │   ├── mod.rs
        │   ├── dc.rs          # DC 모터 RAII
        │   └── servo.rs       # 서보 모터 RAII
        └── peripheral/
            ├── mod.rs
            ├── led.rs         # RGB LED
            └── sensor.rs      # ADC 근접센서
```

### 2.2 코드 규모

| 항목 | Arduino | Rust |
|------|---------|------|
| ESP32-CAM 소스 | 1파일, 221줄 | 7파일, 535줄 |
| ESP32-DevKit 소스 | 1파일, 516줄 | 12파일, 976줄 |
| **총 프로젝트 소스** | **2파일, 737줄** | **19파일, 1,511줄** |
| 벤더 라이브러리 (레포 내) | ~578파일 (ArduinoJson, PubSubClient) | 0파일 (Cargo가 관리) |
| 레포 전체 파일 수 | 587 | 35 (components 제외) |

---

## 3. 핵심 차이점 상세 분석

### 3.1 메모리 안전성

**Arduino (C++)**
```cpp
// 카메라 프레임 버퍼: 수동 관리 필수
camera_fb_t *fb = esp_camera_fb_get();
if (!fb) return;
// ... fb 사용 ...
esp_camera_fb_return(fb);  // 반드시 호출해야 함 — 빼먹으면 메모리 누수
```
- 프레임 반환을 잊으면 PSRAM이 고갈되어 스트리밍이 멈춤
- `fb` 반환 후에도 포인터가 유효한 것처럼 접근 가능 (use-after-free)
- `volatile bool _streaming`에 대한 동시 접근이 C++ 메모리 모델에서 정의되지 않음

**Rust**
```rust
// Frame RAII: Drop 시 자동 반환
pub struct Frame {
    fb: *mut camera::camera_fb_t,
}
impl Drop for Frame {
    fn drop(&mut self) {
        unsafe { camera::esp_camera_fb_return(self.fb); }
    }
}

// 사용: 스코프를 벗어나면 자동 해제
match camera.capture() {
    Some(frame) => {
        streamer.send_frame(&frame)?;
        // frame은 여기서 Drop → esp_camera_fb_return 자동 호출
    }
    None => { ... }
}
```
- **RAII 패턴**으로 리소스 누수가 구조적으로 불가능
- `AtomicBool`로 스레드 안전한 스트리밍 플래그 관리
- ADC 센서도 `Drop`에서 `adc_oneshot_del_unit` 자동 호출

### 3.2 에러 처리

**Arduino (C++)**
```cpp
// 에러 발생 시: 무한 루프로 정지하거나 무시
esp_err_t err = esp_camera_init(&camera_config);
if (err != ESP_OK) {
    Serial.printf("[FAIL] Camera init error 0x%x\n", err);
    while (true) delay(1000);  // 영원히 정지
}

// MQTT 실패: 조용히 넘어감
if (mqtt.connect(clientId.c_str())) {
    mqtt.subscribe(TOPIC_CONTROL);
} else {
    Serial.printf("failed, rc=%d\n", mqtt.state());
    // 에러가 전파되지 않음
}
```

**Rust**
```rust
// 계층적 에러 타입 시스템
pub enum AppError {
    Wifi(EspError),
    Mqtt(EspError),
    Motor(MotorError),
    Sensor(EspError),
    Esp(EspError),
}

// ? 연산자로 일관된 에러 전파
let _wifi = wifi::connect(peripherals.modem, sys_loop, nvs)?;  // 실패 시 즉시 반환
dc_motor.drive(MotorSpeed::new(speed))?;                       // 모터 에러도 전파
publish_status(&mut client, State::Running)?;                   // MQTT 에러도 전파
```
- **모든 오류가 명시적이고 추적 가능** (에러를 무시하면 컴파일러가 경고)
- `Display` 트레잇으로 사람이 읽을 수 있는 에러 메시지 출력
- `From` 변환으로 에러 계층간 자동 변환

### 3.3 타입 안전성

**Arduino (C++)**
```cpp
// 서보 각도: 아무 정수나 넣을 수 있음
void writeDeg(int deg) {
    deg = constrain(deg, 0, 180);  // 런타임에서야 클리핑
    ...
}

// DC 속도: 범위 검증이 런타임에만 존재
int speed = constrain(msg.substring(colonIdx + 1).toInt(), 0, 255);
```

**Rust**
```rust
// 서보 각도: 컴파일 타임에 유효성 보장 (Newtype 패턴)
pub struct ServoAngle(u32);
impl ServoAngle {
    pub const CENTER: Self = Self(90);  // 컴파일 타임 상수
    pub fn try_new(angle: u32) -> Result<Self, MotorError> {
        if angle <= 180 { Ok(Self(angle)) }
        else { Err(MotorError::AngleOutOfRange(angle)) }
    }
}

// DC 속도: u8 뉴타입으로 0-255 자동 보장
pub struct MotorSpeed(u8);

// MQTT 명령 파서: 패턴 매칭으로 모든 케이스 강제 처리
impl<'a> TryFrom<&'a str> for Command {
    fn try_from(s: &'a str) -> Result<Self, Self::Error> {
        match s {
            "DC_STOP" => Ok(Command::DcStop),
            "SORT_DIR:1L" => Ok(Command::SortDir1L),
            _ if s.starts_with("DC_START:") => /* 파싱 */,
            _ => Err(ParseError::Unknown(msg)),
        }
    }
}
```
- `ServoAngle`, `MotorSpeed` 등 **뉴타입 패턴**으로 잘못된 값이 생성 자체가 불가능
- `Command` enum으로 MQTT 명령이 타입으로 표현됨 (문자열 비교 실수 방지)
- FSM `State` enum의 `match` 표현식은 모든 상태를 처리하지 않으면 컴파일 에러

### 3.4 코드 모듈화

**Arduino**: 모든 로직이 `main.cpp` 단일 파일에 존재 (516줄 + 221줄)
- 전역 변수들이 파일 최상단에 산재
- 관심사 분리 없이 하드웨어 초기화, FSM, MQTT, 센서가 혼재
- 코드 재사용이 어려움

**Rust**: 도메인별 모듈로 명확히 분리
```
motor/     → DC모터, 서보 드라이버 (각각 독립 파일)
peripheral/→ LED, 센서 (각각 독립 파일)
fsm.rs     → 상태 기계 로직만 분리
command.rs → MQTT 프로토콜 파싱만 분리
config.rs  → 설정값 중앙 관리
error.rs   → 에러 타입 계층
wifi.rs    → WiFi 연결 로직
```
- 각 모듈이 단일 책임 원칙을 준수
- `main.rs`는 조합(orchestration)만 담당

### 3.5 의존성 관리

**Arduino**
- `lib/` 디렉토리에 라이브러리 전체 소스를 직접 복사 (vendoring)
- ArduinoJson 7.x: ~300+ 파일이 레포에 포함
- PubSubClient: ~50 파일이 레포에 포함
- **레포 587 파일 중 ~578 파일이 벤더 코드**
- 버전 업데이트 시 수동으로 파일 교체 필요

**Rust**
- `Cargo.toml`에 의존성 선언, 빌드 시 자동 다운로드
- 레포에 벤더 코드 0 파일
- `cargo update`로 원클릭 업데이트
- 워크스페이스로 esp32-cam/esp32-devkit가 공통 설정 공유

### 3.6 동시성 모델

**Arduino**
```cpp
// MQTT 콜백에서 volatile 변수 직접 수정 (ISR이 아니라 동일 스레드지만)
static volatile bool _streaming = false;
static void mqttCallback(char* topic, byte* payload, unsigned int length) {
    if (msg.startsWith("DC_START")) {
        _streaming = true;  // C++ 메모리 모델에서 volatile ≠ atomic
    }
}
```

**Rust**
```rust
// 메인 루프 ↔ MQTT 콜백 간 통신
// CAM: AtomicBool (lock-free, 메모리 순서 명시)
let streaming = Arc::new(AtomicBool::new(false));
streaming_flag.store(true, Ordering::Relaxed);

// DevKit: mpsc 채널 (타입 안전 메시지 패싱)
let (tx, rx) = mpsc::sync_channel::<Command>(20);
// 콜백에서: tx.send(cmd)
// 메인 루프에서: while let Ok(cmd) = rx.try_recv() { ... }
```
- ESP32-CAM: `AtomicBool`로 단순 플래그 제어 (올바른 lock-free 패턴)
- ESP32-DevKit: `mpsc::sync_channel`로 **명령 큐** 구현 — MQTT 콜백과 메인 루프가 완전히 분리됨
- Arduino 버전은 콜백 안에서 직접 상태를 변경하여, 콜백 중 재진입 시 경쟁 조건 가능성 존재

### 3.7 빌드 시스템 및 환경변수 주입

**Arduino**
```python
# env_script.py: PlatformIO 빌드 훅
flag = f'-D{key}=\\"{val}\\"'
env.Append(BUILD_FLAGS=[flag])
```
- 환경변수가 C 전처리기 매크로(`-DWIFI_SSID="..."`)로 주입
- `#error` 지시자로 누락 시 컴파일 에러 발생 (좋은 패턴)

**Rust**
```rust
// build.rs: Cargo 빌드 스크립트
println!("cargo:rustc-env={}={}", clean_key, clean_val);

// config.rs: 컴파일 타임에 주입 확인
pub wifi_ssid: &'static str,
// ...
wifi_ssid: env!("WIFI_SSID"),  // 없으면 컴파일 에러
```
- `env!()` 매크로는 환경변수가 없으면 **컴파일 타임 에러** 발생
- `Config` 구조체에 타입화되어 IDE 자동완성/리팩토링 지원
- `.env.example` 파일 제공으로 설정 가이드 명확

---

## 4. ESP32 임베디드 컨텍스트에서의 Rust 장단점

### 4.1 Rust의 장점

| 항목 | 설명 |
|------|------|
| **메모리 안전** | 카메라 프레임 버퍼, ADC 핸들 등 하드웨어 리소스의 RAII 관리. 누수/이중 해제 원천 차단 |
| **컴파일 타임 검증** | 뉴타입(`ServoAngle`, `MotorSpeed`), enum(`State`, `Command`)으로 잘못된 값/상태가 코드에 존재할 수 없음 |
| **에러 전파** | `Result<T, E>` + `?` 연산자로 모든 에러 경로가 명시적. 에러를 무시하면 컴파일러가 경고 |
| **모듈 시스템** | Cargo 워크스페이스로 두 보드가 공통 설정을 공유. 관심사 분리가 자연스러움 |
| **의존성 관리** | Cargo.toml 선언만으로 의존성 해결. 레포에 벤더 코드 불필요 (587 → 35 파일) |
| **동시성 안전** | `AtomicBool`, `mpsc::channel`로 콜백-메인루프 간 경쟁 조건 방지 |
| **패턴 매칭 완전성** | FSM state에 대한 `match`에서 상태를 빼먹으면 컴파일 에러 |
| **UDP 에러 복구** | ENOMEM 시 프레임 드롭 + 통계 로깅 등 세밀한 에러 핸들링 |

### 4.2 Rust의 단점

| 항목 | 설명 |
|------|------|
| **코드량 증가** | 737줄 → 1,511줄 (약 2배). 타입 정의, 에러 타입, From 변환 등 보일러플레이트 |
| **학습 곡선** | 소유권, 라이프타임, unsafe, esp-idf-svc API 이해 필요 |
| **unsafe 블록** | 카메라 C 바인딩, ADC FFI 등에서 `unsafe` 필수. 완전한 안전성은 아님 |
| **빌드 시간** | 초기 빌드 시 esp-idf SDK 전체를 컴파일 (수 분~수십 분). Arduino는 수 초 |
| **생태계 성숙도** | esp-idf-svc가 아직 1.0 미만. API 변경 가능성 존재 |
| **디버깅 어려움** | 스택 트레이스가 C++ 대비 덜 직관적. 패닉 메시지가 ESP32에서 제한적 |
| **팀 접근성** | Arduino는 대부분의 임베디드 개발자가 즉시 읽을 수 있지만, Rust는 그렇지 않음 |
| **bindgen 호환성** | `__bindgen_anon_*` 같은 자동 바인딩 불안정성 (카메라 바인딩에서 실제로 발생) |

---

## 5. 기능별 1:1 비교 매트릭스

| 기능 | Arduino | Rust | 승자 |
|------|---------|------|------|
| WiFi 연결 | `WiFi.begin()` + 폴링 | `BlockingWifi` + 에러 전파 | Rust (에러 처리) |
| MQTT 클라이언트 | PubSubClient (lib/ 복사) | esp-idf-svc 내장 | Rust (의존성 관리) |
| 카메라 프레임 관리 | 수동 get/return | RAII Frame + Drop | **Rust** (메모리 안전) |
| UDP 스트리밍 | `WiFiUdp` + 15ms delay | `UdpSocket` + ENOMEM 처리 + 통계 | **Rust** (에러 복구) |
| FSM 구현 | enum + switch/if | enum + match + 타입 상태 | **Rust** (완전성 보장) |
| DC 모터 제어 | LEDC 직접 사용 | RAII `DcMotor` + 뉴타입 속도 | Rust (타입 안전) |
| 서보 제어 | MCPWM 직접 사용 | LEDC + 뉴타입 각도 | 비슷 |
| ADC 센서 | `analogRead()` | unsafe FFI oneshot | Arduino (간결함) |
| MQTT 명령 파싱 | `String.startsWith()` | `Command` enum + TryFrom | **Rust** (타입 안전) |
| .env 주입 | Python 스크립트 | build.rs + env!() | Rust (네이티브) |
| 코드 가독성 | 단일 파일, 직관적 | 다중 모듈, 추상화 | **Arduino** (단순함) |
| 개발 속도 | 빠름 | 느림 | **Arduino** |
| 디버깅 | Serial.printf 간편 | log 매크로 | 비슷 |

---

## 6. 결론 및 권장사항

### 이 프로젝트에서는 **Rust를 권장**한다.

#### 핵심 근거

1. **메모리 안전이 실질적 가치를 갖는 프로젝트**
   - ESP32-CAM의 PSRAM 프레임 버퍼 관리는 메모리 누수에 매우 취약한 영역
   - Arduino 버전에서 `esp_camera_fb_return(fb)` 호출을 빼먹으면 스트리밍이 멈추는데, Rust의 RAII는 이를 구조적으로 방지
   - 장시간 운영되는 IoT 디바이스에서 메모리 누수는 치명적

2. **FSM 기반 제어 시스템에 타입 시스템이 적합**
   - 4개 상태(IDLE/RUNNING/SORTING/WARNING) × 5개 명령의 조합에서 **누락된 케이스를 컴파일러가 잡아줌**
   - Arduino의 `if/else if` 체인은 새 상태 추가 시 누락 위험
   - `SortDir` enum은 "1L" / "2L" / 미분류를 타입으로 강제하여 문자열 비교 오류 방지

3. **Cargo 워크스페이스가 다중 보드 프로젝트에 적합**
   - esp32-cam / esp32-devkit가 공통 설정 공유
   - Arduino는 두 프로젝트가 완전히 독립적 (lib/ 중복 복사)

4. **동시성 안전이 MQTT 콜백 구조에서 중요**
   - DevKit의 `mpsc::sync_channel`은 콜백→메인루프 간 **제로 경쟁 조건 통신** 보장
   - Arduino의 콜백 내 직접 상태 변경은 미묘한 버그 가능성 내포

#### Arduino가 더 나을 수 있는 경우

- **빠른 프로토타이핑**: PoC 단계에서 2파일 737줄이면 충분
- **팀 전원이 Rust를 모를 때**: 학습 비용이 프로젝트 일정을 초과할 수 있음
- **하드웨어 변경이 잦을 때**: Arduino 라이브러리 생태계가 훨씬 넓음
- **빌드 환경 제약**: Rust ESP32 툴체인 설치가 Arduino 대비 복잡

#### 최종 판단

| 평가 기준 | 가중치 | Arduino | Rust |
|----------|--------|---------|------|
| 코드 안전성 (메모리/타입) | 30% | 5 | 9 |
| 유지보수성 | 25% | 5 | 8 |
| 에러 처리 | 15% | 4 | 9 |
| 개발 생산성 | 15% | 9 | 5 |
| 의존성 관리 | 10% | 3 | 9 |
| 팀 접근성 | 5% | 9 | 4 |
| **가중 평균** | | **5.55** | **7.65** |

> **이 프로젝트처럼 장시간 운영되는 IoT 시스템에서, 카메라 스트리밍과 FSM 기반 모터 제어를 동시에 수행하는 경우, Rust의 안전성 보장이 약간의 코드량 증가와 학습 비용을 상쇄하고도 남는다.** 특히 카메라 프레임 버퍼의 RAII 관리와 MQTT 명령의 타입 안전 파싱은 장기 운영 안정성에 직접적으로 기여한다.
