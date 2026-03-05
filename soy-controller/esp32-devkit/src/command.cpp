#include "command.h"
#include <cstring>

Command Command::parse(const char* msg) {
    Command cmd;

    if (strcmp(msg, "SORT_START") == 0) {
        cmd.type = CommandType::SORT_START;
    } else if (strcmp(msg, "SORT_STOP") == 0) {
        cmd.type = CommandType::SORT_STOP;
    } else if (strcmp(msg, "SORT_PAUSE") == 0) {
        cmd.type = CommandType::SORT_PAUSE;
    } else if (strcmp(msg, "SORT_RESUME") == 0) {
        cmd.type = CommandType::SORT_RESUME;
    } else if (strcmp(msg, "SORT_DIR:1L") == 0) {
        cmd.type = CommandType::SORT_DIR_1L;
    } else if (strcmp(msg, "SORT_DIR:2L") == 0) {
        cmd.type = CommandType::SORT_DIR_2L;
    } else if (strncmp(msg, "DC_SPEED:", 9) == 0) {
        cmd.type = CommandType::DC_SPEED;
        cmd.value = atoi(msg + 9);
    } else if (strncmp(msg, "SERVO_A:", 8) == 0) {
        cmd.type = CommandType::SERVO_DEG_A;
        cmd.value = atoi(msg + 8);
    } else if (strncmp(msg, "SERVO_B:", 8) == 0) {
        cmd.type = CommandType::SERVO_DEG_B;
        cmd.value = atoi(msg + 8);
    }
    // else: UNKNOWN (기본값)

    return cmd;
}
