#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "driver/spi_master.h"
#include "soc/gpio_struct.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"

#include "rc522.h"

static const char* TAG = "ESP-RC522-DUAL";

struct rc522 {
    bool running;
    rc522_config_t* config;
    spi_device_handle_t spi;
    TaskHandle_t task_handle;
    bool scan_started;
    bool tag_was_present_last_time;
};

typedef struct rc522* rc522_handle_t;

// 🌟 [수정 포인트 1] 단일 변수를 배열로 확장하여 2개까지 지원
#define MAX_RC522_DEVICES 2
static rc522_handle_t hndls[MAX_RC522_DEVICES] = {NULL, NULL};
static int device_count = 0;
static rc522_handle_t active_hndl = NULL; // 현재 통신 중인 장치
static bool spi_bus_initialized = false;  // SPI 버스 중복 초기화 방지

#define rc522_fw_version() rc522_read(0x37)

bool rc522_is_inited() {
    return device_count > 0;
}

// 🌟 [수정 포인트 2] SPI 통신 버스는 한 번만 열고, 디바이스(CS핀)만 추가로 등록
static esp_err_t rc522_spi_init() {
    if(! active_hndl || ! active_hndl->config) {
        ESP_LOGE(TAG, "Fail to init SPI. Invalid handle");
        return ESP_ERR_INVALID_STATE;
    }

    if(active_hndl->spi) {
        ESP_LOGW(TAG, "SPI already initialized for this device");
        return ESP_ERR_INVALID_STATE;
    }

    // SPI 버스는 최초 1회만 초기화합니다.
    if(!spi_bus_initialized) {
        spi_bus_config_t buscfg = {
            .miso_io_num = active_hndl->config->miso_io,
            .mosi_io_num = active_hndl->config->mosi_io,
            .sclk_io_num = active_hndl->config->sck_io,
            .quadwp_io_num = -1,
            .quadhd_io_num = -1
        };
        esp_err_t err = spi_bus_initialize(active_hndl->config->spi_host_id, &buscfg, 0);
        if(err != ESP_OK) return err;
        spi_bus_initialized = true;
    }

    // 각 RFID 모듈의 고유한 CS 핀(SDA)을 등록합니다.
    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = 5000000,
        .mode = 0,
        .spics_io_num = active_hndl->config->sda_io,
        .queue_size = 7,
        .flags = SPI_DEVICE_HALFDUPLEX
    };

    esp_err_t err = spi_bus_add_device(active_hndl->config->spi_host_id, &devcfg, &active_hndl->spi);
    if(err != ESP_OK) {
        active_hndl->spi = NULL;
    }
    return err;
}

// 🌟 [수정 포인트 3] 모든 읽기/쓰기 함수가 active_hndl을 바라보도록 변경
static esp_err_t rc522_write_n(uint8_t addr, uint8_t n, uint8_t *data) {
    uint8_t* buffer = (uint8_t*) malloc(n + 1);
    buffer[0] = (addr << 1) & 0x7E;
    for (uint8_t i = 1; i <= n; i++) {
        buffer[i] = data[i-1];
    }
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    t.length = 8 * (n + 1);
    t.tx_buffer = buffer;
    esp_err_t ret = spi_device_transmit(active_hndl->spi, &t);
    free(buffer);
    return ret;
}

static esp_err_t rc522_write(uint8_t addr, uint8_t val) {
    return rc522_write_n(addr, 1, &val);
}

static uint8_t* rc522_read_n(uint8_t addr, uint8_t n) {
    if (n <= 0) return NULL;
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    uint8_t* buffer = (uint8_t*) malloc(n);
    t.flags = SPI_TRANS_USE_TXDATA;
    t.length = 8;
    t.tx_data[0] = ((addr << 1) & 0x7E) | 0x80;
    t.rxlength = 8 * n;
    t.rx_buffer = buffer;
    esp_err_t ret = spi_device_transmit(active_hndl->spi, &t);
    assert(ret == ESP_OK);
    return buffer;
}

static uint8_t rc522_read(uint8_t addr) {
    uint8_t* buffer = rc522_read_n(addr, 1);
    uint8_t res = buffer[0];
    free(buffer);
    return res;
}

static esp_err_t rc522_set_bitmask(uint8_t addr, uint8_t mask) {
    return rc522_write(addr, rc522_read(addr) | mask);
}

static esp_err_t rc522_clear_bitmask(uint8_t addr, uint8_t mask) {
    return rc522_write(addr, rc522_read(addr) & ~mask);
}

static esp_err_t rc522_antenna_on() {
    esp_err_t ret;
    if(~ (rc522_read(0x14) & 0x03)) {
        ret = rc522_set_bitmask(0x14, 0x03);
        if(ret != ESP_OK) return ret;
    }
    return rc522_write(0x26, 0x60); // 43dB gain
}

