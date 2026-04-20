#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_log.h"
#include "mdns.h"
#include "lwip/apps/netbiosns.h"
#include "lwip/inet.h"
#include "esp_mac.h"
#include "esp_wifi.h"
#include "captive_portal.h"
#include "adapt/esp32_wifi.h"
#include "meter_dial.h"

#ifndef CONFIG_EXAMPLE_MDNS_HOST_NAME
#define CONFIG_EXAMPLE_MDNS_HOST_NAME "pulsemeter"
#endif

#define MDNS_INSTANCE "esp pulsemeter server"

static const char *TAG = "web";

extern MeterDial meters[];

static TaskHandle_t s_prov_meter_task = nullptr;

static void provisioning_meter_task(void *arg)
{
    static const int pattern[][2] = {
        {18, 82},
        {35, 65},
        {50, 50},
        {65, 35},
        {82, 18},
        {65, 35},
        {50, 50},
        {35, 65},
    };
    const size_t step_count = sizeof(pattern) / sizeof(pattern[0]);
    size_t step = 0;

    while (true) {
        meters[0].set_percent(pattern[step][0]);
        meters[1].set_percent(pattern[step][1]);
        step = (step + 1) % step_count;

        if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(180)) > 0) {
            break;
        }
    }

    s_prov_meter_task = nullptr;
    vTaskDelete(nullptr);
}

static void start_provisioning_meter_animation(void)
{
    if (s_prov_meter_task != nullptr) {
        return;
    }

    BaseType_t ok = xTaskCreate(
        provisioning_meter_task,
        "prov_meter",
        2048,
        nullptr,
        2,
        &s_prov_meter_task);
    if (ok != pdPASS) {
        s_prov_meter_task = nullptr;
        ESP_LOGW(TAG, "Failed to start provisioning meter animation task");
    }
}

static void stop_provisioning_meter_animation(void)
{
    if (s_prov_meter_task == nullptr) {
        return;
    }

    xTaskNotifyGive(s_prov_meter_task);
}

static void initialise_mdns(void)
{
    mdns_init();
    mdns_hostname_set(CONFIG_EXAMPLE_MDNS_HOST_NAME);
    mdns_instance_name_set(MDNS_INSTANCE);

    // Advertise the PulseMeter TCP data service so Python clients can discover
    // the device without manually entering an IP address.
    ESP_ERROR_CHECK(mdns_service_add("PulseMeter", "_pulsemeter", "_tcp", 5000, NULL, 0));
}

static void event_handler(void *arg, esp_event_base_t event_base,
                          int32_t event_id, void *event_data)
{
    if (event_base == APP_NETWORK_EVENT) {
        switch (event_id) {
        case APP_NETWORK_EVENT_PROV_START:
            ESP_LOGI(TAG, "APP_NETWORK_EVENT_PROV_START");
            ESP_LOGI(TAG, "Provisioning mode active, open 192.168.4.1 to configure Wi-Fi");
            start_provisioning_meter_animation();
            break;
        case APP_NETWORK_EVENT_CONFIG_SUCCESS:
        case APP_NETWORK_EVENT_PROV_TIMEOUT:
            ESP_LOGI(TAG, "APP_NETWORK_EVENT_PROV_END");
            stop_provisioning_meter_animation();
            break;
        default:
            break;
        }
    } else if (event_base == IP_EVENT) {
        switch (event_id) {
        case IP_EVENT_STA_GOT_IP:
            ESP_LOGI(TAG, "IP_EVENT_STA_GOT_IP");
            stop_provisioning_meter_animation();
            // Disable modem sleep so the WiFi radio stays active continuously.
            // Default WIFI_PS_MIN_MODEM causes the AP to buffer packets between
            // beacons (~100ms), delivering them in bursts that creates the
            // alternating long/short interval pattern seen in meter streaming.
            esp_wifi_set_ps(WIFI_PS_NONE);
            break;
        case IP_EVENT_STA_LOST_IP:
            break;
        default:
            break;
        }
    }
}

void start_wifi(void)
{
    meters[0].set_percent(50);
    meters[1].set_percent(50);
    bool is_configured;
    ESP_LOGI(TAG, "Setup Wifi ...");
    wifiIinitialize(CONFIG_PULSEMETER_WIFI_AP_SSID, "", &is_configured);
    ESP_ERROR_CHECK(esp_event_handler_register(APP_NETWORK_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL));
    if (is_configured) {
        wifi_config_t wifi_config;
        esp_wifi_get_config(WIFI_IF_STA, &wifi_config);
        ESP_LOGI(TAG, "SSID:%s, PASSWORD:%s", wifi_config.sta.ssid, wifi_config.sta.password);
    } else {
        start_provisioning_meter_animation();
        captive_portal_start();
    }
    xEventGroupWaitBits(g_wifi_event_group, WIFI_STA_GOT_IP, 0, 0, portMAX_DELAY);
    initialise_mdns();

    stop_provisioning_meter_animation();
    meters[0].set_percent(0);
    meters[1].set_percent(0);
}
