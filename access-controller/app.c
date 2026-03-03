#include <stdio.h>
#include <unistd.h>
#include <math.h>
#include <string.h>

// 🌟 FreeRTOS 관련 에러(vTaskDelete)를 방지하기 위한 필수 헤더
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <driver/gpio.h>
#include <driver/ledc.h>
#include <driver/spi_master.h>
#include "esp_log.h"

#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>

#include <std_msgs/msg/bool.h>
#include <std_msgs/msg/string.h>
#include <std_srvs/srv/set_bool.h>

#include "rc522.h"
#include <rosidl_runtime_c/string_functions.h>

#define ledPin 2
#define servoPin 27
#define RC522_MISO_PIN 19
#define RC522_MOSI_PIN 23
#define RC522_SCK_PIN  18
#define RC522_SDA_PIN  5
#define RC522_SDA_PIN_2  17

#define SERVO_MIN_PULSEWIDTH 500
#define SERVO_MAX_PULSEWIDTH 2500
#define SERVO_MAX_DEGREE     180
#define LEDC_TIMER           LEDC_TIMER_0
#define LEDC_MODE            LEDC_LOW_SPEED_MODE
#define LEDC_CHANNEL         LEDC_CHANNEL_0
#define LEDC_DUTY_RES        LEDC_TIMER_13_BIT 
#define LEDC_FREQUENCY       50             

#define RCCHECK(fn) { rcl_ret_t temp_rc = fn; if((temp_rc != RCL_RET_OK)){printf("Failed status on line %d: %d. Aborting.\n",__LINE__,(int)temp_rc);vTaskDelete(NULL);}}
#define RCSOFTCHECK(fn) { rcl_ret_t temp_rc = fn; if((temp_rc != RCL_RET_OK)){printf("Failed status on line %d: %d. Continuing.\n",__LINE__,(int)temp_rc);}}

rcl_publisher_t status_publisher;
rcl_publisher_t rfid_publisher_entrance;
rcl_publisher_t rfid_publisher_exit;
std_msgs__msg__Bool status_msg;
std_msgs__msg__String rfid_msg;
size_t domain_id = 25;

// 🌟 [추가] 문 열림 남은 시간을 계산할 카운트다운 전역 변수
int door_open_countdown = 0; 

uint32_t servo_degree_to_duty(int degree) {
    uint32_t cal_pulsewidth = (SERVO_MIN_PULSEWIDTH + (((SERVO_MAX_PULSEWIDTH - SERVO_MIN_PULSEWIDTH) * degree) / SERVO_MAX_DEGREE));
    return (uint32_t)((pow(2, LEDC_TIMER_13_BIT) - 1) * cal_pulsewidth / 20000);
}

void set_servo_angle(int degree) {
    ledc_set_duty(LEDC_MODE, LEDC_CHANNEL, servo_degree_to_duty(degree));
    ledc_update_duty(LEDC_MODE, LEDC_CHANNEL);
}

// 🌟 [수정] 1초마다 실행되는 타이머 콜백 (여기에 카운트다운 로직이 들어갑니다)
void timer_callback(rcl_timer_t * timer, int64_t last_call_time) {
    RCLC_UNUSED(last_call_time);
    if (timer != NULL) {
        // LED 상태 퍼블리시
        status_msg.data = gpio_get_level(ledPin);
        RCSOFTCHECK(rcl_publish(&status_publisher, &status_msg, NULL));

        // 🌟 도어락 자동 닫힘 로직 (블로킹 없이 1초마다 감소)
        if (door_open_countdown > 0) {
            door_open_countdown--;  // 1초 감소
            if (door_open_countdown == 0) {
                gpio_set_level(ledPin, 0); // LED OFF
                set_servo_angle(0);        // 서보모터 0도로 복귀
            }
        }
    }
}

void service_callback(const void * req, void * res) {
    std_srvs__srv__SetBool_Request * req_in = (std_srvs__srv__SetBool_Request *) req;
    std_srvs__srv__SetBool_Response * res_in = (std_srvs__srv__SetBool_Response *) res;
    
    gpio_set_level(ledPin, req_in->data);
    set_servo_angle(req_in->data ? 90 : 0);
    
    printf("Command Received: LED %s\n", req_in->data ? "ON" : "OFF");
    res_in->success = true;
}
static const char *TAG = "RFID_SYSTEM";

// 🌟 [수정] 2020년 순정 라이브러리 전용 콜백 함수
void rfid_callback_entrance(uint8_t* sn) {
    if (door_open_countdown > 0)
        return;
    
    char uid_str[20];
    snprintf(uid_str, sizeof(uid_str), "%02X%02X%02X%02X%02X", sn[0], sn[1], sn[2], sn[3], sn[4]);
    
    // micro-ROS String 메시지에 안전하게 복사
    rosidl_runtime_c__String__assign(&rfid_msg.data, uid_str);
    rfid_msg.data.size = strlen(uid_str);
    rfid_msg.data.capacity = sizeof(uid_str);
    RCSOFTCHECK(rcl_publish(&rfid_publisher_entrance, &rfid_msg, NULL));

    // 🌟 특정 태그(F09D64D8D1) 인식 시 비즈니스 로직
    if (strcmp(uid_str, "F09D64D8D1") == 0) {
        // 문이 닫혀있을 때만 인증 완료 메시지 출력 (중복 출력 방지용)
        if (door_open_countdown == 0) {
            printf("✅ 인증 완료! 문을 엽니다. (Tag: %s)\n", uid_str);
            gpio_set_level(ledPin, 1); // LED ON
            set_servo_angle(90);       // 서보모터 90도로 이동
        }
        
        // 🌟 딜레이(Delay) 없이 카운트다운 변수만 5로 리셋하고 즉시 함수 종료!
        // (열려있는 도중에 다시 카드를 대면 5초부터 다시 시작됩니다)
        door_open_countdown = 5; 
    }
}

