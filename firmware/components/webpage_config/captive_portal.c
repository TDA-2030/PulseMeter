// Copyright 2015-2016 Espressif Systems (Shanghai) PTE LTD
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "lwip/sockets.h"
#include "lwip/inet.h"
#include "adapt/esp32_wifi.h"
#include "adapt/esp32_httpd.h"
#include "cgi/cgiwifi.h"
#include "captive_portal.h"

static const char *TAG = "captive_portal";
static bool g_configed = 0;
static esp_timer_handle_t prov_stop_timer;
static TaskHandle_t s_dns_task_handle = NULL;
static int s_dns_sock = -1;

esp_err_t config_timer_start(int TIMEOUT_PERIOD);
esp_err_t config_timer_delete(void);
static esp_err_t dns_server_start(void);
static void dns_server_stop(void);

#define DNS_PORT 53

typedef struct {
    uint16_t id;
    uint16_t flags;
    uint16_t qdcount;
    uint16_t ancount;
    uint16_t nscount;
    uint16_t arcount;
} dns_header_t;

static void captive_dns_task(void *arg)
{
    (void)arg;

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) {
        ESP_LOGE(TAG, "DNS socket create failed");
        s_dns_task_handle = NULL;
        vTaskDelete(NULL);
        return;
    }
    s_dns_sock = sock;

    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(DNS_PORT);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);

    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        ESP_LOGE(TAG, "DNS bind failed");
        close(sock);
        s_dns_sock = -1;
        s_dns_task_handle = NULL;
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "Captive DNS started");

    uint8_t rx_buf[256];
    while (1) {
        struct sockaddr_in source_addr = {0};
        socklen_t socklen = sizeof(source_addr);
        int len = recvfrom(sock, rx_buf, sizeof(rx_buf), 0, (struct sockaddr *)&source_addr, &socklen);
        if (len < 0) {
            break;
        }
        if (len < sizeof(dns_header_t)) {
            continue;
        }

        dns_header_t *hdr = (dns_header_t *)rx_buf;
        uint8_t *ptr = rx_buf + len;
        uint8_t *q = rx_buf + sizeof(dns_header_t);

        while (q < rx_buf + len && *q) {
            q += (*q) + 1;
        }
        if (q >= rx_buf + len) {
            continue;
        }

        ptr[0]  = 0xC0;
        ptr[1]  = 0x0C;
        ptr[2]  = 0x00;
        ptr[3]  = 0x01;
        ptr[4]  = 0x00;
        ptr[5]  = 0x01;
        ptr[6]  = 0x00;
        ptr[7]  = 0x00;
        ptr[8]  = 0x00;
        ptr[9]  = 0x1E;
        ptr[10] = 0x00;
        ptr[11] = 0x04;
        ptr[12] = 192;
        ptr[13] = 168;
        ptr[14] = 4;
        ptr[15] = 1;

        hdr->flags = htons(0x8180);
        hdr->ancount = htons(1);

        sendto(sock, rx_buf, len + 16, 0, (struct sockaddr *)&source_addr, sizeof(source_addr));
    }

    close(sock);
    s_dns_sock = -1;
    s_dns_task_handle = NULL;
    ESP_LOGI(TAG, "Captive DNS stopped");
    vTaskDelete(NULL);
}

static esp_err_t dns_server_start(void)
{
    if (s_dns_task_handle != NULL) {
        return ESP_OK;
    }

    BaseType_t ok = xTaskCreate(captive_dns_task, "cp_dns", 4096, NULL, 3, &s_dns_task_handle);
    if (ok != pdPASS) {
        ESP_LOGE(TAG, "Failed to start captive DNS task");
        s_dns_task_handle = NULL;
        return ESP_FAIL;
    }
    return ESP_OK;
}

static void dns_server_stop(void)
{
    if (s_dns_sock >= 0) {
        close(s_dns_sock);
        s_dns_sock = -1;
    }
    /* Task exits on socket close and clears s_dns_task_handle itself. */
}

static void event_handler(void *arg, esp_event_base_t event_base,
                          int32_t event_id, void *event_data)
{
    if (event_base == APP_NETWORK_EVENT) {
        switch (event_id) {
        case APP_NETWORK_EVENT_CONFIG_SUCCESS:
        case APP_NETWORK_EVENT_PROV_TIMEOUT:
            config_timer_delete();
            esp32HttpServerDisable();
            dns_server_stop();
            break;
        case APP_NETWORK_EVENT_PROV_START:
            break;

        default:
            ESP_LOGW(TAG, "Unhandled App Wi-Fi Event: %"PRIi32, event_id);
            break;
        }
    }
}

esp_err_t captive_portal_start(void)
{
    esp_err_t ret;

    /* start http server task */
    ESP_LOGD(TAG, "Free heap size before enable http server: %d", esp_get_free_heap_size());
    ret = esp32HttpServerEnable();
    if (ESP_OK != ret) {
        return ESP_FAIL;
    }
    ret = dns_server_start();
    if (ESP_OK != ret) {
        esp32HttpServerDisable();
        return ESP_FAIL;
    }

    ESP_ERROR_CHECK(esp_event_handler_register(APP_NETWORK_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL));
    config_timer_start(30);
    esp_event_post(APP_NETWORK_EVENT, APP_NETWORK_EVENT_PROV_START, NULL, 0, portMAX_DELAY);
    ESP_LOGI(TAG, "Http server ready ...");

    return ESP_OK;
}


static void wifi_config_stop(void *priv)
{
    ESP_LOGW(TAG, "Provisioning timed out. Please reboot device to restart provisioning.");
    esp_event_post(APP_NETWORK_EVENT, APP_NETWORK_EVENT_PROV_TIMEOUT, NULL, 0, portMAX_DELAY);
}

esp_err_t config_timer_start(int TIMEOUT_PERIOD)
{
    if (TIMEOUT_PERIOD == 0) {
        return ESP_OK;
    }
    uint64_t prov_timeout_period = (TIMEOUT_PERIOD * 60 * 1000000LL);

    esp_timer_create_args_t prov_stop_timer_conf = {
        .callback = wifi_config_stop,
        .arg = NULL,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "app_wifi_config_stop_tm"
    };
    if (esp_timer_create(&prov_stop_timer_conf, &prov_stop_timer) == ESP_OK) {
        esp_timer_start_once(prov_stop_timer, prov_timeout_period);
        ESP_LOGI(TAG, "Provisioning will auto stop after %d minute(s).", TIMEOUT_PERIOD);
        return ESP_OK;
    } else {
        ESP_LOGE(TAG, "Failed to create Provisioning auto stop timer.");
    }
    return ESP_FAIL;
}

esp_err_t config_timer_delete(void)
{
    if (prov_stop_timer) {
        esp_timer_stop(prov_stop_timer);
        esp_timer_delete(prov_stop_timer);
        prov_stop_timer = NULL;
    }
    return ESP_OK;
}
