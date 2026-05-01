#ifndef __LED_H_
#define __LED_H_

#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct led *led_handle_t;

esp_err_t led_create(int gpio, uint32_t max_leds, uint32_t pixel_index, led_handle_t *out_led);
esp_err_t led_destroy(led_handle_t led);
esp_err_t led_set_pixel(led_handle_t led, uint32_t red, uint32_t green, uint32_t blue);
esp_err_t led_set_pixel_hsv(led_handle_t led, uint32_t hue, uint32_t saturation, uint32_t value);
esp_err_t led_refresh(led_handle_t led);
esp_err_t led_clear(led_handle_t led);

#ifdef __cplusplus
}
#endif

#endif
