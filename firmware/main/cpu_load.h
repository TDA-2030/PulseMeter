#pragma once
#include "esp_event.h"
#include "esp_log.h"
#include <cstdint>
#include <string>
#include <lwip/sockets.h>

class CpuLoad {
public:
    CpuLoad();

    bool startServer();
    bool waitForClient();
    bool readCpuLoad(uint8_t &cpu_load);
    bool isClientConnected();

private:
    uint16_t port_;
    int listen_fd;
    int client_fd;
};
