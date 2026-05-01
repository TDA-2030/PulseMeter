/*
 * SPDX-FileCopyrightText: 2026 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include "led.h"

#include <inttypes.h>
#include <stdbool.h>
#include <stdlib.h>

#include "esp_log.h"
#include "led_strip.h"
#include "led_strip_rmt.h"
#include "led_strip_types.h"

#define LED_RMT_RES_HZ (10 * 1000 * 1000)

static const char *TAG = "led";

struct led {
    int gpio;
    uint32_t max_leds;
    led_strip_handle_t strip;
    uint32_t pixel_index;
};

static void led_hsv_to_rgb(uint32_t hue, uint32_t saturation, uint32_t value, uint32_t *red, uint32_t *green, uint32_t *blue)
{
    uint32_t region = 0;
    uint32_t remainder = 0;
    uint32_t p = 0;
    uint32_t q = 0;
    uint32_t t = 0;

    if (red) {
        *red = 0;
    }
    if (green) {
        *green = 0;
    }
    if (blue) {
        *blue = 0;
    }

    if (!red || !green || !blue) {
        ESP_LOGE(TAG, "HSV conversion output pointer is NULL");
        return;
    }

    if (saturation == 0) {
        *red = value;
        *green = value;
        *blue = value;
        return;
    }

    hue %= 360;
    region = hue / 60;
    remainder = ((hue % 60) * 255) / 60;

    p = (value * (255 - saturation)) / 255;
    q = (value * (255 - ((saturation * remainder) / 255))) / 255;
    t = (value * (255 - ((saturation * (255 - remainder)) / 255))) / 255;

    switch (region) {
    case 0:
        *red = value;
        *green = t;
        *blue = p;
        break;
    case 1:
        *red = q;
        *green = value;
        *blue = p;
        break;
    case 2:
        *red = p;
        *green = value;
        *blue = t;
        break;
    case 3:
        *red = p;
        *green = q;
        *blue = value;
        break;
    case 4:
        *red = t;
        *green = p;
        *blue = value;
        break;
    default:
        *red = value;
        *green = p;
        *blue = q;
        break;
    }
}

esp_err_t led_create(int gpio, uint32_t max_leds, uint32_t pixel_index, led_handle_t *out_led)
{
    if (!out_led || max_leds == 0 || pixel_index >= max_leds) {
        ESP_LOGE(TAG, "LED create failed: invalid arguments");
        return ESP_ERR_INVALID_ARG;
    }
    *out_led = NULL;

    led_handle_t led = calloc(1, sizeof(*led));
    if (!led) {
        ESP_LOGE(TAG, "LED create failed: handle allocation failed");
        return ESP_ERR_NO_MEM;
    }

    led_strip_config_t strip_config = {
        .strip_gpio_num = gpio,
        .max_leds = max_leds,
        .led_model = LED_MODEL_WS2812,
        .color_component_format = LED_STRIP_COLOR_COMPONENT_FMT_GRB,
        .flags = {
            .invert_out = false,
        },
    };
    led_strip_rmt_config_t rmt_config = {
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = LED_RMT_RES_HZ,
        .mem_block_symbols = 0,
        .flags = {
            .with_dma = 0,
        },
    };

    esp_err_t err = led_strip_new_rmt_device(&strip_config, &rmt_config, &led->strip);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LED create failed: %s", esp_err_to_name(err));
        free(led);
        return err;
    }

    led->gpio = gpio;
    led->max_leds = max_leds;
    led->pixel_index = pixel_index;

    err = led_strip_clear(led->strip);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LED clear after create failed: %s", esp_err_to_name(err));
        led_strip_del(led->strip);
        free(led);
        return err;
    }
    *out_led = led;
    return ESP_OK;
}

esp_err_t led_destroy(led_handle_t led)
{
    if (!led) {
        return ESP_OK;
    }

    esp_err_t err = ESP_OK;
    if (led->strip) {
        err = led_strip_clear(led->strip);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "LED strip clear before destroy failed: %s", esp_err_to_name(err));
        }

        err = led_strip_del(led->strip);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "LED strip destroy failed: %s", esp_err_to_name(err));
            free(led);
            return err;
        }
    }

    free(led);
    return ESP_OK;
}

esp_err_t led_set_pixel(led_handle_t led, uint32_t red, uint32_t green, uint32_t blue)
{
    if (!led || !led->strip) {
        ESP_LOGE(TAG, "LED set_pixel failed: invalid led handle");
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t err = led_strip_set_pixel(led->strip, led->pixel_index, red, green, blue);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LED set_pixel failed at index %" PRIu32 ": %s",
                 led->pixel_index, esp_err_to_name(err));
    }
    return err;
}

esp_err_t led_set_pixel_hsv(led_handle_t led, uint32_t hue, uint32_t saturation, uint32_t value)
{
    if (saturation > 255 || value > 255) {
        ESP_LOGE(TAG, "LED set_pixel_hsv failed: saturation and value must be in range 0-255");
        return ESP_ERR_INVALID_ARG;
    }

    uint32_t red = 0;
    uint32_t green = 0;
    uint32_t blue = 0;

    // Convert HSV to RGB because the led_strip driver accepts RGB components.
    led_hsv_to_rgb(hue, saturation, value, &red, &green, &blue);
    return led_set_pixel(led, red, green, blue);
}

esp_err_t led_refresh(led_handle_t led)
{
    if (!led || !led->strip) {
        ESP_LOGE(TAG, "LED refresh failed: invalid led handle");
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t err = led_strip_refresh(led->strip);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LED refresh failed: %s", esp_err_to_name(err));
    }
    return err;
}

esp_err_t led_clear(led_handle_t led)
{
    if (!led || !led->strip) {
        ESP_LOGE(TAG, "LED clear failed: invalid led handle");
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t err = led_strip_set_pixel(led->strip, led->pixel_index, 0, 0, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LED clear failed: %s", esp_err_to_name(err));
        return err;
    }
    return led_refresh(led);
}
