#include <stdio.h>
#include <unistd.h>
#include <math.h>
#include <string.h>

// FreeRTOS 관련 헤더
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

// ROS 2 객체 선언
rcl_publisher_t status_publisher;
rcl_publisher_t rfid_publisher_entrance;
rcl_publisher_t rfid_publisher_exit;
rcl_service_t service_door_control;

std_msgs__msg__Bool status_msg;
std_msgs__msg__String rfid_msg;
std_srvs__srv__SetBool_Request req_door;
std_srvs__srv__SetBool_Response res_door;

size_t domain_id = 25;
int door_open_countdown = 0; 

// 서보모터 및 제어 함수
uint32_t servo_degree_to_duty(int degree) {
    uint32_t cal_pulsewidth = (SERVO_MIN_PULSEWIDTH + (((SERVO_MAX_PULSEWIDTH - SERVO_MIN_PULSEWIDTH) * degree) / SERVO_MAX_DEGREE));
    return (uint32_t)((pow(2, LEDC_TIMER_13_BIT) - 1) * cal_pulsewidth / 20000);
}

void set_servo_angle(int degree) {
    ledc_set_duty(LEDC_MODE, LEDC_CHANNEL, servo_degree_to_duty(degree));
    ledc_update_duty(LEDC_MODE, LEDC_CHANNEL);
}

// 타이머 콜백: 자동 문 닫힘 처리 및 상태 발행
void timer_callback(rcl_timer_t * timer, int64_t last_call_time) {
    RCLC_UNUSED(last_call_time);
    if (timer != NULL) {
        status_msg.data = gpio_get_level(ledPin);
        RCSOFTCHECK(rcl_publish(&status_publisher, &status_msg, NULL));

        if (door_open_countdown > 0) {
            door_open_countdown--;
            if (door_open_countdown == 0) {
                gpio_set_level(ledPin, 0); 
                set_servo_angle(0);        
                printf("🔒 Door Closed Automatically\n");
            }
        }
    }
}

// 🌟 서비스 콜백: Python 노드가 인증 성공 후 이 서비스를 호출하여 문을 엽니다.
void door_service_callback(const void * req, void * res) {
    std_srvs__srv__SetBool_Request * req_in = (std_srvs__srv__SetBool_Request *) req;
    std_srvs__srv__SetBool_Response * res_out = (std_srvs__srv__SetBool_Response *) res;
    
    if (req_in->data) { // true 요청이 오면 문을 엶
        gpio_set_level(ledPin, 1);
        set_servo_angle(90);
        door_open_countdown = 5; // 5초간 유지
        res_out->success = true;
        rosidl_runtime_c__String__assign(&res_out->message, "Door Opened");
        printf("🔓 Service Command: Door Opened\n");
    } else {
        gpio_set_level(ledPin, 0);
        set_servo_angle(0);
        door_open_countdown = 0;
        res_out->success = true;
        rosidl_runtime_c__String__assign(&res_out->message, "Door Closed");
        printf("🔒 Service Command: Door Closed\n");
    }
}

// 입구 RFID 콜백: UID를 토픽으로 발행
void rfid_callback_entrance(uint8_t* sn) {
    char uid_str[20];
    snprintf(uid_str, sizeof(uid_str), "%02X%02X%02X%02X%02X", sn[0], sn[1], sn[2], sn[3], sn[4]);
    
    rosidl_runtime_c__String__assign(&rfid_msg.data, uid_str);
    RCSOFTCHECK(rcl_publish(&rfid_publisher_entrance, &rfid_msg, NULL));
    printf("➡️ [Entrance] Tag Scanned: %s\n", uid_str);
}

// 출구 RFID 콜백: UID를 토픽으로 발행
void rfid_callback_exit(uint8_t* sn) {
    char uid_str[20];
    snprintf(uid_str, sizeof(uid_str), "%02X%02X%02X%02X%02X", sn[0], sn[1], sn[2], sn[3], sn[4]);
    
    rosidl_runtime_c__String__assign(&rfid_msg.data, uid_str);
    RCSOFTCHECK(rcl_publish(&rfid_publisher_exit, &rfid_msg, NULL));
    printf("⬅️ [Exit] Tag Scanned: %s\n", uid_str);
}

