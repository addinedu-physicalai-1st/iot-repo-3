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
    }
    // else: UNKNOWN (기본값)

    return cmd;
}
