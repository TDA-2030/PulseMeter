#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "meter_server.h"
#include "meter_dial.h"
#include "setting.h"

static const char *TAG = "MeterServer";

extern MeterDial meters[];
extern Setting g_settings;

MeterServer::MeterServer()
    : port_(5000), listen_fd(-1), client_fd(-1)
{
    meter_value_[0] = 0;
    meter_value_[1] = 0;
}

bool MeterServer::startServer()
{
    struct sockaddr_in server_addr;
    listen_fd = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    if (listen_fd < 0) {
        ESP_LOGE(TAG, "Failed to create socket");
        return false;
    }

    int opt = 1;
    setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    server_addr.sin_family      = AF_INET;
    server_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    server_addr.sin_port        = htons(port_);

    if (bind(listen_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        ESP_LOGE(TAG, "Failed to bind port %d", port_);
        close(listen_fd);
        return false;
    }

    if (listen(listen_fd, 1) < 0) {
        ESP_LOGE(TAG, "listen() failed");
        close(listen_fd);
        return false;
    }

    ESP_LOGI(TAG, "TCP server listening on port %d", port_);

    xTaskCreate(
        [](void *param) {
            MeterServer *self = static_cast<MeterServer *>(param);
            while (true) {
                self->waitForClient();

                while (true) {
                    uint8_t type = 0, seq = 0;
                    uint8_t payload[PROTO_MAX_PAYLOAD];
                    uint16_t payload_len = 0;

                    if (!self->recvFrame(type, seq, payload, payload_len)) {
                        if (self->client_fd < 0) break;  // disconnected — re-accept
                        continue;                         // bad frame — skip and try again
                    }

                    switch (type) {
                    case MSG_STREAM:
                        self->handleStream(payload, payload_len);
                        break;
                    case MSG_READ_REQ:
                        self->handleReadReq(seq, payload, payload_len);
                        break;
                    case MSG_WRITE_REQ:
                        self->handleWriteReq(seq, payload, payload_len);
                        break;
                    default:
                        ESP_LOGW(TAG, "Unknown message type: 0x%02X", type);
                        break;
                    }
                }
            }
        },
        "server_task",
        4096,
        this,
        5,
        nullptr
    );

    return true;
}

bool MeterServer::waitForClient()
{
    ESP_LOGI(TAG, "Waiting for client...");
    struct sockaddr_in client_addr;
    socklen_t addr_len = sizeof(client_addr);
    client_fd = accept(listen_fd, (struct sockaddr *)&client_addr, &addr_len);
    if (client_fd < 0) {
        ESP_LOGE(TAG, "accept() failed");
        return false;
    }
    // Disable Nagle — we want low-latency streaming
    int flag = 1;
    setsockopt(client_fd, IPPROTO_TCP, TCP_NODELAY, &flag, sizeof(int));
    ESP_LOGI(TAG, "Client connected");
    return true;
}

bool MeterServer::recvFrame(uint8_t &type, uint8_t &seq,
                         uint8_t *payload, uint16_t &payload_len)
{
    uint8_t header[PROTO_HEADER_SIZE];

    int ret = recv(client_fd, header, PROTO_HEADER_SIZE, MSG_WAITALL);
    if (ret == 0) {
        ESP_LOGW(TAG, "Client disconnected");
        close(client_fd);
        client_fd = -1;
        return false;
    }
    if (ret < 0) {
        if (errno != EAGAIN && errno != EWOULDBLOCK) {
            ESP_LOGE(TAG, "recv header error: %d", errno);
            close(client_fd);
            client_fd = -1;
        }
        return false;
    }

    if (header[0] != PROTO_MAGIC0 || header[1] != PROTO_MAGIC1) {
        ESP_LOGW(TAG, "Bad magic: 0x%02X 0x%02X", header[0], header[1]);
        return false;
    }

    type        = header[2];
    seq         = header[3];
    payload_len = ((uint16_t)header[4] << 8) | header[5];

    if (payload_len > PROTO_MAX_PAYLOAD) {
        ESP_LOGW(TAG, "Payload too large: %d", payload_len);
        return false;
    }

    if (payload_len > 0) {
        ret = recv(client_fd, payload, payload_len, MSG_WAITALL);
        if (ret <= 0) {
            ESP_LOGE(TAG, "recv payload error: %d", errno);
            close(client_fd);
            client_fd = -1;
            return false;
        }
    }

    uint8_t crc_rx;
    ret = recv(client_fd, &crc_rx, 1, MSG_WAITALL);
    if (ret <= 0) {
        ESP_LOGE(TAG, "recv CRC error: %d", errno);
        close(client_fd);
        client_fd = -1;
        return false;
    }

    uint8_t crc_calc = proto_crc8(type, seq, payload_len, payload);
    if (crc_rx != crc_calc) {
        ESP_LOGW(TAG, "CRC mismatch: rx=0x%02X calc=0x%02X", crc_rx, crc_calc);
        return false;
    }

    return true;
}

bool MeterServer::sendFrame(uint8_t type, uint8_t seq,
                         const uint8_t *payload, uint16_t len)
{
    // Stack-allocate — max frame is header + payload + crc = 6+32+1 = 39 bytes
    uint8_t buf[PROTO_HEADER_SIZE + PROTO_MAX_PAYLOAD + PROTO_CRC_SIZE];

    buf[0] = PROTO_MAGIC0;
    buf[1] = PROTO_MAGIC1;
    buf[2] = type;
    buf[3] = seq;
    buf[4] = (len >> 8) & 0xFF;
    buf[5] = len & 0xFF;

    if (len > 0 && payload != nullptr) {
        memcpy(buf + PROTO_HEADER_SIZE, payload, len);
    }
    buf[PROTO_HEADER_SIZE + len] = proto_crc8(type, seq, len,
                                               (len > 0 && payload) ? payload
                                                                     : (const uint8_t *)"");

    int total = PROTO_HEADER_SIZE + len + PROTO_CRC_SIZE;
    int ret   = send(client_fd, buf, total, 0);
    if (ret != total) {
        ESP_LOGE(TAG, "send failed: ret=%d expected=%d", ret, total);
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// Message handlers
// ---------------------------------------------------------------------------

void MeterServer::handleStream(const uint8_t *payload, uint16_t len)
{
    if (len < 2) {
        ESP_LOGW(TAG, "STREAM payload too short: %d", len);
        return;
    }

    uint8_t d1 = payload[0];
    uint8_t d2 = payload[1];

    meter_value_[0] = d1;
    meter_value_[1] = d2;

    static int last_time = 0;
    int ct = esp_timer_get_time() / 1000;
    ESP_LOGI(TAG, "stream (+%dms) [%d, %d]", ct - last_time, d1, d2);
    last_time = ct;

    meters[0].set_percent(d1);
    meters[1].set_percent(d2);
}

void MeterServer::handleReadReq(uint8_t seq, const uint8_t *payload, uint16_t len)
{
    if (len < 2) {
        ESP_LOGW(TAG, "READ_REQ payload too short");
        return;
    }

    uint16_t param_id = ((uint16_t)payload[0] << 8) | payload[1];

    // READ_RSP payload: param_id(2) + status(1) + value(4) = 7 bytes
    uint8_t rsp[7];
    rsp[0] = payload[0];  // echo param_id
    rsp[1] = payload[1];

    uint32_t value  = 0;
    uint8_t  status = PROTO_STATUS_OK;

    switch (param_id) {
    case PARAM_METER1_MAX_DUTY:
        value = g_settings.meter1_max_duty;
        break;
    case PARAM_METER2_MAX_DUTY:
        value = g_settings.meter2_max_duty;
        break;
    case PARAM_MODE:
        value = g_settings.mode;
        break;
    case PARAM_METER1_VALUE:
        value = meter_value_[0];
        break;
    case PARAM_METER2_VALUE:
        value = meter_value_[1];
        break;
    default:
        ESP_LOGW(TAG, "READ unknown param 0x%04X", param_id);
        status = PROTO_STATUS_UNKNOWN;
        break;
    }

    rsp[2] = status;
    rsp[3] = (value >> 24) & 0xFF;
    rsp[4] = (value >> 16) & 0xFF;
    rsp[5] = (value >>  8) & 0xFF;
    rsp[6] =  value        & 0xFF;

    sendFrame(MSG_READ_RSP, seq, rsp, sizeof(rsp));
    ESP_LOGI(TAG, "READ param=0x%04X value=%lu status=%d", param_id, value, status);
}

void MeterServer::handleWriteReq(uint8_t seq, const uint8_t *payload, uint16_t len)
{
    if (len < 6) {
        ESP_LOGW(TAG, "WRITE_REQ payload too short");
        return;
    }

    uint16_t param_id = ((uint16_t)payload[0] << 8) | payload[1];
    uint32_t value    = ((uint32_t)payload[2] << 24) | ((uint32_t)payload[3] << 16)
                      | ((uint32_t)payload[4] <<  8) |  payload[5];

    uint8_t status = PROTO_STATUS_OK;

    switch (param_id) {
    case PARAM_METER1_MAX_DUTY:
        meters[0].set_max_duty(value);
        g_settings.meter1_max_duty = value;
        g_settings.save();
        break;
    case PARAM_METER2_MAX_DUTY:
        meters[1].set_max_duty(value);
        g_settings.meter2_max_duty = value;
        g_settings.save();
        break;
    case PARAM_MODE:
        g_settings.mode = (uint8_t)value;
        g_settings.save();
        break;
    case PARAM_METER1_VALUE:
    case PARAM_METER2_VALUE:
        status = PROTO_STATUS_ERR;  // read-only
        break;
    default:
        ESP_LOGW(TAG, "WRITE unknown param 0x%04X", param_id);
        status = PROTO_STATUS_UNKNOWN;
        break;
    }

    // WRITE_RSP payload: param_id(2) + status(1) = 3 bytes
    uint8_t rsp[3] = { payload[0], payload[1], status };
    sendFrame(MSG_WRITE_RSP, seq, rsp, sizeof(rsp));
    ESP_LOGI(TAG, "WRITE param=0x%04X value=%lu status=%d", param_id, value, status);
}