void appMain(void * arg) {
    // 메시지 초기화
    std_msgs__msg__Bool__init(&status_msg);
    std_msgs__msg__String__init(&rfid_msg);
    std_srvs__srv__SetBool_Request__init(&req_door);
    std_srvs__srv__SetBool_Response__init(&res_door);

    // 하드웨어 설정 (LED & PWM)
    gpio_pad_select_gpio(ledPin);
    gpio_set_direction(ledPin, GPIO_MODE_INPUT_OUTPUT);
    
    ledc_timer_config_t lt = {.speed_mode=LEDC_MODE, .timer_num=LEDC_TIMER, .duty_resolution=LEDC_DUTY_RES, .freq_hz=LEDC_FREQUENCY, .clk_cfg=LEDC_AUTO_CLK};
    ledc_timer_config(&lt);
    ledc_channel_config_t lc = {.speed_mode=LEDC_MODE, .channel=LEDC_CHANNEL, .timer_sel=LEDC_TIMER, .gpio_num=servoPin, .duty=servo_degree_to_duty(0)};
    ledc_channel_config(&lc);

    // RFID 시작
    rc522_start_args_t start_args = {.miso_io=RC522_MISO_PIN, .mosi_io=RC522_MOSI_PIN, .sck_io=RC522_SCK_PIN, .sda_io=RC522_SDA_PIN, .callback=&rfid_callback_entrance};
    rc522_start(start_args);
    rc522_start_args_t start_args2 = {.miso_io=RC522_MISO_PIN, .mosi_io=RC522_MOSI_PIN, .sck_io=RC522_SCK_PIN, .sda_io=RC522_SDA_PIN_2, .callback=&rfid_callback_exit};
    rc522_start(start_args2);

    // micro-ROS 초기화
    rcl_allocator_t allocator = rcl_get_default_allocator();
    rclc_support_t support;
    rcl_init_options_t init_ops = rcl_get_zero_initialized_init_options();
    RCCHECK(rcl_init_options_init(&init_ops, allocator));
    RCCHECK(rcl_init_options_set_domain_id(&init_ops, domain_id));
    RCCHECK(rclc_support_init_with_options(&support, 0, NULL, &init_ops, &allocator));

    rcl_node_t node;
    RCCHECK(rclc_node_init_default(&node, "rfid_iot_node", "esp32", &support));

    // 퍼블리셔 초기화 (UID 전송용)
    RCCHECK(rclc_publisher_init_default(&status_publisher, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Bool), "/led_state"));
    RCCHECK(rclc_publisher_init_default(&rfid_publisher_entrance, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String), "/rfid_entrance_door"));
    RCCHECK(rclc_publisher_init_default(&rfid_publisher_exit, &node, ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String), "/rfid_exit_door"));

    // 서비스 서버 초기화 (Python에서 문 열림 명령 수신용)
    RCCHECK(rclc_service_init_default(&service_door_control, &node, ROSIDL_GET_SRV_TYPE_SUPPORT(std_srvs, srv, SetBool), "/set_door_state"));

    // 타이머 및 Executor 설정
    rcl_timer_t timer;
    RCCHECK(rclc_timer_init_default2(&timer, &support, RCL_MS_TO_NS(1000), timer_callback, true));

    rclc_executor_t executor;
    RCCHECK(rclc_executor_init(&executor, &support.context, 5, &allocator)); // 핸들 개수 5개로 조정
    RCCHECK(rclc_executor_add_timer(&executor, &timer));
    RCCHECK(rclc_executor_add_service(&executor, &service_door_control, &req_door, &res_door, door_service_callback));
    
    set_servo_angle(0);
    printf("🚀 RFID Factory System Ready (Pub-Sub + Service Mode)!\n");

    while(1){
        rclc_executor_spin_some(&executor, RCL_MS_TO_NS(100));
        usleep(10000);
    }
}