void rfid_callback_exit(uint8_t* sn) {
    if (door_open_countdown > 0)
        return;
    
    char uid_str[20];
    snprintf(uid_str, sizeof(uid_str), "%02X%02X%02X%02X%02X", sn[0], sn[1], sn[2], sn[3], sn[4]);
    
    // micro-ROS로 태그 UID 전송
    rosidl_runtime_c__String__assign(&rfid_msg.data, uid_str);
    rfid_msg.data.size = strlen(uid_str);
    rfid_msg.data.capacity = sizeof(uid_str);
    RCSOFTCHECK(rcl_publish(&rfid_publisher_exit, &rfid_msg, NULL));

    // 🌟 특정 태그(F09D64D8D1) 인식 시 비즈니스 로직
    if (strcmp(uid_str, "F09D64D8D1") == 0) {
        // 문이 닫혀있을 때만 인증 완료 메시지 출력 (중복 출력 방지용)
        if (door_open_countdown == 0) {
            printf("✅ 인증 완료! 문을 엽니다. (Tag: %s)\n", uid_str);
            gpio_set_level(ledPin, 1); // LED ON
            set_servo_angle(90);       // 서보모터 90도로 이동
        }
        
        // 🌟 딜레이(Delay) 없이 카운트다운 변수만 5로 리셋하고 즉시 함수 종료!
        // (열려있는 도중에 다시 카드를 대면 5초부터 다시 시작됩니다)
        door_open_countdown = 5; 
    }
}

void appMain(void * arg) {
    static std_srvs__srv__SetBool_Request req;
    static std_srvs__srv__SetBool_Response res;
    std_msgs__msg__Bool__init(&status_msg);
    std_msgs__msg__String__init(&rfid_msg);
    std_srvs__srv__SetBool_Request__init(&req);
    std_srvs__srv__SetBool_Response__init(&res);

    gpio_pad_select_gpio(ledPin);
    gpio_set_direction(ledPin, GPIO_MODE_INPUT_OUTPUT);
    
    ledc_timer_config_t lt = {.speed_mode=LEDC_MODE, .timer_num=LEDC_TIMER, .duty_resolution=LEDC_DUTY_RES, .freq_hz=LEDC_FREQUENCY, .clk_cfg=LEDC_AUTO_CLK};
    ledc_timer_config(&lt);
    ledc_channel_config_t lc = {.speed_mode=LEDC_MODE, .channel=LEDC_CHANNEL, .timer_sel=LEDC_TIMER, .gpio_num=servoPin, .duty=servo_degree_to_duty(0)};
    ledc_channel_config(&lc);

    // 2020년 순정 API: 구조체 값 그대로 전달
    rc522_start_args_t start_args = {
        .miso_io = RC522_MISO_PIN,
        .mosi_io = RC522_MOSI_PIN,
        .sck_io  = RC522_SCK_PIN,
        .sda_io  = RC522_SDA_PIN,
        .callback = &rfid_callback_entrance
    };
    rc522_start(start_args);

    // 2020년 순정 API: 구조체 값 그대로 전달
    rc522_start_args_t start_args2 = {
        .miso_io = RC522_MISO_PIN,
        .mosi_io = RC522_MOSI_PIN,
        .sck_io  = RC522_SCK_PIN,
        .sda_io  = RC522_SDA_PIN_2,
        .callback = &rfid_callback_exit
    };
    rc522_start(start_args2);

    rcl_allocator_t allocator = rcl_get_default_allocator();
    rclc_support_t support;
    rcl_init_options_t init_ops = rcl_get_zero_initialized_init_options();
    RCCHECK(rcl_init_options_init(&init_ops, allocator));
    RCCHECK(rcl_init_options_set_domain_id(&init_ops, domain_id));
    RCCHECK(rclc_support_init_with_options(&support, 0, NULL, &init_ops, &allocator));

    rcl_node_t node;
    RCCHECK(rclc_node_init_default(&node, "rfid_iot_node", "esp32", &support));

    RCCHECK(rclc_publisher_init_default(&status_publisher, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Bool), "/led_state"));
    RCCHECK(rclc_publisher_init_default(&rfid_publisher_entrance, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String), "/rfid_entrance_door"));
    RCCHECK(rclc_publisher_init_default(&rfid_publisher_exit, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String), "/rfid_exit_door"));

    rcl_service_t service;
    RCCHECK(rclc_service_init_default(&service, &node, ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool), "/set_state"));

    // 🌟 1000ms(1초) 주기로 작동하는 타이머 설정
    rcl_timer_t timer;
    RCCHECK(rclc_timer_init_default2(&timer, &support, RCL_MS_TO_NS(1000), timer_callback, true));

    rclc_executor_t executor;
    RCCHECK(rclc_executor_init(&executor, &support.context, 5, &allocator));
    RCCHECK(rclc_executor_add_timer(&executor, &timer));
    RCCHECK(rclc_executor_add_service(&executor, &service, &req, &res, service_callback));
    
    // 초기 상태 닫힘으로 설정
    set_servo_angle(0);
    door_open_countdown = 0; 
    printf("RFID IoT System Ready (Non-blocking Timer Mode)!\n");

    while(1){
        rclc_executor_spin_some(&executor, RCL_MS_TO_NS(100));
        usleep(10000);
    }
}