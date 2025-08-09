
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "helper.h"
#include "setting.h"
#include "adc.h"
#include "web.h"
#include "board.h"
#include "led.h"
#include "meter_dial.h"
#include "cpu_load.h"

static const char *TAG = "app_main";

MeterDial meters[] = {
    MeterDial("Meter1"),
    MeterDial("Meter2"),
};

CpuLoad server;

extern "C" void app_main()
{
    /* Initialize NVS. */
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK( err );

    led_init();
    g_settings.load();
    adc_init();
    vTaskDelay(pdMS_TO_TICKS(100));
    bsp_i2c_init();

    /** Determine whether to restore the settings by reading the restart count */
    int restart_cnt = restart_count_get();
    ESP_LOGI(TAG, "Restart count=[%d]", restart_cnt);
    if (restart_cnt >= RESTART_COUNT_RESET) {
        ESP_LOGW(TAG, "Erase information saved in flash and restart");
    }
    meters[0].init(BOARD_IO_METER1);
    meters[1].init(BOARD_IO_METER2);

    meters[0].set_max_duty(448);
    meters[1].set_max_duty(236);

    meters[0].waitSelfTestDone();
    meters[1].waitSelfTestDone();

    start_web();
    server.startServer();
}
