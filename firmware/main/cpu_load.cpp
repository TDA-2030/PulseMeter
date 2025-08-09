#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"

#include "esp_log.h"
#include "cpu_load.h"
#include "meter_dial.h"

static const char *TAG = "CpuLoad";

extern MeterDial meters[];

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

    ESP_LOGI(TAG, "TCP 服务器启动");

    xTaskCreate(
        [](void *param) {
            CpuLoad *server = static_cast<CpuLoad*>(param);
            static int last_time = 0;

            while (true) {
                // 等待客户端连接
                server->waitForClient();

                while (true) {
                    CpuLoad::Data v;
                    bool res = server->readCpuLoad(v);
                    if (!res) {
                        // 客户端断开，重新等待
                        break;
                    }

                    int ct = esp_timer_get_time() / 1000; // 毫秒
                    ESP_LOGI(TAG, "(%dms), data: [%d, %d]", ct - last_time, v.d1, v.d2);
                    last_time = ct;

                    meters[0].set_percent(v.d1);
                    meters[1].set_percent(v.d2);
                }
            }
        },
        "server_task",  // 任务名称
        4096,             // 栈大小
        this,          // 参数
        5,                // 优先级
        nullptr           // 任务句柄
    );
    return true;
}

bool CpuLoad::waitForClient() {
    ESP_LOGI(TAG, "等待客户端连接");
    struct sockaddr_in client_addr;
    socklen_t addr_len = sizeof(client_addr);
    client_fd = accept(listen_fd, (struct sockaddr*)&client_addr, &addr_len);
    if (client_fd < 0) {
        ESP_LOGE(TAG, "接受客户端失败");
        return false;
    }
    // 关闭 Nagle 算法
    int flag = 1;
    setsockopt(client_fd, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(int));
    ESP_LOGI(TAG, "客户端已连接");
    return true;
}

bool CpuLoad::readCpuLoad(Data &_data) {
    uint8_t buffer[8];
    int ret = recv(client_fd, buffer, 5, MSG_WAITALL);
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
    if (buffer[0] != 0x23 || buffer[1] != 0x35) {
        ESP_LOGW(TAG, "包头错误");
        return true;
    }

    if (buffer[2] != 2) {
        ESP_LOGW(TAG, "长度错误");
        return true;
    }

    _data.d1 = buffer[3];
    _data.d2 = buffer[4];
    return true;
}

bool CpuLoad::isClientConnected() {
    return client_fd >= 0;
}
