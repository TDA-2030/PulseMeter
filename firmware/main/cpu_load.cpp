#include "cpu_load.h"

static const char *TAG = "CpuLoad";

CpuLoad::CpuLoad()
    : port_(5000), listen_fd(-1), client_fd(-1)
{}

bool CpuLoad::startServer() {
    struct sockaddr_in server_addr;
    listen_fd = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    if (listen_fd < 0) {
        ESP_LOGE(TAG, "创建 socket 失败");
        return false;
    }

    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    server_addr.sin_port = htons(port_);

    if (bind(listen_fd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
        ESP_LOGE(TAG, "绑定端口失败");
        close(listen_fd);
        return false;
    }

    if (listen(listen_fd, 1) < 0) {
        ESP_LOGE(TAG, "监听失败");
        close(listen_fd);
        return false;
    }

    ESP_LOGI(TAG, "TCP 服务器启动，等待客户端连接...");
    return true;
}

bool CpuLoad::waitForClient() {
    struct sockaddr_in client_addr;
    socklen_t addr_len = sizeof(client_addr);
    client_fd = accept(listen_fd, (struct sockaddr*)&client_addr, &addr_len);
    if (client_fd < 0) {
        ESP_LOGE(TAG, "接受客户端失败");
        return false;
    }
    ESP_LOGI(TAG, "客户端已连接");
    return true;
}

bool CpuLoad::readCpuLoad(uint8_t &cpu_load) {
    uint8_t header[3];
    int ret = recv(client_fd, header, 3, MSG_WAITALL);
    if (ret == 0) { // 对方关闭连接
        ESP_LOGW(TAG, "客户端已断开");
        close(client_fd);
        client_fd = -1;
        return false;
    }
    if (ret < 0) {
        if (errno != EAGAIN && errno != EWOULDBLOCK) {
            ESP_LOGE(TAG, "recv 错误: %d", errno);
            close(client_fd);
            client_fd = -1;
        }
        return false;
    }
    if (header[0] != 0x23 || header[1] != 0x35) {
        ESP_LOGW(TAG, "包头错误");
        return false;
    }

    uint8_t len = header[2];
    uint8_t data[256];
    ret = recv(client_fd, data, len, MSG_WAITALL);
    if (ret != len) {
        ESP_LOGW(TAG, "数据长度错误");
        return false;
    }

    cpu_load = data[0];
    return true;
}

bool CpuLoad::isClientConnected() {
    return client_fd >= 0;
}
