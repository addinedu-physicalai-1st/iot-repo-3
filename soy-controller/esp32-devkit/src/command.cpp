#include "command.h"
#include <cstring>
#include <cstdlib>

Command Command::parse(const char* msg) {
    Command cmd;

    if (strcmp(msg, "DC_STOP") == 0) {
        cmd.type = CommandType::DC_STOP;
    }
    else if (strcmp(msg, "SORT_DIR:1L") == 0) {
        cmd.type = CommandType::SORT_DIR_1L;
    }
    else if (strcmp(msg, "SORT_DIR:2L") == 0) {
        cmd.type = CommandType::SORT_DIR_2L;
    }
    else if (strcmp(msg, "SORT_DIR:WARN") == 0) {
        cmd.type = CommandType::SORT_DIR_WARN;
    }
    else if (strncmp(msg, "DC_START", 8) == 0) {
        cmd.type = CommandType::DC_START;
        // "DC_START" 또는 "DC_START:<speed>"
        if (msg[8] == ':') {
            int parsed = atoi(msg + 9);
            if (parsed < 0) parsed = 0;
            if (parsed > 255) parsed = 255;
            cmd.speed = parsed;
        }
        // speed == -1 이면 기본 속도 사용
    }
    // else: UNKNOWN (기본값)

    return cmd;
}
