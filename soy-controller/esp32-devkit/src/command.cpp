#include "command.h"
#include <cstring>

Command Command::parse(const char* msg) {
    Command cmd;

    if (strcmp(msg, "SORT_START") == 0) {
        cmd.type = CommandType::SORT_START;
    } else if (strcmp(msg, "SORT_STOP") == 0) {
        cmd.type = CommandType::SORT_STOP;
    }
    // else: UNKNOWN (기본값)

    return cmd;
}
