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
    bool isClientConnected();

    struct Data
    {
        uint8_t d1;
        uint8_t d2;
    };
    
    bool readCpuLoad(Data &_data);

private:
    uint16_t port_;
    int listen_fd;
    int client_fd;
};