static void rc522_task(void* arg);

esp_err_t rc522_init(rc522_config_t* config) {
    if(! config) return ESP_ERR_INVALID_ARG;
    if(device_count >= MAX_RC522_DEVICES) {
        ESP_LOGE(TAG, "Max devices reached!");
        return ESP_ERR_NO_MEM;
    }

    rc522_handle_t new_hndl = calloc(1, sizeof(struct rc522));
    if(!new_hndl) return ESP_ERR_NO_MEM;

    if(! (new_hndl->config = calloc(1, sizeof(rc522_config_t)))) {
        free(new_hndl);
        return ESP_ERR_NO_MEM;
    }

    new_hndl->config->callback         = config->callback;
    new_hndl->config->miso_io          = config->miso_io == 0 ? RC522_DEFAULT_MISO : config->miso_io;
    new_hndl->config->mosi_io          = config->mosi_io == 0 ? RC522_DEFAULT_MOSI : config->mosi_io;
    new_hndl->config->sck_io           = config->sck_io == 0 ? RC522_DEFAULT_SCK : config->sck_io;
    new_hndl->config->sda_io           = config->sda_io == 0 ? RC522_DEFAULT_SDA : config->sda_io;
    new_hndl->config->spi_host_id      = config->spi_host_id == 0 ? RC522_DEFAULT_SPI_HOST : config->spi_host_id;
    new_hndl->config->scan_interval_ms = config->scan_interval_ms < 50 ? RC522_DEFAULT_SCAN_INTERVAL_MS : config->scan_interval_ms;
    new_hndl->config->task_stack_size  = config->task_stack_size == 0 ? RC522_DEFAULT_TACK_STACK_SIZE : config->task_stack_size;
    new_hndl->config->task_priority    = config->task_priority == 0 ? RC522_DEFAULT_TACK_STACK_PRIORITY : config->task_priority;

    hndls[device_count] = new_hndl;
    active_hndl = new_hndl; // 초기화 중인 장치를 활성 상태로 설정

    esp_err_t err = rc522_spi_init();
    if(err != ESP_OK) return err;
    
    // ---------- RW test ------------
    const uint8_t test_addr = 0x24, test_val = 0x25;
    for(uint8_t i = test_val; i < test_val + 2; i++) {
        if((err = rc522_write(test_addr, i)) != ESP_OK || rc522_read(test_addr) != i) {
            ESP_LOGE(TAG, "RW test fail on device %d", device_count);
            return err;
        }
    }

    rc522_write(0x01, 0x0F);
    rc522_write(0x2A, 0x8D);
    rc522_write(0x2B, 0x3E);
    rc522_write(0x2D, 0x1E);
    rc522_write(0x2C, 0x00);
    rc522_write(0x15, 0x40);
    rc522_write(0x11, 0x3D);
    rc522_antenna_on();

    active_hndl->running = true;
    device_count++;

    // 🌟 [수정 포인트 4] 백그라운드 스캔 태스크는 최초 1회만 생성!
    if(device_count == 1) {
        if (xTaskCreate(rc522_task, "rc522_task", active_hndl->config->task_stack_size, NULL, active_hndl->config->task_priority, &active_hndl->task_handle) != pdTRUE) {
            ESP_LOGE(TAG, "Fail to create rc522 task");
            return err;
        }
    }

    ESP_LOGI(TAG, "Device %d Initialized (firmware: 0x%x)", device_count, rc522_fw_version());
    return ESP_OK;
}

// ... (rc522_sn_to_u64, rc522_calculate_crc, rc522_card_write, rc522_request, rc522_anticoll, rc522_get_tag 함수들은 내용 변경 없이 그대로 유지됩니다. 코드가 길어 생략된 부분입니다. 기존 코드 그대로 쓰시면 됩니다.) ...
uint64_t rc522_sn_to_u64(uint8_t* sn) {
    if(!sn) return 0;
    uint64_t result = 0;
    for(int i = 4; i >= 0; i--) {
        result |= ((uint64_t) sn[i] << (i * 8));
    }
    return result;
}

static uint8_t* rc522_calculate_crc(uint8_t *data, uint8_t n) {
    rc522_clear_bitmask(0x05, 0x04);
    rc522_set_bitmask(0x0A, 0x80);
    rc522_write_n(0x09, n, data);
    rc522_write(0x01, 0x03);
    uint8_t i = 255;
    uint8_t nn = 0;
    for(;;) {
        nn = rc522_read(0x05);
        i--;
        if(! (i != 0 && ! (nn & 0x04))) break;
    }
    uint8_t* res = (uint8_t*) malloc(2); 
    res[0] = rc522_read(0x22);
    res[1] = rc522_read(0x21);
    return res;
}

static uint8_t* rc522_card_write(uint8_t cmd, uint8_t *data, uint8_t n, uint8_t* res_n) {
    uint8_t *result = NULL;
    uint8_t irq = 0x00;
    uint8_t irq_wait = 0x00;
    uint8_t last_bits = 0;
    uint8_t nn = 0;
    if(cmd == 0x0E) { irq = 0x12; irq_wait = 0x10; }
    else if(cmd == 0x0C) { irq = 0x77; irq_wait = 0x30; }

    rc522_write(0x02, irq | 0x80);
    rc522_clear_bitmask(0x04, 0x80);
    rc522_set_bitmask(0x0A, 0x80);
    rc522_write(0x01, 0x00);
    rc522_write_n(0x09, n, data);
    rc522_write(0x01, cmd);
    if(cmd == 0x0C) rc522_set_bitmask(0x0D, 0x80);

    uint16_t i = 1000;
    for(;;) {
        nn = rc522_read(0x04);
        i--;
        if(! (i != 0 && (((nn & 0x01) == 0) && ((nn & irq_wait) == 0)))) break;
    }
    rc522_clear_bitmask(0x0D, 0x80);

    if(i != 0) {
        if((rc522_read(0x06) & 0x1B) == 0x00) {
            if(cmd == 0x0C) {
                nn = rc522_read(0x0A);
                last_bits = rc522_read(0x0C) & 0x07;
                if (last_bits != 0) *res_n = (nn - 1) + last_bits;
                else *res_n = nn;
                result = (uint8_t*) malloc(*res_n);
                for(i = 0; i < *res_n; i++) result[i] = rc522_read(0x09);
            }
        }
    }
    return result;
}

static uint8_t* rc522_request(uint8_t* res_n) {
    uint8_t* result = NULL;
    rc522_write(0x0D, 0x07);
    uint8_t req_mode = 0x26;
    result = rc522_card_write(0x0C, &req_mode, 1, res_n);
    if(result && *res_n * 8 != 0x10) {
        free(result);
        return NULL;
    }
    return result;
}

static uint8_t* rc522_anticoll() {
    uint8_t res_n;
    rc522_write(0x0D, 0x00);
    uint8_t* result = rc522_card_write(0x0C, (uint8_t[]) { 0x93, 0x20 }, 2, &res_n);
    if(result && res_n != 5) { 
        free(result);
        return NULL;
    }
    return result;
}

static uint8_t* rc522_get_tag() {
    uint8_t* result = NULL;
    uint8_t* res_data = NULL;
    uint8_t res_data_n;
    res_data = rc522_request(&res_data_n);
    if(res_data != NULL) {
        free(res_data);
        result = rc522_anticoll();
        if(result != NULL) {
            uint8_t buf[] = { 0x50, 0x00, 0x00, 0x00 };
            uint8_t* crc = rc522_calculate_crc(buf, 2);
            buf[2] = crc[0];
            buf[3] = crc[1];
            free(crc);
            res_data = rc522_card_write(0x0C, buf, 4, &res_data_n);
            if(res_data) free(res_data);
            rc522_clear_bitmask(0x08, 0x08);
            return result;
        }
    }
    return NULL;
}

esp_err_t rc522_start(rc522_start_args_t start_args) {
    esp_err_t err = rc522_init(&start_args);
    return err != ESP_OK ? err : rc522_start2();
}

esp_err_t rc522_start2() {
    if(! active_hndl) return ESP_ERR_INVALID_STATE;
    active_hndl->scan_started = true;
    return ESP_OK;
}

esp_err_t rc522_pause() {
    if(! active_hndl) return ESP_ERR_INVALID_STATE;
    active_hndl->scan_started = false;
    return ESP_OK;
}

void rc522_destroy() {
    // 사용하지 않는 기능이므로 생략 (듀얼 모드에서는 개별 삭제 시 버스 충돌 우려가 있음)
}

// 🌟 [수정 포인트 5] 태스크가 배열을 돌면서 1번 RFID와 2번 RFID를 번갈아가며 스캔!
static void rc522_task(void* arg) {
    while(1) {
        for(int i = 0; i < device_count; i++) {
            active_hndl = hndls[i]; // 컨텍스트 스위칭! 통신 대상을 바꿈

            if(!active_hndl->running || !active_hndl->scan_started) continue;

            uint8_t* serial_no = rc522_get_tag();

            if(serial_no && !active_hndl->tag_was_present_last_time) {
                rc522_tag_callback_t cb = active_hndl->config->callback;
                if(cb) { cb(serial_no); }
            }
            
            if((active_hndl->tag_was_present_last_time = (serial_no != NULL))) {
                free(serial_no);
                serial_no = NULL;
            }
        }
        
        // 두 RFID를 모두 훑어본 후 50ms 대기 (통신 과부하 방지)
        vTaskDelay(50 / portTICK_PERIOD_MS);
    }
    vTaskDelete(NULL);
}